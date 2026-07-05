---
title: Design overview — Storage, HyperSpace, Category, Dependency, ProcessManager
description: Executive overview and conceptual diagram of the Aiko Services
  distributed system infrastructure
type: overview
audience: [architects, developers, end-users]
status: draft
version: "0.6"
last_updated: 2026-07-05
related: [dependency, category, hyperspace, storage, process_manager,
  service, actor, share, registrar, lifecycle, message]
---

# Design overview

## Executive summary

Aiko Services is a distributed system framework in which every unit of
functionality — [Service](service.md), [Actor](actor.md), Agent,
[PipelineElement](pipeline_element.md), [Pipeline](pipeline.md) — is a
network-discoverable, message-driven component. This document is the
executive overview of the *structural model*; the full framework catalog
— runtime foundations, composition, messaging, Services and Pipelines —
is indexed in [ReadMe.md](ReadMe.md). The five structural concepts answer
the questions every distributed system must eventually answer:

| Question | Concept | Analogy |
|----------|---------|---------|
| How do I *refer to* a Service that may not be running yet, may be local or remote? | [Dependency](dependency.md) | A file-system symbolic link / URL |
| How do I *group and organise* those references? | [Category](category.md) | A directory |
| How do I *navigate* everything as one coherent, persistent graph? | [HyperSpace](hyperspace.md) | The root file-system, `/` |
| How is all of that *persisted*? | [Storage](storage.md) | The disk / block layer |
| How do the referenced Services actually *get started and stopped*? | [ProcessManager](process_manager.md) | Unix `init` (pid 1) |

Together they form something deliberately reminiscent of a file-system — but
generalised into a **distributed, directed network graph of live Service
references**: a mash-up of hypermedia ("hyperspace"), directed graphs and
file-system concepts. Where a file-system organises inert files on one host,
HyperSpace organises *references to running (or runnable) Services across
many hosts*, with discovery, lifecycle management and persistence attached to
every entry.

## Conceptual diagram

```
                    Aiko Services namespace (MQTT transport + Registrar discovery)
  ┌───────────────────────────────────────────────────────────────────────────────┐
  │                                                                               │
  │   HyperSpace  (root Category + LifeCycleManager of Categories)                │
  │   ═══════════════════════════════════════════════════════════                │
  │                                                                               │
  │        /                                    in-memory graph of Entries        │
  │        ├── models/                ◄─ Category   (container)                   │
  │        │    ├── yolo_v8           ◄─ Dependency (leaf: Service reference)     │
  │        │    └── shared/           ◄─ Category                                 │
  │        │         └── llm_gemma    ◄─ Dependency ──┐                           │
  │        └── agents/                ◄─ Category     │  "link": one Entry may    │
  │             └── llm_gemma         ◄─ Dependency ──┘  appear on many paths,    │
  │                                                      so the structure is a    │
  │                │            ▲                        graph, not just a tree   │
  │       persists │            │ loads at startup                                │
  │                ▼            │                                                 │
  │   Storage SPI  (StorageFile: directories + files + symbolic links)            │
  │   ─────────────────────────────────────────────────────────────────           │
  │                                                                               │
  │   Each Dependency carries three coordinates ...                               │
  │                                                                               │
  │      Dependency ┬── service_filter          "WHAT":  discover the Service     │
  │                 │      (name, protocol,              via the Registrar        │
  │                 │       transport, owner, tags)                               │
  │                 ├── lifecycle_manager_url   "WHO":   which LifeCycleManager   │
  │                 │                                    starts / stops it        │
  │                 └── storage_url             "WHERE": which Storage persists   │
  │                                                      its definition/content   │
  │                                                                               │
  │   ProcessManager  (a LifeCycleManager: creates/destroys OS processes,         │
  │   ══════════════   one per host, analogous to Unix init pid 1)                │
  │        │                                                                      │
  │        ├── <000001>  aiko_registrar          ◄─ managed OS processes          │
  │        ├── <000002>  aiko_pipeline create …                                   │
  │        └── <000003>  python my_agent.py                                       │
  │                                                                               │
  └───────────────────────────────────────────────────────────────────────────────┘
```

## The type hierarchy: the Composite design pattern

The heart of the design is the *Composite* pattern, applied twice — once
in-memory and once on disk:

```
   In-memory (Actors / Interfaces)          On disk (StorageFile)
   ───────────────────────────────          ─────────────────────
   Dependency        = Component            file           (leaf)
   Category          = Container,           directory      (container)
                       and also a
                       Dependency
   HyperSpace        = root Category        the initialized root, "."
                       + LifeCycleManager
```

