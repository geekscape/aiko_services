---
title: Aiko Services — Framework Design Principles
description: The framework design principles (P1–P10, P12) — the constitution
  of the framework. When a specification is silent, decisions appeal to these
type: principles
audience: [architects, developers, ai-coding-agents]
status: normative
ste: adapted
related: [e_00_TransitionPlan, p_01_PrinciplesGovernance,
  p_02_CandidatePrinciples, s_00_Specifications, s_02_InterfaceComposition,
  a_00_ArchitectureReview_2026-06, adr/ADR-021_SynthesizedDefaultInit,
  adr/ADR-022_CompositionBoundary, adr/ADR-023_GuardedEvalDefaultDeny]
last_updated: 2026-08-01
---

# Aiko Services — Framework Design Principles

**Status:** Normative. These principles are the constitution of the framework. When a
specification is silent, agents (human or AI) decide by appeal to these principles. Changing a
principle needs an ADR approved by the project lead. How principles are adopted, amended,
deferred and kept aligned with the code is governed by
[p_01_PrinciplesGovernance.md](p_01_PrinciplesGovernance.md) (rules G1–G7).

Each principle states the rule, the reasoning, and — because AI coding agents reliably make
certain mistakes — the specific anti-pattern it forbids.

**Amendments of 2026-07-07:** directed by the project lead, incorporating the June 2026
architecture review (`a_00_ArchitectureReview_2026-06.md`) and the July 2026 critique
[Privately maintained register]. Amendments are marked inline and cite the critique's
U1–U8 / S1–S9 items. Principle numbering and titles are unchanged. Genuinely *new* principles are
queued (see "Candidate principles awaiting ADR" at the end), not silently inserted.

**Policy (2026-07-07): principles are current, not aspirational** (governance rule **G3**). This
document always reflects the design principles *currently in play* — rules an agent can comply
with today, in this codebase. A strengthening can first need the source, documentation,
tests or examples to be brought up to scratch. Such a strengthening is recorded as a
**deferred amendment** (see "Deferred amendments" below). It lives in the roadmap, marked
critically important, and it is promoted
into its principle only when the artifacts comply. This prevents the principles drifting into
aspiration while the code drifts elsewhere.

---

## P1. Asynchronous at the protocol level, not the language level

All distributed interaction is one-way message passing. A method on a remote Service is an
S-expression message published to a topic. It does not block, and **it never returns a value**.
The framework therefore does not need, and deliberately does not use, Python `async`/`await`.
Concurrency lives in the architecture (many communicating processes, each with a single-threaded
event loop) rather than in the language.

*Why:* this is what makes the framework language-agnostic. A C firmware implementation, a Rust
implementation and the Python reference implementation interoperate. Asynchrony is a
property of the wire protocol, not of any language runtime. The closest peer on this dimension is
Zenoh, not Ray or asyncio.

*Forbidden:* introducing `async def` into framework interfaces. Adding methods that return values
across the wire. Wrapping message sends in futures/promises as a core API. (A convenience
request/response helper may exist at the edge — see P3 — but never in interface definitions.)

*Amendment (2026-07-07) — delivery semantics are part of this principle.* One-way messaging over
in-memory mailboxes means delivery is **at-most-once**: a message may be lost on crash, on queue
overflow, or when a handler raises mid-processing. This is a legitimate design point (Erlang makes
the same choice) **only if stated and compensated at the endpoints** (end-to-end argument,
critique U7). Framework documentation, interfaces and examples must not imply guaranteed
delivery. The sanctioned confirmation idiom is *command, then observe* through EC state (see P3
amendment and candidate principle CP-A). Because asynchrony is a wire property, flow control will
need to be a wire property too. But that strengthening needs protocol machinery that does not
yet exist. Thus it is deferred amendment **DA-4**, not yet a rule of this principle.
*Forbidden (added):* application or framework code that assumes a sent message was delivered or
processed. Documentation that leaves delivery semantics unstated. Adding flow-control or
backpressure mechanisms that exist only in one language runtime rather than in the protocol
(pre-empts DA-4).

