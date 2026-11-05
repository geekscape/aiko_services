#!/usr/bin/env python3
#
# Aiko Services: the PowerManager Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Host power as a Service: what the supply and the battery are doing, and
# what to do about it (ADR-028).
#
# One Interface with one Implementation for each platform, in the way that
# DaemonSupervisor has one for each operating system (ADR-026).  The
# Implementations are the power management module on a single-board
# computer, a Linux laptop, a MacBook, and a mock.  The mock is the
# registered default, so a platform with no Implementation reports itself
# rather than doing something that cannot work.
#
# Properties, not capabilities of the Actor: properties() says which parts
# of the Interface are real here.  A property that a platform lacks is a
# no-op and never an error (ADR-022 decision 1, as NullOutputImpl is).  A
# laptop cannot hold its own power, so hold() does nothing there, and the
# Service tag "hold=false" says so before a client tries.
#
# Phase 1 is read-only.  It reads, publishes and logs, and it acts on
# nothing: "policy" is "advisory", the thresholds are published but not
# enforced, and no Implementation claims an output.  The hold, the signals,
# the button and the policy arrive in the phases after it.
#
# The wire surface is narrower than the Interface.  open(), close(),
# add_handler(), properties() and read() are the device seam, which the CLI
# and this Actor call directly and which nothing on the bus may reach.
# DEVICE_FUNCTIONS names them and FUNCTIONS subtracts them, so the allow
# list still comes from the contract (P12, ADR-023).
#
# Safe by default, as the ProcessManager is: safe mode accepts (sample) and
# the log level, and nothing else.  "safe" is published as a report, and a
# request to change it from the bus is denied.
#
# Threads (P11): the sample timer runs on the event-loop thread, because one
# I2C read is about one millisecond.  A device callback never touches shared
# state, and posts to the mailbox instead.
#
# To Do
# ~~~~~
# * hold(), signal() and the button: the plan's phases 2 and 3
# * decide(), the pure policy, and the quiesce mode: phase 3
# * percent, minutes_left and watt_hours, after measurement: phase 6
# * The Linux and macOS Implementations: phase 7

from abc import abstractmethod
import time

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname

from aiko_services.actors.power_manager.log import PowerLog
from aiko_services.actors.power_manager.policy import (
    Dwell, EXACT_REASONS, HOLD, MODE_NORMAL, MODE_QUIESCE, SHUTDOWN, decide,
    decide_mode, writing_ok as policy_writing_ok
)
from aiko_services.actors.power_manager.quiesce import (
    HOOK_QUIESCE, Quiesce
)
from aiko_services.actors.power_manager.reading import (
    PowerReading, boot_id, utc_now
)
from aiko_services.actors.power_manager.shutdown import power_off
from aiko_services.actors.power_manager.powered_up import (
    BRIDGE_TOPIC, LeaseConstraint, POWERED_UP_MAXIMUM_S,
    POWERED_UP_REQUESTS_MAXIMUM, PoweredUpRegister, REFUSED_PARAMETERS
)

try:
    import psutil
except ImportError:                                      # pragma: no cover
    psutil = None

__all__ = [
    "BUTTON_SHUTDOWN", "DEVICE_FUNCTIONS", "DOCK_DWELL_S", "ENFORCE",
    "FUNCTIONS",
    "LOG_DIRECTORY", "PERIOD_DEVELOPMENT", "PERIOD_PRODUCTION",
    "POLICY_ADVISORY", "POLICY_SHUTTING_DOWN", "PROPERTIES", "PROTOCOL",
    "POWERED_DOWN_GRACE_S", "SAFE", "SAFE_FUNCTIONS", "THRESHOLDS",
    "UNDOCKED_MAXIMUM_S", "WORKING_DWELL_S",
    "WORKING_PATTERN", "WORKING_REPORTERS_MAXIMUM", "PowerManager",
    "PowerManagerCommon", "choose_power_manager", "power_manager_args",
    "service_filter", "service_tags",
]

PROTOCOL = f"{aiko.SERVICE_PROTOCOL_AIKO}/power_manager:0"

# The two deadlines on an undocked hold, in the order they fire.
#
# Both are deliberately short, because of what the postures mean.  The
# voltage rules are the natural protection for a battery pack, and they are
# the ones that an advisory posture holds back, since their thresholds come
# from a data sheet rather than from the pack that is fitted.  So on a host
# that has not been measured, these two deadlines are the only thing
# between an undocked host and a flat pack.  They are therefore set from
# what the pack can be relied on to do, which on this hardware is not yet
# known.
#
# A measured discharge curve is what raises them, and the characterization
# of the plan's phase 6 is where it comes from.
#
# 600 s at the 10.7 W that was measured is about 1.8 Wh, and 900 s is about
# 2.7 Wh.  A pack at 10.05 V holds little, so both are inside what even a
# tired pack should carry.
POWERED_DOWN_GRACE_S = 600.0       # The deployment's deadline: ten minutes
UNDOCKED_MAXIMUM_S = 900.0         # The backstop: fifteen minutes

# What a report of work sounds like, and the two limits that bound it.  A
# report makes a noise that reaches a person, so one reporter cannot sound
# it again until the dwell has passed, and the number of reporters is
# capped.  Without those two a Service in a loop would be a siren
WORKING_PATTERN = "pipeline"
WORKING_DWELL_S = 300.0
WORKING_REPORTERS_MAXIMUM = 32

# Which parts of the Interface a platform may have.  The Actor registers one
# tag for each, such as "hold=true".  One tag for each property, rather than
# one tag with a list, because ServiceFilter splits a value that holds a
# space into two tags (ADR-028 decision 2)
PROPERTIES = ("readings", "hold", "signal", "button", "dock")

PERIOD_DEVELOPMENT = 5.0           # Seconds between samples, while watching
PERIOD_PRODUCTION = 60.0           # Seconds between samples, in the field
PERIOD_LOW, PERIOD_HIGH = 0.5, 3600.0

LOG_DIRECTORY = "~/power_log"

# The policy decides on every sample, and acts only when it is allowed to.
# "advisory" is the default, and it is not timidity: the thresholds of
# THRESHOLDS are from a data sheet, and the lead's direction is to measure
# the battery pack before anything acts on them.  An operator reads "policy_would"
# and "policy_reason" for as long as that takes, and then turns it on
ENFORCE = False
POLICY_ADVISORY = "advisory"       # It decides, publishes, and acts on nothing
POLICY_SHUTTING_DOWN = "shutting_down"

