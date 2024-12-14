# Usage
# ~~~~~
# Can't use utilities.logger.LoggingHandlerMQTT to diagnose this MQTT module !
#
# When using AIKO_LOG_LEVEL=DEBUG for the rest of framework or applications,
# typically don't want to see low-level MQTT message debug log records.
# Therefore, AIKO_LOG_LEVEL=DEBUG doesn't affect this MQTT module, instead use
#
#     AIKO_LOG_LEVEL_MQTT=DEBUG application parameters ...
#
# To Do
# ~~~~~
# - Allow default MQTT_HOST and MQTT_PORT to be overridden by CLI parameters
#
# - BUG: If on MQTT thread, then if waiting for a condition to change that
#   depends upon an incoming message, then wait will timeout, because that
#   incoming message can't be processed.
#   For example, if wait_disconnected() called whilst on MQTT thread,
#   then the MQTT broker message for "disconnect" --> on_disconnect()
#   won't happen.
#   For example, when Registrar processed "(primary absent)" message and
#   attempts set_last_will_and_testament(), which causes a wait_disconnected()
#   whilst on the MQTT thread.
# - SOLUTION: By default queue all incoming MQTT messages and process on the
#   main event.loop() !
#
# - Track which topic subscriptions have succeeded ...
#     mqtt_client.subscribe() return value is saved (subscribe topic list index)
#     to be compared to the on_subscribe(..., mid, ...) parameter value
#
# - Refactor wait_disconnected(), wait_connected() and wait_published(self)
#     into a single function
#   - Parameter is a variable condition to test,
#       e.g not self.connected, self.connected and self.published
#
# - Implement message to change logging level !
# - Implement reconnect on disconnection from MQTT server
#   - Maybe raise an exception if reconnection fails, rather than sys.exit(-1)
# - Implement discovery and manual setting of AIKO_MQTT_HOST, etc
#   - Rediscover on disconnection
# - Implement destructor ?

import os
import paho.mqtt.client as mqtt
import socket
import time
from typing import Any, List

from aiko_services.main.message import *
from aiko_services.main.utilities import *

__all__ = ["MQTT"]

# MQTT_HOST = "mqtt.fluux.io"
# MQTT_HOST = "test.mosquitto.org"

_AIKO_LOG_LEVEL = os.environ.get("AIKO_LOG_LEVEL_MQTT", "INFO")
_LOGGER = get_logger(__name__, log_level=_AIKO_LOG_LEVEL, logging_handler=None)
_MAXIMUM_WAIT_TIME = 2000  # milliseconds

def _on_message(mqtt_client: Any, userdata: Any, message: Any) -> None:
    if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
        _LOGGER.debug(f"message: {message.topic}: {message.payload}")

class MQTT(Message):
    def __init__(
        self: Any,
        message_handler: Any = _on_message,
        topics_subscribe: Any = None,
        topic_lwt: str = None,
        payload_lwt:str = None,
        retain_lwt: bool = False
        ) -> None:

        self.message_handler = message_handler
        self.connected = False
        self.published = True
        self.topics_subscribe = []
        self.wildcard_topic = False
        self.wildcard_subscribed = False
        self.subscribe(topics_subscribe)

        mqtt_configuration = get_mqtt_configuration()
        server_up = mqtt_configuration[0]
        self.mqtt_host = mqtt_configuration[1]
        self.mqtt_port = mqtt_configuration[2]
        self.mqtt_transport = mqtt_configuration[3]
        self.mqtt_username = mqtt_configuration[4]
        self.mqtt_password = mqtt_configuration[5]
        self.mqtt_tls_enabled = mqtt_configuration[6]
        tls_state = "TLS enabled" if self.mqtt_tls_enabled else "TLS disabled"
        self.mqtt_info = f"{self.mqtt_host}:{self.mqtt_port}:{tls_state}"

        if server_up:
            self._connect(topic_lwt, payload_lwt, retain_lwt)
        else:
            diagnostic = f"Couldn't connect to MQTT server {self.mqtt_info}"
            raise SystemError(diagnostic)

    def _connect(
        self: Any,
        topic_lwt: Any,
        payload_lwt: str,
        retain_lwt: Any
        ) -> None:

        _LOGGER.debug(f"connecting to {self.mqtt_info}")
        self.mqtt_client = mqtt.Client(transport=self.mqtt_transport)
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self.message_handler
        self.mqtt_client.on_publish = self._on_publish

        if topic_lwt:
            self.mqtt_client.will_set(
                topic_lwt, payload=payload_lwt, retain=retain_lwt)
        if self.mqtt_tls_enabled:
            self.mqtt_client.tls_set()
        if self.mqtt_username:
            self.mqtt_client.username_pw_set(
                self.mqtt_username, self.mqtt_password)

        diagnostic = f"Couldn't connect to MQTT server {self.mqtt_info}"
        try:
            self.mqtt_client.connect(
                host=self.mqtt_host, port=self.mqtt_port, keepalive=60)
            self.mqtt_client.loop_start()  # Handles MQTT reconnections
        except socket.gaierror:
            raise SystemError(diagnostic)
        except ConnectionRefusedError:
            raise SystemError(diagnostic)
    #   except ConnectionResetError:  # TODO: Is this required as well ?
    #       raise SystemError(diagnostic)

    def _disconnect(self: Any) -> None:
        _LOGGER.debug(f"disconnect from {self.mqtt_info}")
        self.wait_published()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()    # Note: Does not cause LWT to be sent
