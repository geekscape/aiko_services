---
title: "Aiko Services — Testing Strategy: Roadmap, Design, Execution, ADRs"
description: Golden traces exploit the framework's self-exercising property
  for integration testing. Hand-written tests only where that cannot reach
  establishes ADR-012 through ADR-016
type: plan
audience: [architects, developers, ai-coding-agents]
status: execution-plan
ste: adapted
related: [e_03_FirstClassAgents, p_02_CandidatePrinciples]
last_updated: 2026-08-01
---

# Aiko Services — Testing Strategy: Roadmap, Design, Execution, ADRs

**Goal:** A test architecture that uses the self-exercising property of the framework where
that property is genuinely strong: integration and wiring, through golden traces. It spends
the scarce hand-written test logic *only* where self-exercising structurally cannot reach:
the error boundaries, the foundational primitives,
cross-language contracts) — minimizing test-maintenance cost while maximizing bug-catching power.

**Status:** Document e_06_TestingStrategy. Establishes the testing constitution (ADR-012…ADR-016) and is the concrete
build-out of Phase 0 referenced across the execution plans. Supersedes the ad-hoc testing
notes in the review.

---

## 1. The thesis (from the preceding analysis, made normative)

Two facts, held together:

1. **The framework tests itself for integration and wiring — for free, and powerfully.** A working
   Registrar is an *integration oracle*. Its success is a real end-to-end trace. That trace
   proves eight facts. The event loop dispatches. MQTT round-trips. S-expression
   parse/generate agree. The topic paths match on both ends. Mailbox dispatch fires.
   Registration flows. The leases run. EC state converges. Self-
   hosting in the Smalltalk/LISP-image tradition.
2. **Self-exercising proves only the happy path through the states a run happened to visit.** It is
   a wide net with large holes. It cannot, by construction, test malformed input, the raising
   handler (which current dispatch *swallows* — so a liveness-only self-test reads a swallowed bug
   as success), timeouts with no responder, races, partitions, primary-election contention, or
   version-divergent behavior. The self-hosting compiler is the cautionary tale: it compiles
   itself every build and still ships codegen bugs, because it only exercises the features its own
   source uses.

**The strategic inversion that this permits:** minimize *test logic*, not *test coverage*.
They are different axes.

Push the bulk of the coverage into **golden-trace replay** (near-zero logic, because the
framework is the harness). Spend **hand-written tests only on the boundaries and the
foundational primitives** (high logic, irreplaceable, few). Write almost nothing for what a
golden trace
already covers transitively.

**The "who tests the tests?" answer, structurally:**
- *Golden traces* are recordings, not hand-written assertions — they have no logic, so they cannot
  have a logic bug. The regress collapses to a one-time human blessing of captured behavior.
- *Foundational-primitive tests* (parser, composition) are what make the golden traces
  *trustworthy*: if the parser is subtly wrong, every trace inherits the blind spot. So the
  primitives are tested narrowly and adversarially, and that narrow testing is precisely what
  entitles us to trust the integration evidence built on top. The primitives test the tests.

---

## 2. The four test methodologies (and which class of bug each owns)

This is the spine of the strategy. Every test in the suite is consciously one of these four. Mixing
them is the failure mode that produces brittle, low-value suites.

### M1 — Golden traces (integration & wiring correctness)

A handful of canonical end-to-end runs, each recorded **once** as a sequence of MQTT topic/payload
events and replayed against the current build. The fixture *is* the specification. Covers the
interlocking middle of the architecture that self-exercises well.

The canonical set (small on purpose — each trace exercises more than 20 mock-heavy unit tests):
1. **Bootstrap + Registrar handshake** — process start, MQTT connect, registrar discovery, first
   `add`.
2. **Actor message delivery** — `(command args)` published → mailbox → method dispatched, in order.
3. **EC convergence** — producer publishes snapshot + updates. Consumer attaches and converges.
4. **Lease lifecycle** — grant → extend → expire → reclamation.
5. **Pipeline stream** — create_stream → N × process_frame → destroy_stream, including a 2-element
   graph and a remote element.