## P2. Everything is an Actor. Actors share nothing

A Service that holds state is an Actor: it owns a mailbox, processes one message at a time, in
order, and is the only writer of its own state. There are no locks, no shared mutable memory
between Services, and no reentrancy within an Actor's message handler.

*Why:* the Actor Model (and its Smalltalk lineage — "everything is an object, objects communicate
by messages") gives the simplest possible concurrency story for distributed embedded systems:
serial reasoning inside, message passing outside.

*Forbidden:* threads that mutate Actor state from outside the mailbox. Callbacks that bypass the
event loop. Any API requiring a lock for correctness.

*Amendment (2026-07-07) — name the unit of scheduling isolation honestly.* Mailboxes give
**messaging** isolation, not **scheduling** isolation: all Actors in one process share a single
cooperative event-loop thread, so one slow handler stalls every co-located Actor (critique U5).
Until per-Actor executor isolation exists (free-threaded CPython / subinterpreters are the watch
items, per S8), the unit of scheduling isolation is the **OS process**. Element and Actor authors
must treat the event-loop thread as a hard-real-time resource: long or blocking work goes to a
worker and posts results back through the mailbox (the ProcessManager reaper pattern). Two Actors
that must not be able to stall each other must be deployed in separate processes.
*Forbidden (added):* blocking calls, unbounded loops, or model-loading in `process_frame` /
message handlers on the event-loop thread. Documentation or examples that imply co-located Actors
are isolated in time.

*Note (2026-07-07):* the Actor Model's missing half here is **supervision** (restart policies,
links/monitors, poison-pill and stream-failure semantics — critique S4). That is a new principle,
not an amendment: see candidate CP-B.

## P3. Request/response is two messages, state observation is subscription

Because methods return nothing, the two things return values are normally used for are recast:

- A **query** is a message that carries a reply destination (the caller's `topic_out` or an
  explicit reply topic). The response is an independent one-way message back. Correlation, when
  needed, is by explicit token in the payload.
- **Observation of state** does not use queries at all. An Actor exposes state through an
  ECProducer. Interested parties attach an ECConsumer, and they receive the current value
  plus a stream of updates, with eventual consistency. "Getters" do not exist in the distributed API.

*Why:* this keeps every interaction non-blocking. It makes state observable to N consumers at
the cost of one (publish-on-change). That is what dashboards, monitors and digital twins need
anyway.

*Forbidden:* RPC-style `get_x()` methods in interfaces. Blocking "call and wait" wrappers in the
core. Polling loops where an ECConsumer belongs.

*Amendment (2026-07-07) — every request has a deadline. Confirmation is observation.* A request
whose responder is absent must fail in bounded time. New code that builds on the
request/response pattern carries a **timeout as part of the pattern, not as an option**. The
known gaps in `do_command` / `do_request` (review §4.6 — today they can wait forever) are to
be closed,
not copied. To confirm that a one-way command *took effect*, do not use a reply message.
Instead **observe the EC state of the target converge** — "command, then observe" (candidate
CP-A states this fully). A protocol-level idempotency-token mechanism (retry-safe commands,
critique U7) is deferred amendment **DA-5**.
*Forbidden (added):* new request helpers without a deadline/timeout path. Retry logic for
commands that are not idempotent.

## P4. Eventual consistency over consensus

Shared state across the system converges. It is never globally locked. The ECProducer/ECConsumer
mechanism is the canonical pattern. Where stronger coordination is genuinely needed, it is
modeled explicitly as an Actor that owns the contested resource. That Actor serializes access
through one
mailbox — never as a distributed lock.

*Why:* Aiko Services targets edge networks where partitions, sleeping devices, and lossy links are
normal. Consensus protocols buy guarantees these environments cannot honor, at a complexity cost
the framework refuses to pay.

