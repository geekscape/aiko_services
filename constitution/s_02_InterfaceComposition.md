---
title: Aiko Services — Design by Composition of Interfaces
description: How behavior is declared (Interfaces), given
  (Implementations) and bound (composition), plus the canonical interface
  catalog — the design behind Principle P7
type: design
audience: [architects, developers, ai-coding-agents]
status: draft-for-verification
ste: adapted
related: [p_00_DesignPrinciples, s_00_Specifications, e_03_FirstClassAgents,
  ../adr/ADR-021_SynthesizedDefaultInit, ../adr/ADR-022_CompositionBoundary]
last_updated: 2026-07-31
---

# Aiko Services — Design by Composition of Interfaces

**Status:** Draft for verification against the current `master`. Principle P7 and §2.4 of
the specifications refer to this design. It gives four things: how behavior is declared
(Interfaces), how it is supplied (Implementations), how the two are bound (composition), and
the canonical interface catalog. One rule governs all of it: **every interface method is
asynchronous and returns nothing.** A method is a message, and a message is
fire-and-forget.

**Verification:** done 2026-07-13, as the full per-file audit [Privately maintained].
The drift findings are annotated in place in the §3 catalog (see the verification record
there). This document stays draft until e_10 Phase 4 regenerates the
catalog from the normalized source. The composition boundary (which public APIs must follow
this design, and the three exempt categories) is ADR-022. The synthesized default `__init__`
is ADR-021.

---

## 1. The pattern

Three kinds of class, with strictly separated roles:

**Interface** — a pure abstract class: method signatures only, no state, no implementation.
An Interface MAY refine other Interfaces (multiple inheritance of *declarations only*).

Every Interface binds to a versioned protocol identifier. The Interface *is* the Python
projection of that wire protocol. Its methods correspond one-to-one with `(method args…)`
messages.

**Implementation** — a concrete class that supplies one or more Interfaces. An
Implementation holds state, but its public surface is exactly the union of the Interfaces
that it implements. All the other members are private. An Implementation never inherits from
a different Implementation. To share behavior, compose the same Implementation. Do not make a
subclass of it.

**Composition** — `compose_instance(implementation_class, init_args)` assembles a concrete
component. It binds the implementation graph behind the declared Interfaces, and it registers
the
component's protocol identifier(s) for discovery. A default implementation is registered for
each Interface, and each composition can override it. Thus a test can substitute a fake
`Transport`, and an embedded build can substitute a lean `Registrar` client. No other binding
changes.

Sketch (names per the reference implementation — verify against `component.py`):

    class Interface:                      # marker base + composition support
        ...

    class Greeter(Interface):
        """protocol: …/greeter:0"""
        def greet(self, name): ...        # one-way; no return annotation other than None

    class GreeterImpl(Greeter):
        def __init__(self, context):      # context: composition-time wiring (service info, …)
            context.get_implementation("Actor")  # access composed siblings
        def greet(self, name):
            self.logger.info(f"Hello {name}")

    greeter = compose_instance(GreeterImpl, context)

A remote caller never sees `GreeterImpl`. It discovers a Service whose protocol is
`greeter:0`, then publishes `(greet Andy)` to the `in` topic of that Service. The Actor
mailbox dispatches to `greet`. Thus local and remote invocation have the same shape. This is
a deliberate Smalltalk echo. You always send a
message. Locality is an optimization.

## 2. The no-return-value discipline (what replaces return values)

Three patterns, in order of preference, replace every use a return value would have had:

**State observation (most queries).** The component publishes through an ECProducer, and
interested parties attach ECConsumers. Usually, what a `get_x()` would have returned must be
a key in shared state. This is push-on-change. It costs less than polling, it is one-to-many
by nature, and it tolerates a partition.
*(2026-07-13: the standing generalization of this pattern — a leased, filtered local replica with
a local non-blocking `get()` and filtered update call-backs — is the `ECCache` deliverable,
the composition rollout §2.1 [Privately maintained], which generalizes `ServicesCache`. It is also the MCP/A2A observation
shim [Privately maintained].)*

**Reply-to messaging (genuine requests).** The request message carries the caller's reply topic
(and a correlation token when the caller multiplexes):

    def find(self, filters, reply_topic): ...        # request
    # responder later publishes: (found <token> <results…>) to reply_topic

The response is itself a one-way message to an interface method the *caller* implements. Both
halves are declared: a request/response pair is two Interfaces (or two methods on mirrored
Interfaces), making the protocol symmetric and traceable.

**Event streams (continuous results).** Results that are sequences — frames, detections, telemetry
— are streams on `topic_out` or Pipeline graph edges, never iterated returns.

Errors follow the same rule: no exceptions cross the wire. A failed request produces an error
message to the reply topic, or an error value in shared state, per the owning interface's spec.

## 3. Canonical interface catalog

The framework-defining Interfaces, layered per the repository layout. The February review
listed eleven of them. This list is that catalog, reorganized to the new layout. Confirm
the names and the methods against the source before you promote the list to
`docs/interfaces/CATALOG.md`. After that, CI regenerates the catalog from the source and
diffs it against this document.

