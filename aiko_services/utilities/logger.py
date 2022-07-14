# Notes
# ~~~~~
# This is a low-level mechanism, used by the AikoServices framework
# and should not have any static dependencies on that framework
#
# Usage: Logger
# ~~~~~~~~~~~~~
# AIKO_LOG_LEVEL=DEBUG python
#   from aiko_services.utilities import *
#   _LOGGER = get_logger(__name__)
#   _LOGGER.debug("Diagnostic message")
#
# Usage: LoggingHandlerMQTT
# ~~~~~~~~~~~~~~~~~~~~~~~~~
# AIKO_LOG_LEVEL=DEBUG python   # with MQTT logging (default)
# AIKO_LOG_MQTT=false python    # without MQTT logging
#   from aiko_services import *
#   _LOGGER = aiko.logger(__name__)
#   _LOGGER.debug("hello")
#   aiko.process(True)
#
# Usage: Logging with ECProducer
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#   def _ec_producer_change_handler(self, command, item_name, item_value):
#       if item_name == "log_level":
#           _LOGGER.setLevel(str(item_value).upper())
#   self.state = {
#       "log_level": get_log_level_name(_LOGGER)
#   }
#   self.ec_producer = ECProducer(self.state)
#   self.ec_producer.add_handler(self._ec_producer_change_handler)
#
# To Do: Logger
# ~~~~~~~~~~~~~
# - BUG: get_logger.info(message) doesn't display for AIKO_LOG_LEVEL=INFO
#
# - Implement logging to a file (break into chunks by date/time or size)
#
# - Turn "logger" into a Python class, nothing global !
#
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

__all__ = ["DEBUG", "get_level_name", "get_logger", "LoggingHandlerMQTT"]

DEBUG = logging.DEBUG

_RING_BUFFER_SIZE=128

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_LOG_FORMAT_DATE = "%Y-%m-%d_%H:%M:%S"
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

_LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",      # 10
    logging.INFO: "INFO",        # 20
    logging.WARNING: "WARNING",  # 30
    logging.ERROR: "ERROR",      # 40
    logging.FATAL: "FATAL"       # 50
}

AIKO_LOG_LEVEL = os.environ.get("AIKO_LOG_LEVEL", "INFO").upper()

# if AIKO_LOG_LEVEL == "INFO":
#     logging.config.dictConfig(_CONFIGURATION)

def get_log_level_name(logger):
    log_level = logger.level
    level_name = str(log_level)
    if log_level in _LEVEL_NAMES:
        level_name = _LEVEL_NAMES[log_level]
    return level_name

def get_logger(name: str, log_level="INFO", logging_handler=None) -> Any:
#   print(f"Create logger {name}: {log_level}, {logging_handler}")
    name = name.rpartition('.')[-1].upper()
    logger = logging.getLogger(name)
#   logging.basicConfig(filename="aiko.log")  # TODO: Implement logging to file

    if logging_handler:
        logger.addHandler(logging_handler)
        formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_FORMAT_DATE)
        logging_handler.setFormatter(formatter)

    logger.setLevel(log_level if log_level else "INFO")
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
                print(f"emit(): MQTT: {payload_out}")
                self.aiko.message.publish(self.topic, payload_out)
            else:
                print(f"emit(): ring_buffer: {payload_out}")
                self.ring_buffer.append(payload_out)
            self.flush()
        except Exception:
            self.handleError(record)  # TODO: Start buffering log records

# -----------------------------------------------------------------------------
