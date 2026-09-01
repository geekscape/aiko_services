---
title: "Aiko Services — Specifications: Runtime, Services, Actors, Agents"
description: Normative-voice specifications (RFC 2119) for the wire protocol,
  runtime, Services, Actors and Agents. Verify each section against
  master before promotion
type: specification
audience: [architects, developers, ai-coding-agents]
status: draft-for-verification
ste: adapted
related: [p_00_DesignPrinciples, s_01_RepositoryLayout,
  s_02_InterfaceComposition]
last_updated: 2026-07-31
---

# Aiko Services — Specifications: Runtime, Services, Actors, Agents

**Status:** Draft for verification. This document was drafted from a deep review of the codebase
(`src/aiko_services/main` as of early 2026) and from the framework's documented behavior. It is
written in the *normative voice* it should eventually carry, but every section must be verified
against current `master` before being promoted to normative. Items marked **[VERIFY]** are the
highest-priority checks. The intent is that this document, completed, becomes
`docs/specifications/` — split into one file per numbered section.

Conformance keywords MUST / MUST NOT / SHOULD / MAY are used in the RFC 2119 sense.

**Verification aid (2026-07-05):** `documentation/concepts/` now documents the implemented
behavior of every subsystem that this specification covers. There is one OKF document for
each concept. Each document separates implemented behavior from planned behavior, and gives
the wire protocols in the Public API sections
(see especially `utilities/parser.md` for the S-expression grammar, `process.md` for the topic
namespace and Registrar boot protocol, `service.md`, `actor.md`, `share.md`, `registrar.md` and
`pipeline.md`). Check each **[VERIFY]** item against the corresponding concept document first,
then against `master`.

---

## 1. The wire protocol (language-neutral core)

This section is the heart of the language-agnosticism claim and the document a non-Python
implementation would be built from.

### 1.1 Message encoding

Messages are S-expressions encoded as UTF-8 text: `(command argument ...)`. Arguments are atoms or
nested S-expressions. The canonical parser/generator in the reference implementation defines
the tokenization, quoting and escaping rules. You MUST extract those rules here as a grammar
(EBNF)
rather than left implicit in `utilities/parser.py`. **[VERIFY: exact quoting/escape rules,
treatment of binary payloads, maximum practical message size over MQTT.]**

*Rationale (ADR-002):* S-expressions over JSON/protobuf — homoiconic, trivially parsed on
microcontrollers, human-readable on the wire, LISP heritage. JSON appears only inside specific
payloads (for example, PipelineDefinitions) where structured documents are being transported, not for
control messages.

### 1.2 Topic namespace

Every Service owns a set of MQTT topics derived from its identity, never configured by hand:

    {namespace}/{host}/{process_id}/{service_id}/in       — commands to the Service
    {namespace}/{host}/{process_id}/{service_id}/out      — responses / events from the Service
    {namespace}/{host}/{process_id}/{service_id}/state    — ECProducer state publications
    {namespace}/{host}/{process_id}/{service_id}/control  — framework-level control
    {namespace}/service/registrar                          — Registrar rendezvous (well-known)

**[VERIFY: the exact topic path components and their order. The well-known registrar topic
name. Whether
`control` and `state` are both present in the current master. The LWT (last-will) topic and
payload used for crash detection.]**

A Service MUST treat its topic paths as opaque and derived. Application code MUST NOT construct
peer topic strings (Principle P5).

### 1.3 Service identity

A Service is described by five fields (the ServiceFields tuple): **name**, **protocol**,
**transport**, **owner**, **tags**. The `protocol` field is a versioned URI-style identifier, for example
`github.com/geekscape/aiko_services/protocol/actor:0`. Protocol identifiers are the unit of
compatibility: a client requiring `storage:1` MUST be served by any Service declaring it,
regardless of implementation language. Tags are `key=value` strings used for discovery filtering.
**[VERIFY: field order and exact protocol URI prefix in current master.]**

### 1.4 Registrar protocol

The Registrar is the discovery Actor. The protocol MUST specify, as message sequences:

- **Bootstrap:** how a starting Process learns the Registrar's topic (well-known topic plus the
  Registrar's periodic/retained `(primary ...)` announcement), and the behavior when no Registrar
  is present (wait/retry, and optionally start one). **[VERIFY: retained-message compared with broadcast
  mechanics, and the primary-election behavior when multiple registrars start.]**
- **Registration:** `(add <service_fields...>)` on the `in` topic of the Registrar.
  Deregistration is `(remove ...)`. Crash-deregistration uses the MQTT last will.