> **Verification record (2026-07-13).** The confirm-against-source pass was the full audit
> of `src/aiko_services/main/`, in the composition audit [Privately maintained]. Treat the entries below as
> the *target* catalog. Treat e_10 §1–§2 as the per-file *current* state.
>
> The drift found is:
>
> `ECProducer` and `ECConsumer` remain plain classes. Their real surfaces differ from the
> entries below (see the annotated entries). The `Registrar` Interface is an empty marker.
> Its wire commands are `add`/`remove`/`share`/`history` (there is no `query`), and
> `_topic_in_handler()` dispatches them by hand. The message layer is a classic `abc.ABC`
> (`Message` → `MQTT`, `Castaway`), not a framework Interface. No `Transport` Interface
> exists. `docs/interfaces/CATALOG.md` and its CI drift check do not exist yet.
>
> Remediation and the catalog regeneration are scheduled by e_10 (approved 2026-07-13). The
> boundary and the retrospective normalization are in ADR-022. The synthesized default
> `__init__` is in ADR-021.

**runtime/**

- `Interface` — composition marker base.
- `Service` — the discoverable unit. `add_tags(tags)` and `set_protocol(...)` at
  construction. The lifecycle drives the registration add/remove. Properties (local, not
  wire): ServiceFields, topic paths.
- `ServiceDiscovery` / Registrar-client — `find(filters, reply_topic)`, standing-query attach through
  ECConsumer on the Registrar.
- `Transport` — `connect()`, `disconnect()`, `publish(topic, payload)`,
  `subscribe(topic, handler)`, `set_last_will(topic, payload)`. *(Verified 2026-07-13: it
  does not exist. The current reality is `message/Message(abc.ABC)` with
  `publish(topic, payload)`,
  `subscribe(topic)`, `unsubscribe(topic)`, `set_last_will_and_testament(…)` — conversion
  target in e_10 §2.12.)*
- `ECProducerInterface` — `update(key, value)`, `add(key, value)`, `remove(key)`. These
  mutate local state, and the publication is the side effect. *(Verified 2026-07-13: it is a
  plain class. The real surface is
  `add_handler(handler)`, `get(item_name)`, `remove(item_name)`, `remove_handler(handler)`,
  `update(item_name, item_value)` — no `add`. Interface target in e_10 §2.1.)*
- `ECConsumerInterface` — `attach(state_topic, handler)`, `detach()`. *(Verified 2026-07-13:
  it is a plain class. The attach occurs in the constructor, and the teardown is
  `terminate()`. Interface target in e_10 §2.1.)*
- `Lease` — `extend()`, `expire()` plus granter-side `grant(duration, reply_topic)`.
- `LifeCycleManager` — `create(specification)`, `destroy(client_id)`.
- `LifeCycleClient` — `attach(manager_topic)`, keep-alive.
- `StateMachine` (local utility) — `transition(event)`, entry/exit handlers.

**actors/**

- `Actor` (refines `Service`) — mailbox dispatch. The standard control verbs are
  `terminate()` and `set_log_level(level)`. The standard state keys go through an ECProducer.
- `Registrar` (refines `Actor`) — `add(service_fields)`, `remove(service_id)`,
  `query(filters, reply_topic)`. *(Verified 2026-07-13: the Interface is an empty marker.
  The actual wire commands are `add(topic_path, name, protocol, transport, owner, tags)`,
  `remove(topic_path)`, `share(topic_response, …filter…)`, `history(topic_response, count)` —
  no `query`. Contract promotion in e_10 §2.2.)*
- `ProcessManager` (refines `Actor`) — `spawn(command, specification)`, `terminate(process_id)`.
- `Recorder` (refines `Actor`) — `record(topic_filter)`, `stop(recording_id)`. Replay lands
  here.

**pipeline/**

- `Pipeline` (refines `Actor`) — `create_stream(stream_id, parameters)`,
  `process_frame(stream_id, frame)`, `destroy_stream(stream_id)`.
- `PipelineElement` — `start_stream(stream, stream_id)`, `process_frame(stream, **inputs)`,
  `stop_stream(stream, stream_id)`. The outputs of `process_frame` return to the in-process
  Pipeline runtime. This is the documented local exception. Across the wire, the Pipeline
  mediates.

**agents/**

- `Agent` (refines `Actor`) — goal/policy state through an ECProducer. The `perceive`/`act`
  surfaces are Pipeline attachments. To be specified spec-first (specifications §4.3).
- `McpBridge` — exposes discovered Services/Pipelines as MCP tools/resources.

## 4. Rules for agents writing or changing interfaces

New behavior means a new Interface, or a new method on an Interface that exists. It never
means a public method on an Implementation alone.

A method MUST take only S-expression-representable arguments. It MUST NOT return a value or
raise across the wire. If it is a request, it MUST name its reply interface.
Interfaces with more than about seven methods are split. Changing a published Interface bumps the
protocol version. Compatibility within a major version means added methods only. Every Interface
change updates `docs/interfaces/CATALOG.md` in the same PR — the drift check fails the build
otherwise. When unsure whether something is a query, an observation, or a stream, §2's order of
preference decides: shared state first, reply-to second, streams for sequences.
