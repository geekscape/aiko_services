#!/usr/bin/env python3
#
# Aiko Services: Recorder
# ~~~~~~~~~~~~~~~~~~~~~~~
# Records the log records of other Services, and republishes them as
# shared state, so that the Dashboard and any other client reads the
# recent log of a Service it did not watch at the time.
#
# One ring buffer for each topic, held in an LRU cache of topics.  A busy
# system has more log topics than a Recorder should hold, so the least
# recently used topic is evicted, and its shared state goes with it.
#
# Usage
# ~~~~~
# aiko_recorder [--lru_cache_size N] [--ring_buffer_size N] [TOPIC_FILTER]
#
# Where TOPIC_FILTER defaults to "<namespace>/+/+/+/log"
#
#   mosquitto_sub -t '#' -v        # watch everything, in another terminal
#   aiko_registrar &
#   aiko_recorder &
#   aiko_dashboard                 # select the Recorder, then press S
#
# Both sizes are shared variables as well as options, so a Dashboard
# changes them while the Recorder runs.  A smaller LRU cache evicts at
# once, and a smaller ring buffer keeps the newest records.  Small sizes
# are how a person sees the edge cases sooner ...
#
#   aiko_recorder -l 2 -r 2        # two topics, two records each
#
# An Actor, so a client adds a filter while it runs ...
#
#   mosquitto_pub -t <topic_path>/in -m "(record aiko/+/+/+/out)"
#   mosquitto_pub -t <topic_path>/in -m "(record_stop aiko/+/+/+/out)"
#
# Deny by default (P12, ADR-023): record, record_stop, set_log_level and
# stop, and nothing else.
#
# To Do
# ~~~~~
# - Replay, which s_02_InterfaceComposition says lands here
# - A recording identity of its own, instead of the filter.  s_02 asks for
#   "stop(recording_id)", which cannot be written: "stop" is the
#   framework's control verb and takes no argument
# - Publish the whole ring buffer, not only the newest record.  Measured:
#   a depth of 128 is about 8 KB for each record published, for each
#   attached consumer, so this waits on a decision about coalescing
# - Why doesn't the Python MQTT client subscribe("+/+/+/+/log") work ?

import click
from abc import abstractmethod
from collections import deque

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = [
    "LRU_CACHE_SIZE", "PROTOCOL", "RING_BUFFER_SIZE", "Recorder",
    "RecorderImpl", "SERVICE_TYPE",
]

_VERSION = 0

SERVICE_TYPE = "recorder"
PROTOCOL = f"{SERVICE_PROTOCOL_AIKO}/{SERVICE_TYPE}:{_VERSION}"

LRU_CACHE_SIZE = 128     # topics held at once
RING_BUFFER_SIZE = 128   # log records held for each topic

# The functions a client may call (P12, ADR-023).  "recorder_handler" is
# the subscription callback: it takes the transport's (aiko, topic,
# payload) and a subscription delivers it, so no client calls it and it is
# taken off the allow list
FUNCTIONS = None    # composed below, once Recorder is declared

# The shared variables a client may change, and the bounds on each
SIZES = {
    "lru_cache_size": (1, 4096),
    "ring_buffer_size": (1, 4096),
}

# --------------------------------------------------------------------------- #

class Recorder(Actor):
    """
    Ring-buffers the log topics that match each filter, and republishes
    them as shared state for the Dashboard (concepts/recorder.md).

    An Actor since 2026-10-23, as s_02_InterfaceComposition says it should
    be: the spike refined Service, which is why a filter could only be set
    at construction.  record() adds one while it runs
    """
    Interface.default("Recorder", "aiko_services.main.recorder.RecorderImpl")

    @abstractmethod
    def record(self, topic_path_filter):
        """Record the log topics that match this filter as well.  The
        filter is the identity of a recording, so recording one twice
        changes nothing.  Projection: command"""

    @abstractmethod
    def record_stop(self, topic_path_filter):
        """Stop recording this filter, and forget what it recorded.

        Named record_stop, and not stop(recording_id) as
        s_02_InterfaceComposition says, because "stop" is the framework's
        control verb and takes no argument.  ADR-025 decision 1 resolved
        the same clash for the Display Actor's "exit".  Projection:
        command"""

    @abstractmethod
    def recorder_handler(self, aiko, topic, payload_in):
        """Record one message into the topic's ring buffer and publish it
        via the ECProducer ("lru_cache.<topic>" share key).  Invoked by
        subscription to a filter, never by a client.  Projection:
        command"""

FUNCTIONS = interface_functions(Recorder) - {"recorder_handler"}

