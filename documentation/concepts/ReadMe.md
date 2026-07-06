---
title: Aiko Services distributed system infrastructure documentation
description: Index of OKF concept documents covering the Aiko Services
  framework — runtime foundations, composition, messaging, Services,
  Pipelines, structure and persistence, tools and utilities
type: index
audience: [architects, developers, end-users]
status: draft
version: "0.6"
last_updated: 2026-07-06
---

# Aiko Services: distributed system infrastructure

This directory documents the concepts that make up the Aiko Services
framework, from the per-process event loop up to the distributed
structural model. One concept per file, following the Open Knowledge
Format (OKF) conventions:

- **One concept per file**, each self-contained and individually linkable
- **YAML front-matter** carrying metadata: title, description, type,
  audience, status, source files and related concepts
- **Audience-first sections** in every concept document, ordered from
  broadest to most specialised audience: *Overview*, then
  *For application developers* (Command-line usage, Public API), then
  *For framework developers* (Design, Implementation notes, CRC card)
- **Explicit cross-links** between related concepts

The full section structure and writing guidance is defined in the
constitution's OKF Concepts documentation template
(`documentation/constitution/okf_concept_template.md`).

## Start here

- [Design overview](design_overview.md) — executive summary and conceptual
  diagram of the structural model (Dependency, Category, HyperSpace,
  Storage, ProcessManager). Read this first for the distributed-system
  picture.

## Process runtime foundations

The single-process machinery that everything else builds on.

| Concept | One-line summary |
|---------|------------------|
| [Process](process.md) | The per-OS-process framework singleton — the `aiko` global, MQTT connection ownership, message dispatch, Service registration and Registrar tracking |
| [Event](event.md) | The cooperative event loop at the heart of every Aiko Services process — timer, mailbox, queue and flat-out handlers on a single event-loop thread |
| [Hook](hook.md) | Named extension points inside the framework that third-party developers attach handler functions to |
| [State](state.md) | A finite state machine wrapper (StateMachineOld) over the "transitions" package, used by the Registrar election |
| [Lease](lease.md) | A time-limited claim on a resource that expires unless extended — the keep-alive and garbage-collection primitive |
| [Connection](connection.md) | A per-process ladder of connectivity states — from no network up to Registrar available — with change handlers |
| [Utilities](utilities/ReadMe.md) | Index of the fourteen utility modules: S-expression parser, configuration, logging, graph, importer and friends |

## Composition

How Aiko Services components are assembled from Interfaces —
"Design by Composition of Interfaces".

| Concept | One-line summary |
|---------|------------------|
| [Component](component.md) | The composition engine — compose_class() and compose_instance() build concrete classes from Interface contracts |
| [Context](context.md) | The single constructor argument for composed components, plus the Interface base class and its default-implementation registry |
| [Proxy](proxy.md) | Transparent method interception — ProxyAllMethods routes every public method call through a proxy function |

## Messaging

| Concept | One-line summary |
|---------|------------------|
| [Message](message.md) | The publish/subscribe abstraction — MQTT implementation (connection lifecycle, last-will-and-testament) and the Castaway null implementation |
| [Transport](transport.md) | The layer above Message that turns remote Services into callable Python objects via dynamic proxies |

## Services

The distributed component model: discoverable, message-addressable units.

| Concept | One-line summary |
|---------|------------------|
| [Service](service.md) | The distributed component primitive — described by topic path, name, protocol, transport, owner and tags |
| [Actor](actor.md) | A Service following the Actor Model — mailboxes invoked one at a time on the event-loop thread |
| [Share (Eventual Consistency)](share.md) | ECProducer publishes live state that any number of ECConsumers replicate and watch; plus the ServicesCache |
| [LifeCycle](lifecycle.md) | The LifeCycleManager / LifeCycleClient pair — creating, tracking and destroying fleets of client Actors |
| [Registrar](registrar.md) | The Service discovery hub — live directory, add/remove streams, share/history queries, primary election |
| [Discovery](discovery.md) | Finding and invoking remote Services — ServiceDiscovery, remote proxies, do_discovery / do_command / do_request |
| [Recorder](recorder.md) | A Service that ring-buffers log topics and republishes them as shared state for the Dashboard |

