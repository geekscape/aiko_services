#!/usr/bin/env python3
#
# Aiko Services: a Lease on staying powered up
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# A battery pack is a finite resource that may be consumed within reason,
# so what consumes it is managed by a Lease (ADR-028 decision 13).
#
# The policy asks one question of everybody, and names no application.
#
#     Does anything still need this host?
#
# A client answers by holding a PoweredUpLease.  It asks for a number of
# seconds, extends the Lease before it expires, and releases it when its
# work is done.  Thus a Pipeline that records, an Agent that thinks, a store
# and forward of files, and Aiko Services itself all make the same claim in
# the same way, and the power manager knows what none of them are.
#
# **The unknown case disappears, and that is the point.**  A client that
# cannot be reached cannot hold a Lease, and a Lease that nothing extends
# expires.  So "nobody answered" and "nobody needs me" become one
# measurable thing, rather than a guess that the power manager made on
# behalf of an Actor it could not see.
#
# One word throughout: "powered up", the state that a client asks to keep.
# PoweredUpLease, PoweredUpRegister, "(request_powered_up ...)",
# "powered_up.held".  An earlier version said "power up" for the verb and
# "powered up" for the noun, which made a reader hold two spellings of one
# idea (project-lead direction, 2026-11-05).
#
# PoweredUpLease extends the framework's Lease, as ECLease does, so an
# expiry acts at the time that was agreed and not at the next convenient
# moment.
# Prompt action at the agreed timeout is a large part of what a Lease is
# for: the last Lease to expire is the event that lets a host stop, and a
# host that waited for its next sample would be holding a battery pack up
# for no one.
#
# **A Lease has two conditions, and both must hold.**  The lease_time is
# the period for which it is valid, and a client extends it.  The
# constraint is a quantity of a finite resource, in whatever unit measures
# it, and the host must still be able to meet it.  A Lease whose time is
# current but whose constraint cannot be met is not usable, so it stops
# counting as a reason to keep the host up, and its holder is told.
#
# Today one unit is declared: watt-hours of the battery pack.  Seconds are
# not a constraint, because the lease_time already is one.  A request with
# no constraint asks for time alone, which is what a client that does not
# know its own energy cost should do.
#
# **A constraint in a unit the host cannot measure is refused**, and never
# granted.  Granting what cannot be checked is worse than refusing it: the
# client would plan on a promise that nothing can keep.  The power manager
# can measure watt-hours only after the battery pack is characterized, so
# until then such a request is refused with "no_measurement".
#
# One finite resource is shared, so the register answers for the whole of
# it and not for each Lease alone.  Two clients that each ask for 20 Wh of
# 30 Wh are each satisfiable and together are not.  The rule is first
# granted, first served: the register meets Leases in the order they were
# taken until the quantity runs out, and the rest are unmet.  That rule is
# arbitrary in the way that any fair rule is, and it is at least one a
# person can predict.
#
# A Lease asks, and it never commands.  It cannot outlive the bound on
# undocked time, the battery voltage floor or the battery pack temperature
# gate: those stop a host whatever is held here.
#
# To Do
# ~~~~~
# * Measure the watt-hours that are left, which is phase 6 of the plan.
#   The mechanism is here and the quantity is not, so a request in
#   watt-hours is refused today
# * More units, as something needs them: inbox bytes for a host with a
#   full disk, or thermal headroom for one that is throttling.  A unit is
#   a name in CONSTRAINTS and a quantity that available() can report

from dataclasses import dataclass

from aiko_services.main.lease import Lease

__all__ = [
    "BRIDGE_TOPIC",
    "CONSTRAINTS",
    "CONSTRAINT_WATT_HOURS",
    "LeaseConstraint",
    "POWERED_UP_MAXIMUM_S",
    "POWERED_UP_REQUESTS_MAXIMUM",
    "REFUSED_MAXIMUM",
    "REFUSED_NO_MEASUREMENT",
    "REFUSED_NO_RESOURCE",
    "REFUSED_PARAMETERS",
    "PoweredUpLease",
    "PoweredUpRegister",
]

POWERED_UP_MAXIMUM_S = 600.0  # The longest single request that is given
POWERED_UP_REQUESTS_MAXIMUM = 32  # How many may be held at once

# The reserved key of a Lease that the power manager holds for a client
# that cannot yet ask for itself.  It is not a topic, so nothing is ever
# published to it.  Nothing uses it since StoreForward learned to ask
BRIDGE_TOPIC = "-"