#       self.mqtt_client.loop_forever()  # Handles MQTT reconnections
        self.mqtt_client = None

    # pylint: disable=unused-argument
    def _on_connect(
        self: Any,
        mqtt_client: Any,
        user_data: Any,
        dict_flags: Any,
        result_code: Any
        ) -> None:

        _LOGGER.debug(f"connected to {self.mqtt_info}")
        self.connected = True
        self._subscribe_if_connected(self.topics_subscribe)

    def _on_disconnect(
        self: Any,
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
        self: Any,
        mqtt_client: Any,
        userdata: Any,
        result: Any
        ) -> None:

        self.published = True

    def publish(
        self: Any,
        topic: str,
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
        self: Any,
        topic_lwt: str = None,
        payload_lwt: str = "(absent)",
        retain_lwt: bool = False
        ) -> None:

        self._disconnect()
        self.wait_disconnected()
        self._connect(topic_lwt, payload_lwt, retain_lwt)

    def subscribe(self: Any, topics: Any) -> None:
        if topics:
            if isinstance(topics, str):
                topics = [topics]
            if isinstance(topics, dict):
                topics = topics.keys()
            for topic in topics:
                if topic == "#":
                    self.wildcard_topic = True
                    self.unsubscribe(self.topics_subscribe, remove=False)
                else:
                    self.topics_subscribe.append(topic)

            self._subscribe_if_connected(topics)

    def _subscribe_if_connected(self, topics: Any):
        if self.connected:
            if self.wildcard_topic:
                if not self.wildcard_subscribed:
                    self.mqtt_client.subscribe("#")
                    self.wildcard_subscribed = True
                    _LOGGER.debug(f"subscribed to {self.mqtt_info}: #")
            elif topics:
                for topic in topics:
                    self.mqtt_client.subscribe(topic)
                    _LOGGER.debug(f"subscribed to {self.mqtt_info}: {topic}")

    def unsubscribe(self: Any, topics: Any, remove=True) -> None:
        if topics:
            if isinstance(topics, str):
                topics = [topics]
            if isinstance(topics, dict):
                topics = topics.keys()
            for topic in topics:
                if topic == "#":
                    if self.wildcard_topic:
                        self.wildcard_topic = False
                        if self.wildcard_subscribed:
                            self.mqtt_client.unsubscribe("#")
                            self.wildcard_subscribed = False
                            _LOGGER.debug(f"unsubscribed from {self.mqtt_info}: #")
                        self._subscribe_if_connected(self.topics_subscribe)
                elif topic in self.topics_subscribe:
                    if remove:
                        self.topics_subscribe.remove(topic)
                    if self.connected:
                        self.mqtt_client.unsubscribe(topic)
                        _LOGGER.debug(f"unsubscribed from {self.mqtt_info}: {topic}")

# TODO: Only wait a limited time and either carry on without failing ...
#       or fail and choose to reconnect to MQTT

    def wait_disconnected(self: Any) -> None:
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

    def wait_connected(self: Any) -> None:
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

    def wait_published(self: Any) -> None:
#       _LOGGER.debug("wait published")
        for counter in range(_MAXIMUM_WAIT_TIME + 1):
            if self.published: break
            time.sleep(0.001)
        if counter >= _MAXIMUM_WAIT_TIME:
            _LOGGER.error(f"wait published timeout: {counter}")
#       else:
#           _LOGGER.debug(f"wait published: {counter}")