# The button acts even while the posture is advisory, and this is why.
# Advisory exists because the voltage and temperature thresholds come from a
# data sheet and not from the battery pack that is fitted.  A person who
# holds the button for three seconds is not a measurement, and no
# calibration makes their request more or less true.  A power button that
# does nothing is a fault to the operator who pressed it: seen on
# 2026-11-05, where the Actor accepted a press, sounded it, decided to stop
# and then did nothing, because every reason shared one posture.
#
# So the two are separate.  "advisory" still means that no measured reason
# acts.  "--no_button_shutdown" turns off even this, for a host where
# nothing may stop the operating system
BUTTON_SHUTDOWN = True

# A supply glitches, and a dock that flickers must not start a shutdown.
# So the host counts as docked until it has been undocked this long
DOCK_DWELL_S = 10.0

# The first values of the plan's threshold table.  Phase 1 publishes them
# and enforces none of them: the battery pack measured 10.047 V, which is under
# battery_volts_low, so enforcement before measurement would stop the host
# on its first sample
THRESHOLDS = {
    "battery_volts_floor": 9.9,    # The battery pack must not go below this
    "battery_volts_low": 10.5,     # Start the orderly shutdown
    "quiesce_volts": 10.2,         # Stop writing, and flush
    "battery_pack_celsius_maximum": 45.0,     # The battery pack, never the processor
    "battery_dwell_s": 30.0,       # The voltage must stay low this long
    # The backstop on an undocked hold.  It is the longer of the two, so it
    # fires only where a deployment turned the deadline below off or set it
    # longer than this
    "undocked_maximum_s": UNDOCKED_MAXIMUM_S,
    # The deadline: when the supply goes and does not come back, stop after
    # this long whatever work is claimed.  Twenty minutes while the battery
    # pack is unmeasured and it is not certain that the pack charges, which
    # the lead set on 2026-11-05.  A deployment sets it shorter until both
    # are known, and None turns it off, which leaves the backstop above as
    # the only deadline.
    #
    # It is shorter than the backstop, so it is the deadline that fires.
    # The backstop still applies to a deployment that sets this longer, or
    # turns it off
    "powered_down_grace_s": POWERED_DOWN_GRACE_S,
    # How long the host stays undocked before an application is told to
    # stop writing.  It must be shorter than the deadline above, so that
    # the writers stop before the host does.  None is off, and then an
    # undocked host conserves at once
    "powered_down_application_grace_s": None,
    "powered_up_grace_s": 60.0,      # After the last Lease is released
    "dock_dwell_s": DOCK_DWELL_S,  # Before an undock is believed
    # The limits on the request surface, which ADR-028 decision 13 makes
    # part of the design: a client can only ask a host to stay up, and
    # these bound what a client in a loop can ask for
    "powered_up_maximum_s": POWERED_UP_MAXIMUM_S,
    "powered_up_requests_maximum": POWERED_UP_REQUESTS_MAXIMUM,
    # The same reasoning for the report of work, which also reaches a person
    "working_dwell_s": WORKING_DWELL_S,
    "working_reporters_maximum": WORKING_REPORTERS_MAXIMUM,
}

def _grace_order(thresholds):
    """The one rule that relates two thresholds, checked where they meet.

    The writers must stop before the host does, so the deadline that will
    fire must be longer than the application grace.  Two thresholds can
    fire, and the shorter one does, so this reads both: checking only the
    deployment's deadline let an application grace past the backstop
    through, and the host then stopped before the writers were told.  An inconsistent pair is reported
    and the application grace is turned off, which is the behavior from
    before that threshold existed.  A mistyped setting must not stop a host,
    and it must not be silent either: the reason is published in
    "last_error", and the command line refuses the pair outright, where a
    person is there to read it.

    Returns the diagnostic, or None.  It changes the thresholds in place"""

    application = thresholds.get("powered_down_application_grace_s")
    if application is None:
        return None
    try:
        application = float(application)
    except (TypeError, ValueError):
        return None                # _number() already ignores what it
                                   #   cannot read
    if application <= 0:
        return None
    # The deadline that will fire, and not one of the two.  Checking only
    # "powered_down_grace_s" let an application grace past the backstop
    # through, and then the host stopped before the writers were ever told
    deadlines = []
    for name in ("powered_down_grace_s", "undocked_maximum_s"):
        try:
            value = float(thresholds.get(name))
        except (TypeError, ValueError):
            continue
        if value > 0:
            deadlines.append((value, name))
    if not deadlines:
        return None                # No deadline at all: nothing to be
                                   #   shorter than
    deadline, name = min(deadlines)
    if deadline > application:
        return None
    thresholds["powered_down_application_grace_s"] = None
    return (f"powered_down_application_grace_s {application:g} is not less "
        f"than {name} {deadline:g}: turned off")

