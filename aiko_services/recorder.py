#!/usr/bin/env python3
#
# Aiko Service: Recorder
# ~~~~~~~~~~~~~~~~~~~~~~
#
# Usage
# ~~~~~
# mosquitto_sub -t '#' -v
# REGISTRAR=0 LOG_LEVEL=DEBUG registrar &
# RECORDER=0 ./recorder.py [topic_path] &
#
# Where "topic_path" default: "namespace/+/+/log"
#
# To Do
# ~~~~~
# - Improve CLI to record multiple different topic paths
# - Recorder remove Service history (duplicate code in Aiko Dashboard)
#   - Aiko Dashboard should check Recorder for Service history
#   - Keep separate last "n" historical Services LRU Cache and Ring Buffers
# - On-the-fly configuration ...
#   - _HISTORY_LRU_CACHE_SIZE, _RING_BUFFER_SIZE, _TOPIC_LRU_CACHE_SIZE
#   - topic_path causes unsubscribe and resubscribe to correct topic
# - Keep statistics for ...
#   - History and Topic LRU cache length
#   - Total messages received / sent, messages received / sent per second
# - Why doesn't Python MQTT client subscribe("+/+/+/log") work ?

import click
from collections import deque

from aiko_services import *
from aiko_services.utilities import *

__all__ = []

PROTOCOL = f"{AIKO_PROTOCOL_PREFIX}/recorder:0"

_LOGGER = aiko.logger(__name__)

_HISTORY_LRU_CACHE_SIZE = 2  # 32
_RING_BUFFER_SIZE = 2  # 128
_TOPIC_LRU_CACHE_SIZE = 2  # 128

# --------------------------------------------------------------------------- #

class RecorderService:
    def __init__(self, topic_path):
# TODO: Add LRUCache popitem() handler to remove oldest ring buffer ?
#       And send ECProducer.remove(topic) to update the ECConsumer
        self.lru_cache = LRUCache(_TOPIC_LRU_CACHE_SIZE)
        self.state = {
            "history": {},
            "history_lru_cache_size": _HISTORY_LRU_CACHE_SIZE,
            "lifecycle":  "initialize",
            "log_level":  "info",
            "ring_buffer_size": _RING_BUFFER_SIZE,
            "topic_lru_cache_size": _TOPIC_LRU_CACHE_SIZE,
            "topic_path": topic_path
        }
        self.ec_producer = ECProducer(self.state)

        aiko.set_protocol(PROTOCOL)  # TODO: Move into service.py
        aiko.add_message_handler(self.recorder_handler, topic_path)

    def recorder_handler(self, _aiko, topic, payload_in):
        if topic in self.lru_cache:
            ring_buffer = self.lru_cache.get(topic)
        else:
            ring_buffer = deque(maxlen=_RING_BUFFER_SIZE)
# TODO: If LRUCache popitem(), then manually remove oldest ring buffer ?
#       And send ECProducer.remove(topic) to update the ECConsumer
            self.lru_cache.put(topic, ring_buffer)

# TODO: "utilities/parser.py": generate() and parse() need to handle
#       log messages with special characters ... use Canonical S-Expressions ?

        log_record = payload_in.replace(' ', '_')
        log_record = log_record.replace('(', '{')
        log_record = log_record.replace(')', '}')
        ring_buffer.append(log_record)

# TODO: "share.py:ECConsumer._consumer_handler()" needs to handle list and dict
#       Appears that the "(add ...)" fails, but "(update ...)" works ?
#       Dashboard being updated with dict of entries that are lists ... works !

# TODO: "dashboard.py:DashboardFrame._update()" doesn't show subsequent updates
#       to RecorderService.ECProducer "history.topic" log record lists

        history_topic_log = []
        for entry in ring_buffer:
            history_topic_log.append(entry)
        history_topic_key = f"history.{topic.replace('.', '_')}"
        self.ec_producer.update(history_topic_key, history_topic_log)

# --------------------------------------------------------------------------- #

@click.command("main", help="Recorder Service")
@click.argument("topic_path", nargs=1, required=False,
    default=f"{get_namespace()}/+/+/log")
def main(topic_path):
    RecorderService(topic_path)
    aiko.process()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