- **Query/share:** `(share ...)` / query messages with filters over protocol, name, owner and tags.
  results delivered as one-way messages to the requester's reply topic, followed by incremental
  add/remove notifications if the query is standing. **[VERIFY: exact verbs and whether standing
  queries are supported directly or through ECConsumer on the Registrar's state.]**

Conformance: a Registrar implementation in any language passing the golden traces for this section
is a valid Registrar.

### 1.5 Actor invocation protocol

Invoking method `m(a, b)` on a remote Actor is publishing `(m a b)` to that Actor's `in` topic.
There is no return value and no acknowledgment at the protocol level (Principle P1). Delivery
semantics are those of the transport (MQTT QoS). The assumptions of the framework about the QoS level MUST
be stated here — **[VERIFY: default QoS]**). Message arguments MUST be representable as
S-expressions. A complex payload is a nested expression, or JSON-in-a-string by documented
convention per interface.

### 1.6 Eventual-consistency state protocol (ECProducer / ECConsumer)

An ECProducer publishes a Service's state dictionary on its `state` topic: a full snapshot on
consumer attach, then incremental `(update key value)` / `(add key value)` / `(remove key)`
messages on change. An ECConsumer maintains a converging local replica and surfaces change
callbacks. The spec MUST define: snapshot request/delivery sequence, incremental message grammar,
nested-key syntax (for example, `a.b.c`), and the (deliberate) absence of ordering guarantees across
producers. **[VERIFY: exact verbs, snapshot mechanism, nested-dictionary key encoding.]**

### 1.7 Lease protocol

Leases bound the lifetime of distributed resources so crashes cannot leak them: a lease is granted
with a duration, MUST be extended before expiry by the holder, and expiry triggers reclamation by
the granter. The spec defines grant/extend/expire message forms and recommended durations.
**[VERIFY: the message forms. Where leases are used in master — registrar entries, lifecycle clients,
streams.]**

### 1.8 Lifecycle protocol

LifeCycleManager / LifeCycleClient: a manager Actor creates client Actors (locally through
ProcessManager or remotely), tracks them through lease keep-alives, and destroys or recovers them. The
spec defines the manager→client creation handshake, the client→manager attachment message, and
failure behavior. **[VERIFY: handshake details.]**

---

## 2. Runtime specification (`aiko_services.runtime`)

The Runtime is everything a single OS process needs to host Services. It is mechanism only: it
MUST NOT contain concrete Services, but only what the bootstrap needs.

### 2.1 Process and event loop

Each OS process hosts exactly one Aiko **Process** (singleton, `aiko.process`): a single-threaded
event loop that owns all framework execution. The event system gives: **mailboxes** (named
queues whose handlers are invoked in order — the Actor substrate), **timers** (one-shot and
periodic handlers), and **flush/termination** semantics. All framework callbacks are dispatched on
the event-loop thread. User code MUST NOT block it (long work belongs in a worker, handed back through
a mailbox) and external threads MUST NOT touch Service state except by posting messages.
`process.run()` / `process.terminate()` define startup and orderly shutdown, including Registrar
deregistration. **[VERIFY: the precise event API names. The threading model of the MQTT client relative to
the event loop.]**

### 2.2 Transport abstraction

`runtime/transport/` defines the transport-neutral interface — connect, disconnect, publish,
subscribe, last-will registration, connection-state callbacks — with MQTT as the reference
implementation. The interface MUST be small enough that a Zenoh or serial transport is a plausible
weekend project. The transport choice is per-Service, through the `transport` ServiceField.

### 2.3 Message layer

`runtime/message/` owns S-expression parse/generate (the implementation of §1.1) and topic-path
construction (§1.2). No other package may construct topic strings or parse payloads unplanned.

### 2.4 Component / composition machinery

`runtime/component.py` gives the interface-composition mechanism specified in
`s_02_InterfaceComposition.md`: Interface base, implementation binding, `compose_instance`, and the
protocol-identifier registry mapping protocol URIs to interfaces.

### 2.5 Shared state, leases, lifecycle, state machines

ECProducer/ECConsumer (`share`), Lease, LifeCycleManager/Client (`lifecycle`), and the StateMachine
utility (`state`) are runtime mechanisms implementing §1.6–§1.8. StateMachine is a local utility
(explicit states, transitions, entry/exit actions). The framework and the applications both use it. It has
no wire protocol of its own but SHOULD publish current state through the owning Service's ECProducer.

### 2.6 Proxy / remote invocation

Given discovered ServiceFields, the runtime gives a proxy object whose method calls serialize
to §1.5 invocation messages — `do_command` and friends. The proxy MUST expose only one-way
semantics (Principle P1/P3). A convenience request/response helper lives at the application edge
and is implemented as two one-way messages with an explicit reply topic.

---

## 3. Service and Actor specification (`aiko_services.actors`)

### 3.1 Service

A **Service** is the unit of discovery. It has ServiceFields (§1.3) and owns topic paths
(§1.2). It registers with the Registrar on start, and deregisters on stop (§1.4). It MAY
expose state through an ECProducer. A Service without a mailbox is stateless with respect to the message system (for example, a
pure transformation hosted behind a Pipeline).