# The refusal vocabulary that the framework's own Lease proposes in its To
# Do, so that one spelling serves both
REFUSED_MAXIMUM = "maximum_seconds"
REFUSED_NO_RESOURCE = "no_resource"
REFUSED_NO_MEASUREMENT = "no_measurement"
REFUSED_PARAMETERS = "parameters"

# The units a constraint may be given in.  Seconds are not here: the
# lease_time is already the time condition
CONSTRAINT_WATT_HOURS = "watt_hours"
CONSTRAINTS = (CONSTRAINT_WATT_HOURS,)


@dataclass(frozen=True)
class LeaseConstraint:
    """A quantity of a finite resource that a Lease needs, in the unit that
    measures it.

    It is the second of a Lease's two conditions.  The first is the
    lease_time, which a client extends; this one the host must still be
    able to meet"""

    name: str
    value: float

    @staticmethod
    def of(name, value):
        """One constraint, or None for no constraint at all.

        Raises ValueError for a unit that is not declared, or a quantity
        that is not a positive number: a constraint that cannot be read is
        refused at the boundary, and never assumed away (P12)"""

        if name is None or name == "-":
            return None
        if name not in CONSTRAINTS:
            raise ValueError(f'unknown constraint "{name}": one of {list(CONSTRAINTS)}')
        try:
            quantity = float(value)
        except (TypeError, ValueError):
            raise ValueError(f'constraint "{name}" needs a number') from None
        if quantity <= 0:
            raise ValueError(f'constraint "{name}" must be more than zero')
        return LeaseConstraint(name, quantity)

    def __str__(self):
        return f"{self.name} {self.value:g}"


class PoweredUpLease(Lease):
    """One client's claim on staying powered up, for a time that was agreed.

    It extends the framework's Lease, as ECLease does, so the expiry runs
    on the event loop at the agreed time.  The "reason" is one token, for
    the operator, and the lease_uuid is the client's own topic"""

    def __init__(self, lease_time, topic, reason="-", constraint=None, lease_expired_handler=None):

        super().__init__(lease_time, topic, lease_expired_handler=lease_expired_handler)
        self.reason = str(reason or "-")
        self.constraint = constraint  # LeaseConstraint, or None

    @property
    def topic(self):
        """The client that holds this Lease, which is where it is told
        things"""

        return self.lease_uuid

    def asks(self, name):
        """How much of "name" this Lease needs, and zero when it needs none
        of it"""

        if self.constraint is None or self.constraint.name != name:
            return 0.0
        return self.constraint.value


