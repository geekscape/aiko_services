# To Do
# ~~~~~
# - BUG: If on MQTT thread, then if waiting for a condition to change that
#   depends upon an incoming message, then wait will timeout, because that
#   incoming message can't be processed.
#   For example, if wait_disconnected() called whilst on MQTT thread,
#   then the MQTT broker message for "disconnect" --> on_disconnect()
#   won't happen.
#   For example, when Registrar processed "(primary stopped)" message and
#   attempts set_last_will_and_testament(), which causes a wait_disconnected()
#   whilst on the MQTT thread.
# - SOLUTION: By default queue all incoming MQTT messages and process on the
#   main event.loop() !
#
# - Refactor wait_disconnected(), wait_connected() and wait_published(self)
#     into a single function
#   - Parameter is a variable condition to test,
#       e.g not self.connected, self.connected and self.published
#
# - Implement message to change logging level !
# - Allow default MQTT_HOST and MQTT_PORT to be overridden by CLI parameters
# - Implement reconnect on disconnection from MQTT server
#   - Maybe raise an exception if reconnection fails, rather than sys.exit(-1)
# - Implement discovery and manual setting of AIKO_MQTT_HOST, etc
#   - Rediscover on disconnection
# - Implement destructor ?

from logging import DEBUG
import paho.mqtt.client as mqtt
import time
from typing import Any

from aiko_services.message import *
from aiko_services.utilities import *

__all__ = ["MQTT"]

MQTT_HOST = "localhost"
# MQTT_HOST = "202.130.215.177"  # "lounge.local"
# MQTT_HOST = "zeus_t"
# MQTT_HOST = "mqtt.fluux.io"
# MQTT_HOST = "test.mosquitto.org"
MQTT_PORT = 1883

_LOGGER = get_logger(__name__)
_MAXIMUM_WAIT_TIME = 2000  # milliseconds

def _on_message(mqtt_client: Any, userdata: Any, message: Any) -> None:
    if _LOGGER.isEnabledFor(DEBUG):
        _LOGGER.debug(f"message: {message.topic}: {message.payload}")

class MQTT(Message):
    def __init__(
        self,
        message_handler: Any = _on_message,
        topics_subscribe: Any = None,
        lwt_topic: str = None,
        lwt_payload:str = None,
        lwt_retain: bool = False
        ) -> None:

        self.message_handler = message_handler
        self.topics_subscribe = topics_subscribe

        self.connected = False
        self.published = True

        self._connect(lwt_topic, lwt_payload, lwt_retain)

    def _connect(
        self: Any,
        lwt_topic: Any,
        lwt_payload: str,
        lwt_retain: Any
        ) -> None:

        _LOGGER.debug(f"connecting to {MQTT_HOST}")
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self.message_handler
        self.mqtt_client.on_publish = self._on_publish

        if lwt_topic:
            self.mqtt_client.will_set(
                lwt_topic, payload=lwt_payload, retain=lwt_retain)
        try:
            self.mqtt_client.connect(
                host=MQTT_HOST, port=MQTT_PORT, keepalive=60)
            self.mqtt_client.loop_start()
        except ConnectionRefusedError:
            diagnostic = f"Error: Couldn't connect to MQTT server {MQTT_HOST}"
            raise SystemError(diagnostic)

    def _disconnect(self: Any) -> None:
        _LOGGER.debug(f"disconnect from {MQTT_HOST}")
        self.wait_published()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect() # Note: Does not cause the LWT to be sent
#       self.mqtt_client.loop_forever()
        self.mqtt_client = None

    # pylint: disable=unused-argument
    def _on_connect(
        self,
        mqtt_client: Any,
        user_data: Any,
        dict_flags: Any,
        result_code: Any
        ) -> None:

        _LOGGER.debug(f"connected to {MQTT_HOST}")
        self.connected = True
        if self.topics_subscribe:
            topics = self.topics_subscribe
            if type(topics) is dict:
                topics = topics.keys()
            for topic in topics:
                mqtt_client.subscribe(topic)
                _LOGGER.debug(f"subscribed to {MQTT_HOST}: {topic}")

    def _on_disconnect(
        self,
        mqtt_client: Any,
        user_data: Any,
        return_code: Any
        ) -> None:

        _LOGGER.debug(f"on_disconnect")
        self.connected = False
        if return_code != 0:
            _LOGGER.info(f"on_disconnect: will reconnect: {return_code}")

    # pylint: disable=unused-argument
    def _on_publish(
        self,
        mqtt_client: Any,
        userdata: Any,
        result: Any
        ) -> None:

        self.published = True

    def publish(
        self: Any,
        topic: Any,
        payload: Any,
        retain: bool = False,
        wait: bool = False
        ) -> None:

        self.published = False
        self.wait_connected()
        self.mqtt_client.publish(topic, payload, retain=retain)
        if wait:
            self.wait_published()

    def set_last_will_and_testament(
        self, lwt_topic: str = None,
        lwt_payload: str = None,
        lwt_retain: bool = False
        ) -> None:

        self._disconnect()
        self.wait_disconnected()
        self._connect(lwt_topic, lwt_payload, lwt_retain)

# TODO: Only wait a limited time and either carry on without failing ...
#       or fail and choose to reconnect to MQTT

    def wait_disconnected(self) -> None:
#       _LOGGER.debug("wait disconnected")
        for counter in range(_MAXIMUM_WAIT_TIME + 1):
            if not self.connected: break
            time.sleep(0.001)
        if counter >= _MAXIMUM_WAIT_TIME:
            _LOGGER.error(f"wait disconnected timeout: {counter}")
#       else:
#           _LOGGER.debug(f"wait disconnected: {counter}")

# TODO: Only wait a limited time and either carry on without failing ...
#       or fail and choose to reconnect to MQTT

    def wait_connected(self) -> None:
#       _LOGGER.debug("wait connected")
        for counter in range(_MAXIMUM_WAIT_TIME + 1):
            if self.connected: break
            time.sleep(0.001)
        if counter >= _MAXIMUM_WAIT_TIME:
            _LOGGER.error(f"wait connected timeout: {counter}")
#       else:
#           _LOGGER.debug(f"wait connected: {counter}")

# TODO: Only wait a limited time and either carry on without failing ...
#       or fail and choose to reconnect to MQTT

    def wait_published(self) -> None:
#       _LOGGER.debug("wait published")
        for counter in range(_MAXIMUM_WAIT_TIME + 1):
            if self.published: break
            time.sleep(0.001)
        if counter >= _MAXIMUM_WAIT_TIME:
            _LOGGER.error(f"wait published timeout: {counter}")
#       else:
#           _LOGGER.debug(f"wait published: {counter}")