6. **LifeCycle** — manager creates a client, client attaches, manager destroys it.

Normalization rules (so traces are stable): nondeterministic fields (PID, timestamps, hostnames,
UUIDs, lease ids) are masked. Ordering is asserted only where the protocol guarantees it. Payloads
compared as parsed S-expressions, not bytes. Re-blessing a trace is a reviewed, deliberate act
(ADR-013).

**M1's discipline (the anti-complacency rule):** golden traces assert **liveness *and* the specific
contract**, never liveness alone. "Registrar came up and registered three services" is a happy-path
check a swallowed bug passes. Traces must also encode the *shape* of the exchange (the exact
commands, the convergence sequence), so a regression that still "stays up" but changes the protocol
is caught.

### M2 — Boundary tests (what the happy path structurally avoids)

Hand-written, isolated, **adversarial**. Highest bug-catching-per-line in the suite because nothing
else can reach these states. Each asserts a **negative or boundary fact**, not success:
- malformed / truncated / oversized payloads → logged diagnostic, loop survives, *no silent
  success*
- unknown command → diagnostic + Actor remains responsive (the swallowed-exception trap)
- `do_request` with no responder → returns within timeout, does **not** hang (today it hangs —
  this test will fail until §6.1 lands, which is correct)
- handler raises → captured with traceback, mailbox continues, failure is *observable* not absorbed
- race windows (update during consumer attach, and lease extension at the expiry instant)
- resource limits (mailbox backpressure, large frame).

### M3 — Foundational-primitive tests (what everything silently assumes)

Hand-written, **property-based** where possible. These are tested directly *because the self-testing
argument depends on them being correct*.
- **S-expression parser/generator:** round-trip `parse(generate(x)) == x` over a generated corpus —
  nesting, quoting/escaping, empty/edge atoms, the binary/ZMQ side-channel boundary, Unicode,
  pathological depth. Plus explicit malformed-input cases (asserting *graceful* failure, M2-style).
- **Composition engine** (`compose_class`/`compose_instance`): interface resolution, override
  precedence, the two code-flagged suspects (`_check_interfaces_implemented`, over-broad
  implementation pickup), diamond/multiple-interface cases (for example, `HyperSpace(Category, Actor)`),
  and the abstract-method recalculation.
- **Topic-path construction/parse** round-trip. **lease arithmetic**. **EC dictionary merge** logic.

### M4 — Conformance tests (contract for other implementations)

The golden traces from M1, plus a protocol conformance harness, run against **any** implementation
claiming Aiko compatibility — `aiko_engine_mp` first, a future Rust/TS client next. The moment the
wire protocol is a cross-language commitment, "the Python framework runs" stops being evidence that
another implementation conforms. Only M4 bridges that. M4 is M1's fixtures pointed at a foreign
binary over a real broker.

---

## 3. Failure-mode coverage (the specific concerns, mapped to method + mechanism)

Each item states *what self-exercising misses* and *how to test it*. All chaos items run in
`tests/chaos/` (building on the existing `network_chaos_monkey.py`).

### 3.1 Brokers fully and partially failed (flaky)
Self-runs assume a healthy broker. Test with a **fault-injecting broker proxy**: a TCP shim
between the Services and mosquitto. It can drop the connection and add latency and jitter.
It can drop a fraction of the messages, reorder within the QoS limits, and partition subsets
of the clients. Assert: reconnect/backoff
works. LWT fires and produces deregistration. QoS-expected redelivery holds. No duplicate-side-
effect on redelivery. The system *converges* after the fault clears (not merely survives). Partial
failure (flaky, not down) is the harder and more important case — steady packet loss, not a clean
cut.

