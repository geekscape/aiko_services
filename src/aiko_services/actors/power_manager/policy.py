#!/usr/bin/env python3
#
# Aiko Services: when to keep the power on, and when to stop
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# One rule, in one function, with no hardware and no Actor in it.  decide()
# takes numbers and tokens and returns a decision and the one word that says
# why.  Therefore a truth table tests every row of it (ADR-028 decision 8),
# and classify() in the WhisPlay button is the precedent.
#
# The order of the rows is the rule.  The button beats everything, because
# a person asked.  The floor voltage and the battery pack temperature beat
# every claim on the host, because a battery pack that is damaged is damaged
# for good and work can wait for the next working period.  A claim that is
# held keeps the power on, because the work is why this host has a battery
# at all, and the undocked deadline bounds how long that can go on.
#
# The deadline is read before the claims, and that order is the whole of
# what a deployment's grace period means: when the supply goes and does not
# come back, the host stops after that long whatever work is claimed.  Two
# thresholds set the deadline and the shorter wins, so _deadline() names
# which one fired.
#
# Nothing here names an application.  A client that needs the host asks for
# a powered-up Lease and holds a Lease (powered_up.py, ADR-028 decision 13), so this rule
# counts claims and never asks any Actor what work it has left.
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
# A mode that is not "normal" means that an application should stop writing
# to the file systems.  That is the whole use an application makes of this,
# so the Actor publishes it as one boolean and a client reads that rather
# than learning the modes.
#
# To Do
# ~~~~~
# * A percentage and an estimated time, after a discharge curve is measured
#   (ADR-028 decision 10).  decide() takes volts today

__all__ = [
    "Dwell", "EXACT_REASONS", "HOLD", "MODES", "MODE_CONSERVE",
    "MODE_NORMAL", "MODE_QUIESCE", "REASONS", "SHUTDOWN", "decide",
    "SUPPLY_WARNINGS", "decide_action", "decide_mode", "supply_warning",
    "writing_ok",
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
    "button_held", "battery_floor", "battery_pack_temperature",
    "no_hold_property", "docked", "battery_low", "undocked_timeout",
    "powered_down_grace", "powered_up_held", "powered_up_idle",
    "powered_up_grace", "hook_missing", "application_grace",
)

# The reasons that act whatever the posture is.
#
# The advisory posture exists for one reason: the voltage and the
# temperature thresholds come from a data sheet, and not from the battery
# pack that is fitted.  Until that pack is measured, a host must not stop
# itself because of a number nobody checked.
#
# These three need no such number.  A person held the button.  A dock line
# says the supply is gone, and a clock says for how long.  Both are exact,
# and no calibration makes them more true.  So refusing to act on them is
# not caution: it is how a battery pack gets drained flat, which is the
# outcome the whole design exists to prevent.
#
# A deployment turns the two deadlines off by setting neither of them.
# Setting a deadline is how a deployment asks for the action.
EXACT_REASONS = frozenset({
    "button_held",                 # A person asked
    "powered_down_grace",          # The deployment's own deadline
    "undocked_timeout",            # The backstop on an undocked hold
})

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

def decide(volts, battery_pack_celsius, docked, properties, powered_up_held,
    button_held, undocked_s, battery_low_s, powered_up_idle_s, thresholds):

    """What to do now: (HOLD, reason) or (SHUTDOWN, reason).

    Pure.  Every argument is a number, a token or a boolean, and no argument
    is a device.  "volts" and "battery_pack_celsius" may be None, which is a host
    that cannot measure them rather than a host in trouble.

    The rows are tried in order, and the order is the rule:

      the button was held        -> shutdown, a person asked
      under the voltage floor    -> shutdown, before the cells spoil
      the battery pack is hot    -> shutdown, before the cells spoil
      cannot hold its own power  -> hold, there is nothing to decide
      docked                     -> hold, the supply is not ours to save
      undocked, the pack is low  -> shutdown, after its dwell
      undocked past its deadline -> shutdown, the deadline on the hold:
                                    the deployment's grace period, or the
                                    backstop, whichever is shorter
      undocked, a claim is held  -> hold, this is what the battery is for
      undocked, no claim is held -> shutdown, after its grace, and
                                    "powered_up_grace" until then
    """

    floor = _number(thresholds.get("battery_volts_floor"))
    low = _number(thresholds.get("battery_volts_low"))
    hot = _number(thresholds.get("battery_pack_celsius_maximum"))
    dwell = _number(thresholds.get("battery_dwell_s"), 0.0)
    maximum = _number(thresholds.get("undocked_maximum_s"))
    powered_down = _number(thresholds.get("powered_down_grace_s"))
    grace = _number(thresholds.get("powered_up_grace_s"), 0.0)

    for decision, reason in _rows(volts, battery_pack_celsius, docked,
        properties, powered_up_held, button_held, undocked_s, battery_low_s,
        powered_up_idle_s, floor, low, hot, dwell, maximum, powered_down,
        grace):

        return decision, reason                  # The first, and the most
                                                 #   urgent, is the answer