class PowerManager(aiko.Actor):
    """What the supply and the battery are doing, and what to do about it.

    The wire functions are (sample) and (set_period SECONDS), with (hold
    on|off) and (signal NAME) behind an unsafe posture.  Every outcome is
    observed in the shared state, never returned across the wire.  The rest
    of the Interface is the device seam: the CLI and the Actor call it, and
    DEVICE_FUNCTIONS keeps it off the bus"""

    PROTOCOL = PROTOCOL

    aiko.Interface.default("PowerManager",
        "aiko_services.actors.power_manager.mock.MockPowerManagerImpl")

    @abstractmethod
    def properties(self):
        """Which parts of this Interface are real on this platform: a tuple
        of PROPERTIES tokens.

        Local only, and never on the bus: the Actor publishes the answer as
        Service tags and as shared variables, so a client reads it from
        discovery rather than by asking"""

    @abstractmethod
    def open(self):
        """Acquire what this platform offers, and raise nothing when a part
        is absent: an absent part is a property that properties() leaves
        out.  Local only (DEVICE_FUNCTIONS)"""

    @abstractmethod
    def read(self):
        """One PowerReading from the devices, with no publishing and no
        logging.  Never blocks for longer than a register read.

        Local only (DEVICE_FUNCTIONS).  Use sample() to read and publish"""

    @abstractmethod
    def sample(self):
        """Read the devices, publish the reading and append it to the log.

        No arguments.  Wire form: "(sample)".  The reading is observed in
        the shared state ("battery.volts", "supply.watts", "sampled_utc" and
        the rest), and the local return value is the PowerReading"""

    @abstractmethod
    def set_period(self, seconds):
        """Change the seconds between samples.

        "seconds" is 0.5 to 3600.  Wire form: "(set_period 5.0)".  The
        accepted value is observed in the shared state as
        "sample_period_s", and a refused one in "last_error" """

    @abstractmethod
    def request_powered_up(self, response_topic, seconds, reason,
        constraint_name=None, constraint_value=None):
        """Ask this host to stay powered for "seconds", and say why.

        "response_topic" is the client's own topic, which identifies the
        request and receives the answers.  "seconds" greater than zero
        takes or extends the request, and zero releases it.  "reason" is
        one token, for the operator.

        A Lease has two conditions, and both must hold.  "seconds" is the
        period for which it is valid, and a client extends it.  A
        constraint is a quantity of a finite resource, in the unit that
        measures it, and the host must still be able to meet it:
        "watt_hours" is the one unit declared so far.  A constraint in a
        unit this host cannot measure is refused, and never granted.

        Wire form:
        "(request_powered_up NAMESPACE/HOST/PID/SID/in 300 upload)", or
        with a constraint,
        "(request_powered_up NAMESPACE/HOST/PID/SID/in 300 upload
        watt_hours 12.5)".  The
        answer is published to that topic as "(powered_up_granted SECONDS)"
        or "(powered_up_refused WHY)", and a change of mode as
        "(power_mode MODE REASON)".  The totals are observed in the shared
        state as "powered_up.held" and "powered_up.reasons".

        A request asks, and never commands: it cannot outlive the bound on
        undocked time, the voltage floor or the battery pack temperature
        gate (ADR-028 decision 13)"""

    @abstractmethod
    def report_working(self, response_topic, detail="-"):
        """Report that the Service at "response_topic" is doing its work.

        The reporter decides what working means, because only it knows:
        a Pipeline that captures frames knows that the frames arrive, and
        this Actor cannot know it without naming the application.  This
        Actor decides what the report sounds like, because the buzzer is
        its property and one sound must mean one thing.

        Wire form: "(report_working NAMESPACE/HOST/PID/SID/in frames)".
        "detail" is one token, for the operator and the log.

        The sound plays once for each reporter, and again only after
        "working_dwell_s".  No more than "working_reporters_maximum"
        reporters are kept.  Nothing is published in answer: the outcome is
        observed in the shared state as "working.reporters" and
        "metrics.working_reports".

        This is in the safe posture, and "signal" is not.  A reporter can
        ask for one pattern that this Actor chose, at a rate this Actor
        bounds, and that is a different surface from a buzzer any client
        can play what it likes on (ADR-028 decision 7)"""

    @abstractmethod
    def hold(self, on):
        """Keep this host powered, or stop keeping it powered.

        "on" is a boolean or one of "on", "off", "true", "false".  Wire
        form: "(hold off)", which is denied in the safe posture, because it
        stops a host.  The outcome is observed in "hold_state".  A no-op
        where the "hold" property is absent"""

    @abstractmethod
    def signal(self, name):
        """Make one sound or show one light.

        "name" is a pattern name.  Wire form: "(signal booted)", which is
        denied in the safe posture, because a signal reaches a person.  The
        outcome is observed in "metrics.signals".  A no-op where the
        "signal" property is absent"""

    @abstractmethod
    def add_handler(self, handler):
        """Ask for handler(event, value) on a button, dock or supply change.

        The handler runs on the device's own thread, never on the
        event-loop thread (P11).  Local only (DEVICE_FUNCTIONS)"""

    @abstractmethod
    def close(self):
        """Release what open() acquired.  Never releases a power hold:
        only the shutdown hook does that (ADR-028 decision 6)"""

# The device seam, which the allow list subtracts.  A name here is called by
# the CLI and by this Actor, and never from the message bus
DEVICE_FUNCTIONS = frozenset(
    {"open", "close", "read", "add_handler", "properties"})

# P12, ADR-023: derived from the contract, less the device seam
FUNCTIONS = aiko.interface_functions(PowerManager) - DEVICE_FUNCTIONS

SAFE = True                        # The default posture of "run"

# A power manager can stop its host, so what it accepts from the bus is not
# a small matter.  Safe mode allows the one function that changes nothing:
# a sample, and the log level the Dashboard sets.
#
# "signal" and "set_period" stay out, even though neither stops anything.
# A buzzer that any client can sound is a nuisance that reaches a person,
# and a sample period is the resolution of the evidence.  The
# ProcessManager's rule applies: only a design and a test campaign make a
# function safe, not the observation that it looks harmless
# "request_powered_up" is here because it can only ask a host to stay up, a
# refusal is always available, and two limits in THRESHOLDS bound what a
# client in a loop can ask for.  The ProcessManager's rule is satisfied by
# those limits being part of the design, and not found later.  Without it
# the whole request surface would be unusable in the default posture
# "report_working" is here for the same reason, and behind the same kind of
# limits: a dwell for each reporter and a cap on the reporters.  It names
# one pattern that this Actor chose, so it is not control of the buzzer
SAFE_FUNCTIONS = frozenset(
    {"report_working", "request_powered_up", "sample", "set_log_level"})