### 3.2 Registrar primary & secondary, fully and partially failed (flaky)
Self-runs use one healthy Registrar. Test: kill the primary mid-operation → secondary
election.
two Registrars racing to become primary → exactly one wins, no split-brain. A *flaky* Registrar
(intermittent responses) → clients do not thrash registrations, discovery re-stabilizes. Registrar
restart → services re-register, consumers re-converge. This is the crux of the "self-healing"
claims elsewhere and cannot be reached by any successful single-Registrar run.

### 3.3 S-expression parser/generator failure cases
M3 property tests + explicit malformed corpus: unbalanced parens, unterminated strings, bad escapes,
non-UTF-8, truncation mid-token, injection-looking payloads, depth/size bombs, the binary-payload
boundary. Assert graceful, *observable* rejection — never a crash, never a silent mis-parse (the
worst case, because it poisons every trace built on it).

### 3.4 Eventual-consistency failure cases
Self-runs show convergence under good conditions. Test the *paths a happy run skips*: update lost in
transit then reconciled. Consumer attaches mid-update-burst (snapshot/stream interleave). Producer
restarts (consumers re-snapshot). Two updates to one key (last-writer-wins observed). Lease expiry
during active sharing. Out-of-order delivery across producers (no global order is guaranteed — assert
the *documented* weak guarantee, not a stronger one). Property/model-based: drive random
operation/fault sequences, assert eventual convergence as the invariant.

### 3.5 Stream failure cases (network, broker, Registrar, remote element, and *pipeline design*)
The richest category, because failures compose. Two sub-classes:
- *Infrastructure-induced:* frame loss mid-stream. Remote element disappears mid-stream. Broker
  hiccup during a stream. Registrar loss while a remote element is in use. Assert: StreamEvent
  error/stop semantics fire correctly. Partial graphs degrade per spec. No frame silently dropped
  without an error. Stop/cleanup runs (no leaked per-stream state).
- *Design/implementation-induced (often the real culprit):* an element that raises in
  `process_frame`. Type-mismatched edges (declared port types not honored — see §6.2). A slow
  element causing backpressure. A cyclic or malformed graph. An element that leaks per-stream state
  across `stop_stream`. These are **author errors that the framework must surface, not
  absorb**. The tests assert that the error is attributed to the element at fault, and that
  the stream fails loudly.

### 3.6 Remote Service/Actor/PipelineElement/Pipeline fully and partially failed (flaky)
Test: target never present (discovery + timeout, not hang). Target dies mid-request. Target *flaky*
(responds slowly/intermittently — the partial case). Target present but raising. Assert timeouts,
error propagation as messages (not exceptions across the wire), and that callers do not block the
event loop waiting. Partial/flaky failure is explicitly harder than clean failure and gets its own
cases.

### 3.7 Anything else fundamental that golden traces will not catch
- **Concurrency/ordering** beyond the recorded path. Mailbox starvation/priority.
- **Resource exhaustion:** memory under sustained streams, file descriptors, mailbox growth, broker
  topic cardinality.
- **Process lifecycle:** ProcessManager spawn/kill, orphan/zombie handling, clean shutdown
  (deregistration on SIGTERM).
- **Version divergence:** behavior across Python 3.9→3.13 (the matrix that current CI omits).
- **Swallowed-error detection:** a meta-test that asserts handler exceptions are *recorded somewhere
  observable*, so the broad-catch behavior cannot hide regressions.
- **Composition latent bugs:** the two the code itself flags.
- **Security boundary** (when it exists): unauthorized message rejected, identity enforced — see M-
  security below.

---

## 4. Test taxonomy (the requested test types, and how each is realized)