Because a Category **is-a** Dependency, any Category can be an Entry inside
another Category — that single rule produces arbitrarily deep, navigable
structures with path names like `category_a/category_b/entry_c`. Because
StorageFile represents Entries as *symbolic links* to content-addressed
storage, the same Entry can be linked at multiple paths — turning the tree
into a directed graph.

The Python class hierarchy mirrors this:

```
   Dependency (Interface)
        △
        │ is-a
   Category (Actor, Dependency)
        △
        │ is-a
   HyperSpace (Category, Actor)

   Storage (Actor)                  ◄─ SPI, implemented by StorageFileImpl
   ProcessManager (Actor)           ◄─ a LifeCycleManager (planned unification)
```

## How a Service reference comes alive

The end-to-end story that these five concepts enable:

1. An application developer **adds an Entry** to HyperSpace at a path, e.g.
   `agents/llm_gemma`, providing a *ServiceFilter* (and optionally a
   LifeCycleManager URL and Storage URL). This creates a
   [Dependency](dependency.md) inside a [Category](category.md), and
   [Storage](storage.md) persists it.
2. When the Dependency needs to be *resolved*, the ServiceFilter is used for
   **discovery** via the Registrar. If the Service is already running, the
   Dependency's `service` field becomes a local or remote reference to it.
3. If the Service is *not* running, the `lifecycle_manager_url` identifies
   the LifeCycleManager — typically a [ProcessManager](process_manager.md) —
   that can **create the operating system process** for it, and the
   `storage_url` identifies where its definition/content can be loaded from.
   (This full lazy-loading loop is the design intent; parts are still
   work-in-progress — see the individual documents.)
4. On restart, [HyperSpace](hyperspace.md) **reloads the entire graph** from
   Storage, so the structure of the distributed system survives any
   individual process.

## Distributed and bootstrap operation

Every one of these components is itself an Aiko Services
[*Actor*](actor.md): it registers with the [Registrar](registrar.md),
exposes its state via eventually-consistent shared state
([ECProducer](share.md), visible in the Aiko Services
[Dashboard](dashboard.md)) and is operated remotely over
[MQTT](message.md). All CLI
commands follow the same pattern: discover the target Actor by
*ServiceFilter* (name defaults to the local hostname), invoke the method
remotely, print any response.

Because you cannot use a distributed Storage Service to bootstrap the
Storage Service itself, StorageFile also operates in **bootstrap mode**
(`--bootstrap` / `-b`): the same commands run standalone, directly against
the local file-system, with no Services running at all. This is how a fresh
host is initialized before HyperSpace and ProcessManager come up.

## Command-line surface (summary)

| Tool | Operates on | Key commands |
|------|-------------|--------------|
| `aiko_hyperspace` | the live HyperSpace graph | `run`, `add`, `create`, `list`, `remove`, `destroy`, `update`, `dump`, `exit` |
| `aiko_storage_file` | persistence (Service or bootstrap) | `initialize`, `run`, `add`, `create`, `link`, `list`, `remove`, `destroy`, `dump`, `exit` |
| `./category.py` | an individual Category Actor | `run`, `add`, `list`, `remove`, `update`, `exit` |
| `aiko_process` | OS processes on a host | `run`, `create`, `list`, `destroy`, `dump`, `exit` |

## Design principles

- **Everything is a Service reference.** Dependencies decouple *naming and
  structure* from *liveness*: the graph exists whether or not the referenced
  Services are running.
- **Structure is a graph, persistence is pluggable.** HyperSpace owns the
  in-memory graph; the Storage SPI hides the backing store (file-system
  today; in-memory, SQLite, MQTT, ValKey are envisaged).
- **Uniform CRUD verbs everywhere.** `create/add`, `list`, `update`,
  `remove/destroy` are used consistently across HyperSpace, Category,
  Storage and ProcessManager — and consistently between Python APIs and CLI
  commands.
- **Bootstrappable.** The system can be brought up from a bare file-system
  with no network infrastructure, then transition seamlessly to distributed
  operation.
- **Observable.** All components publish shared state (entry counts,
  metrics, log level) through ECProducer for the Dashboard and other
  consumers.

## Related documents

- [Dependency](dependency.md)
- [Category](category.md)
- [HyperSpace](hyperspace.md)
- [Storage](storage.md)
- [ProcessManager](process_manager.md)
- [Concepts guide index](ReadMe.md) — the full framework catalog
- [Service](service.md) / [Actor](actor.md) — the component model these
  structures refer to
- [Registrar](registrar.md) — the discovery hub behind every ServiceFilter
- [Share (Eventual Consistency)](share.md) — the shared-state machinery
- [LifeCycle](lifecycle.md) — the manager/client pattern ProcessManager
  will realise
