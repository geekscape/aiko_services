---
title: Metrics utility
description: Placeholder for framework-wide metrics collection — currently
  a single memory-usage helper that does not compile and is not imported;
  the roadmap (Pipeline timing, MQTT distribution, Dashboard) is the value
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/metrics.py
related: [design_overview, pipeline, dashboard, system]
version: "0.6"
last_updated: 2026-07-05
---

# Metrics utility

## Overview

The metrics utility is intended to become the home of **framework-wide
metrics collection**: Pipeline / PipelineElement timing and resource
usage, general Actor and MQTT Service metrics, distribution over MQTT
and Aiko Services Dashboard display. Today it is a **placeholder**: it contains
one function, `print_memory_usage()`, exports nothing (`__all__ = []`),
is not imported by `utilities/__init__.py`, has no callers — and does
not currently compile (see limitations).

**Why it exists**: the `To Do` header is effectively a design sketch for
the metrics subsystem. For working memory/uptime readings *today*, use
the [system](system.md) utility instead:

```python
from aiko_services.main.utilities import print_memory_used
print_memory_used("Frame 42: ")   # the working equivalent, in system.py
```

## For application developers

### Command-line usage

There is no CLI and nothing exercises this module; do not import it until
the syntax error is fixed.

### Public API

None exported (`__all__ = []`). The single (intended) function:

```python
def print_memory_usage(label, unit="Mb")   # unit: "Kb"|"Mb"|"Gb"|"Tb"
```

It is meant to run `gc.collect()`, read `psutil.virtual_memory().used`,
scale it by the chosen binary unit and print `"{label}: Memory used:
..."`. Note this duplicates — less completely — what
[system](system.md).`print_virtual_memory()` already provides.

## For framework developers (internals)

### Design

Planned rather than implemented. From the `To Do` header, the intended
shape is:

```
  PipelineElement / Actor
        │  timing, resource usage
        ▼
  Metrics ──► self.share[]  (ECProducer shared state)
        │
        ├──► Aiko Services Dashboard  ("metrics:0" dashboard_plugin.py)
        └──► MQTT ──► InfluxDB / DynamoDB / Redis
                      ──► CloudWatch / DataDog consolidation
```

That is: metrics gathered where work happens
([Pipeline](../pipeline.md), Actors), published as shared state so the
[Dashboard](../dashboard.md) can display them via a `metrics:0` plugin,
and optionally distributed via MQTT into time-series storage and cloud
monitoring services.

### CRC card

The module is purely functions; one row describes the module itself:

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `metrics` (module) | (Planned) collect and publish framework metrics — Pipeline/PipelineElement timing, Actor and MQTT Service counters; (present) a broken host-memory print helper | `psutil`; [Pipeline](../pipeline.md), [Share](../share.md), [Dashboard](../dashboard.md) (all planned) |

## Current limitations and roadmap

Implemented behaviour: **none usable**.

- **Syntax error** — the module does not compile:
  `raise ValueError(f"Unknown unit: {unit}"` at line 47 is missing its
  closing parenthesis (`SyntaxError: '(' was never closed`). This is
  harmless only because nothing imports the module
- Even once fixed, the print statement hard-codes `Gb` in its output
  regardless of the unit selected, and the functionality duplicates
  [system](system.md).`print_virtual_memory()`
- Stale import: `from aiko_services.component import Interface` predates
  the `aiko_services.main` package layout (and `Interface` is unused)
- Not listed in `utilities/__init__.py`; `__all__` is empty

From the source `To Do` list (all planned):

- PipelineElement metrics: Dashboard support via `self.share[]`, a
  `metrics:0` `dashboard_plugin.py`, and Pipeline/PipelineElement
  timing and resource usage collected here
- General Aiko Services framework and MQTT Service metrics (any Actor,
  e.g. AlohaHonua), with Aiko Services Dashboard support
- Distribution via MQTT; storage in InfluxDB, DynamoDB or Redis;
  consolidation to CloudWatch, DataDog, etc

## Related concepts

- [System utility](system.md) — the working memory/uptime helpers to use
  today
- [Pipeline](../pipeline.md) — the primary source of timing metrics
- [Dashboard](../dashboard.md) — the intended display surface
- [Share](../share.md) — the shared-state mechanism metrics would ride