| Type | Realization in Aiko | Cadence |
|---|---|---|
| **Unit** | M3 primitives + small pure-logic (graph, parser, lease, EC merge). Mock transport, no broker (`run(mqtt_connection_required=False)`) | every commit |
| **Integration** | M1 golden traces. Real mosquitto service container | every PR |
| **Subsystem** | Registrar+EC together. Pipeline+elements together. Lifecycle+ProcessManager | every PR |
| **System** | Full deployment scenario (the V4.1-style end-to-end), recorded + replayed | nightly |
| **Load / stress** | Many services/streams/frames. High message rate. Mailbox backpressure | nightly / pre-release |
| **Chaos — network** | broker proxy: loss, latency, jitter, partition (3.1) | nightly |
| **Chaos — process** | kill/restart Registrar, elements, ProcessManager children (3.2, 3.6) | nightly |
| **Chaos — resource** | memory/FD/CPU exhaustion under load (3.7) | weekly |
| **Regression** | every fixed bug adds a focused M2/M3 test *or* a golden trace. Drift checks | every commit |
| **Security** | unauthorized/identity/authz cases (grows with the protocol-security work) | every PR once it exists |
| **Continuous Integration** | unit+integration+conformance gates, version × OS matrix | every push/PR |
| **Long-running** | soak test: a deployment up for hours/days, watch for leaks/drift | weekly |
| **Massive scale** | hundreds–thousands of services across the test fabric. Discovery/broker limits | pre-release / milestone |
| **Cross-language** | M4 conformance against `aiko_engine_mp` (and future clients) | every PR (when impl available) |

CI gate order (fail fast): unit → primitives (M3) → integration/golden (M1) → conformance (M4) →
type-check → (nightly) chaos/load/soak. The matrix (Python 3.9–3.13 × {ubuntu, macos}) closes the
version-divergence hole §3.7.

---

## 5. Design notes for the test infrastructure

- **`tests/conformance/`** — golden traces (JSON fixtures) + a replay harness + a normaliser. The
  trace format is itself spec'd so M4 can consume it from any language. Doubles as the cross-
  language conformance suite.
- **Trace capture** — built on the existing `Recorder` Service (P6: testing infra is just
  Services). Recording a scenario = running it once with a Recorder subscribed to all topics.
- **Fault-injecting broker proxy** — a small Service/process sitting between clients and mosquitto
  configurable fault profiles. The single most valuable new piece of test infrastructure after the
  golden traces.
- **Property/model-based engine** — for M3 (parser, EC convergence): generate operation/fault
  sequences, assert invariants (round-trip, eventual convergence). Hypothesis-style.
- **Swallowed-error probe** — a hook (using the existing Hooks AOP) that records every caught
  dispatch exception, so tests and chaos runs can assert "no error was silently absorbed."
- **The test fabric** (bench + proving-ground + Pi, per g_02_ClaudeCodeOperatingGuide) hosts multi-host, scale, and
  cross-language runs. Three real heterogeneous hosts are the honest environment for a
  distributed framework. The fabric is itself a credibility artifact.

---

## 6. Two prerequisites this strategy surfaces (and depends on)

