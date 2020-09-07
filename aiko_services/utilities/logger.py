# Usage
# ~~~~~
# LOG_LEVEL=DEBUG python ...
# LOG_LEVEL=DEBUG_ALL python ...
#
# To Do
# ~~~~~
# - BUG: get_logger.info(message) doesn't display for LOG_LEVEL=INFO
# - Set logging level and log file from command line argument
# - Implement message to change logging level !

from typing import Any
import logging
from logging.config import dictConfig
import os

__all__ = ["get_logger"]

_CONFIGURATION = {
    "version": 1,
    "formatters": {
        "f": { "format":
               "%(asctime)s %(levelname)s %(name)s %(message)s",
               "datefmt": "%H:%M:%S"
        }
    },
    "handlers": {
        "h": { "class": "logging.StreamHandler",
               "formatter": "f"
        }
    },
    "loggers": { 
        "": { 
            "handlers": ["h"],
            "level": "DEBUG"
        },
        "MQTT": { 
            "handlers": ["h"],
            "level": "INFO"
        },
        "STATE": { 
            "handlers": ["h"],
            "level": "INFO"
        }
    }
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

def get_logger(name: str) -> Any:
#   logging.basicConfig(filename="aiko.log")
    name = name.rpartition('.')[-1].upper()
#   logging.debug(f"create logger {name}")
    logger = logging.getLogger(name)
    return logger