class PowerManagerCommon:
    """What every Implementation does the same way: the shared state, the
    sample timer, the log and the metrics.

    A plain mixin, and not a second Interface: the four Implementations hold
    it in common, as the display outputs hold _Emulated (ADR-028 decision 4)
    """

    def _init_power(self, context, period=PERIOD_DEVELOPMENT,
        log_directory=LOG_DIRECTORY, keep_days=None, safe=SAFE,
        thresholds=None, telemetry=True, timer=True, enforce=ENFORCE,
        button_shutdown=BUTTON_SHUTDOWN, quiesce=None,
        power_off_runner=None, worker=True):

        """Compose the Actor part.  An Implementation calls this from its
        own __init__, after it has recorded its devices"""

        context.call_init(self, "FunctionGate", context,
            functions=FUNCTIONS & SAFE_FUNCTIONS if safe else FUNCTIONS)
        context.call_init(self, "Actor", context)

        self._safe = bool(safe)
        self._telemetry = bool(telemetry)
        self._thresholds = dict(THRESHOLDS)
        self._thresholds.update(thresholds or {})
        self._threshold_error = _grace_order(self._thresholds)
        self._period = self._valid_period(period)
        self._log = PowerLog(log_directory, keep_days) if log_directory  \
            else None
        self._boot_id = boot_id()

        # The policy's memory.  decide() is pure, so everything it needs to
        # know about time lives here and is handed to it as numbers
        self._enforce = bool(enforce)
        self._button_shutdown = bool(button_shutdown)
        self._quiesce = quiesce or Quiesce()
        # worker=False runs the power-off where it is decided, which is how
        # the tests exercise the acting path.  Nothing else sets it
        self._power_off_runner = power_off_runner
        self._worker = bool(worker)
        self._mode = MODE_NORMAL
        self._button_held = False
        self._undocked = Dwell()       # How long the dock line has said no
        self._battery_low = Dwell()    # How long the battery pack has been
                                       #   under its low voltage
        self._powered_up_idle = Dwell()  # How long nothing has claimed it
        self._unmet_told = set()       # Holders already told, told once
        # The expiry handler runs on the event-loop thread at the agreed
        # time, which is most of what a Lease is for: the last one to
        # expire is the event that lets a host stop
        self._powered_up = PoweredUpRegister(
            maximum_seconds=self._thresholds.get(
                "powered_up_maximum_s", POWERED_UP_MAXIMUM_S),
            maximum_requests=self._thresholds.get(
                "powered_up_requests_maximum", POWERED_UP_REQUESTS_MAXIMUM),
            expired_handler=self._powered_up_expired)
        self._stopping = False
        # Who has reported that they are working, and when each last made a
        # sound.  A dwell for each one, so a Service in a loop is quiet
        self._working = {}
        # The clock, so that a test walks the dwell rather than waiting it
        # out.  It is an attribute and not a parameter of report_working,
        # because a parameter would let a client on the bus pass its own
        # time and defeat the dwell
        self._clock = time.monotonic
        self.add_hook(HOOK_QUIESCE)

        properties = tuple(self.properties())
        declared = tuple(getattr(self, "DECLARED_PROPERTIES", properties))
        self.share.update({
            "source_file": f"v{aiko.__version__}⇒ {__file__}",
            "device": getattr(self, "device", "mock"),
            "safe": self._safe,       # ADR-023 decision 3: observable policy
            **{name: name in (properties or declared)
                for name in PROPERTIES},
            "policy": POLICY_ADVISORY,
            "policy_reason": "-",
            "policy_would": "-",       # What it would do, while advisory
            "enforce": self._enforce,
            "button_shutdown": self._button_shutdown,
            "mode": self._mode,
            "mode_reason": "-",
            # The one thing an application asks of this Actor.  It is
            # published rather than answered, so a writer subscribes and
            # needs no function of its own (P3)
            "writing_ok": policy_writing_ok(self._mode),
            "undocked_since_utc": "-",
            "hold_state": "unknown",
            "hook": "unknown",
            "sample_period_s": f"{self._period:.1f}",
            "log": str(self._log.directory) if self._log else "-",
            "last_error": self._threshold_error or "-",
            # A threshold that is None is off, and it publishes as "-"
            # rather than as the word "None": the shared state is read by
            # an operator, and "None" reads like a fault
            "thresholds": {name: ("-" if value is None else f"{value}")
                for name, value in self._thresholds.items()},
            "metrics": {"samples": 0, "sensor_errors": 0, "signals": 0,
                "hold_changes": 0, "denied": 0, "shutdowns": 0,
                "quiesces": 0, "button_presses": 0,
                "powered_up_granted": 0, "powered_up_refused": 0,
                "powered_up_expired": 0, "working_reports": 0},
            "working": {"reporters": 0, "last": "-"},
            # The share is a nested dictionary of at most two levels, and a
            # dotted name is a path into it, not a key (share.py).  So the
            # snapshot nests what _publish() later updates by path
            **_nest({**PowerReading().as_share(),
                "battery.margin_volts": "-",
                **self._powered_up.as_share(),
                **self._quiesce.done()}),
        })
        self.ec_producer.add_handler(self._power_change_handler)

        self._timer = bool(timer)
        if self._timer:
            aiko.event.add_timer_handler(self._sample_timer, self._period)