class PoweredUpRegister:
    """Every live claim on the host, keyed by the client that made it.

    A client that asks again extends the Lease it holds, rather than taking
    a second one: the key is the client, so a client in a loop cannot fill
    the register with copies of itself.

    "expired_handler(topic)" is called on the event-loop thread at the
    moment a Lease ends, so the holder is told and the policy is asked
    again at once"""

    def __init__(
        self, maximum_seconds=POWERED_UP_MAXIMUM_S, maximum_requests=POWERED_UP_REQUESTS_MAXIMUM, expired_handler=None
    ):

        self.maximum_seconds = float(maximum_seconds)
        self.maximum_requests = int(maximum_requests)
        self.expired_handler = expired_handler
        self._leases = {}
        self.granted = 0  # For the metrics
        self.refused = 0
        self.expired = 0
        self.released = 0

    def request(self, topic, seconds, reason, constraint=None, available=None):
        """Take, extend or release one claim.

        Returns (outcome, detail).  The outcome is "granted" with the
        seconds, "released", or "refused" with the reason.  Zero seconds
        releases, because a client that has finished should say so rather
        than wait to expire.

        "constraint" is the second condition, as a LeaseConstraint or None.
        "available" says what the host can measure, as {unit: quantity}.  A
        unit that is absent from it cannot be checked, so a constraint in
        that unit is refused rather than granted"""

        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            self.refused += 1
            return "refused", REFUSED_PARAMETERS
        if seconds <= 0:
            if self.release(topic):
                self.released += 1
            return "released", "0"
        if seconds > self.maximum_seconds:
            self.refused += 1
            return "refused", f"{REFUSED_MAXIMUM} {self.maximum_seconds:.0f}"
        refusal = self._refuse_constraint(topic, constraint, available)
        if refusal is not None:
            self.refused += 1
            return "refused", refusal
        lease = self._leases.get(topic)
        if lease is not None:
            lease.reason = str(reason or "-")
            lease.constraint = constraint
            lease.extend(seconds)  # Its timer moves with it
            self.granted += 1
            return "granted", f"{seconds:.0f}"
        if len(self._leases) >= self.maximum_requests:
            self.refused += 1
            return "refused", f"{REFUSED_NO_RESOURCE} requests"
        self._leases[topic] = PoweredUpLease(
            seconds, topic, reason, constraint=constraint, lease_expired_handler=self._lease_expired
        )
        self.granted += 1
        return "granted", f"{seconds:.0f}"

    def _refuse_constraint(self, topic, constraint, available):
        """Why this constraint cannot be agreed, or None when it can.

        Three reasons.  The unit is not one that this host measures, so
        nothing could check the promise.  The quantity is more than there
        is.  Or it is more than there is once the Leases already held are
        counted, because one finite resource is shared"""

        if constraint is None:
            return None
        available = available or {}
        if constraint.name not in available:
            return f"{REFUSED_NO_MEASUREMENT} {constraint.name}"
        quantity = float(available[constraint.name])
        committed = sum(lease.asks(constraint.name) for key, lease in self._leases.items() if key != topic)
        if committed + constraint.value > quantity:
            left = max(0.0, quantity - committed)
            return f"{REFUSED_NO_RESOURCE} {constraint.name} {left:g}"
        return None

    def demand(self):
        """How much of each unit the live Leases ask for, in total"""

        totals = {}
        for lease in self._leases.values():
            if lease.constraint is not None:
                name = lease.constraint.name
                totals[name] = totals.get(name, 0.0) + lease.constraint.value
        return totals

    def satisfied(self, available=None):
        """Which Leases the host can still meet, and which it cannot.

        Returns (met, unmet) as tuples of topics.  First granted, first
        served: the quantity is spent in the order the Leases were taken,
        and a Lease that the remainder cannot cover is unmet.  A Lease with
        no constraint is always met, because its only condition is its time.

        A unit that "available" does not mention cannot be checked, so such
        a Lease is unmet: the same answer its request would have had"""

        available = {name: float(value) for name, value in (available or {}).items()}
        met, unmet = [], []
        for topic, lease in self._leases.items():
            constraint = lease.constraint
            if constraint is None:
                met.append(topic)
                continue
            left = available.get(constraint.name)
            if left is None or constraint.value > left:
                unmet.append(topic)
                continue
            available[constraint.name] = left - constraint.value
            met.append(topic)
        return tuple(met), tuple(unmet)

    def release(self, topic):
        """Drop one claim, and its timer with it.  True when there was one"""

        lease = self._leases.pop(topic, None)
        if lease is None:
            return False
        lease.terminate()
        return True

    def terminate(self):
        """Drop every claim.  A register that is not terminated leaves its
        timers in the event loop"""

        for topic in list(self._leases):
            self.release(topic)

    def held(self, available=None):
        """How many claims are live **and** able to be met.

        A Lease has two conditions.  Without "available" only the time is
        counted, which is every Lease that has not expired.  With it, a
        Lease whose constraint cannot be met is not counted: its time is
        current and it is not usable, so it is not a reason to keep the
        host up"""

        if available is None:
            return len(self._leases)
        return len(self.satisfied(available)[0])

    def topics(self):
        """The client topics that hold a claim, except the reserved one"""

        return tuple(topic for topic in self._leases if topic != BRIDGE_TOPIC)

    def reasons(self):
        """The reasons given, each one once, in the order they were made"""

        seen = []
        for lease in self._leases.values():
            if lease.reason not in seen:
                seen.append(lease.reason)
        return tuple(seen)

    def seconds(self):
        """The longest Lease time that is held, for the operator"""

        return max((lease.lease_time for lease in self._leases.values()), default=0.0)

    def as_share(self):
        """The shared-state items, so an operator sees who is holding the
        host up"""

        return {
            "powered_up.held": str(self.held()),
            "powered_up.reasons": "+".join(self.reasons()) or "-",
            "powered_up.seconds": f"{self.seconds():.0f}",
            "powered_up.maximum_s": f"{self.maximum_seconds:.0f}",
            "powered_up.demand": "+".join(f"{name}:{value:g}" for name, value in sorted(self.demand().items())) or "-",
        }

    def _lease_expired(self, topic):
        """The agreed time has passed.  The framework's Lease calls this on
        the event-loop thread, which is where the policy runs"""

        lease = self._leases.pop(topic, None)
        if lease is None:
            return
        lease.terminate()
        self.expired += 1
        if self.expired_handler:
            self.expired_handler(topic)


# --------------------------------------------------------------------------- #
