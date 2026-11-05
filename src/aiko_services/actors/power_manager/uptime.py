#!/usr/bin/env python3
#
# Aiko Services: who still needs this host
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The policy asks one question of everybody, and names no application
# (ADR-028 decision 13).
#
#     Does anything still need this host?
#
# A client answers by holding a Lease.  It asks for a number of seconds,
# extends the Lease before it expires, and releases it when its work is
# done.  Thus a Pipeline that records, an Agent that thinks, a store and
# forward of files, and Aiko Services itself all make the same claim in the
# same way, and the power manager knows what none of them are.
#
# **The unknown case disappears, and that is the point.**  A client that
# cannot be reached cannot hold a Lease, and a Lease that nothing extends
# expires.  So "nobody answered" and "nobody needs me" become one
# measurable thing, rather than a guess that the power manager made on
# behalf of an Actor it could not see.
#
# Expiry is checked when the power manager samples, and not on a timer of
# its own.  The framework's Lease exists for a holder that must act the
# moment a Lease ends, as ECProducer must.  This register is consulted only
# when a reading is taken, so one timer for each client would do no work
# between samples.  The clock is an argument, so a test walks time.
#
# A Lease asks, and it never commands.  It cannot outlive the bound on
# undocked time, the battery voltage floor or the battery pack temperature
# gate: those stop a host whatever is held here.
#
# This module is a value type and a plain register: ADR-022 "value or data
# type" exemption from Interface composition.
#
# To Do
# ~~~~~
# * A client that asks for more than the battery can give is refused with
#   the time that is left, once phase 6 can estimate it.  Today the
#   refusal carries the configured maximum

from dataclasses import dataclass

__all__ = [
    "BRIDGE_TOPIC", "REFUSED_NO_RESOURCE", "REFUSED_MAXIMUM",
    "REFUSED_PARAMETERS", "UPTIME_MAXIMUM_S", "UPTIME_REQUESTS_MAXIMUM",
    "UptimeLease", "UptimeRegister",
]

UPTIME_MAXIMUM_S = 600.0           # The longest single request that is given
UPTIME_REQUESTS_MAXIMUM = 32       # How many may be held at once

# The reserved key of a request that the power manager holds for a client
# that cannot yet ask for itself (queue.py).  It is not a topic, so nothing
# is ever published to it
BRIDGE_TOPIC = "-"

# The refusal vocabulary that the framework's own Lease proposes in its To
# Do, so that one spelling serves both
REFUSED_MAXIMUM = "maximum_seconds"
REFUSED_NO_RESOURCE = "no_resource"
REFUSED_PARAMETERS = "parameters"

@dataclass(frozen=True)
class UptimeLease:
    """One client's claim on the host, until "expires_at" """

    topic: str
    seconds: float
    reason: str
    expires_at: float              # Monotonic

    def left(self, now):
        """Seconds until this expires, and never below zero"""

        return max(0.0, self.expires_at - now)

class UptimeRegister:
    """Every live claim on the host, keyed by the client that made it.

    A client that asks again extends what it holds, rather than adding a
    second claim: the key is the client, so a client in a loop cannot fill
    the register with copies of itself"""

    def __init__(self, maximum_seconds=UPTIME_MAXIMUM_S,
        maximum_requests=UPTIME_REQUESTS_MAXIMUM):

        self.maximum_seconds = float(maximum_seconds)
        self.maximum_requests = int(maximum_requests)
        self._leases = {}
        self.granted = 0           # For the metrics
        self.refused = 0
        self.expired = 0
        self.released = 0

    def request(self, topic, seconds, reason, now):
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
            self.released += 1 if self.release(topic) else 0
            return "released", "0"
        if seconds > self.maximum_seconds:
            self.refused += 1
            return "refused", f"{REFUSED_MAXIMUM} {self.maximum_seconds:.0f}"
        if topic not in self._leases  \
            and len(self._leases) >= self.maximum_requests:
            self.refused += 1
            return "refused", f"{REFUSED_NO_RESOURCE} requests"
        self._leases[topic] = UptimeLease(
            topic=topic, seconds=seconds, reason=str(reason or "-"),
            expires_at=now + seconds)
        self.granted += 1
        return "granted", f"{seconds:.0f}"

    def release(self, topic):
        """Drop one claim.  True when there was one to drop"""

        return self._leases.pop(topic, None) is not None

    def expire(self, now):
        """Drop every claim that has run out, and return their topics.

        The caller tells the clients, so an expiry is never silent"""

        gone = [topic for topic, lease in self._leases.items()
            if lease.expires_at <= now]
        for topic in gone:
            del self._leases[topic]
        self.expired += len(gone)
        return gone

    def held(self, now=None):
        """How many claims are live.  With "now", the expired are not
        counted even before expire() has dropped them"""

        return len(self.live(now))

    def live(self, now=None):
        """Every live claim, newest expiry last"""

        leases = sorted(self._leases.values(), key=lambda one: one.expires_at)
        if now is None:
            return tuple(leases)
        return tuple(one for one in leases if one.expires_at > now)

    def topics(self, now=None):
        """The client topics that hold a claim, except the bridge's"""

        return tuple(one.topic for one in self.live(now)
            if one.topic != BRIDGE_TOPIC)

    def reasons(self, now=None):
        """The reasons given, each one once, in order"""

        seen = []
        for one in self.live(now):
            if one.reason not in seen:
                seen.append(one.reason)
        return tuple(seen)

    def as_share(self, now=None):
        """The shared-state items, so an operator sees who is holding the
        host up and for how much longer"""

        leases = self.live(now)
        longest = max((one.left(now) for one in leases), default=0.0)  \
            if now is not None else 0.0
        return {
            "uptime.held": str(len(leases)),
            "uptime.reasons": "+".join(self.reasons(now)) or "-",
            "uptime.longest_s": f"{longest:.0f}",
            "uptime.maximum_s": f"{self.maximum_seconds:.0f}",
        }

# --------------------------------------------------------------------------- #