*Known gap (2026-07-07) — convergence is currently hoped for, not guaranteed.* The
ECProducer/ECConsumer mechanism has no repair path after a lost incremental update, and no
defined merge for concurrent writes. The Registrar election compares `time.monotonic()` values
across hosts (critique U1). The strengthened form of this principle is *"eventually
consistent" needs a stated convergence argument* (anti-entropy repair, CRDT merge semantics or
causal ordering. No cross-host clock comparison). That form is deferred amendment **DA-1,
critically important**, promoted
into P4 only as the codebase, tests and documentation are brought into compliance (direction:
critique S2, CRDT-backed shared state). One in-play rule applies now:
*Forbidden (added):* introducing any *new* protocol decision that compares local clock values
across hosts, or any *new* state-sharing mechanism without a stated convergence argument.

## P5. Discovery over configuration

Services find each other through the Registrar by **protocol identifier + tags + owner**, never by
hard-coded addresses or topic strings. A Service declares what it *is* (its protocol URI and
version). Clients ask for what they *need*. Topic paths are derived, not configured.

*Forbidden:* literal topic strings in application code. Configuration files containing peer
addresses. Any code that assumes a particular host/PID layout.

*Known gap (2026-07-07) — identity is not address.* The topic path (`namespace/host/pid/sid`) is
a **current binding (an address)**, not an identity: it embeds host and PID, so it dies with the
process — and today nothing else identifies a logical Service across restarts (critique U3). The
strengthened form of this principle is a stable logical identity. The Registrar binds it to the
current address, leases, history, lifecycle and Dashboard correlate by it, and HyperSpace names
identities. That form is deferred amendment **DA-2**. No identity scheme exists yet to comply with. One
in-play rule applies now:
*Forbidden (added):* introducing any further naming scheme that is neither the (future) logical
identity nor the topic-path address (pre-empts DA-2).

*Note (2026-07-07):* discovery is also where **authorization** naturally lives: who may *receive*
an address is a policy decision, and unguessable (capability) addresses make possession-of-address
meaningful (critique U4). That is a new principle — see candidate CP-C.

## P6. Everything is a Service — including the framework itself

The Registrar is a Service. The Dashboard is a Service (an Actor observing other Services'
ECProducers). The ProcessManager, the Recorder, every Pipeline and every PipelineElement host are all
Services. They are discoverable, observable and controllable through exactly the same protocol
as user code. There is no privileged management plane.

*Why:* one mechanism to learn, one mechanism to secure, one mechanism to observe. New
infrastructure (tracing, replay, MCP exposure) is added by writing Services, not by extending the
core.

*Amendment (2026-07-07) — uniformity is also the security and observability surface.* "One
mechanism to secure" is only true if the one mechanism *is* securable. Whatever security model
is adopted (candidate CP-C) must apply uniformly to infrastructure Services and user Services.
There is no privileged bypass for the Registrar, ProcessManager or Dashboard, because a
privileged bypass is a privileged management plane by another name. Likewise "one mechanism to observe" makes the
message bus itself the system's ground truth: the Recorder is the seed of first-class
record/replay (conformance golden traces, deterministic debugging, digital-twin simulation) and
should be treated as core capability, not an optional extra (review §4.1, critique S1/S3
dependencies).

## P7. Design by composition of interfaces

Behavior is specified as small Interfaces (abstract classes containing only one-way methods) and
given by Implementations composed together at class-construction time. Inheritance expresses
*interface refinement only* (for example, `Actor` refines `Service`). It never shares implementation. A
concrete component is a composition: `Service + Actor + LifeCycleClient + <domain interfaces>`.
The full pattern is specified in `s_02_InterfaceComposition.md`.

*Why:* interfaces are the unit of protocol compatibility. A remote caller cares only that the
target implements `protocol/storage:1`. Composition lets one process assemble exactly the
capability set it advertises, and lets alternative implementations be substituted per-interface.

*Forbidden:* deep implementation-inheritance hierarchies. Mixins that smuggle state. Interfaces
with more than ~7 methods (split them). Methods on Implementations that are not declared on an
Interface (the implementation may have private helpers, but its public surface *is* its
interfaces).

