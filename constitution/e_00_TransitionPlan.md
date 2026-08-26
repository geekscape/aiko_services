---
title: "Aiko Services: Transition to AI-Assisted, Context-Engineered
  Development"
description: The transition plan that moves the project's truth from code
  into a small set of normative artifacts, with the Python source as the
  reference implementation
type: plan
audience: [project-lead, ai-coding-agents]
status: proposal
ste: adapted
related: [p_00_DesignPrinciples, s_00_Specifications, s_01_RepositoryLayout,
  s_02_InterfaceComposition]
last_updated: 2026-07-31
---

# Aiko Services: Transition to AI-Assisted, Context-Engineered Development

**Status:** Proposal for review · **Audience:** Andy (project lead) and AI coding agents
**Companion documents:** `p_00_DesignPrinciples.md`, `s_00_Specifications.md`, `s_01_RepositoryLayout.md`, `s_02_InterfaceComposition.md`

---

## 1. The core idea

The transition is not "let AI agents loose on the repository." It is an
inversion of where the truth of the project lives. Today the truth is in
your head and in the Python source. The documentation trails the code.
After the transition, the truth lives in a small set of **normative
artifacts** (protocol specification, interface catalog, design principles,
ADRs). The Python source becomes the **reference implementation** of those
artifacts. It is one of potentially several implementations, because
Aiko Services is deliberately language-agnostic at the protocol level.

This inversion is precisely what makes multi-agent AI development
tractable. AI coding agents fail when intent is ambient and implicit.
They succeed when intent is explicit, local, and testable. Each phase
below extracts implicit knowledge into normative artifacts, or builds the
verification machinery. That machinery lets agents change code without a
second human review of every line.

A useful frame: **the specifications become the source code, and Python
becomes a build artifact.** That is an exaggeration today, but it is the
asymptote. It also matches the existing philosophy of Aiko Services. The
dataflow graph definitions are already declarative specifications that
the runtime "executes."

## 2. Phases

### Phase 0 — Freeze observable behavior (1–2 weeks of effort)

Before any restructure, capture what the framework *does*, so that agents
cannot change it silently. The observable behavior of the framework is its
wire traffic. That is a gift: you can record the traffic without
instrumentation of the internals.

Deliverables: a `tests/conformance/` suite of **golden protocol traces**.
Each trace is a recorded MQTT topic and payload sequence for one canonical
scenario:

- process bootstrap and the Registrar handshake
- Actor message delivery and in-order message processing
- ECProducer/ECConsumer state synchronization
- lease grant, extension, and expiry
- pipeline creation, stream start, N frames, stream stop
- a LifeCycleManager that creates and destroys LifeCycleClients

Each trace is a fixture. A replay harness asserts that the current
implementation produces equivalent traffic. The harness accepts
nondeterministic fields: PIDs, timestamps, hostnames, and ordering where
the specification permits it.

This suite is the single most valuable asset for AI-assisted refactoring.
It converts "did the agent break anything?" from a human review question
into a CI gate.

### Phase 1 — Extract the normative specifications (the main human-effort phase)

This phase closes the most significant genuine gap that the February
reviews identified: Aiko Services has no formal, language-neutral protocol
specification, but language-agnosticism is a core design claim. Write
these documents, in order of leverage:

1. **The wire protocol specification** — S-expression message grammar,
   topic namespace structure, Registrar protocol, Actor invocation
   protocol, EC state-sharing protocol, lease protocol, lifecycle
   protocol. This document lets a developer implement Aiko Services in
   Rust or C, with no need to read the Python. See
   `s_00_Specifications.md` for the proposed structure.
2. **The interface catalog** — every Interface class, every method,
   argument semantics, and the message that maps to each method. The
   February session produced a draft catalog. Promote it from "review
   output" to a versioned normative document.
