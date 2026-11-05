#!/usr/bin/env python3
#
# Aiko Services: a bridge, until a peer asks for up-time itself
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# **This module is a bridge, and it is meant to go.**
#
# The policy names no application (uptime.py, ADR-028 decision 13).  A
# client that needs the host asks for up-time and holds a Lease, and the
# policy counts claims.  Today's SegmentStoreForward Actor knows nothing
# about up-time, so the power manager watches its queue and holds a claim
# on its behalf.  When that Actor asks for itself, this module is deleted
# and nothing else changes.
#
# The SegmentStoreForward Actor publishes its queue already, as
# "queue.depth", "queue.oldest_s", "queue.bytes" and "link", so this module
# observes it and adds nothing of its own (P3: state observation is
# subscription).
#
# **It never counts files in a directory.**  The outbox belongs to another
# account, and a count is not the same as "in flight": a segment that is
# half sent is not waiting and is not done.  The Actor that owns the custody
# is the one that knows.
#
# "known" is the field that matters most.  A source that has not heard from
# the peer says so, and the bridge then holds no claim: an unknown queue is
# not a reason to keep a host up, because the client that would have asked
# is not there to ask.  A source that reported zero because it could not
# ask would be worse still.
#
# Three sources.  NoQueueSource is the default and always unknown, which is
# a host that forwards nothing.  StoreForwardQueueSource discovers the peer
# and leases a consumer of its shared state.  FakeQueueSource is scripted,
# for the tests and for a bench run with no peer.
#
# The discovery handler and the consumer both run off the event-loop
# thread, so they only write into a dictionary that the Actor reads (P11).
#
# To Do
# ~~~~~
# * Several peers on one host, when a Device forwards to more than one
#   server.  The policy wants the total, and "known" then means all of them

from dataclasses import dataclass, replace

import aiko_services as aiko

__all__ = [
    "FakeQueueSource", "NoQueueSource", "QueueState", "STORE_FORWARD_PROTOCOL",
    "StoreForwardQueueSource", "choose_queue_source",
]

STORE_FORWARD_PROTOCOL =  \
    f"{aiko.SERVICE_PROTOCOL_AIKO}/store_forward:0"

@dataclass(frozen=True)
class QueueState:
    """What waits to be transferred, as last heard.

    "known" is False until a peer has been heard from.  "busy" is True while
    anything waits, which is what the policy asks"""

    known: bool = False
    depth: int = 0
    oldest_s: float = 0.0
    bytes: int = 0
    link: str = "unknown"
    peer: str = "-"

    @property
    def busy(self):
        """Whether anything still waits to go"""

        return self.known and self.depth > 0

    def as_share(self):
        """The shared-state items that the power manager republishes, so
        that one screen shows the power and the work together"""

        return {
            "queue.known": "yes" if self.known else "no",
            "queue.depth": str(self.depth),
            "queue.oldest_s": f"{self.oldest_s:.0f}",
            "queue.link": self.link,
            "queue.peer": self.peer,
        }

class NoQueueSource:
    """No peer: the default.  The queue is always unknown, which keeps the
    power on and leaves the undocked time to bound it"""

    device = "none"

    def open(self):
        pass

    def state(self):
        return QueueState()

    def close(self):
        pass

class FakeQueueSource(NoQueueSource):
    """A queue that a test or a bench run sets by hand"""

    device = "fake"

    def __init__(self, state=None, **_):
        self._state = state or QueueState()

    def state(self):
        return self._state

    def set_state(self, **fields):
        """Change what the next state() reports"""

        self._state = replace(self._state, **fields)
        return self._state

class StoreForwardQueueSource(NoQueueSource):
    """The queue of a SegmentStoreForward Actor, by discovery and a lease.

    It finds every Service whose protocol is store_forward:0, leases a
    consumer of the first one's shared state, and reads the queue items from
    the cache that the consumer fills.  Nothing is asked for: the peer
    publishes, and this follows"""

    device = "store_forward"

    def __init__(self, name=None, protocol=STORE_FORWARD_PROTOCOL, **_):
        self.name = name
        self.protocol = protocol
        self._cache = {}
        self._discovery = None
        self._consumer = None
        self._peer = "-"

    def open(self):
        """Start watching for the peer.  Returns at once: the peer may not
        exist yet, and the queue stays unknown until it does"""

        self._discovery = aiko.ActorDiscovery(aiko.process)
        self._discovery.add_handler(self._service_change, self._filter())
        return self

    def state(self):
        """The queue, as last published by the peer.

        Unknown until a depth has arrived.  A peer that is present but has
        published nothing yet is still unknown, which is the honest answer"""

        queue = self._cache.get("queue")
        if not isinstance(queue, dict) or "depth" not in queue:
            return QueueState(peer=self._peer)
        return QueueState(
            known=True,
            depth=_integer(queue.get("depth")),
            oldest_s=_float(queue.get("oldest_s")),
            bytes=_integer(queue.get("bytes")),
            link=str(self._cache.get("link", "unknown")),
            peer=self._peer)

    def close(self):
        if self._consumer is not None:
            try:
                self._consumer.terminate()
            except Exception:                            # noqa: BLE001
                pass
        self._consumer = None
        self._discovery = None
        self._cache = {}

    def _filter(self):
        return aiko.ServiceFilter(
            "*", self.name or "*", self.protocol, "*", "*", "*")

    def _service_change(self, command, service):
        """Runs on the services cache thread, so it only leases and writes
        into the cache dictionary.  It never touches Actor state (P11)"""

        if command == "remove":
            if str(service[0]) == self._peer:
                self._cache = {}
                self._peer = "-"
            return
        if command != "add" or self._consumer is not None:
            return
        topic_path = str(service[0])
        self._peer = topic_path
        self._consumer = aiko.compose_instance(
            aiko.ECConsumerImpl, aiko.ec_consumer_args(
                aiko.process, 0, self._cache, f"{topic_path}/control"))

def _integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def choose_queue_source(source="none", **parameters):
    """The queue source for "source": "store_forward", "fake" or "none".

    "none" is the default, because a host that forwards nothing must not
    wait for a peer that will never answer"""

    choices = {
        "store_forward": StoreForwardQueueSource,
        "fake": FakeQueueSource,
        "none": NoQueueSource,
    }
    if source not in choices:
        raise ValueError(
            f'unknown queue source "{source}": one of {sorted(choices)}')
    if source == "none":
        return NoQueueSource()
    return choices[source](**parameters)

# --------------------------------------------------------------------------- #