# The wire surface ---------------------------------------------------------- #

    def reading(self):
        """One reading with both clocks and the processor load filled in,
        and nothing published and nothing logged.

        What "sample" prints on the command line, so that one reading has
        the same shape there as it has in the log and in the shared state.
        A device failure is recorded rather than raised, as in sample()"""

        return self._read_guarded()

    def sample(self):
        """Read the devices, publish the reading, decide, append to the log.

        The decision is taken on every sample, and acted on only when this
        Actor is enforcing.  So a host runs for as long as an operator wants
        with the decision visible and nothing happening"""

        reading = self.reading()
        self._publish(reading)
        now = self._now()
        decision, reason, mode, mode_reason = self._evaluate(reading, now)
        if self._log:
            self._log.write(reading, extra={
                "policy": self.share["policy"],
                "policy_would": decision,
                "policy_reason": reason,
                "mode": mode,
                "mode_reason": mode_reason,
                "enforce": self._enforce,
                "powered_up_held": self._powered_up.held(),
                "power_up_reasons": "+".join(
                    self._powered_up.reasons()) or "-",
                "period_s": self._period,
                # How long this host has been undocked, so that a reading
                # of the log can say how long real undocked periods last
                # and what the battery pack did through them.  That is
                # what the deadlines are tuned from
                "undocked_s": round(self._undocked.seconds(now), 1),
            })
            if self._log.last_error:
                self.ec_producer.update(
                    "last_error", self._log.last_error[:120])
                self._log.last_error = None
        return reading

    def publish_properties(self):
        """Publish properties() again, after open() has found what is there.

        The Service tags carry what an Implementation declares, which is
        known before a bus is opened.  The shared state carries what this
        host actually has, which is known only after.  A client filters on
        the tag, then reads the share.

        The hold and the artifacts of the operating system are published
        here too, because open() is where both become knowable"""

        properties = tuple(self.properties())
        for name in PROPERTIES:
            self.ec_producer.update(name, name in properties)
        self.ec_producer.update("hold_state", self.hold_state())
        self.ec_producer.update("hook", self.hook_state())
        return properties

    def hold_state(self):
        """"on", "off" or "unknown".  An Implementation with no hold
        property reports "unknown", which is what it is"""

        return "unknown"

    def hook_state(self):
        """"installed", "missing" or "unknown" for the shutdown hook.

        A host whose hook is missing fails safe and costs a charge: the pin
        stays asserted and the halted host stays on the battery pack.  So this is
        published rather than assumed"""

        return "unknown"

    def request_powered_up(self, response_topic, seconds, reason="-",
        constraint_name=None, constraint_value=None):
        """Take, extend or release one claim on this host.

        The client names its own topic, and that topic is checked before
        anything is published to it: without the check an unknown client
        makes this Actor publish where it likes"""

        from aiko_services.main.process_manager import coerce_response_topic

        topic = coerce_response_topic(response_topic, str(self.topic_path))
        if topic is None or topic == BRIDGE_TOPIC:
            self.logger.warning(
                f"request_powered_up refused: {str(response_topic)[:60]} is not "
                "a topic this Service may publish to")
            self._count("denied")
            return
        # Coerced and checked at the boundary, never assumed away (P12)
        try:
            constraint = LeaseConstraint.of(constraint_name, constraint_value)
        except ValueError as error:
            self.logger.warning(f"request_powered_up refused: {error}")
            self._answer(topic, "refused", REFUSED_PARAMETERS)
            self._powered_up.refused += 1
            self._publish_powered_up()
            return
        outcome, detail = self._powered_up.request(
            topic, seconds, reason, constraint, self.available())
        self._answer(topic, outcome, detail)
        self._publish_powered_up()
        self.logger.info(f"Powered up {outcome} {detail}: {reason}"
            f"{f' [{constraint}]' if constraint else ''} ({topic})")

    def report_working(self, response_topic, detail="-"):
        """Note that one Service is doing its work, and sound it.

        The sound is the point, so everything here exists to keep it
        meaningful: one reporter cannot sound it twice inside the dwell,
        and the reporters are capped"""

        from aiko_services.main.process_manager import coerce_response_topic

        topic = coerce_response_topic(response_topic, str(self.topic_path))
        if topic is None or topic == BRIDGE_TOPIC:
            self.logger.warning(
                f"report_working refused: {str(response_topic)[:60]} is not a "
                "topic this Service may publish to")
            self._count("denied")
            return False
        now = self._clock()
        maximum = int(self._thresholds.get(
            "working_reporters_maximum", WORKING_REPORTERS_MAXIMUM))
        if topic not in self._working and len(self._working) >= maximum:
            self.logger.warning(
                f"report_working refused: {maximum} reporters already")
            self._count("denied")
            return False
        dwell = float(self._thresholds.get("working_dwell_s", WORKING_DWELL_S))
        sounded = self._working.get(topic)
        self._count("working_reports")
        self.ec_producer.update("working.reporters", len(self._working) + (
            0 if topic in self._working else 1))
        self.ec_producer.update("working.last", str(detail)[:24])
        if sounded is not None and now - sounded < dwell:
            self._working[topic] = sounded     # The dwell is not restarted
            self.logger.debug(
                f"Working {detail} ({topic}): inside the dwell, so no sound")
            return False
        self._working[topic] = now
        self.logger.info(f"Working: {detail} ({topic})")
        self.signal(WORKING_PATTERN)
        return True

    def _answer(self, topic, outcome, detail):
        """Tell one client what became of its request"""

        command = {
            "granted": "powered_up_granted",
            "released": "powered_up_released",
            "refused": "powered_up_refused",
        }[outcome]
        # The detail becomes separate arguments, so the wire form is
        # "(uptime_refused maximum_seconds 600)" and not one length-prefixed
        # string with a space in it (ADR-002)
        self._publish_to(topic, command, *str(detail).split())

    def _publish_to(self, topic, command, *arguments):
        """One S-expression to one client topic.  A publication that fails
        must never stop a reading.

        Named apart from _publish(), which puts a reading into the shared
        state: one is a message to a client, the other is state"""

        from aiko_services.main.utilities import generate

        # aiko.process.message, and not aiko.message: the latter is the
        # module of that name, which has no publish().  share.py reaches it
        # through a name that "from aiko_services.main import *" provides.
        # It is None until the process runs, which a composed Actor in a
        # test is
        message = getattr(aiko.process, "message", None)
        if message is None:
            self.logger.debug(f"No message layer yet: {command} {topic}")
            return
        try:
            message.publish(topic, generate(command, list(arguments)))
        except Exception as error:                       # noqa: BLE001
            self.logger.warning(f"Could not answer {topic}: {error}")

    def _publish_powered_up(self):
        """The register's totals, and the metrics it counts"""

        for name, value in self._powered_up.as_share().items():
            self.ec_producer.update(name, value)
        for name, value in (
            ("powered_up_granted", self._powered_up.granted),
            ("powered_up_refused", self._powered_up.refused),
            ("powered_up_expired", self._powered_up.expired)):
            self.ec_producer.update(f"metrics.{name}", value)

    def available(self):
        """What this host can measure of its finite resources, as
        {unit: quantity}.

        A unit that is absent cannot be checked, so a Lease constrained in
        it is refused rather than granted: a client must not plan on a
        promise that nothing can keep.  Watt-hours arrive with the
        characterization of phase 6, which is why this is empty today"""

        return {}

    def _tell_unmet(self, unmet):
        """Tell each holder whose constraint can no longer be met.

        Its time is still current and the Lease is not usable, so the
        policy stops counting it and the holder hears why"""

        if not unmet:
            return
        available = self.available()
        for topic in unmet:
            if topic == BRIDGE_TOPIC or topic in self._unmet_told:
                continue
            lease = self._powered_up._leases.get(topic)
            name = lease.constraint.name if lease and lease.constraint  \
                else "-"
            left = available.get(name)
            self._publish_to(topic, "powered_up_unmet", name,
                "-" if left is None else f"{left:g}")
            self.logger.warning(f"Powered up unmet: {name} ({topic})")
        self._unmet_told = set(unmet)

    def _powered_up_expired(self, topic):
        """One Lease reached the time that was agreed.

        The framework's Lease calls this on the event-loop thread, so the
        holder is told and the policy is asked again at once.  Waiting for
        the next sample would hold a battery pack up for nobody, which is
        the opposite of what a Lease is for"""

        self.logger.info(f"Powered up expired: {topic}")
        if topic != BRIDGE_TOPIC:
            self._publish_to(topic, "powered_up_expired")
        self._publish_powered_up()
        if self._powered_up.held() == 0:
            self._evaluate(self.reading())

    @staticmethod
    def _now():
        import time

        return time.monotonic()

    def set_period(self, seconds):
        """Change the seconds between samples"""

        try:
            period = self._valid_period(seconds)
        except ValueError as error:
            self.logger.warning(f"Refused set_period: {error}")
            self.ec_producer.update("last_error", str(error)[:120])
            return
        if period == self._period:
            return
        # Only move a timer that is running.  An Actor composed without one
        # must not gain one here: a wire function that starts the sampling
        # it was asked to re-time is a surprise
        if self._timer:
            aiko.event.remove_timer_handler(self._sample_timer)
        self._period = period
        if self._timer:
            aiko.event.add_timer_handler(self._sample_timer, self._period)
        self.ec_producer.update("sample_period_s", f"{period:.1f}")
        self.logger.info(f"Sample period: {period} s")