3. **Design principles** (`p_00_DesignPrinciples.md`) — these are the
   constitution. Agents consult them when the specification is silent.
   They encode the judgments that currently live only in your head. Some
   of these judgments are easy to get wrong from the outside (for
   example, "the absence of async/await is a design decision, not a
   deficiency").
4. **Architecture Decision Records** (`docs/adr/`) — short, dated records
   for the decisions already made. Start with the big five:
   - Protocol-level asynchrony over language-level asynchrony
   - S-expressions over JSON/protobuf for control messages
   - MQTT as the first transport, with a transport abstraction
   - Eventual consistency over consensus
   - Composition of interfaces over inheritance

Honest note on the division of labor: AI agents (including me) can draft
80% of these documents from the source code. To draft them is an
excellent early multi-agent task. But the *normative* judgment — "is this
behavior intended or accidental?" — is yours alone. That judgment is
exactly the knowledge that this transition extracts. Budget your personal
time here, not in code review later.

### Phase 2 — Build the agent context architecture

Context engineering for a repository means this: an agent that starts in
any directory can discover what it needs, in priority order. The agent
does not need to read the whole tree.

Structure (detail in `s_01_RepositoryLayout.md`):

- Root `AGENTS.md` (with `CLAUDE.md` as a symlink or thin pointer). It
  carries the project identity, the ten design principles in compressed
  form, the rules of engagement, pointers to the spec documents, and the
  conformance-suite commands. The rules of engagement state what agents
  can change freely, what needs an ADR, and what needs Andy.
- Per-package `AGENTS.md` files (`runtime/`, `actors/`, `pipeline/`,
  `elements/`): the responsibility of the package, its public interfaces,
  its invariants, and its forbidden dependencies (for example,
  "`runtime/` must never import from `actors/` or `elements/`").
- `docs/specifications/` — the normative documents from Phase 1.
- `docs/adr/` — decision records, append-only.
- Curate `examples/` as **executable specifications**: each example shows
  exactly one concept, is named for that concept, and runs in CI. Agents
  learn the idioms of the framework from examples more reliably than
  from prose. Treat the examples directory as a teaching corpus.

Two rules matter more than any tool choice. First, **single source of
truth**: a fact lives in exactly one document, and other documents refer
to it. Duplicated context drifts, and drifted context actively poisons
agents. Second, **context files describe intent and invariants, not
current implementation details**. Implementation detail belongs in the
code, and it goes stale in prose within weeks.

### Phase 3 — Repository restructure (`main/` → `runtime/` + `actors/`)

Now, and only now, do the mechanical restructure. AI agents do the work,
gated by the Phase 0 conformance suite and the current test suite.
`s_01_RepositoryLayout.md` specifies the target layout and the migration
sequence. The sequence includes a `aiko_services.main` compatibility
shim, so downstream code continues to work for one release cycle.

Do the restructure as a sequence of small moves, each individually green,
not as one big change. Extract `utilities/` and `message/` first (no
dependents inside `main/` itself). Then move the mechanism layer
(`event`, `process`, `component`, `state`, `lease`, `connection`). Then
move `service` + `share` + `transport`. Split `actor` and the concrete
actors out last. Each move is an ideal single-agent task: tightly scoped,
mechanically verifiable, and boring.

### Phase 4 — Multi-agent development workflow

With specs, context, and conformance gates in place, define the standing
workflow:

**Roles, not just models.** A change flows through distinct agent roles,
even when the same model plays several of them. The *spec author* updates
the specification and writes the conformance case first. The
*implementer* changes code to satisfy the spec, and must not edit the
spec. The *test author* is adversarial: this role writes tests from the
spec, and does not look at the implementation. The *reviewer* checks the
diff against the design principles and the ADRs, not only against
correctness.

The separation matters because it reproduces the property that made your
human process work. The person who decides what must happen is not the
person who decides whether it happened.

**Spec-first discipline.** No implementation PR without a corresponding
spec section or ADR. For a framework whose value is its protocol, this
discipline is cheap insurance. It guards against the most common AI-agent
failure mode: locally-reasonable changes that erode global coherence.

**CI gates, in order:** conformance traces → unit tests → type checks
(see below) → an interface-drift check. The interface-drift check is a
script that regenerates the interface catalog from source. The script
fails if the result differs from the committed catalog. This check
catches an agent that changed a public surface but did not update the
spec.

**Type annotations as the contract surface.** The February review flagged
the missing type annotations as a critical gap. In an AI-agent workflow,
this gap graduates to a blocker, because annotations are the
highest-density context an agent gets. Annotate the `runtime/` interfaces
fully, and run a checker in CI. Land this work during Phase 3, while
agents touch every file in any case.

### Phase 5 — Expansion (the genuine gaps)

With the machine in operation, point it at the remaining gaps from the
February analysis. Do each gap as a spec-first project:

- Complete the MCP Server/Client. To turn every Service into an
  MCP-discoverable tool surface is a natural fit for the Registrar.
- Add pipeline I/O schema validation: declared frame schemas, checked at
  graph-construction time.
- Add observability: a trace/metrics Actor that subscribes to
  `topic_state` traffic. This is observability as a Service, consistent
  with the "everything is a Service" principle.
- Add message persistence and replay: a Recorder generalization, which
  also strengthens the Phase 0 conformance machinery.

## 3. Risks worth naming

**Spec rot.** Once the specs are normative, an out-of-date spec is worse
than no spec. The interface-drift CI check and the "single source of
truth" rule are the mitigations. Minimal specs also help: specify the
protocol and the interfaces, not the internals.

**Agent-driven entropy.** Many small agent changes, each fine alone, can
sum to a framework that no longer feels designed. The design-principles
document and the reviewer role exist for this risk. So does a periodic
(quarterly) human "aesthetic review" that looks only at the shape of the
public API. For a framework whose identity is elegance, this review is
not optional.

**Your own bottleneck moves — it does not disappear.** Your review effort
shifts from code to specs and ADRs. That is the correct trade — it is
leverage — but it is still real effort. The plan fails quietly if spec
review becomes a rubber stamp.

## 4. Immediate next steps

1. Review and correct the four companion documents. Give special
   attention to `s_00_Specifications.md`: I drafted it from my February
   2026 review of the codebase, and you must verify it against current
   `master` (I could not fetch the live repository in this session).
2. Decide the two open layout questions flagged in
   `s_01_RepositoryLayout.md`: where the `Actor` base abstraction lives,
   and whether `pipeline/` and `agents/` are one package or two.
3. Start Phase 0: pick the six canonical scenarios and record the first
   golden traces.

## 5. Update 2026-07-05 — Concepts documentation baseline

The concept layer of this transition now exists. `documentation/concepts/`
documents ~40 concepts — every `main/` module, `message/`, `transport/`
and all fourteen `utilities/` modules. There is one OKF document per
concept, structured per `t_00_OkfConceptTemplate.md`. Each document
separates implemented behavior from planned behavior. Consequences for
this plan:

- **Phase verification became cheaper.** Check the [VERIFY] items of
  s_00_Specifications against the concept documents first (each concept
  document cites its source and was verified against it). Then check
  them against `master`.
- **The truth-transfer is under way in-repo**: the usage headers, the
  Interfaces and the CLI surfaces moved from source into navigable
  documents. This is exactly the "truth out of code into artifacts"
  motion that this plan calls for.
- **Newly surfaced facts for the phases to absorb**:
  - Only five unit tests exist repo-wide (see the Testing Strategy
    reality audit).
  - Several modules hand-assemble wire payloads and do not use
    `generate()`.
  - The Registrar election fragility is the main robustness risk.
  - A convergent "all mutation on the event-loop thread" rule is now a
    candidate principle (see p_00_DesignPrinciples, pending ADR).

## Update 2026-07-06 — examples documentation complete

Per-module OKF documentation now covers `src/aiko_services/examples/`
(`documentation/examples/`, 30 documents, 11 package indexes). It joins
the concepts and elements trees. All three trees separate implemented
behavior from planned behavior. So the "truth moves from code into
artifacts" migration now has a verified documentation baseline. The
baseline covers the entire `src/aiko_services/` surface, except the
`main/` internals not yet promoted to specification status.
