# To Do
# ~~~~~
# - Implement message to change logging level !
# - Allow default MQTT_HOST and MQTT_PORT to be overridden by CLI parameters
# - Decouple MQTT message handling thread by using a queue
# - Move global variables into thread-local context
# - Implement reconnect on disconnection from MQTT server
#   - Maybe raise an exception if reconnection fails, rather than sys.exit(-1)
# - Implement discovery and manual setting of AIKO_MQTT_HOST, etc
#   - Rediscover on disconnection
# - Implement destructor ?

from logging import DEBUG
import paho.mqtt.client as mqtt
import time
from typing import Any

from aiko_services.utilities import get_logger
from .message import Message

__all__ = ["MQTT"]

# MQTT_HOST = "test.mosquitto.org"
# MQTT_HOST = "localhost"
MQTT_HOST = "lounge.local"
MQTT_PORT = 1883

_CONNECTED = False
_LOGGER = get_logger(__name__)
_PUBLISHED = True
_TOPICS_SUBSCRIBE: Any = None

# pylint: disable=unused-argument
def on_connect(
    mqtt_client: Any, user_data: Any, dict_flags: Any, result_code: Any
) -> None:
    global _CONNECTED, _TOPICS_SUBSCRIBE  # pylint: disable=global-statement
    _CONNECTED = True
    _LOGGER.debug(f"connected to {MQTT_HOST}")
    if _TOPICS_SUBSCRIBE:
        topics = _TOPICS_SUBSCRIBE
        if type(topics) is dict:
            topics = topics.keys()
        for topic in topics:
            mqtt_client.subscribe(topic)
            _LOGGER.debug(f"subscribed to {MQTT_HOST}: {topic}")


def on_disconnect(mqtt_client: Any, user_data: Any, return_code: Any) -> None:
    _LOGGER.debug(f"on_disconnect")
    if return_code != 0:
        _LOGGER.info(f"on_disconnect: will reconnect: {return_code}")

def on_message(mqtt_client: Any, userdata: Any, message: Any) -> None:
    if _LOGGER.isEnabledFor(DEBUG):
        _LOGGER.debug(f"message: {message.topic}: {message.payload}")

# pylint: disable=unused-argument
def on_publish(mqtt_client: Any, userdata: Any, result: Any) -> None:
    global _PUBLISHED  # pylint: disable=global-statement
    _PUBLISHED = True


class MQTT(Message):
    def __init__(
        self, message_handler: Any = on_message, topics_subscribe: Any = None, lwt_topic: str = None, lwt_payload:str = None, lwt_retain: bool = False
    ) -> None:
        global _TOPICS_SUBSCRIBE  # pylint: disable=global-statement
        _TOPICS_SUBSCRIBE = topics_subscribe

        self.message_handler = message_handler
        self._connect(lwt_topic, lwt_payload, lwt_retain)

    def _connect(self: Any, lwt_topic: Any, lwt_payload: str, lwt_retain: Any) -> None:
        _LOGGER.debug(f"connecting to {MQTT_HOST}")
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_disconnect = on_disconnect
        self.mqtt_client.on_message = self.message_handler
        self.mqtt_client.on_publish = on_publish

        if lwt_topic:
            self.mqtt_client.will_set(lwt_topic, payload=lwt_payload, retain=lwt_retain)
        try:
            self.mqtt_client.connect(host=MQTT_HOST, port=MQTT_PORT, keepalive=60)
            self.mqtt_client.loop_start()
        except ConnectionRefusedError:
            raise SystemError(f"Error: Couldn't connect to MQTT server {MQTT_HOST}")

    def _disconnect(self: Any) -> None:
        global _CONNECTED  # pylint: disable=global-statement
        _LOGGER.debug(f"disconnect from {MQTT_HOST}")
        self.wait_published()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect() # Note: Does not cause the LWT to be sent
#       self.mqtt_client.loop_forever()
        self.mqtt_client = None
        _CONNECTED = False

    def publish(self: Any, topic: Any, payload: Any, retain: bool = False, wait: bool = False) -> None:
        global _PUBLISHED  # pylint: disable=global-statement
        _PUBLISHED = False
        self.wait_connected()
        self.mqtt_client.publish(topic, payload, retain=retain)
        if wait:
            self.wait_published()

    def set_last_will_and_testament(self, lwt_topic: str = None, lwt_payload: str = None, lwt_retain: bool = False) -> None:
        self._disconnect()
        self._connect(lwt_topic, lwt_payload, lwt_retain)

    def wait_connected(self) -> None:
        global _CONNECTED  # pylint: disable=global-statement
# TODO: Only wait a limited time and either carry on without failing ... or fail and choose to reconnect to MQTT
        _LOGGER.debug("wait connected")
        for counter in range(2000):
            if _CONNECTED: break
            time.sleep(0.001)
        _LOGGER.debug(f"wait connected: {counter}")

    def wait_published(self) -> None:
        global _PUBLISHED  # pylint: disable=global-statement
# TODO: Only wait a limited time and either carry on without failing ... or fail and choose to reconnect to MQTT
        _LOGGER.debug("wait published")
        for counter in range(2000):
            if _PUBLISHED: break
            time.sleep(0.001)
        _LOGGER.debug(f"wait published: {counter}")
