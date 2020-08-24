# To Do
# ~~~~~
# - Fix logging
# - Allow default MQTT_HOST and MQTT_PORT to be overridden by CLI parameters
# - Decouple MQTT message handling thread by using a queue
# - Move global variables into thread-local context
# - Implement reconnect on disconnection from MQTT server
#   - Maybe raise an exception if reconnection fails, rather than sys.exit(-1)
# - Implement discovery and manual setting of AIKO_MQTT_HOST, etc
#   - Rediscover on disconnection
# - Implement destructor ?

import time
from typing import Any
import paho.mqtt.client as mqtt

from .message import Message

__all__ = ["MQTT"]

# MQTT_HOST = "test.mosquitto.org"
# MQTT_HOST = "localhost"
MQTT_HOST = "lounge.local"
MQTT_PORT = 1883

_CONNECTED = False
_PUBLISHED = False
_TOPICS_SUBSCRIBE: Any = None

# pylint: disable=unused-argument
def on_connect(
    mqtt_client: Any, user_data: Any, dict_flags: Any, result_code: Any
) -> None:
    global _CONNECTED, _TOPICS_SUBSCRIBE  # pylint: disable=global-statement
    _CONNECTED = True
    if _TOPICS_SUBSCRIBE:
        topics = _TOPICS_SUBSCRIBE
        if type(topics) is dict:
            topics = topics.keys()
        for topic in topics:
            mqtt_client.subscribe(topic)
#           self.logger.info(f"Subscribed to {MQTT_HOST}: {topic}")


def on_message(mqtt_client: Any, userdata: Any, message: Any) -> None:
    print(f"on_message: {message.topic}: {message.payload}")


# pylint: disable=unused-argument
def on_publish(mqtt_client: Any, userdata: Any, result: Any) -> None:
    global _PUBLISHED  # pylint: disable=global-statement
    _PUBLISHED = True


class MQTT(Message):
    def __init__(
        self, message_handler: Any = None, topics_subscribe: Any = None, lwt_topic: str = None, lwt_retain: bool = False
    ) -> None:
        global _TOPICS_SUBSCRIBE  # pylint: disable=global-statement
        _TOPICS_SUBSCRIBE = topics_subscribe
        if not message_handler:
            message_handler = on_message
        self.mqtt_client = mqtt.Client()
        self.connected = True

        try:
            self.mqtt_client.on_connect = on_connect
            self.mqtt_client.on_message = message_handler
            self.mqtt_client.on_publish = on_publish
            if lwt_topic:
                self.mqtt_client.will_set(lwt_topic, payload="(nil)", retain=lwt_retain)
            self.mqtt_client.connect(host=MQTT_HOST, port=MQTT_PORT, keepalive=60)
        except ConnectionRefusedError:
            raise SystemError(f"Error: Couldn't connect to MQTT server {MQTT_HOST}")

        self.loop_start()

    def loop_start(self: Any) -> None:
        self.mqtt_client.loop_start()

    def publish(self: Any, topic: Any, payload: Any, wait: bool = False) -> None:
        global _PUBLISHED  # pylint: disable=global-statement
        _PUBLISHED = False
        self.mqtt_client.publish(topic, payload)
        if wait:
            self.wait_published()

    def wait_published(self) -> None:
        global _PUBLISHED  # pylint: disable=global-statement
        while not _PUBLISHED:
            time.sleep(0.001)


def on_message_1(mqtt_client: Any, userdata: Any, message: Any) -> None:
    payload_in = message.payload.decode("utf-8")
    print("on_message_1()", message.topic, str(payload_in))


def on_message_2(mqtt_client: Any, userdata: Any, message: Any) -> None:
    payload_in = message.payload.decode("utf-8")
    print("on_message_2()", message.topic, str(payload_in))


def example() -> None:
    print("Running MQTT example")
    #   message = Message(on_message_1, {"test1", "test2"})
    Message(None, {"test1": on_message_1, "test2": on_message_2})
    while True:
        time.sleep(0.1)


# example()
