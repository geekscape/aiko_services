# Notes
# ~~~~~
# This is a low-level mechanism, used by the AikoServices framework
# and should not have any static dependencies on that framework
#
# Usage: Logger
# ~~~~~~~~~~~~~
# LOG_LEVEL=DEBUG python
#   from aiko_services.utilities import *
#   _LOGGER = get_logger(__name__)
#   _LOGGER.debug("Diagnostic message")
#
# Usage: LoggingHandlerMQTT
# ~~~~~~~~~~~~~~~~~~~~~~~~~
# LOG_LEVEL=DEBUG python  # without MQTT logging
# LOG_MQTT=DEBUG python   # with MQTT logging
#   from aiko_services import *
#   _LOGGER = aiko.logger(__name__)
#   _LOGGER.debug("hello")
#   aiko.process(True)
#
# To Do: Logger
# ~~~~~~~~~~~~~
# - Turn "logger" into a Python class, nothing global !
#
# - Implement message to change logging level !
#
# - BUG: If LOG_LEVEL=DEBUG, then get_logger.debug(message) message may appear
#     twice, but not if LOG_LEVEL=DEBUG_ALL
# - BUG: get_logger.info(message) doesn't display for LOG_LEVEL=INFO
# - Set logging level and log file from command line argument
#
# To Do: LoggingHandlerMQTT
# ~~~~~~~~~~~~~~~~~~~~~~~~~
# - Add support for ConnectionState.TRANSPORT (MQTT) connection updates

from collections import deque
import logging
from logging.config import dictConfig
import os
from typing import Any

from aiko_services.connection import ConnectionState
from aiko_services.utilities import *

__all__ = ["get_logger", "LoggingHandlerMQTT"]

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_LOG_FORMAT_DATE = "%Y-%m-%d_%H:%M:%S"

_RING_BUFFER_SIZE=128

_CONFIGURATION = {
    "version": 1,
    "formatters": {
        "f": { "format": _LOG_FORMAT, "datefmt": _LOG_FORMAT_DATE }
    },
    "handlers": {
        "h": { "class": "logging.StreamHandler", "formatter": "f" }
    },
    "loggers": {
        "": { "handlers": ["h"], "level": "DEBUG" }
    }
}

_LOGGING_HANDLERS_THIRD_PARTY = [
    "asyncio", "matplotlib", "MESSAGE", "MQTT", "PIL.PngImagePlugin",
    "shapely.geos", "sgqlc.endpoint", "STATE", "transitions.core",
    "websockets.protocol"
]

for logging_handler in _LOGGING_HANDLERS_THIRD_PARTY:
    _CONFIGURATION["loggers"][logging_handler] = {
            "handlers": ["h"],
            "level": "INFO"
    }

_LOG_LEVEL = os.environ.get("LOG_LEVEL", False)

if _LOG_LEVEL == "DEBUG_ALL":
    _LOG_LEVEL="DEBUG"
    loggers = _CONFIGURATION["loggers"]
    keys = [key for key, value in loggers.items() if value["level"] == "INFO"]
    for key in keys:
        del loggers[key]

if _LOG_LEVEL == "DEBUG":
    logging.config.dictConfig(_CONFIGURATION)

def get_logger(name: str, logging_handler=None, log_level=None) -> Any:
#   logging.basicConfig(filename="aiko.log")
    name = name.rpartition('.')[-1].upper()
#   print(f"Create logger {name}")  # logging.debug()
    logger = logging.getLogger(name)
    if logging_handler:
        formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_FORMAT_DATE)
        logger.addHandler(logging_handler)
        logging_handler.setFormatter(formatter)
        if log_level:
            logger.setLevel(log_level)
    return logger

# -----------------------------------------------------------------------------

class LoggingHandlerMQTT(logging.Handler):
    def __init__(self, aiko, topic, ring_buffer_size=_RING_BUFFER_SIZE):
        super().__init__()
        self.aiko = aiko
        self.topic = topic

        self.ready = False
        self.ring_buffer = deque(maxlen=ring_buffer_size)
        aiko.connection.add_handler(self._connection_state_handler)

    def _connection_state_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.TRANSPORT):
            self.ready = True
            while len(self.ring_buffer):
                payload_out = self.ring_buffer.popleft()
                self.aiko.message.publish(self.topic, payload_out)

    def __del__(self):
        try:
            pass  # TODO: release resources
        except:
            pass
        try:
            pass  # TODO: self.???? = None
        except:
            pass

    def emit(self, record):  # record: logging.LogRecord has lots of details
        try:
            payload_out = self.format(record)
            if self.ready:
                self.aiko.message.publish(self.topic, payload_out)
            else:
                self.ring_buffer.append(payload_out)
            self.flush()
        except Exception:
            self.handleError(record)  # TODO: Start buffering log records

# -----------------------------------------------------------------------------