class RecorderImpl(Recorder):
    def __init__(self, context, topic_path_filter,
        lru_cache_size=LRU_CACHE_SIZE, ring_buffer_size=RING_BUFFER_SIZE):

        context.call_init(
            self, "FunctionGate", context, functions=FUNCTIONS)
        context.call_init(self, "Actor", context)

        self.ring_buffer_size = int(ring_buffer_size)
        self.lru_cache = LRUCache(int(lru_cache_size))
    # The counters are held here and published from here, never read back
    # from the share: a share item is writable from the "control" topic,
    # so a count taken from the share is a count a client can set, and it
    # is a string once they have
        self._records = 0
        self._evicted = 0

        self._filters = []
        self.share.update({
            "source_file": f"v{_VERSION}⇒ {__file__}",
        # One item for each recorded topic, holding its newest log record
            "lru_cache": {},
            "lru_cache_size": self.lru_cache.size,
            "ring_buffer_size": self.ring_buffer_size,
            "filters": [],
            "metrics": {
                "records": 0,     # log records recorded
                "topics": 0,      # topics held, which is the LRU cache length
                "evicted": 0,     # topics evicted, each one losing its records
            },
        })
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self.record(topic_path_filter)

    def _ec_producer_change_handler(self, command, item_name, item_value):
    # "log_level" is the Actor's, which handles it through self.logger.
    # The Recorder had its own handler for it, and its own module logger,
    # when it refined Service
        if item_name in SIZES:
            self._set_size(item_name, item_value)

    def _set_size(self, item_name, item_value):
        """Apply a size a client changed, or publish the one still in
        force, so that a bad Dashboard edit converges back"""

        minimum, maximum = SIZES[item_name]
        size = parse_int(item_value, 0)
        in_force = (self.ring_buffer_size
            if item_name == "ring_buffer_size" else self.lru_cache.size)
        if size == in_force:
            return                              # our own publication
        if not minimum <= size <= maximum:
            self.logger.warning(f"{item_name} must be {minimum} to {maximum}, "
                            f"not {item_value}: unchanged")
            self.ec_producer.update(item_name, in_force)
            return
        if item_name == "lru_cache_size":
            for topic, _ in self.lru_cache.resize(size):
                self._forget(topic)
        else:
            self.ring_buffer_size = size
            for topic in list(self.lru_cache):
                records = self.lru_cache.get(topic)
                self.lru_cache.put(topic, deque(records, maxlen=size))
        self.ec_producer.update(item_name, size)
        self._publish_metrics()
        self.logger.info(f"{item_name}: {size}")

    def record(self, topic_path_filter):
        """Record the topics that match this filter as well"""

        if topic_path_filter in self._filters:
            return                              # already recording it
        self._filters.append(topic_path_filter)
        self.add_message_handler(self.recorder_handler, topic_path_filter)
        self.ec_producer.update("filters", list(self._filters))
        self.logger.info(f"Record: {topic_path_filter}")

    def record_stop(self, topic_path_filter):
        """Stop recording this filter, and forget what it recorded"""

        if topic_path_filter not in self._filters:
            self.logger.warning(f"Not recording: {topic_path_filter}")
            return
        self._filters.remove(topic_path_filter)
        self.remove_message_handler(
            self.recorder_handler, topic_path_filter)
        self.ec_producer.update("filters", list(self._filters))
        self.logger.info(f"Record stop: {topic_path_filter}")

    def _forget(self, topic):
        """Remove an evicted topic's shared state, or a consumer keeps its
        last log record for ever"""

        self.ec_producer.remove(f"lru_cache.{topic}")
        self._evicted += 1
        self.ec_producer.update("metrics.evicted", self._evicted)

    def _publish_metrics(self):
        self.ec_producer.update("metrics.topics", len(self.lru_cache))

    def recorder_handler(self, aiko, topic, payload_in):
        ring_buffer = self.lru_cache.get(topic)
        if ring_buffer is None:
            ring_buffer = deque(maxlen=self.ring_buffer_size)
            evicted = self.lru_cache.put(topic, ring_buffer)
            if evicted:
                self._forget(evicted[0])
            self._publish_metrics()

    # The record is stored and published as it arrived.  It used to have
    # its parentheses turned into braces, and a replace() that was meant
    # to remove a non-breaking space but had an ordinary space on both
    # sides, so it did nothing at all.  Neither is necessary: generate()
    # gives a value with a space, a parenthesis, a quote, a newline or a
    # non-breaking space a length prefix, and parse() returns it exactly.
    # Measured over ten awkward records, and the tests hold that
        ring_buffer.append(payload_in)
        self.ec_producer.update(f"lru_cache.{topic}", payload_in)
        self._records += 1
        self.ec_producer.update("metrics.records", self._records)

    def get_records(self, topic):
        """The ring buffer of one topic, oldest first.  A local read: the
        shared state carries only the newest record of each topic, until
        the To Do above is settled"""

        ring_buffer = self.lru_cache.get(topic)
        return list(ring_buffer) if ring_buffer else []

# --------------------------------------------------------------------------- #

@click.command("main", help="Recorder Service")
@click.option("--lru_cache_size", "-l", type=click.INT,
    default=LRU_CACHE_SIZE, help="Topics held at once")
@click.option("--ring_buffer_size", "-r", type=click.INT,
    default=RING_BUFFER_SIZE, help="Log records held for each topic")
@click.argument("topic_path_filter", nargs=1, required=False,
    default=f"{get_namespace()}/+/+/+/log")

def main(lru_cache_size, ring_buffer_size, topic_path_filter):
    tags = ["ec=true"]  # TODO: Add ECProducer tag before add to Registrar
    init_args = actor_args(SERVICE_TYPE, None, None, PROTOCOL, tags)
    init_args["topic_path_filter"] = topic_path_filter
    init_args["lru_cache_size"] = lru_cache_size
    init_args["ring_buffer_size"] = ring_buffer_size
    recorder = compose_instance(RecorderImpl, init_args)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
