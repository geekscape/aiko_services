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
# Environment variables
# ~~~~~~~~~~~~~~~~~~~~~
# AIKO_LOG_LEVEL:         ERROR, WARNING, INFO, DEBUG
# AIKO_LOG_MQTT:          false: Console, true: MQTT, all: Both Console / MQTT
# AIKO_LOG_REPEAT_PERIOD: Period for repeated log messages, default 6 seconds
# AIKO_LOG_REPEAT_DEPTH:  To be implemented
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
#         _LOGGER.setLevel(log_level_real(item_value))
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
# * Add support for AIKO_LOG_REPEAT_DEPTH to handle multiple repeated messages

from collections import deque
import logging
from logging.config import dictConfig
import os
import sys
import time
from typing import Any

from aiko_services.main.utilities import *

__all__ = [
    "DEBUG", "get_level_name", "get_logger", "LoggingHandlerMQTT",
    "log_level_all", "log_level_real", "print_error"
]

DEBUG = logging.DEBUG
DEFAULT_LOG_REPEAT_PERIOD = "6"  # seconds for "AIKO_LOG_REPEAT_PERIOD"

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

def log_level_all(log_level):
    return log_level.upper().endswith("_ALL")

def log_level_real(log_level):  # Make uppercase and strip "_ALL" suffix
    log_level = log_level.upper()
    log_level = log_level[:-4] if log_level_all(log_level) else log_level
    return log_level

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

        self.repeated_period = os.environ.get(
            "AIKO_LOG_REPEAT_PERIOD", DEFAULT_LOG_REPEAT_PERIOD)
        if self.repeated_period.isnumeric():
            self.repeated_period = int(self.repeated_period)
        else:
            self.repeated_period = 0

        self.ready = False
        self.record_previous = None
        self.record_repeat_count = 0
        self.record_time = 0
        self.ring_buffer = deque(maxlen=ring_buffer_size)
        aiko.connection.add_handler(self._connection_state_handler)

    def _connection_state_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.TRANSPORT):
            self.ready = True
            self._publish_ring_buffer()
        else:
            self.ready = False

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
            repeated, repeated_message = self._repeated_record(record)
            if repeated:
                if repeated_message:
                    record.msg = repeated_message
                else:
                    return

            payload_out = self.format(record)
            if self.console_flag:
                try:
                    print(payload_out)  # TODO: For shell pipes ... flush=True
                except BrokenPipeError:
                    pass

            if self.ready:
                self._publish_ring_buffer()
                self.aiko.message.publish(self.topic, payload_out)
            else:
                self.ring_buffer.append(payload_out)
            self.flush()
    # TODO: Catch specific Exceptions, don't hide other problems !
        except Exception as exception:  # TODO: When does this occur ?
            self.handleError(record)  # TODO: Start buffering log records

    def _publish_ring_buffer(self):
        while len(self.ring_buffer):
            payload_out = self.ring_buffer.popleft()
            self.aiko.message.publish(self.topic, payload_out)

    def _repeated_record(self, record):
        message = None
        repeated = self.record_previous and  \
                   self.record_previous.msg == record.msg and  \
                   self.record_previous.name == record.name and  \
                   self.record_previous.levelname == record.levelname
        if self.repeated_period > 0 and repeated:
            self.record_repeat_count += 1
            if time.time() > self.record_time + self.repeated_period:
                message = f"Repeated message count: {self.record_repeat_count}"
                self.record_repeat_count = 0
                self.record_time = time.time()
        else:
            repeated = False
            self.record_previous = record
            self.record_repeat_count = 0
            self.record_time = time.time()
        return repeated, message

# -----------------------------------------------------------------------------
