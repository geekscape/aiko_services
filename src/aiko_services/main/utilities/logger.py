# Notes
# ~~~~~
# This is a low-level utility used by the AikoServices framework, so be
# careful when making static dependencies on the AikoServices framework.
#
# Python's "logging" package is NOT intuitive :(
# https://stackoverflow.com/questions/43109355/logging-setlevel-is-being-ignored
# https://docs.python.org/3/library/logging.html
# https://docs.python.org/3/library/logging.html#formatter-objects
# https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting
#
# Typical usage: Aiko and LoggingHandlerMQTT
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# AIKO_LOG_LEVEL=INFO python                      # MQTT logging (default)
# AIKO_LOG_LEVEL=INFO AIKO_LOG_MQTT=false python  # Console logging
#   from aiko_services.main import *
#   _LOGGER = aiko.logger(__name__)
#   _LOGGER.info("Informative message")
#   aiko.process.run(True)  # Required for MQTT based logging
#
# Direct usage: Standalone Logger
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# AIKO_LOG_LEVEL=DEBUG python  # AIKO_LOG_LEVEL=INFO (default)
#   from aiko_services.main.utilities import get_logger
#   _LOGGER = get_logger(__name__)
#   _LOGGER.debug("Diagnostic message")
#
# Usage: Change logging level on-the-fly using ECProducer
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# from aiko_services.main import *
# from aiko_services.main.utilities import *
# _LOGGER = aiko.logger(__name__)
#
# def ec_producer_change_handler(command, item_name, item_value):
#     if item_name == "log_level":
#         _LOGGER.setLevel(str(item_value).upper())
#
# state = {"log_level": get_log_level_name(_LOGGER)}
# ec_producer = ECProducer(service, state)
# ec_producer.add_handler(ec_producer_change_handler)
# _LOGGER.info("Informative message")
# aiko.process.run(True)  # Required for ECProducer and MQTT based logging
#
# To Do: Logger
# ~~~~~~~~~~~~~
# * Implement set_log_level(name, level) and keep a dictionary of all loggers,
#   so that an individual, a list or all loggers can be changed at once
#
# - Based on current log_level, select _LOG_FORMAT/_DEBUG on-the-fly
# - Allow AIKO_LOG_MQTT value to be changed on-the-fly (via ECProducer)
#
# - Implement logging to a file (break into chunks by date/time or size)
#   - Set log file path and logging level via command line arguments
# - Turn "logger" into a Python class, nothing global !
#
# To Do: LoggingHandlerMQTT
# ~~~~~~~~~~~~~~~~~~~~~~~~~
# - Add support for ConnectionState.TRANSPORT (MQTT) connection updates

from collections import deque
import logging
from logging.config import dictConfig
import os
import sys
from typing import Any

from aiko_services.main.utilities import *

__all__ = [
    "DEBUG", "get_level_name", "get_logger", "LoggingHandlerMQTT", "print_error"
]

DEBUG = logging.DEBUG

_RING_BUFFER_SIZE = 128  # Maximum log messages to store before MQTT available

_LEVEL_NAMES = {
    0: "LOG_LEVEL_NOTSET",        #  0
    logging.DEBUG: "DEBUG",       # 10
    logging.INFO: "INFO",         # 20
    logging.WARNING: "WARNING",   # 30
    logging.ERROR: "ERROR",       # 40
    logging.CRITICAL: "CRITICAL"  # 50
}

_LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname) 8s"
_LOG_FORMAT_DEBUG = f"{_LOG_FORMAT}s %(module)s.%(funcName)s() %(message)s"
_LOG_FORMAT_DEFAULT = f"{_LOG_FORMAT} %(name)18s %(message)s"
_LOG_FORMAT_DATETIME = "%Y-%m-%d_%H:%M:%S"

def get_log_level_name(logger):
    if logger.level in _LEVEL_NAMES:
        level_name = _LEVEL_NAMES[logger.level]
    else:
        level_name = str(logger.level)
    return level_name

def get_logger(name: str, log_level=None, logging_handler=None) -> Any:
#   logging.basicConfig(filename="aiko.log")  # TODO: Implement logging to file

    name = name.rpartition('.')[-1].upper()
#   print(f"Create logger {name}: {log_level}, {logging_handler}")

    if log_level is None:
        log_level = os.environ.get("AIKO_LOG_LEVEL", logging.INFO)
    if log_level == "":
        log_level = logging.INFO

    if logging_handler is None:
        logging_handler = logging.StreamHandler()

    format = _LOG_FORMAT_DEFAULT  # _LOG_FORMAT_DEBUG
    formatter = logging.Formatter(format, datefmt=_LOG_FORMAT_DATETIME)
    logging_handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.addHandler(logging_handler)
    logger.setLevel(log_level)
    return logger

def print_error(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

# -----------------------------------------------------------------------------

from aiko_services.main.connection import ConnectionState

class LoggingHandlerMQTT(logging.Handler):
    def __init__(
        self, aiko, topic, option="all", ring_buffer_size=_RING_BUFFER_SIZE):

        super().__init__()
        self.aiko = aiko
        self.console_flag = option == "all"
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
            if self.console_flag:
                try:
                    print(payload_out)  # TODO: For shell pipes ... flush=True
                except BrokenPipeError:
                    pass

            if self.ready:
                self.aiko.message.publish(self.topic, payload_out)
            else:
                self.ring_buffer.append(payload_out)
            self.flush()
        except Exception:
            self.handleError(record)  # TODO: Start buffering log records

# -----------------------------------------------------------------------------
