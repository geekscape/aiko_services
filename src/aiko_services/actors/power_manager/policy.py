#!/usr/bin/env python3
#
# Aiko Services: when to keep the power on, and when to stop
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# One rule, in one function, with no hardware and no Actor in it.  decide()
# takes numbers and tokens and returns a decision and the one word that says
# why.  Therefore a truth table tests every row of it (ADR-028 decision 8),
# and classify() in the WhisPlay button is the precedent.
#
# The order of the rows is the rule.  The button beats everything, because a
# person asked.  The floor voltage and the battery pack temperature beat the queue,
# because a battery pack that is damaged is damaged for good and a queue can wait
# for the next shift.  An unknown queue keeps the power on, because the data
# is why this host has a battery at all, and the undocked time bounds how
# long that can go on.
#
# Dwell is the other half of the rule.  A load step makes the voltage sag
# for seconds, and a supply glitches, so a reading that crosses a threshold
# is not yet a reason.  Dwell counts how long a condition has been true and
# takes the clock as an argument, so a test walks time without sleeping.
#
# Modes are a second, smaller decision.  decide_mode() says whether the host
# is running normally, conserving, or about to lose its power and therefore
# writing nothing.  It never returns to "normal" without a dock: a battery
# that recovered a little is not a battery that was charged.
#
# To Do
# ~~~~~
# * A percentage and an estimated time, after a discharge curve is measured
#   (ADR-028 decision 10).  decide() takes volts today

__all__ = [
    "Dwell", "HOLD", "MODES", "MODE_CONSERVE", "MODE_NORMAL", "MODE_QUIESCE",
    "REASONS", "SHUTDOWN", "decide", "decide_mode",
]

HOLD = "hold"
SHUTDOWN = "shutdown"

MODE_NORMAL = "normal"
MODE_CONSERVE = "conserve"
MODE_QUIESCE = "quiesce"
MODES = (MODE_NORMAL, MODE_CONSERVE, MODE_QUIESCE)

# Every word that a decision can carry.  One token, no spaces, so it is a
# shared variable and a log column that a reader can count
REASONS = (
    "button_held", "battery_floor", "battery_pack_temperature", "no_hold_property",
    "docked", "battery_low", "undocked_timeout", "queue_empty",
    "queue_busy", "queue_unknown", "hook_missing",
)

class Dwell:
    """How long a condition has been true, without sleeping.

    update(True, now) starts the clock and keeps it; update(False, now)
    clears it.  seconds(now) is how long it has been true, or 0.0.  The
    clock is an argument, so a test walks time"""

    def __init__(self):
        self.since = None

    def update(self, condition, now):
        """Record the condition at "now".  Returns the seconds so far"""

        if not condition:
            self.since = None
            return 0.0
        if self.since is None:
            self.since = now
        return self.seconds(now)

    def seconds(self, now):
        """How long the condition has held, or 0.0 when it does not hold"""

        return 0.0 if self.since is None else max(0.0, now - self.since)

    def passed(self, limit, now):
        """Whether the condition has held for at least "limit" seconds"""

        return self.since is not None and self.seconds(now) >= float(limit)

def decide(volts, battery_pack_celsius, docked, properties, queue_busy, queue_known,
    button_held, undocked_s, battery_low_s, queue_empty_s, thresholds):

    """What to do now: (HOLD, reason) or (SHUTDOWN, reason).

    Pure.  Every argument is a number, a token or a boolean, and no argument
    is a device.  "volts" and "battery_pack_celsius" may be None, which is a host
    that cannot measure them rather than a host in trouble.

    The rows are tried in order, and the order is the rule:

      the button was held               -> shutdown, a person asked
      the battery pack is under its floor       -> shutdown, before the cells spoil
      the battery pack is too hot               -> shutdown, before the cells spoil
      this host cannot hold its power   -> hold, there is nothing to decide
      docked                            -> hold, the supply is not ours to save
      undocked and the battery pack is low      -> shutdown, after its dwell
      undocked for too long             -> shutdown, the bound on the hold
      undocked and the queue is empty   -> shutdown, after its grace
      undocked and the queue is busy    -> hold, this is what the battery pack is for
      undocked and the queue is unknown -> hold, and the bound above applies
    """

    floor = _number(thresholds.get("battery_volts_floor"))
    low = _number(thresholds.get("battery_volts_low"))
    hot = _number(thresholds.get("battery_pack_celsius_maximum"))
    dwell = _number(thresholds.get("battery_dwell_s"), 0.0)
    maximum = _number(thresholds.get("undocked_maximum_s"))
    grace = _number(thresholds.get("queue_grace_s"), 0.0)

    if button_held:
        return SHUTDOWN, "button_held"
    if volts is not None and floor is not None and volts < floor:
        return SHUTDOWN, "battery_floor"
    if battery_pack_celsius is not None and hot is not None and battery_pack_celsius > hot:
        return SHUTDOWN, "battery_pack_temperature"
    if "hold" not in properties:
        return HOLD, "no_hold_property"
    if docked:
        return HOLD, "docked"

    # Undocked from here down
    if volts is not None and low is not None and volts < low  \
        and battery_low_s >= dwell:
        return SHUTDOWN, "battery_low"
    if maximum is not None and undocked_s is not None  \
        and undocked_s > maximum:
        return SHUTDOWN, "undocked_timeout"
    if not queue_known:
        return HOLD, "queue_unknown"
    if not queue_busy and queue_empty_s >= grace:
        return SHUTDOWN, "queue_empty"
    return HOLD, "queue_busy"

def decide_mode(mode, decision, volts, docked, hook_state, thresholds):
    """The next mode: one of MODES, and the one word that says why.

    Pure.  "mode" is the mode now, because this decision has memory: a mode
    never returns to normal without a dock.  A battery pack that recovered a little
    is not a battery pack that was charged, and a host that stopped writing has
    nothing to gain by starting again.

    Reaching MODE_QUIESCE is the signal that the power will end, by any
    route: the policy decided to stop, the battery pack fell past its quiesce
    voltage, or the shutdown hook is known to be missing on an undocked
    host, which means the hold will not be released and the battery pack will run
    out.

    "hook_state" is a token, and only "missing" is a trigger.  An unknown
    hook is not evidence that the hold will be left asserted, and a
    platform that has no such hook at all reports "unknown" for ever.

    The decision is read before the dock, because a host that is about to
    halt should stop writing even while its supply is still there
    """

    quiesce_volts = _number(thresholds.get("quiesce_volts"))

    # A decision to stop comes first, docked or not.  A host that is about
    # to halt should stop writing even while its supply is still there: the
    # button is pressed on a docked host too
    if decision == SHUTDOWN:
        return MODE_QUIESCE, "policy"
    if docked:
        return MODE_NORMAL, "docked"
    if volts is not None and quiesce_volts is not None  \
        and volts <= quiesce_volts:
        return MODE_QUIESCE, "battery"
    if hook_state == "missing":
        return MODE_QUIESCE, "hook_missing"
    if mode == MODE_QUIESCE:
        return MODE_QUIESCE, "held"              # Never back, without a dock
    return MODE_CONSERVE, "undocked"

def _number(value, default=None):
    """A threshold as a float.  A missing or unreadable one is "default",
    and a rule whose threshold is None does not fire: a policy must not
    stop a host because a setting was mistyped"""

    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

# --------------------------------------------------------------------------- #