# The event-loop thread ----------------------------------------------------- #

    def _sample_timer(self):
        self.sample()

    def _wake_after_grace(self):
        """Come back when the remount grace has passed, and not at the next
        sample.

        The grace is a few seconds and a sample period can be a minute.
        Without this a host that decided to stop at its voltage floor runs
        on, and lets its applications write, for most of a minute after the
        decision.  That is the case where a delay costs the most, because
        the battery pack is nearly empty.

        An Actor composed without a timer is driven by its tests, which
        call the decision themselves, so it gains no timer here.  Nor does
        an advisory one, which has no shutdown to finish"""

        if not self._timer or not self._enforce:
            return                     # Nothing waits on a grace to act
        aiko.event.add_timer_handler(
            self._grace_timer, float(self._quiesce.grace))

    def _grace_timer(self):
        """One shot: it takes itself away, then decides again"""

        aiko.event.remove_timer_handler(self._grace_timer)
        self._evaluate(self.reading())

    def _read_guarded(self):
        """read(), with every device failure turned into a reading that says
        so.  A sensor that stops answering must not stop the Actor"""

        try:
            reading = self.read()
        except OSError as error:                         # A bus or a part
            self.ec_producer.update(
                "metrics.sensor_errors",
                int(self.share["metrics"]["sensor_errors"]) + 1)
            self.ec_producer.update("last_error", str(error)[:120])
            reading = PowerReading(
                device=getattr(self, "device", "mock"), error=str(error)[:120])
        return self._with_host_telemetry(reading)

    def _with_host_telemetry(self, reading):
        """The processor load beside the power, so that the log shows what
        the host was doing when it took the current that it took.

        The processor temperature is its own field.  It is never the battery
        battery pack temperature, which the battery pack's own sensor reports"""

        from dataclasses import replace

        values = {
            "sampled_utc": reading.sampled_utc or utc_now(),
            "sampled_monotonic": reading.sampled_monotonic,
            "boot_id": reading.boot_id or self._boot_id,
        }
        if values["sampled_monotonic"] is None:
            import time
            values["sampled_monotonic"] = round(time.monotonic(), 3)
        if self._telemetry:
            cpu, memory, celsius, load = _host_telemetry()
            if reading.cpu_percent is None:
                values["cpu_percent"] = cpu
            if reading.memory_percent is None:
                values["memory_percent"] = memory
            if reading.cpu_celsius is None:
                values["cpu_celsius"] = celsius
            if reading.load_1m is None:
                values["load_1m"] = load
        return replace(reading, **values)

    def _evaluate(self, reading, now=None):
        """Decide, publish the decision, and act when allowed to.

        Returns (decision, reason, mode, mode_reason).  Runs on the
        event-loop thread, after every sample and after a button press"""

        import time

        now = time.monotonic() if now is None else now
        properties = tuple(self.properties())
        thresholds = self._thresholds

        # A Lease that runs out is dropped by its own timer, which tells
        # the holder and asks the policy again at that moment
        # (_powered_up_expired).  Nothing is swept here

        # The dock line glitches, so the host counts as docked until it has
        # been undocked for its dwell.  Holding the power is the safe side
        # of that doubt
        reported = reading.docked
        undocked_s = self._undocked.update(reported is False, now)
        dock_dwell = float(thresholds.get("dock_dwell_s", DOCK_DWELL_S))
        docked = True if reported is None else (
            reported or not self._undocked.passed(dock_dwell, now))

        low = _as_float(thresholds.get("battery_volts_low"))
        battery_low_s = self._battery_low.update(
            reading.battery_volts is not None and low is not None
            and reading.battery_volts < low, now)
        available = self.available()
        met, unmet = self._powered_up.satisfied(available)
        self._tell_unmet(unmet)
        powered_up_held = len(met)
        powered_up_idle_s = self._powered_up_idle.update(
            powered_up_held == 0, now)

        decision, reason = decide(
            reading.battery_volts, reading.battery_pack_celsius, docked,
            properties, powered_up_held, self._button_held,
            undocked_s, battery_low_s, powered_up_idle_s, thresholds)
        mode, mode_reason = decide_mode(
            self._mode, decision, reading.battery_volts, docked,
            self.hook_state(), thresholds, undocked_s)

        self._publish_decision(
            decision, reason, mode, mode_reason, docked, undocked_s, now)
        if mode != self._mode:
            self._enter_mode(mode, mode_reason, now)
        if decision == SHUTDOWN:
            self._act(reason, now)
        return decision, reason, mode, mode_reason

    def _publish_decision(self, decision, reason, mode, mode_reason,
        docked, undocked_s, now=None):

        """Everything the decision produced, whether or not it is acted on.

        "now" is the clock that the decision used.  One clock, or a claim
        that the policy counted would be published as expired"""

        now = self._now() if now is None else now

        items = {
            "policy_would": decision,
            "policy_reason": reason,
            "mode_reason": mode_reason,
            "docked": "yes" if docked else "no",
            **self._powered_up.as_share(),
            **self._quiesce.done(),
        }
        if not self._enforce:
            items["policy"] = POLICY_ADVISORY
        elif not self._stopping:
            items["policy"] = HOLD if decision == HOLD  \
                else "shutdown_pending"
        if undocked_s and self.share["undocked_since_utc"] == "-":
            items["undocked_since_utc"] = utc_now()
        elif not undocked_s:
            items["undocked_since_utc"] = "-"
        for name, value in items.items():
            self.ec_producer.update(name, value)

    def _notify_holders(self, command, *arguments):
        """Tell every client that holds a claim.  The bridge is not a
        client and has no topic to tell"""

        for topic in self._powered_up.topics():
            self._publish_to(topic, command, *arguments)

    def _enter_mode(self, mode, reason, now):
        """A mode change, with what each mode asks for.

        Quiesce flushes the file systems once and runs the declared hook, so
        that whatever is writing can stop before the power goes"""

        self._mode = mode
        self.ec_producer.update("mode", mode)
        self.ec_producer.update("writing_ok", policy_writing_ok(mode))
        self.logger.info(f"Power mode: {mode} ({reason}), "
            f"writing {'okay' if policy_writing_ok(mode) else 'not okay'}")
        # Every client that holds a claim hears the mode, so it can stop
        # writing without watching the shared state for itself
        self._notify_holders("power_mode", mode, reason)
        if mode != MODE_QUIESCE:
            return
        self._count("quiesces")
        outcome = self._quiesce.enter(now)
        # The grace starts here in the ordinary path, so this is where the
        # wake-up belongs.  _act() has the same call for the case where
        # nothing entered the mode
        self._wake_after_grace()
        if outcome and not outcome[0]:
            self.logger.error(f"Sync failed: {outcome[1]}")
            self.ec_producer.update("last_error", outcome[1][:120])
        self.run_hook(HOOK_QUIESCE,
            lambda: {"mode": mode, "reason": reason})
        for name, value in self._quiesce.done().items():
            self.ec_producer.update(name, value)

    def _act(self, reason, now):
        """Stop the host, when this Actor is enforcing, or when the reason
        is one that needs no calibration.

        While it is advisory a reason that rests on a data-sheet threshold
        logs the decision and does nothing, which is the whole point of the
        posture: those numbers are untested until the battery pack has been
        measured. The button, the deployment's deadline and the backstop
        rest on a person, a dock line and a clock, so they act
        (EXACT_REASONS). A deadline that never acted would let an undocked
        host drain its pack flat"""

        # Some reasons act whatever the posture.  Advisory is about
        # thresholds from a data sheet, and these need no such number: a
        # person held the button, or a dock line and a clock agreed that
        # the supply has been gone for the deadline (EXACT_REASONS).  An
        # undocked host that does not act on those drains its battery pack
        # flat, which is the outcome this design exists to prevent
        exact = reason in EXACT_REASONS
        if reason == "button_held" and not self._button_shutdown:
            exact = False
        if not self._enforce and not exact:
            self.logger.warning(
                f"Advisory: would shut down now ({reason})")
            return
        if self._stopping:
            return
        floor = _as_float(self._thresholds.get("battery_volts_floor"))
        volts = _as_float(self.share["battery"].get("volts"))
        at_floor = reason == "battery_floor" or (
            volts is not None and floor is not None and volts < floor)
        # A press is answered now, and not after a grace.  The mode change
        # has already told the writers and flushed the file systems, and
        # the power-off unmounts in an orderly way by itself.  Waiting out
        # the remount grace here would cost the operator a whole sample
        # period, which is a minute in production.
        #
        # A deadline is not a press.  Nobody is waiting on it, and the
        # battery pack is the thing at risk, so it takes the quiesce and
        # the read-only remount in full
        if reason == "button_held":
            at_floor = False
        if at_floor and self._quiesce.entered_at is None:
            # Start the grace here, rather than wait on one that nothing
            # started.  Otherwise a mode that never changed would leave the
            # host running on the last of its charge for ever
            self._quiesce.enter(now)
            self._wake_after_grace()
            return
        if at_floor and self._quiesce.ready_to_remount(now):
            outcome = self._quiesce.remount()
            if outcome and not outcome[0]:
                self.logger.error(f"Remount failed: {outcome[1]}")
                self.ec_producer.update("last_error", outcome[1][:120])
            for name, value in self._quiesce.done().items():
                self.ec_producer.update(name, value)
        elif at_floor:
            return                     # Wait out the grace, then remount

        self._stopping = True
        self.ec_producer.update("policy", POLICY_SHUTTING_DOWN)
        self._count("shutdowns")
        self.logger.warning(f"Shutting down: {reason}")
        self.signal("shutdown")
        self._power_off()

    def _power_off(self):
        """Ask the operating system to stop, on a worker thread.

        A subprocess blocks, and the event-loop thread must not (P2).  The
        shutdown hook releases the power hold after the file systems are
        unmounted, and this Actor never does (ADR-028 decision 6)"""

        from threading import Thread

        def run():
            ok, detail = power_off(runner=self._power_off_runner)
            if not ok:
                self._post_message(
                    aiko.ActorTopic.IN, "_power_off_failed", [detail[:120]])

        if not self._worker:
            ok, detail = power_off(runner=self._power_off_runner)
            if not ok:
                self._power_off_failed(detail[:120])
            return
        Thread(target=run, daemon=True, name="power_off").start()

    def _power_off_failed(self, detail):
        """The host could not be stopped.  An operator must see this: a
        battery policy that cannot act is advice, whatever it says"""

        self.logger.error(f"Power off refused: {detail}")
        self.ec_producer.update("last_error", f"power off: {detail}"[:120])
        self.ec_producer.update("policy", "shutdown_pending")
        self._stopping = False

    def _input_event(self, event, value):
        """A button or dock event, on the event-loop thread.

        The device reports on its own thread and posts here (P11)"""

        if event == "dock":
            self.logger.info(f"Dock: {value}")
            # Decided now, and not at the next sample.
            #
            # The two directions are not alike.  Losing the supply can
            # wait: the battery pack exists for exactly that, a glitch must
            # not stop a recording, and the dock dwell and the two
            # deadlines are all deliberately patient.  Getting the
            # application working again should be prompt, because nothing
            # is gained by a host that stays quiesced while its supply is
            # back.
            #
            # So the dwell and the deadlines keep the patience on the
            # losing side, and this takes the sample period out of the
            # returning side.  In production that period is a minute, so
            # without this a recording resumed up to a minute after the
            # supply did
            self._evaluate(self.reading())
            return
        if event == "button":
            if value == "held":
                self._count("button_presses")
                self._button_held = True
                self.logger.warning("Button held: shutting down")
                self.signal("accepted")
                self._evaluate(self.reading())
            elif value.startswith("up") or value == "short":
                self.logger.info(f"Button {value}")
                # A release clears the latch, unless a shutdown is already
                # running.  Without this one press makes the policy report
                # "button_held" for ever, and that reason is read before
                # every other one, so the Actor goes blind to its own
                # battery pack.  Seen in production on 2026-11-05: four
                # readings in a row reported "button_held" while the pack
                # was under its floor, and the floor is what mattered
                # Only where a latch is actually set, so that a press
                # which asked for nothing also changes nothing
                if self._button_held and not self._stopping:
                    self._button_held = False
                    # Decide again now, so that an operator sees the policy
                    # recover rather than waiting out a sample period
                    self._evaluate(self.reading())

    def _publish(self, reading):
        """One reading into the shared state, through the producer"""

        items = reading.as_share()
        items["battery.margin_volts"] = _token(
            reading.margin_volts(self._thresholds["battery_volts_floor"]))
        items["metrics.samples"] =  \
            int(self.share["metrics"]["samples"]) + 1
        for name, value in items.items():
            self.ec_producer.update(name, value)

    def _power_change_handler(self, command, item_name, item_value):
        """"safe" is a report of the posture, and not a control for it.  The
        posture comes from the command line, which does not cross the bus"""

        if command != "update" or item_name != "safe":
            return
        if item_value != self._safe:
            self.logger.warning('Refused "safe": read only')
            self.ec_producer.update("metrics.denied",
                int(self.share["metrics"]["denied"]) + 1)
            self.ec_producer.update("safe", self._safe)

    @staticmethod
    def _valid_period(seconds):
        period = float(seconds)
        if not PERIOD_LOW <= period <= PERIOD_HIGH:
            raise ValueError(
                f"period must be {PERIOD_LOW} to {PERIOD_HIGH}, not {period}")
        return period

