---
title: AlohaHonua example index
description: Index of the AlohaHonua (hello world) tutorial documents —
  the graduated four-stage introduction to Actors, discovery, remote
  commands and request / response
type: index
audience: [developers, end-users]
status: draft
ste: false
source:
  - src/aiko_services/examples/aloha_honua
related: [actor, service, discovery, registrar]
version: "0.6"
last_updated: 2026-07-06
---

# AlohaHonua example index

The Aiko Services "hello world": four small programs in
`src/aiko_services/examples/aloha_honua/` that introduce distributed
[Actors](../../concepts/actor.md) one feature at a time. All four
stages are covered by a single concept document:

- [AlohaHonua hello-world Actor tutorial](aloha_honua.md)

## Source files

| Source file | Demonstrates |
|-------------|--------------|
| `aloha_honua_0.py` | The minimal `AlohaHonua` Actor — discoverable Service, remotely callable `aloha(name)`, Share entries, distributed logging |
| `aloha_honua_1.py` | A client program — `click` arguments, discovery with `aiko.do_command()` and a `ServiceFilter`, remote fire-and-forget call |
| `aloha_honua_2.py` | Actor and client in one file as a `click` group: `hoomaka` (start), `aloha` (call), `ku` (remote stop) |
| `aloha_honua_3.py` | `aiko.do_request()` — remote call with a reply on a caller-provided topic, and the `AlohaHonuaResponse` Interface |

The source directory also contains a narrative
[ReadMe](../../../src/aiko_services/examples/aloha_honua/ReadMe.md)
with a beginner's line-by-line walk-through of stage 0, an
architecture diagram (`aiko_diagram_0.png`) and a Dashboard screenshot
(`aiko_dashboard_0a.png`).

## Reading path

Absolute beginners should start with the source
[ReadMe](../../../src/aiko_services/examples/aloha_honua/ReadMe.md)
walk-through of `aloha_honua_0.py`, running it alongside
`scripts/system_start.sh` and the
[Dashboard](../../concepts/dashboard.md). Then read
[aloha_honua.md](aloha_honua.md) and work through stages 1, 2 and 3
in order — each file's usage header lists the exact terminal
sessions to run.

## Related documentation

- [Actor](../../concepts/actor.md) — the base class of every stage
- [Service](../../concepts/service.md) — Service identity and
  `ServiceFilter` matching
- [Discovery](../../concepts/discovery.md) — `do_command()` and
  `do_request()` used by the client stages
- [Registrar](../../concepts/registrar.md) — the Core Service that
  answers discovery
- [Process](../../concepts/process.md) — the event loop every stage
  runs
- [Share](../../concepts/share.md) — the state stage 0 publishes to
  the Dashboard
- [Dashboard](../../concepts/dashboard.md) — monitoring the running
  Actor
