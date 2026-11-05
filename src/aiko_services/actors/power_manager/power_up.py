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
# The names follow one rule, because "power up" can be read two ways.  A
# noun for the thing that is held says "powered up", as PoweredUpLease and
# PoweredUpRegister do: what a client holds is a claim on *being* powered
# up.  The verb and its namespace say "power up", as "(request_power_up
# ...)" and "power_up.held" do: what a client *does* is ask to be powered
# up.  So neither reading has to carry both meanings.
#
# PoweredUpLease extends the framework's Lease, as ECLease does, so an
# expiry acts at the time that was agreed and not at the next convenient
# moment.
# Prompt action at the agreed timeout is a large part of what a Lease is
# for: the last Lease to expire is the event that lets a host stop, and a
# host that waited for its next sample would be holding a battery pack up
# for no one.
#
# A Lease asks, and it never commands.  It cannot outlive the bound on
# undocked time, the battery voltage floor or the battery pack temperature
# gate: those stop a host whatever is held here.
#
# To Do
# ~~~~~
# * Denominate a request in energy and not only in seconds.  The battery
#   pack is finite in watt-hours, so a request that the remaining charge
#   cannot cover should be refused with what is left.  That needs the
#   measurement of phase 6; until then the refusal carries the configured
#   maximum time

from aiko_services.main.lease import Lease

__all__ = [
    "BRIDGE_TOPIC", "POWER_UP_MAXIMUM_S", "POWER_UP_REQUESTS_MAXIMUM",
    "REFUSED_MAXIMUM", "REFUSED_NO_RESOURCE", "REFUSED_PARAMETERS",
    "PoweredUpLease", "PoweredUpRegister",
]

POWER_UP_MAXIMUM_S = 600.0         # The longest single request that is given
POWER_UP_REQUESTS_MAXIMUM = 32     # How many may be held at once

# The reserved key of a Lease that the power manager holds for a client
# that cannot yet ask for itself.  It is not a topic, so nothing is ever
# published to it.  Nothing uses it since StoreForward learned to ask
BRIDGE_TOPIC = "-"

# The refusal vocabulary that the framework's own Lease proposes in its To
# Do, so that one spelling serves both
REFUSED_MAXIMUM = "maximum_seconds"
REFUSED_NO_RESOURCE = "no_resource"
REFUSED_PARAMETERS = "parameters"

class PoweredUpLease(Lease):
    """One client's claim on staying powered up, for a time that was agreed.

    It extends the framework's Lease, as ECLease does, so the expiry runs
    on the event loop at the agreed time.  The "reason" is one token, for
    the operator, and the lease_uuid is the client's own topic"""

    def __init__(self, lease_time, topic, reason="-",
        lease_expired_handler=None):

        super().__init__(lease_time, topic,
            lease_expired_handler=lease_expired_handler)
        self.reason = str(reason or "-")

    @property
    def topic(self):
        """The client that holds this Lease, which is where it is told
        things"""

        return self.lease_uuid

class PoweredUpRegister:
    """Every live claim on the host, keyed by the client that made it.

    A client that asks again extends the Lease it holds, rather than taking
    a second one: the key is the client, so a client in a loop cannot fill
    the register with copies of itself.

    "expired_handler(topic)" is called on the event-loop thread at the
    moment a Lease ends, so the holder is told and the policy is asked
    again at once"""

    def __init__(self, maximum_seconds=POWER_UP_MAXIMUM_S,
        maximum_requests=POWER_UP_REQUESTS_MAXIMUM, expired_handler=None):

        self.maximum_seconds = float(maximum_seconds)
        self.maximum_requests = int(maximum_requests)
        self.expired_handler = expired_handler
        self._leases = {}
        self.granted = 0           # For the metrics
        self.refused = 0
        self.expired = 0
        self.released = 0

    def request(self, topic, seconds, reason):
        """Take, extend or release one claim.

        Returns (outcome, detail).  The outcome is "granted" with the
        seconds, "released", or "refused" with the reason.  Zero seconds
        releases, because a client that has finished should say so rather
        than wait to expire"""

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
        lease = self._leases.get(topic)
        if lease is not None:
            lease.reason = str(reason or "-")
            lease.extend(seconds)              # Its timer moves with it
            self.granted += 1
            return "granted", f"{seconds:.0f}"
        if len(self._leases) >= self.maximum_requests:
            self.refused += 1
            return "refused", f"{REFUSED_NO_RESOURCE} requests"
        self._leases[topic] = PoweredUpLease(seconds, topic, reason,
            lease_expired_handler=self._lease_expired)
        self.granted += 1
        return "granted", f"{seconds:.0f}"

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

    def held(self):
        """How many claims are live"""

        return len(self._leases)

    def topics(self):
        """The client topics that hold a claim, except the reserved one"""

        return tuple(topic for topic in self._leases
            if topic != BRIDGE_TOPIC)

    def reasons(self):
        """The reasons given, each one once, in the order they were made"""

        seen = []
        for lease in self._leases.values():
            if lease.reason not in seen:
                seen.append(lease.reason)
        return tuple(seen)

    def seconds(self):
        """The longest Lease time that is held, for the operator"""

        return max((lease.lease_time for lease in self._leases.values()),
            default=0.0)

    def as_share(self):
        """The shared-state items, so an operator sees who is holding the
        host up"""

        return {
            "power_up.held": str(self.held()),
            "power_up.reasons": "+".join(self.reasons()) or "-",
            "power_up.seconds": f"{self.seconds():.0f}",
            "power_up.maximum_s": f"{self.maximum_seconds:.0f}",
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