# Phase 1 has no outputs ---------------------------------------------------- #

    def hold(self, on):
        """A no-op where the "hold" property is absent"""

        self.logger.warning(
            f'hold({on}) ignored: this Implementation has no "hold" property')

    def signal(self, name):
        """A no-op where the "signal" property is absent"""

        self.logger.warning(
            f'signal({name}) ignored: no "signal" property')

    def _count(self, name):
        """One more of a metric, published through the producer"""

        self.ec_producer.update(
            f"metrics.{name}", int(self.share["metrics"][name]) + 1)

    def add_handler(self, handler):
        """Recorded, and nothing fires it while there is no button or dock
        property (phase 3)"""

        self._handlers = getattr(self, "_handlers", [])
        self._handlers.append(handler)

    def close(self):
        """Release the devices, the Leases and the log.  Never the power
        hold.

        Every Lease carries two event-loop timers, so a register that is
        not terminated leaves them behind.  So do the sample timer and a
        remount grace that never finished"""

        self._powered_up.terminate()
        if self._timer:
            aiko.event.remove_timer_handler(self._sample_timer)
            # A grace that never finished leaves its timer behind otherwise
            aiko.event.remove_timer_handler(self._grace_timer)
        if self._log:
            self._log.close()

def _nest(items):
    """Dotted names as the nested dictionary that the shared state holds.

    "battery.volts" becomes {"battery": {"volts": ...}}.  The share is at
    most two levels deep, which is every name that this Actor publishes"""

    nested = {}
    for name, value in items.items():
        if "." in name:
            group, item = name.split(".", 1)
            nested.setdefault(group, {})[item] = value
        else:
            nested[name] = value
    return nested

