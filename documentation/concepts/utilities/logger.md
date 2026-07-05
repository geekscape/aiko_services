---
title: Logger utility
description: Logging for Aiko Services — console and/or MQTT log
  transport with ring buffering and repeated-message suppression,
  configured by AIKO_LOG_* environment variables
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/logger.py
related: [design_overview, configuration]
version: "0.6"
last_updated: 2026-07-05
---

# Logger utility

## Overview

The logger utility wraps Python's (notoriously unintuitive) `logging`
package into two pieces: `get_logger()`, a one-call standalone logger
factory driven by `AIKO_LOG_LEVEL`; and `LoggingHandlerMQTT`, a logging
handler that publishes log records to an MQTT topic — buffering them in a
ring buffer until the connection is up, and collapsing repeated messages.
Distributed logging over MQTT is what lets the Recorder and Dashboard
show every process's log stream from anywhere on the network.

**Why you'd use it**: the framework idiom, one logger per module, MQTT
transport by default:

```python
from aiko_services.main import *
_LOGGER = aiko.logger(__name__)
_LOGGER.info("Informative message")
aiko.process.run(True)   # required for MQTT-based logging
```

Standalone (before / without the framework):

```python
from aiko_services.main.utilities import get_logger
_LOGGER = get_logger(__name__)
_LOGGER.debug("Diagnostic message")
```

## For application developers

### Command-line usage

There is no CLI; behaviour is controlled by environment variables, which
apply to every Aiko Services process:

```bash
AIKO_LOG_LEVEL=DEBUG         # ERROR, WARNING, INFO (default), DEBUG
AIKO_LOG_MQTT=false          # false: console, true: MQTT, all: both (default)
AIKO_LOG_REPEAT_PERIOD=6     # seconds between repeated-message summaries
AIKO_LOG_REPEAT_DEPTH=...    # to be implemented
```

The MQTT log topic is `{namespace}/{host}/{pid}/{sid}/log`; the Recorder
subscribes to `{namespace}/+/+/+/log` to capture them all.

### Public API

```python
get_logger(name, log_level=None, logging_handler=None)  # standalone logger
get_log_level_name(logger)        # "DEBUG" | "INFO" | ... for shared state
log_level_all(log_level)          # does the level string end in "_ALL"?
log_level_real(log_level)         # uppercase, strip "_ALL" suffix
print_error(*args)                # print to stderr
DEBUG                             # re-exported logging.DEBUG

class LoggingHandlerMQTT(logging.Handler):
    LoggingHandlerMQTT(aiko, topic, option="all", ring_buffer_size=128)
```

The `"_ALL"` level-name convention: writing `log_level=DEBUG_ALL` to a
Pipeline's shared state propagates `DEBUG` to every PipelineElement,
while `log_level_real()` recovers the plain level. Real call sites:

```python
# src/aiko_services/main/process.py — how aiko.logger() is built
option = os.environ.get("AIKO_LOG_MQTT", "all")
if option in ("all", "true"):
    logging_handler = LoggingHandlerMQTT(aiko, topic, option)
return get_logger(name, log_level, logging_handler)

# src/aiko_services/main/actor.py — on-the-fly level change via ECProducer
self.share = {"log_level": get_log_level_name(self.logger), ...}
...
self.logger.setLevel(log_level_real(item_value))
```

## For framework developers (internals)

### Design

```
   _LOGGER.info(...)
        │
        ▼
   LoggingHandlerMQTT.emit()
        │── repeated message?  ──► suppress, emit count each period
        │── option == "all"    ──► print to console
        │── connected?  yes    ──► publish(topic, record)  (+ drain buffer)
        │               no     ──► ring buffer (128 records, oldest dropped)
```

The handler registers a connection-state handler; when MQTT transport
connects, buffered records are drained to the topic in order. Repeated
records (same message, logger name and level) are suppressed and
summarised as `Repeated message count: N` at most once per
`AIKO_LOG_REPEAT_PERIOD` seconds.

### Implementation notes

- This is a low-level module used *by* the framework — keep static
  dependencies on the framework minimal. `ConnectionState` is imported
  mid-file, after the standalone functions, to soften the circularity;
  `message/mqtt.py` deliberately cannot use `LoggingHandlerMQTT` to
  diagnose itself.
- `get_logger()` uppercases the last dotted component of `name` and
  **adds a handler on every call** — calling it twice for the same name
  duplicates output.
- The `__all__` list exports `get_level_name`, which does not exist (the
  function is `get_log_level_name`); harmless today because
  `utilities/__init__.py` imports names explicitly.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `LoggingHandlerMQTT` | Publish log records over MQTT; console echo (`option="all"`); ring-buffer until connected; suppress and summarise repeats | `aiko.message` (publish), `aiko.connection` (readiness), `logging.Handler` (parent) |
| *functions* `get_logger` et al. | Create configured loggers; translate level names for shared state and the `"_ALL"` propagation convention | `logging`; `process.py` (`aiko.logger()`), `actor.py` / `pipeline.py` (level changes) |

## Current limitations and roadmap

From the source `To Do` lists:

- `set_log_level(name, level)` with a registry of all loggers, so one,
  several or all can be changed at once
- Select debug versus default format on-the-fly from the current level;
  change `AIKO_LOG_MQTT` on-the-fly via ECProducer
- Logging to file (chunked by date/time or size); make the logger a
  class, "nothing global!"
- `AIKO_LOG_REPEAT_DEPTH` (suppressing *sets* of repeating messages) is
  unimplemented
- `emit()` catches bare `Exception` (marked in-source as hiding problems)
  and `__del__` is a stub; no unit tests exist for this module

## Related concepts

- [Configuration](configuration.md) — same `AIKO_*` environment-variable
  style; supplies namespace/host/pid for the log topic
- [Lock](lock.md) — uses this module for its diagnostics
- [Design overview](../design_overview.md) — Recorder and Dashboard, the
  consumers of MQTT log streams
