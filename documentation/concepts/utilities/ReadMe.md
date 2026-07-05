---
title: Utilities concepts index
description: Index of the concept documents for the Aiko Services utility
  modules in src/aiko_services/main/utilities/
type: index
audience: [developers]
status: work-in-progress
related: [design_overview]
version: "0.6"
last_updated: 2026-07-05
---

# Utilities concepts index

Concept documents for the utility modules in
`src/aiko_services/main/utilities/` — the dependency-light helpers that
the rest of the Aiko Services framework is built on. Most are exported
via `utilities/__init__.py` and imported with
`from aiko_services.main.utilities import *`.

Part of the [Concepts guide](../ReadMe.md).

| Concept | Summary |
|---------|---------|
| [configuration](configuration.md) | Environment-driven discovery of the MQTT server, namespace and process identity (hostname, username, PID) used to bootstrap every process |
| [context](context.md) | Minimal process-global holder for the `(aiko, message)` pair, set once at process start and readable from anywhere |
| [graph](graph.md) | Lightweight directed graph — Nodes with ordered successors — plus an S-expression graph-definition parser; the foundation of Pipeline dataflow graphs |
| [importer](importer.md) | Dynamic module loading by file pathname or dotted module name, with caching — loads PipelineElements, Components and Dashboard plugins at runtime |
| [lock](lock.md) | Named, diagnosable wrapper around `threading.Lock` that records who holds it; `AIKO_LOG_LEVEL_LOCK=DEBUG` watches contention live |
| [logger](logger.md) | Logging with console and/or MQTT transport, ring buffering and repeated-message suppression, configured by `AIKO_LOG_*` environment variables |
| [lru_cache](lru_cache.md) | Minimal fixed-size least-recently-used cache built on `OrderedDict`, used for log records, audio clips and frame diagnostics |
| [metrics](metrics.md) | Placeholder for framework-wide metrics (Pipeline timing, MQTT distribution, Dashboard); currently one broken memory helper — the roadmap is the value |
| [network](network.md) | Discover which TCP/UDP ports are in use on this host and find a free port in a range — used by DataSchemes that open sockets |
| [parser](parser.md) | The S-expression `generate()`/`parse()` pair defining the wire format of every Aiko Services message — lists, dictionaries, canonical symbols, the `0:` None sentinel |
| [probe](probe.md) | Empty placeholder file — zero bytes; presumably reserved for a future diagnostic probe capability |
| [system](system.md) | Host and process introspection — `dir_base_name()` path splitting, process/virtual memory usage, cross-platform system uptime |
| [thread](thread.md) | `ThreadManager`: a named-thread registry with a background janitor pruning finished threads — written for ProcessManager, not yet wired in |
| [utc_iso8601](utc_iso8601.md) | Conversions between epoch seconds, `datetime`, UTC ISO 8601 strings and local time — the framework's timestamp vocabulary |

## Related concepts

- [Concepts guide](../ReadMe.md) — the parent index of all Aiko Services
  concept documents
- [Design overview](../design_overview.md) — where the utilities sit in
  the overall architecture