*Amendment (2026-07-07) — no capability may bypass the catalog.* Every framework capability must
be an Interface with a registered Implementation — no "plain class" exceptions. The June review
verified two standing violations: `ECProducer`/`ECConsumer` are plain classes (making the
framework's defining state primitive the only non-substitutable capability), and
`DataSource`/`DataTarget` inherit from `PipelineElementImpl` (implementation inheritance). Both
are to be normalized (review §2.4, §5.5). The composition machinery itself is the single most
load-bearing and least-tested code in the tree. Its two flagged latent bugs
(`_check_interfaces_implemented()`, over-broad default-implementation pickup) must gain
regression tests before further refactoring builds on it.
*Forbidden (added):* introducing a framework capability as a plain class rather than an
Interface + Impl. Inheriting from an `…Impl` class. Modifying `component.py`/`context.py`
without accompanying unit tests.

*Amendment (2026-07-13) — the composition boundary and retrospective normalization
(ADR-022).* The 2026-07-13 audit (the composition rollout §1 [Privately maintained]) showed the 2026-07-07 rule is
undecidable at the margins. The boundary is now explicit: the mandate covers every **public
behavioral capability** (anything a test double, alternative backend or embedded build might
substitute). Exactly three categories are exempt:

- **Value and data types**
- **Presentation and CLI shells**
- **Pre-composition bootstrap**, which still declares an Interface as its contract, without
  registration or `compose_instance`

Every exempt file carries a header note that names its category, so the drift audit is
decidable. Legacy non-compliance is **fixed retrospectively, not grandfathered**. e_10
(approved 2026-07-13) brings the pre-gate source up to this principle, rather than re-scoping
the principle to the source. This is a deliberate, bounded exception to the G3 default. e_10 §1
enumerates the violations, and the drift audit tracks them to closure. From 2026-07-13 onward, new public APIs comply at
introduction. The synthesized default `__init__` (ADR-021) is the approved reduction of the
pattern's boilerplate. The explicit constructor remains valid everywhere.
*Forbidden (added):* claiming an exemption without the ADR-022 category header note. New
public framework APIs landing without either composition or a categorized exemption.

## P8. Pipelines are declarative dataflow graphs

ML/multimedia processing is expressed as a graph definition (data, not code): named
PipelineElements, their connections, and their parameters. Elements implement a fixed stream
lifecycle (`start_stream`, `process_frame`, `stop_stream`) and know nothing about their neighbors.
The graph definition is the specification. The Pipeline runtime executes it. Elements may be
local (in-process) or remote (other Services) without the graph author caring.

*Why:* low-latency streaming multimedia heritage — frames flow, elements transform, topology is
configuration. It is also the property that makes Aiko Services legible to AI agents: the most
important artifacts are already declarative.

*Forbidden:* elements that discover or message their neighbors directly. Topology constructed
imperatively in application code. Hidden element state that outlives a stream without being
declared.

*Amendment (2026-07-07) — a graph definition is a contract.* New code that constructs, parses or
emits PipelineDefinitions validates them: do not discard a validation result (the verified
`parse_pipeline_definition()` defect, review §4.5), do not commit example definitions that cannot
load, and treat declared port types as meaningful. The full strengthening has two parts: *definitions that
fail schema or port-type validation do not load*, and graph edits expressed as
invariant-preserving rewrite operations over a defined topology algebra (critique U2 — the
property that turns runtime self-modification from hot-patching into provably safe
transformation). That strengthening needs runtime and theory work that does not yet exist. Thus it is deferred
amendment **DA-3, critically important** (prerequisite for V4.1/Gatekeeper).
*Forbidden (added):* new code that ignores or discards a schema-validation result. Committing a
PipelineDefinition that fails validation or cannot load. New element behavior that breaks the
declared-state / no-neighbor-knowledge conditions.

## P9. Edge-first frugality

The runtime must remain deployable on small embedded Linux devices. Core dependencies are minimal
and justified individually. Optional capabilities (media codecs, ML frameworks, dashboards) live in
`elements/` or separate distributions with optional dependency groups. Startup cost, memory
footprint, and message overhead are design inputs, not afterthoughts.

*Forbidden (for `runtime/`):* heavyweight dependencies. Mandatory cloud services. Features that
assume abundant CPU/RAM. When in doubt, the Raspberry Pi-class device wins the argument.

*Amendment (2026-07-07) — unbounded memory is a frugality violation.* Frugality is not only about
dependencies: **no new queue, cache or buffer enters the runtime without a bound and a stated
overflow policy** (drop-oldest, drop-newest, withhold — protocol-level credit flow control is
DA-4). Unbounded growth is verified today: `Queue.Queue()` mailboxes with warnings but no
limits, and per-stream Frame caches with no eviction. That growth is a critically-important
remediation item for the roadmap. It is not a claim that this principle makes about existing
code. This principle targets Raspberry-Pi-class
devices. On those devices, unbounded queues make OOM the *most likely* failure mode under
load. The edge-first argument cuts against them twice.
*Forbidden (added):* introducing a queue, cache or buffer without a documented bound and
overflow policy.

## P10. Elegance is a requirement, not a garnish

Prefer the smallest design that composes. Prefer one mechanism reused (messages, topics,
S-expressions, Services) over many mechanisms each locally optimal. Public API names are chosen
with care and changed reluctantly. If a feature cannot be explained in a paragraph and demonstrated
in a 30-line example, the design is not finished.

*Why:* this framework's longevity has come from conceptual economy in the LISP/Smalltalk
tradition. It is the easiest property to lose under multi-agent development, because entropy
arrives as many individually-reasonable additions. The reviewer role and the quarterly aesthetic
review (see transition plan) exist specifically to defend this principle.

*Amendment (2026-07-07) — elegance includes standing on established theory.* The smallest design
that composes is usually the one the field already proved:

- CRDTs rather than a bespoke sync protocol (P4)
- Kahn-network conditions rather than bespoke determinism rules (P8)
- Capabilities rather than bolted-on ACLs (CP-C)
- Credit-based flow control rather than ad-hoc throttles (P1)
Reinventing a solved problem is an elegance failure even when the reinvention is small: it adds a
mechanism the field cannot recognize, review, or reuse. When a design need matches a
well-understood body of theory, the burden of proof is on *not* using it.

## P12. The public API surface is guarded by default

*(Adopted 2026-07-13, ADR-023 — candidate CP-E adopted with its mobile-code tension resolved,
plus the exposure rule. P11 remains reserved for its own candidate.)*

**Guarded evaluation.** Nothing arriving from the bus — payloads, parameters,
PipelineDefinitions, frame data — is ever executed or deserialized into executable objects in
the host language: no `eval`/`exec`, no pickle of bus-derived input, safe parsers only
(`ast.literal_eval`, schema-validated JSON/Avro), and parameters are coerced and validated at
the boundary before steering behavior. Mobile code is a different case. It is LISP-style filter and predicate
expressions that travel in payloads (Registrar filters, ECCache filters, the LISP-shell
direction). Mobile code is a *supported capability* of the framework. It evaluates **only** in
the sandboxed, capability-bounded expression interpreter (the s_04 predicate language, item
06):
**mobile LISP code must never result in an unguarded, insecure `eval()`.** Until the sandbox
ships, the compliant behavior is refusal — hard-coded filters only.

**Default-deny exposure.** Every public API is **deny-all by default, per method**. The
composed Interface declaration seeds the allowed surface. Message dispatch never reaches a
method that is not declared on a composed Interface (P7's "the public surface *is* its
interfaces", made enforceable). Per-API, per-method **allow / deny lists** refine it. Policy is
declarative data (P8), updatable (CRUD) at runtime. The policy-update surface is itself a
public API under the same default-deny. It is grantable only to operator-authenticated or
gate-governed channels, with every change published and auditable (CP-I).
Enforcement lives in the Service's dispatch layer and in every projection gateway (MCP, A2A)
— never assumed of the broker.

*Why:* the bus is (today) unauthenticated and any MQTT client can invoke any public method on
any Service (July audit). The strategic mobile-code direction multiplies the stakes.
Deny-by-default makes both rules in play immediately (G3): a Service that evaluates no mobile
code and dispatches only its declared Interfaces complies today.

*Relationship to CP-C:* exposure lists bound *what is offered*. Capabilities (candidate CP-C)
govern *who may invoke it*. They compose — defense in depth — and P10's "capabilities rather
than bolted-on ACLs" stands: P12's lists are dispatch-layer surface definition, not
broker-enforced authority.

*Development mode (ADR-023 decision 6):* deny-all is the *default* — and defaults are what
production gets. In a simple, **isolated development environment**, the guard posture may be
set to **allow-all** for the edit/run/debug cycle. The mode is an explicit per-deployment
configuration value (never the shipped default, never a code change). The deployment
advertises it as observable state (CP-I), externally-reachable surfaces refuse it, and it
relaxes *policy only*: even in allow-all mode, mobile code evaluates only in the sandboxed
interpreter — an unguarded `eval()` is forbidden in every mode, everywhere.

*Forbidden:* `eval`/`exec`/pickle on bus-derived input, in any mode, including development.
Evaluating any mobile expression outside the sandboxed interpreter. Dispatching to methods
not declared on a composed Interface. Shipping a projection surface without per-method
default-deny. A policy-update path that is not itself access-controlled, observable and
auditable. Allow-all as a shipped default, an unadvertised mode, or on an
externally-reachable surface.

---

## Precedence and prioritization (action 3, 2026-07-07)

### Precedence among the adopted principles (conflict resolution)

All adopted principles bind (P1–P10, plus P12 since 2026-07-13). Precedence exists for the case
two principles genuinely collide in a design decision — a lower tier never justifies violating a
higher tier. Within a tier, the project lead decides by ADR.

- **Tier 1 — identity.** P1 (asynchronous at the protocol level), P2 (everything is an Actor,
  share nothing), P6 (everything is a Service). Trading any of these away produces a different
  framework. These are also the wire-facing commitments other implementations will build on —
  the most expensive to reverse.
- **Tier 2 — architecture.** P3 (two messages / subscription), P4 (eventual consistency over
  consensus), P5 (discovery over configuration), P7 (composition of interfaces), P8 (declarative
  dataflow graphs), P12 (guarded-by-default public API surface — added 2026-07-13). Violations
  are serious but repairable by refactoring one implementation.
- **Tier 3 — disciplines.** P9 (edge-first frugality), P10 (elegance). These govern *how*
  decisions are executed rather than *what* the architecture is — with two scoped exceptions
  that survive from the principles themselves: P9 remains decisive for runtime dependency and
  footprint questions ("the Raspberry-Pi-class device wins the argument"), and P10 is the
  universal tiebreaker: when multiple compliant designs remain, the smallest that composes wins.

### Deferred amendments DA-1…DA-5

Per the "principles are current, not aspirational" policy (G3), five strengthenings of
P1/P3/P4/P5/P8 are **deferred amendments** — normative intentions held in the roadmap, not
yet rules of this document. Each principle's *Known gap* note above names its own gap
honestly. The full DA register — wording, evidence, design order and promotion order — is
maintained privately [Reserved for private items]. Each DA is promoted into its
principle, per G3, only when the source, tests, documentation and examples comply.
Promotion *is* the act of bringing the artifacts up to scratch, so the principles never
drift from the code.

---

## Candidate principles awaiting ADR

Per governance rules G2/G4, new principles need an ADR approved by the project lead. Entries
here are direction-of-travel stubs, not binding principles. **Full draft wording, in-play
assessments (G3) and adoption paths for all candidates live in
[p_02_CandidatePrinciples.md](p_02_CandidatePrinciples.md)**. That includes CP-E…CP-I, which
the action (2) gap analysis surfaced. Prioritization is action (3).

**P11 (candidate, 2026-07-05). All state mutation happens on the event-loop thread.**
The same rule appears independently in the To Do lists of `event.py`,
`connection.py`, `pipeline.py` and `utilities/lock.py` ("eliminate most
Locks by funnelling mutation through the event loop"). The concepts
documentation audit found real bugs where the rule is violated or
half-applied. `ActorImpl.run()` and `PipelineImpl.set_parameter()` write
`self.share[…]` directly, invisible to remote observers. `connection.py`
notifies handlers on the calling — possibly MQTT — thread. ProcessManager's reaper thread
shows the compliant pattern: worker threads post work to the main thread
through `_post_message()` and never mutate shared data.
*Additional evidence (2026-07-06):* committed examples stop Actors by raising `SystemExit`
inside message and frame handlers (aloha_honua `ku()`, PE_WhisperX spoken "terminate").
xgo_robot runs its own camera thread with a hand-rolled loop, rather than event-loop
machinery. Whatever
P11's final wording, the ADR should state the sanctioned way for an Actor to stop itself.
*Additional evidence (2026-07-07):* the July audit found the same hazard class in
`event.py` (`_handler_count` not thread-safe, per its own BUG comment) and `mqtt.py` (documented
deadlock when waiting on the MQTT thread for a condition dependent on an incoming message).

**CP-A (candidate, 2026-07-07). Command, then observe** — the end-to-end reliability idiom
(critique U7, S7): commands are one-way and carry idempotency tokens. *confirmation* of effect is
observation of the target's EC state converging, never an awaited reply. Interacts with P1
(delivery semantics), P3 (deadlines) and P4 (convergence).

**CP-B (candidate, 2026-07-07). Supervision is part of the Actor Model** (critique S4): every
Actor has a defined failure policy. Links/monitors exist as protocol concepts. A stream whose
element dies has defined semantics (restart / skip / kill). Interacts with P2 and P8.

**CP-C (candidate, 2026-07-07). Authority is a capability, not an ACL** (critique U4): Service
addresses are unguessable. Possession of an address is authorization to message it. The Registrar
grants addresses under policy. Infrastructure Services hold no privileged bypass (P6). Must be
designed before any externally-reachable surface (MCP gateway, shell) ships.
*(2026-07-13: P12/ADR-023 adopted the complementary exposure rule — per-method default-deny
lists at the dispatch layer and gateways. That is surface definition, not the broker-enforced
authority this candidate rejects. CP-C's capability mechanism remains the pending authority
answer, and the two compose as defense in depth.)*

**CP-D (candidate, 2026-07-07). The ecosystem unit is the shareable element** (critique U8, S6):
third-party PipelineElements are packaged, schema-carrying, independently distributable artifacts.
Possibly a project principle rather than a framework principle. Action (2) decides.

---

## How agents should use this document

Before proposing a change, check it against the adopted principles (P1–P10, P12). If a change
conflicts with a principle, the change is wrong or the principle needs an ADR — there is no
third option. In review, citing a
principle by number ("rejected: violates P3, introduces a blocking getter") is the expected style:
terse, checkable, and teachable. Amendments carry their date and their evidence trail (review
section or critique U/S number) so that a future reader can reconstruct *why* each rule exists.

---

## Change log

- **2026-07-13 (c)** — P12 development-mode provision (project-lead amendment at ADR-023
  acceptance): in a simple, isolated development environment the guard posture may be set to
  allow-all for the edit/run/debug cycle. It is explicit per-deployment configuration,
  advertised as observable state, refused on externally-reachable surfaces, and it relaxes
  policy only
  (the sandboxed-interpreter mechanism and the unguarded-`eval()` prohibition hold in every
  mode).
- **2026-07-13 (b)** — **P12 adopted** (directed and approved by the project lead, ADR-023):
  guarded evaluation (candidate CP-E adopted with its mobile-code tension resolved — mobile
  LISP expressions evaluate only in the sandboxed capability-bounded interpreter, never an
  unguarded `eval()`) and default-deny per-method exposure (composed Interfaces seed the
  allow surface. Per-API, per-method allow/deny lists as governed, observable, runtime-CRUD
  data). P12 joins Tier 2. CP-C's capability mechanism remains a candidate. The exposure
  rule composes with it (defense in depth), preserving P10's "capabilities rather than
  bolted-on ACLs".
- **2026-07-13** — P7 amended (directed and approved by the project lead): the composition
  boundary made decidable. Three categories are exempt (value/data types, presentation and CLI
  shells, pre-composition bootstrap), and each one needs a category header note. Legacy
  non-compliance is fixed retrospectively through e_10_PublicApiComposition, rather than by <!-- future-ref-ok: historical change-log record -->
  re-scoping the principle (a bounded, tracked exception to the G3 default). ADR-022 records
  the boundary and the retrospective-normalization decision. ADR-021 records the synthesized
  default `__init__` convenience. Basis: the 2026-07-13 full audit of
  `src/aiko_services/main/` (e_10 §1) and the s_02 verification record of the same date.
- **2026-07-07 (d)** — Prioritization delivered (action 3, directed by the project lead): P1–P10
  given a three-tier precedence order for conflict resolution (identity / architecture /
  disciplines, which keeps the dependency-question decisiveness of P9 and the tiebreaker role
  of P10). Deferred amendments are ordered DA-1 → DA-3 → DA-2 → DA-5 → DA-4 for implementation
  and promotion. All five are designed into the AS-RFC drafts from the start. Candidate adoption ordered in
  three waves in `p_02_CandidatePrinciples.md` (Wave 1 safety/honesty: CP-E, CP-C slice, P11,
  CP-I+CP-B slice. Wave 2 protocol readiness: CP-G, CP-F, CP-A, CP-H slice. Wave 3
  mechanism-gated: CP-C full, CP-B full, CP-H full, CP-D).
- **2026-07-07 (c)** — Governance formalized and gap analysis delivered (actions 2): the
  governance rules moved to normative `p_01_PrinciplesGovernance.md` (G1–G7, including the G3
  in-play test and the G7 drift audit). The full candidate-principle proposals moved to proposal
  `p_02_CandidatePrinciples.md`, with G3 in-play assessments and adoption paths, awaiting
  prioritization (action 3). Those proposals are P11, CP-A…CP-D, and the newly surfaced CP-E
  (payloads are data, never code — with the mobile-code note of the project lead), CP-F
  (in-band control, out-of-band bulk), CP-G (versioned compatible protocol evolution), CP-H
  (specification + reference implementation are the source of truth) and CP-I (observable by
  default).
- **2026-07-07 (b)** — Policy adopted (project lead): principles reflect the design *currently in
  play*. Aspirational strengthenings become **deferred amendments** living in the roadmap, marked
  critically important, promoted only when the artifacts comply. Accordingly, five items moved to the new "Deferred
  amendments" section as **DA-1…DA-5**: the P4 convergence rule, P5 identity/address
  separation, P8 enforced-loading + topology algebra, P1 protocol flow control and P3
  idempotency tokens. The P1/P3/P4/P5/P8/P9 amendment texts re-scoped to rules new code can comply
  with today (P4 and P5 now carry *Known gap* notes rather than normative amendments).
- **2026-07-07** — Amendments to P1–P10 directed and approved by the project lead, incorporating
  `a_00_ArchitectureReview_2026-06.md` and `a_02_CritiqueUnknownUnknowns_2026-07.md`: P1 (delivery <!-- future-ref-ok: historical change-log record -->
  semantics stated. Flow control is a wire property), P2 (scheduling/messaging isolation named),
  P3 (deadlines mandated, idempotency, observe-to-confirm), P4 (a convergence argument
  mandated, no cross-host clock comparison), P5 (identity separated from address), P6 (uniform security, and the bus
  as ground truth), P7 (no plain-class capabilities, and composition-core test discipline), P8
  (schemas enforced, and topology algebra), P9 (bounded queues), P10 (stand on established theory).
  Candidate principles CP-A…CP-D queued for action (2). P11 candidate retained with added
  evidence. "Aiko" corrected to "Aiko Services" throughout per naming convention.
- **2026-07-06** — P11 candidate: additional evidence from the examples audit.
- **2026-07-05** — P11 candidate surfaced.