### 6.1 Discovery timeouts
M2/§3.6 cannot pass until `do_command`/`do_request` honor timeouts (the code's own TODO). This is
both a bug fix and a test prerequisite. It lands first.

### 6.2 Pipeline I/O schema validation
§3.5's design-error cases need the declared port types to be *enforced* at graph construction.
Builds the validation already flagged in the review and necessary by the Gatekeeper work (the demonstration plan [Privately maintained] / e_03_FirstClassAgents).

---

## 7. Execution task list

Workstream D (worktree `as-conformance`, branch `phase0/conformance`), the highest-risk-to-starve
stream per g_02_ClaudeCodeOperatingGuide — these are appointments, not aspirations. Spec-first. Critical path ≈ 4 weeks
focused. Thereafter a standing weekly cadence.

**Phase 0 — Foundations the rest depends on (1 week)**
- T1 (AI, 1 session, plus a review). ADRs 012–016 (below). The trace format spec. The canonical-scenario
  list frozen.
- T2 (AI, 1–2 sessions). **M3 parser/generator property tests** + malformed corpus — the primitive
  everything else trusts. Do this before golden traces so the traces are trustworthy.
- T3 (AI, 1 session). Fix **discovery timeouts** (§6.1) + the boundary test that proves it.

**Phase 1 — Golden-trace machinery (1 week)**
- T4 (AI, 1–2 sessions). Recorder-based capture harness + normaliser + replay harness. Trace format
  validated.
- T5 (AI, 2 sessions). Record + bless the **six canonical traces** (M1). Wire replay into CI as a
  necessary gate.
- T6 (AI, 1 session). **Composition-engine tests** (M3) incl. the two code-flagged suspects.

**Phase 2 — Boundaries & the anti-complacency rule (1 week)**
- T7 (AI, 2 sessions). **M2 boundary suite**: malformed payloads, unknown commands, raising
  handlers, races — each asserting a *negative/boundary* fact. Add the **swallowed-error probe** and
  a meta-test that no dispatch exception is silently absorbed.
- T8 (AI, 1 session). Narrow the over-broad exception handling in Actor dispatch (review §4.6) under
  cover of T7.
- T9 (AI, 1–2 sessions). **Pipeline schema validation** (§6.2) + design-error stream tests (§3.5).

**Phase 3 — Chaos & failure injection (1–2 weeks)**
- T10 (AI, 2 sessions). **Fault-injecting broker proxy** + broker-failure suite (§3.1, full +
  flaky).
- T11 (AI, 2 sessions). **Registrar primary/secondary chaos** (§3.2): election, split-brain
  prevention, flaky-registrar stabilization.
- T12 (AI, 2 sessions). **EC failure/property suite** (§3.4) + **remote-target failure suite**
  (§3.6, incl. flaky).
- T13 (AI, 1–2 sessions). **Stream failure suite** (§3.5 infrastructure-induced) on the Pi+bench
  fabric.

**Phase 4 — Scale, soak, cross-language, CI (1–2 weeks)**
- T14 (AI, 1 session). CI matrix (3.9–3.13 × {ubuntu, macos}) + mosquitto integration job +
  type-check job + coverage. Gate order per §4.
- T15 (AI, 1–2 sessions). Load/stress + long-running soak (leak/drift detection) on the fabric.
- T16 (AI, 1–2 sessions). **M4 cross-language conformance** against `aiko_engine_mp` using the M1
  traces. Record divergences as spec findings.
- T17 (AI, 1 session, milestone). Massive-scale run (hundreds–thousands of services) — discovery and
  broker-cardinality limits.

**Standing cadence (after Phase 4):** every bug fix ships a focused test or a trace (regression by
construction). One new chaos/edge scenario per fortnight. Nightly chaos/load/soak. Weekly D-merge.

**Acceptance:** the six golden traces gate CI and run cross-language against
`aiko_engine_mp`.
parser and composition engine have property-based coverage. Every §3 failure mode has at least one
test asserting a negative/boundary fact. The swallowed-error probe proves no silent absorption. The
broker proxy and Registrar-chaos suites pass full-and-flaky. CI runs the version×OS matrix. A soak
test runs clean for ≥24h.

## 8. Constitution updates (ADRs)

**ADR-012 — Test by methodology, not by habit.** Every test is consciously one of M1 (golden
trace), M2 (boundary), M3 (primitive) or M4 (conformance). Coverage is pushed to M1 (low
logic).
hand-written logic is reserved for M2/M3 (irreplaceable, few). Tests that are *only* tests of the
happy path a golden trace already covers are not added.

**ADR-013 — Golden traces are blessed recordings.** Integration coverage is recorded MQTT traces,
normalized for nondeterminism, compared as parsed S-expressions. Re-blessing a trace is a reviewed,
deliberate act with a recorded rationale. Traces assert contract-shape *and* liveness, never
liveness alone.

**ADR-014 — Self-exercising tests assert negative and boundary facts.** A test that relies on
the normal operation of the framework must assert at least one negative or boundary fact: a
thing that must *not* occur, or a limit. To assert only that the system stayed up is not enough. The dispatch layer can absorb errors, and a liveness-only check passes a swallowed bug.

**ADR-015 — Foundational primitives are tested directly and adversarially.** The
S-expression parser/generator and the composition engine carry property-based tests. The
tests use explicit malformed
cases, *because the trustworthiness of every golden trace depends on their correctness*. This is the
structural answer to "who tests the tests": primitives test the tests.

**ADR-016 — The wire protocol is a cross-language contract. Conformance is mandatory.** Behavior
asserted as protocol is certified by the conformance suite (M4) against every implementation claiming
compatibility (`aiko_engine_mp` first). "The Python framework runs" is never accepted as evidence
that another implementation conforms.

**Proposed principle amendment — add P11:** *"Test what the system cannot test about itself. The
framework's correct operation is evidence of integration health, not of correctness at the
boundaries. Coverage concentrates the hand-written effort on the error paths, the
foundational primitives and the cross-language contracts that self-exercising structurally
cannot reach. It minimizes the test
logic everywhere else."* Run the g_02_ClaudeCodeOperatingGuide amendment process (`/adr`, approval, then edit principles).

## 9. Testing reality audit (2026-07-05)

Baseline gathered while writing the concepts documentation — the ground
truth this strategy starts from:

**What exists**: five unit tests in `src/aiko_services/tests/unit/` —
test_context.py (only `actor_args()` field defaults, and its own To Do asks
for all `*_args()` and real composition coverage), test_hook.py (full hook
lifecycle — the one well-covered module), test_pipeline_graph.py (PR #27),
test_stream_event.py (PR #32), test_stream_lock.py (PR #42). Plus
`tests/chaos/network_chaos_monkey.py` (unautomated) and
`transport/test_mqtt.py` (a manual harness, not pytest).

**What has zero coverage**: the S-expression parser, which is the wire
format of every message and has only its `main()` self-test. The Registrar
(election state machine, wire protocol, process-level removal — the single
point
of failure), process.py (message dispatch, topic matching and Service
registration — pure-logic candidates all), service.py / actor.py /
share.py (share.py To Do: "Give unit tests !"), event.py (To Do:
"Give unit tests!"), all of message/ and transport/, and thirteen of
the fourteen utilities.

**Cheap, high-value unit tests surfaced by the audit** (pure logic, no
broker needed — complements the golden-trace thesis rather than replacing
it): parser `generate()`/`parse()` round-trips and canonical forms.
`Services.filter_by_attributes()`. The EC sync protocol. Actor mailbox
ordering and delayed-message timing (virtual clock). `Stream.set_state()`
downgrade guards (currently buggy). `dir_base_name()` tables.
utc_iso8601 conversions (two functions are broken today and tests would
have caught both). Graph cycle handling. Configuration.py's header even
contains a ready-made "To Do: Tests" scenario list.

**Known bugs a first test pass should pin down** (all found or confirmed
during the audit): `process.py remove_message_handler()` binary-topic
branch. `process.py` Service-id reuse after `remove_service()`.
`process.py topic_matcher()` divergence from MQTT wildcard semantics.
`Stream.set_state()` ERROR-downgrade. Avro validation return
discarded in `parse_pipeline_definition()`. ECProducer f-string incremental
encoding compared with `generate()` snapshots. `event.py remove_timer_handler()`
wrong-timer removal. Lifecycle re-entry spawning duplicate client fleets.

### Elements library addendum (2026-07-06)

The PipelineElements documentation pass (documentation/elements/) extends
the audit: **nothing under `src/aiko_services/elements/` has any tests**.
Cheapest first targets are dependency-free pure logic: the Expression
evaluators (`evaluate_define/condition/expression` — whose comparison
regex is broken for `<=` and `>` today), the text elements and
DataSchemeFile path/glob resolution. New bugs a first pass should pin
down: the Expression operator regex. `eval()` on `define` parameters
(replace with `ast.literal_eval` and test the boundary). Uppercase
parameter keys silently missing `get_parameter()` (case sensitivity).
Parameter coercion (`"false"` truthy, string `rate` TypeError).
`VideoShow.stream_stop_handler()` that the framework never calls.
and the GStreamer error paths that raise `NameError`
(`video_stream_reader.py`) or hit a live `breakpoint()` (`utilities.py`).
`video_example.py`'s own To Do — "Turn this into a CI test!" — is the
package's stated intent.

### Examples addendum (2026-07-06)

The example-application audit (documented in `documentation/examples/`)
extends the §9 testing-reality picture. Zero tests exist under
`src/aiko_services/examples/`. Every package's own "To Do" list reads
"None, yet !".

More importantly, the audit found that **four committed PipelineDefinitions
cannot load at all**. They are `colab_ds_pipeline_0.json`
(nonexistent deploy module `aiko_services.elements.colab.elements`),
`pipeline_encode.json` (nonexistent `...pipeline.test_elements`),
`pipeline_transcription.json` (graph names undefined `PE_Speaker`) and
the eight speech microphone/speaker JSONs (deploy classes inside
the disabled legacy block of `audio_io.py`).

A cheap, hardware-free **PipelineDefinition validation test** would have
caught all of these. For every committed `*.json` it does four steps:
parse the file, import each deploy module, resolve each class, and check
that every graph node is defined. It belongs at the top of the examples
testing backlog.

The second-cheapest test is an **import smoke test** over the `examples/`
modules. It catches the PEP 701 f-string in `colab/elements.py:53`
(a SyntaxError below Python 3.12, which contradicts
the supported-versions claim in ADR-013's 3.9.7–3.14.2 matrix) and the
`NameError` path in `scheme_colab.py:42` outside Google Colab.

The hardware-dependent behavior (microphones, CUDA, XGO robot, Ollama,
Colab browser widgets) is untestable in CI as it is structured. The
seams to introduce fakes are the same seams that §5 identifies for the
element library (the DataScheme and ML-model boundaries).

## 10. Alignment (action 5, 2026-07-07) — potential list and amended Design Principles

This plan is the design authority for **potential item 01** (conformance test foundation) and
supplies test machinery to most other items. Mapping and corrections:

- **Methodology ↔ potential items:** M1/M4 = item 01 + item 04 (golden traces become AS-RFC
  appendix fixtures bound to `[REQ-n]`s — M4 gains mechanical spec↔test traceability). M2
  boundary suite + §6.1 timeouts = item 03 (the safety sweep lands the fixes, this plan lands
  the tests — same change, per G3). §6.2 schema validation = item 06's near half. §3.4 EC
  property suite = item 05's convergence evidence (upgrade its assertions from "documented weak
  guarantee" to the CRDT convergence argument once DA-1 lands). §3.7 resource exhaustion = item
  10's load tests. CI matrix (T14) = item 02. The trace format is shared with item 14
  (Recorder/tracing) — one format for tests, debugging and demos.
- **Numbering collision, resolved:** §8's proposed principle *"Test what the system cannot test
  about itself"* was drafted as "P11", but P11 is now the event-loop-mutation candidate
  (p_00_DesignPrinciples). Per governance G4, route this proposal through
  `p_02_CandidatePrinciples.md` with a CP identifier, if it is pursued. Note the action-2
  decision of 01B: testing discipline may belong in the ADRs of this plan (012–016 already
  carry most of
  its force) rather than in the Design Principles.
- **ADR-016 is CP-H's enforcement arm:** "the wire protocol is a cross-language contract" and
  CP-H (spec + traces + reference implementation are the source of truth) are the same
  commitment from two sides. Cite each other when the ADRs are enacted.
- **§3.2 Registrar chaos tests will be reshaped by item 05.** The election respecification
  (no cross-host clock comparison, DA-1) changes what "correct" means for the split-brain
  cases. Write the chaos assertions against the `[REQ-n]`s of AS-RFC-2, not against the
  current behavior. Expect them to fail until item 05 lands (the §6.1 pattern: a correct failing
  test is the point).