def decide_action(volts, battery_pack_celsius, docked, properties,
    powered_up_held, button_held, undocked_s, battery_low_s,
    powered_up_idle_s, thresholds, actionable=None):

    """The first decision a caller can act on, and the one word that says
    why.

    The rows are the same rows, in the same order.  The difference is what
    happens when the most urgent reason is one the caller cannot act on: a
    hold is final, and a shutdown is not, so the next shutdown is offered
    instead.

    **This exists because an inert reason masked an active one**, measured
    in production on 2026-11-05.  A battery pack sagged below its floor in
    the first second of every undocking, so `decide()` answered
    "battery_floor" every time.  That reason comes from a data sheet, so an
    advisory posture holds it back, and `decide()` had already returned, so
    the deadline below it was never reached.  The deadline would have acted.
    The host therefore ran on a flat pack until it browned out, with the
    log saying "would shut down now" once a minute.

    "actionable" is the set of reasons the caller can act on, and None
    means every one of them.  Passing a set is how the posture reaches a
    pure function: as data, and not as a flag with behavior behind it"""

    floor = _number(thresholds.get("battery_volts_floor"))
    low = _number(thresholds.get("battery_volts_low"))
    hot = _number(thresholds.get("battery_pack_celsius_maximum"))
    dwell = _number(thresholds.get("battery_dwell_s"), 0.0)
    maximum = _number(thresholds.get("undocked_maximum_s"))
    powered_down = _number(thresholds.get("powered_down_grace_s"))
    grace = _number(thresholds.get("powered_up_grace_s"), 0.0)

    for decision, reason in _rows(volts, battery_pack_celsius, docked,
        properties, powered_up_held, button_held, undocked_s, battery_low_s,
        powered_up_idle_s, floor, low, hot, dwell, maximum, powered_down,
        grace):

        if decision == HOLD:
            return decision, reason              # A hold is final
        if actionable is None or reason in actionable:
            return decision, reason
    return HOLD, "powered_up_grace"              # The rows end in a hold

def _rows(volts, battery_pack_celsius, docked, properties, powered_up_held,
    button_held, undocked_s, battery_low_s, powered_up_idle_s, floor, low,
    hot, dwell, maximum, powered_down, grace):

    """Every decision the rule reaches, in its order.

    One rule, read two ways.  decide() takes the first of these, which is
    the most urgent truth and what an operator is shown.  decide_action()
    walks past a shutdown it cannot act on and takes the next, which is
    what stops a host.  A generator is what lets both read one rule rather
    than two copies of it that can drift apart"""

    if button_held:
        yield SHUTDOWN, "button_held"
    if volts is not None and floor is not None and volts < floor:
        yield SHUTDOWN, "battery_floor"
    if battery_pack_celsius is not None and hot is not None  \
        and battery_pack_celsius > hot:
        yield SHUTDOWN, "battery_pack_temperature"
    if "hold" not in properties:
        yield HOLD, "no_hold_property"
        return
    if docked:
        yield HOLD, "docked"
        return

    # Undocked from here down
    if volts is not None and low is not None and volts < low  \
        and battery_low_s >= dwell:
        yield SHUTDOWN, "battery_low"
    deadline, deadline_reason = _deadline(powered_down, maximum)
    if deadline is not None and undocked_s is not None  \
        and undocked_s > deadline:
        yield SHUTDOWN, deadline_reason
    if powered_up_held:
        yield HOLD, "powered_up_held"
        return
    if powered_up_idle_s >= grace:
        yield SHUTDOWN, "powered_up_idle"
    yield HOLD, "powered_up_grace"

