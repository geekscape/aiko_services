#!/usr/bin/env python3
#
# Aiko Service: Recorder
# ~~~~~~~~~~~~~~~~~~~~~~
#
# Usage
# ~~~~~
# mosquitto_sub -t '#' -v
# REGISTRAR=0 registrar &
# RECORDER=0 ./recorder.py [topic_path_filter] &
#
# Where "topic_path_filter" default: "aiko/+/+/+/log"
#
# To Do
# ~~~~~
# - Improve CLI to record multiple different topic paths
# - On-the-fly configuration parameter updates ...
#   - _RING_BUFFER_SIZE, _TOPIC_LRU_CACHE_SIZE
#   - topic_path_filter causes unsubscribe and resubscribe to correct topic
# - Keep statistics for ...
#   - Topic LRU cache length
#   - Total messages received / sent, messages received / sent per second
# - Why doesn't Python MQTT client subscribe("+/+/+/+/log") work ?

import click
from collections import deque

from aiko_services.main import *
from aiko_services.main.utilities import *

_VERSION = 0

SERVICE_TYPE = "recorder"
PROTOCOL = f"{SERVICE_PROTOCOL_AIKO}/{SERVICE_TYPE}:{_VERSION}"

_LOGGER = aiko.logger(__name__)

_LRU_CACHE_SIZE = 2    # 128
_RING_BUFFER_SIZE = 2  # 128

# --------------------------------------------------------------------------- #

class Recorder(Service):
    Interface.default("Recorder", "aiko_services.main.recorder.RecorderImpl")

#   @abstractmethod
#   def METHOD_NAME(self):
#       pass

class RecorderImpl(Recorder):
    def __init__(self, context, topic_path_filter):
        context.get_implementation("Service").__init__(self, context)

# TODO: Add LRUCache popitem() handler to remove oldest ring buffer ?
#       And send ECProducer.remove(topic) to update the ECConsumer
        self.lru_cache = LRUCache(_LRU_CACHE_SIZE)

        self.share = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒ {__file__}",
            "lru_cache": {},                                             # HACK
            "lru_cache_size": _LRU_CACHE_SIZE,
            "ring_buffer_size": _RING_BUFFER_SIZE,
            "topic_path_filter": topic_path_filter
        }
        self.ec_producer = ECProducer(self, self.share)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self.add_message_handler(self.recorder_handler, topic_path_filter)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def recorder_handler(self, aiko, topic, payload_in):
        if topic in self.lru_cache:
            ring_buffer = self.lru_cache.get(topic)
        else:
            ring_buffer = deque(maxlen=_RING_BUFFER_SIZE)
# TODO: If LRUCache popitem(), then manually remove oldest ring buffer ?
#       And send ECProducer.remove(topic) to update the ECConsumer
            self.lru_cache.put(topic, ring_buffer)

# TODO: "utilities/parser.py": generate() and parse() need to handle
#       log messages with special characters ... use Canonical S-Expressions ?

        log_record = payload_in.replace(" ", " ")  # Unicode U00A0 (NBSP)
        log_record = log_record.replace("(", "{")
        log_record = log_record.replace(")", "}")
        ring_buffer.append(log_record)
        self.ec_producer.update(f"lru_cache.{topic}", log_record)        # HACK

# TODO: "share.py:ECConsumer._consumer_handler()" needs to handle list and dict
#       Appears that the "(add ...)" fails, but "(update ...)" works ?
#       Dashboard being updated with dict of entries that are lists ... works !

# --------------------------------------------------------------------------- #

@click.command("main", help="Recorder Service")
@click.argument("topic_path_filter", nargs=1, required=False,
    default=f"{get_namespace()}/+/+/+/log")

def main(topic_path_filter):
    tags = ["ec=true"]  # TODO: Add ECProducer tag before add to Registrar
    init_args = service_args(SERVICE_TYPE, None, None, PROTOCOL, tags)
    init_args["topic_path_filter"] = topic_path_filter
    recorder = compose_instance(RecorderImpl, init_args)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