## Pipelines

Dataflow: graphs of PipelineElements processing Streams of Frames.

| Concept | One-line summary |
|---------|------------------|
| [Pipeline](pipeline.md) | An Actor executing a graph of PipelineElements from a validated PipelineDefinition JSON file, locally or distributed |
| [PipelineElement](pipeline_element.md) | The unit of work — the start_stream / process_frame / stop_stream contract, local or remote deployment |
| [Parameters](parameters.md) | How parameters are declared in the PipelineDefinition, overridden per-Stream and resolved by get_parameter() |
| [Stream](stream.md) | A leased flow of Frames — Stream and Frame dataclasses, StreamEvent / StreamState semantics and lifecycle |
| [Scheme](scheme.md) | The pluggable mapping from URL schemes (file:, zmq:, ...) to concrete data access code |
| [Data Source / Target](data_source_target.md) | PipelineElement base classes that load and store frames of data at URL-named locations |

## Structure and persistence

The distributed structural model — see the
[Design overview](design_overview.md).

| Concept | One-line summary |
|---------|------------------|
| [Dependency](dependency.md) | A reference to a distributed Service — discovery filter, LifeCycleManager URL and Storage URL |
| [Category](category.md) | An Actor that groups Entries — Dependencies and other Categories — into a named, observable collection |
| [HyperSpace](hyperspace.md) | The root Category and LifeCycleManager of Categories — a unified, persistent, navigable network graph |
| [Storage](storage.md) | The persistence SPI and StorageFile, its file-system implementation using directories, files and symbolic links |
| [ProcessManager](process_manager.md) | Create, list and destroy operating system processes in a unified, distributed fashion — analogous to Unix init |

## Tools

| Concept | One-line summary |
|---------|------------------|
| [Dashboard](dashboard.md) | A terminal user interface for observing and controlling every running Service |
| [Dashboard plug-in](dashboard_plugin.md) | How to extend the Dashboard with a custom page (ServiceFrame) for a Service name or protocol |

## Reading paths

- **Architects / evaluators**: [Design overview](design_overview.md), then
  the *Overview* sections of [Service](service.md), [Pipeline](pipeline.md)
  and [HyperSpace](hyperspace.md).
- **Application developers**: [Service](service.md), [Actor](actor.md) and
  [Pipeline](pipeline.md) *For application developers* sections first;
  then [Parameters](parameters.md), [Stream](stream.md),
  [Data Source / Target](data_source_target.md) for pipeline work, or
  [HyperSpace](hyperspace.md) and [Category](category.md) for the
  structural model; [Dashboard](dashboard.md) to observe it all running.
- **Framework developers**: bottom-up — [Event](event.md),
  [Process](process.md), [Component](component.md) / [Context](context.md),
  [Message](message.md), [Service](service.md), [Actor](actor.md),
  [Share (Eventual Consistency)](share.md), [Registrar](registrar.md) —
  paying particular attention to the *For framework developers* sections,
  the [utilities/parser](utilities/parser.md) wire format, and the
  Composite design pattern described in [Dependency](dependency.md) and
  [Storage](storage.md).

## Status

These subsystems are under active development (version 0.6). Each document
distinguishes **implemented** behaviour from **planned / work-in-progress**
behaviour, based on the source code as of 2026-07-05.

## Related documentation

- [PipelineElements guide](../elements/ReadMe.md) — OKF documentation for
  the element library in `src/aiko_services/elements/` (control,
  gstreamer, media, observe, utilities), built on the Pipeline concepts
  above
- [Examples guide](../examples/ReadMe.md) — OKF documentation for the
  example applications in `src/aiko_services/examples/`, from the
  AlohaHonua hello-world Actor tutorial to computer vision, speech, LLM
  and robot applications