def _deadline(powered_down_grace_s, undocked_maximum_s):
    """The deadline on an undocked hold, and the word for whichever
    threshold set it.

    Two thresholds answer one question, so one rule reads both and the
    shorter one wins.  They mean different things.  The backstop says that
    no host runs on its battery pack for ever, and it is not meant to be
    reached.  The grace period is a deployment's own rule: when the supply
    goes, and does not come back, stop after this long whatever work is
    claimed.  A deployment that sets a grace period usually sets it far
    shorter than the backstop.  So the decision names which one fired, and
    a log explains a shutdown rather than only reporting it.

    A grace period that is absent, zero or negative is off, which is the
    default.  Then the backstop is the only deadline, and the behavior is
    what it was before this threshold existed.  A tie goes to the grace
    period, because an operator set that one on purpose"""

    if powered_down_grace_s is not None and powered_down_grace_s <= 0:
        powered_down_grace_s = None
    found = [(seconds, reason) for seconds, reason in (
        (powered_down_grace_s, "powered_down_grace"),
        (undocked_maximum_s, "undocked_timeout"))
        if seconds is not None]
    if not found:
        return None, None
    return min(found, key=lambda item: item[0])

def decide_mode(mode, decision, volts, docked, hook_state, thresholds,
    undocked_s=0.0):
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
    halt should stop writing even while its supply is still there.

    MODE_CONSERVE means that an application should stop writing to the file
    systems.  A supply that goes for a moment must not stop a recording, so
    "powered_down_application_grace_s" is how long the host stays undocked
    before the mode says so.  Until then the mode is normal, with the
    reason "application_grace".  A dock makes the undocked seconds zero, so
    the grace starts again from the beginning.  The threshold is off by
    default, and then an undocked host conserves at once, which is what it
    did before the threshold existed
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

    # Undocked, and nothing above applies.  The application grace is the
    # last word: a supply that went for a moment must not stop a recording
    application = _number(
        thresholds.get("powered_down_application_grace_s"))
    if application is not None and application > 0  \
        and (undocked_s or 0.0) <= application:
        return MODE_NORMAL, "application_grace"
    return MODE_CONSERVE, "undocked"

# What a warning about the supply can say.  One token each, for a shared
# variable and a log column
SUPPLY_WARNINGS = ("supply_current", "supply_headroom")

def supply_warning(supply_volts, supply_amps, battery_volts, docked,
    thresholds):

    """Whether the supply looks too small for this host, and the one word
    that says how.  None when it looks adequate, or when there is nothing
    to judge it by.

    **It decides nothing.** A warning is for a person, and the policy is
    untouched by it: a small supply is a thing to replace, not a reason to
    stop a host.  So this is reported and counted, and no row of decide()
    reads it.

    Two ways to see it, and the current is the cause where the rating is
    known.

    "supply_current": the supply is at the rating its label claims.  A
    supply at its limit has nothing left for the battery pack, and it
    drops its voltage as well, which is the other half of the symptom.

    "supply_headroom": docked, and the supply is barely above the battery
    pack.  A charger needs to be enough above the pack to push current
    into it, so with no headroom the pack is held wherever it happens to
    be and never fills.  Measured on 2026-11-05: a supply at 10.22 V and a
    pack at 9.89 V, which is 0.33 V where about 2 V is wanted, on a pack
    that had never been charged.

    Both are read from one reading, so there is no history to keep"""

    rating = _number(thresholds.get("supply_amps_maximum"))
    fraction = _number(thresholds.get("supply_amps_fraction"), 0.95)
    if rating is not None and rating > 0 and supply_amps is not None  \
        and supply_amps >= rating * fraction:
        return "supply_current"
    headroom = _number(thresholds.get("supply_headroom_volts"))
    if docked and headroom is not None and headroom > 0  \
        and supply_volts is not None and battery_volts is not None  \
        and supply_volts > 0  \
        and supply_volts - battery_volts < headroom:
        return "supply_headroom"
    return None

def writing_ok(mode):
    """Whether an application should write to the file systems now.

    One boolean, derived in one place.  An application asks this and does
    not learn the modes, so a later rule that stops writing for a new
    reason needs no change in any client"""

    return mode == MODE_NORMAL

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