def _as_float(value, default=None):
    """A shared variable or a threshold as a float.  "-" and a mistyped
    value are "default", and a rule whose number is None does not fire"""

    if value is None or value == "-":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def _token(value):
    return "-" if value is None else f"{value:.3f}"

def _host_telemetry():
    """(cpu percent, memory percent, processor celsius, one minute load), or
    None for each one that this host does not report.

    The same psutil calls that actors/display/status.py makes, with no
    interval, so cpu_percent() reads the counters since the last call rather
    than waiting (P2: the event-loop thread must not block)"""

    import os

    load = None
    try:
        load = round(os.getloadavg()[0], 2)
    except (AttributeError, OSError):
        pass
    if psutil is None:
        return None, None, None, load
    cpu = round(psutil.cpu_percent(interval=None), 1)
    memory = round(psutil.virtual_memory().percent, 1)
    celsius = None
    try:
        for readings in psutil.sensors_temperatures().values():
            if readings:
                celsius = round(readings[0].current, 1)
                break
    except (AttributeError, NotImplementedError, OSError):
        pass
    return cpu, memory, celsius, load

# Composition --------------------------------------------------------------- #

def power_manager_args(name, device, declared=(), **parameters):
    """init_args for composing a PowerManager Implementation.

    "declared" is what the Implementation offers, which the Service tags
    carry.  It is named apart from the Implementation's own "properties"
    parameter, so that one word never means two things in one call"""

    init_args = aiko.actor_args(
        name, protocol=PROTOCOL, tags=service_tags(device, declared))
    init_args.update(parameters)
    return init_args

def choose_power_manager(device="auto"):
    """The Implementation class for "device", with nothing acquired.

    "auto" is the power management module where its parts answer, then the
    laptop of this operating system, then the mock.  The explicit names are
    "pmm", "linux", "macos" and "mock" """

    from aiko_services.actors.power_manager.mock import MockPowerManagerImpl
    from aiko_services.actors.power_manager.pmm import (
        PmmPowerManagerImpl, module_present
    )

    implementations = {
        "pmm": PmmPowerManagerImpl,
        "mock": MockPowerManagerImpl,
    }
    if device == "auto":
        device = "pmm" if module_present() else "mock"
    if device in ("linux", "macos"):
        raise ValueError(
            f'"{device}" is phase 7 of the power manager plan: use "mock"')
    if device not in implementations:
        raise ValueError(
            f'unknown device "{device}": one of {sorted(implementations)}')
    return implementations[device]

def service_tags(device, properties=()):
    """The tags the Actor registers with: shared state, the device kind, and
    one tag for each property of PROPERTIES"""

    return ["ec=true", f"device={device}",
        *[f"{name}={'true' if name in properties else 'false'}"
            for name in PROPERTIES]]

def service_filter(name=None):
    """The discovery filter for the PowerManager named NAME (default: this
    host's name): protocol power_manager:0, any namespace, owner, transport,
    tags"""

    return aiko.ServiceFilter(
        "*", name or get_hostname(), PROTOCOL, "*", "*", "*")

# --------------------------------------------------------------------------- #