The necessary behavior is: add/remove the registration at the lifecycle boundaries. Configure
the last will, so that a crash causes deregistration. The tags and the protocol are immutable
after registration **[VERIFY: mutability]**.

### 3.2 Actor

An **Actor** is a Service plus a mailbox. The Actor queues the messages that arrive on its
`in` topic. It dispatches them **one at a time, in arrival order**, on the event-loop thread.
The dispatch maps `(method_name args...)` to the method `method_name` of the composed
instance. Unknown methods are
logged and dropped **[VERIFY: error behavior]**. An Actor is the sole writer of its own state
(Principle P2). Standard composed interfaces give every Actor for free: lifecycle participation,
ECProducer state publication (including framework-standard keys such as lifecycle state and
log level **[VERIFY: standard key set]**), and control verbs on the `control` topic
(for example, terminate, log-level) **[VERIFY: standard control verbs]**.

### 3.3 Built-in Actors

Normative behavior specs (each one page, message-sequence oriented) for: **Registrar** (§1.4),
**ProcessManager** (spawn/monitor/terminate OS processes hosting Services), **LifeCycleManager**
(§1.8), **Dashboard** (observer composing ECConsumers — explicitly *not* privileged, Principle
P6), **Recorder** (subscribes and keeps message traffic — the seed of replay/observability).

---

## 4. Pipeline and Agent specification (`aiko_services.pipeline`, `aiko_services.agents`)

### 4.1 PipelineDefinition

A Pipeline is constructed from a declarative definition (JSON document) containing: pipeline name
and version. Next is the element list: the name of each element, its implementation reference
(module/class for local deployment, or a service filter for remote), its parameters, and its
declared input/output names. Last is
the graph (edges that connect element outputs to element inputs). The definition is data. The
Pipeline Actor is its interpreter (Principle P8). The spec MUST include the JSON schema — this is
also where the planned I/O schema validation lands: each element declares the names *and types* of
its inputs/outputs, and graph construction MUST fail on mismatch. **[VERIFY: current definition
format and graph encoding in master.]**

### 4.2 Streams and frames

A Pipeline processes **streams**, each identified by a stream id and carrying per-stream
parameters. A stream is a sequence of **frames**. Each frame is a dictionary of named data
plus a frame id.
Element lifecycle per stream:

    start_stream(stream, stream_id)            — allocate per-stream state
    process_frame(stream, **inputs) → outputs  — transform one frame
    stop_stream(stream, stream_id)             — release per-stream state

`process_frame` returns its outputs *to the Pipeline runtime* (a local, in-process return — this is
the deliberate exception to "no return values", which is a *distributed* rule. The distributed
boundary is the Pipeline Actor, not the element call). Elements signal flow control through stream
events (okay / stop / error semantics — **[VERIFY: exact event enumeration]**). Frames MAY be
processed across local elements synchronously, and across remote elements through §1.5
messaging. The
graph author does not distinguish.

### 4.3 Agents

An **Agent** is an Actor whose behavior comes from one or more Pipelines plus policy. It
perceives (input streams), decides (ML elements, state machines, LLM calls), and acts (output
streams, messages to other Actors).

Concretely, `agents/` gives three things. First, an Agent base composition (Actor + Pipeline
host + goal/policy state through an ECProducer). Second, patterns for ML inference agents
(model-loading elements, batching, hardware targeting per P9). Third, the
LLM/MCP bridge. It exposes
Aiko Services and Pipelines as MCP tools and resources. Thus external AI systems can find and
drive them through the Registrar (the MCP Server/Client completion from the gap list). This
section is the least extracted-from-code and the most design-forward. It SHOULD be written as a
spec *before* implementation, as the first full exercise of the Phase 4 workflow.

---

## 5. Conformance

Every MUST in §1 is backed by at least one golden trace in `tests/conformance/`. An implementation
(in any language) claiming Aiko Services compatibility passes the §1 trace suite against a live
broker. The Python reference implementation additionally passes §2–§4 unit and integration suites.

### Update 2026-07-06 — examples as specification witnesses

The `documentation/examples/` audit adds verification material. It goes beyond the
concepts/elements documents already cited as verification aids. The aloha_honua stage 3
documents the only in-repo end-to-end witness of the `do_request()` request/response
exchange. It also shows the client that duplicates `DiscoveryResponse` by hand. That is the
reply-interface surface that this specification must define normatively. Also,
`system_pipelines/0_process_manager.json` is the sole committed witness
of the ProcessManager bootstrap definition format (a bare JSON list of
`str.split()` command lines, with no shell quoting. Specify or replace
before promoting R5). When promoting the wire-protocol sections, note
that examples currently stop Actors through `SystemExit` raised inside
handlers rather than any specified lifecycle verb.
