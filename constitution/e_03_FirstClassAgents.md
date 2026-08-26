---
title: "Aiko Services — First-Class Agents: Roadmap, Design, and Execution
  Plan"
description: "Introduce Agent into the interface chain (Pipeline is-a
  PipelineElement is-an Agent is-an Actor is-a Service) with a pluggable
  backend abstraction over third-party agent frameworks"
type: plan
audience: [architects, developers, ai-coding-agents]
status: execution-plan
ste: adapted
related: [s_00_Specifications, s_02_InterfaceComposition,
  p_02_CandidatePrinciples]
last_updated: 2026-07-31
---

# Aiko Services — First-Class Agents: Roadmap, Design, and Execution Plan

**Goal:** Introduce Agent into the interface chain: `Pipeline is-a PipelineElement is-an Agent
is-an Actor is-a Service`, built with Component composition. Then Agents range from lightweight
Actors to full Pipelines. Agents have agency (goals, state, memory/RAG, reasoning, decision,
action). They also get a pluggable backend abstraction over third-party agent frameworks.

**Status:** Document e_03_FirstClassAgents. This plan supersedes the Agent sketch in
s_00_Specifications §4.3.

It also corrects the interface catalog in s_02_InterfaceComposition. That catalog placed
`Pipeline` and `Agent` as siblings that refine `Actor`. The real and intended chain is as
above. Task T1 below updates those documents.

---

## 1. What the hierarchy means (and the one constraint that keeps it sound)

`PipelineElement is-an Agent` makes every element an agent. The correct reading of this
hierarchy is Minsky's *Society of Mind*: intelligence that comes from societies of agents, most
of which are individually simple. Use this framing in the write-up when this work ships. A
`resize` element is an agent with a degenerate, reflexive policy. An LLM-backed planner is an
agent with a deliberative policy. **Agency is a spectrum, and the interface is the slot, not the
sophistication.**

A Pipeline is then literally a society of agents. Because `Pipeline is-a PipelineElement`,
societies nest. This design is a genuinely distinctive architectural claim. No current agent
framework gives "agent" a place in a dataflow/Actor unification. They all bolt agents onto
nothing.

The constraint that keeps it sound is the P7 interface budget. If `Agent` (the interface in the
chain) is fat, every trivial element pays for it. Then the chain collapses under its own weight.
So the design splits agency in the same way as the planned Parameter and Stream split:

**`Agent` in the chain is thin — the contract of agency, ~5 one-way methods.**
**Agency *capabilities* are orthogonal interfaces, composed in when wanted.**

This split makes the Parameter/Stream orthogonalization and the Agent introduction the *same*
refactor pattern, applied uniformly. Service is minimal. Actor composes the common aspects by
default (Parameter, Stream eventually, thin Agent in the chain). Richer aspects — Goal, Memory,
Reasoner — compose per component. One idea, applied four times: that is the P10 version of this
design.

## 2. Design

### 2.1 The thin `Agent` interface (in the is-a chain)

Protocol `…/agent:0`. All methods are one-way (P1/P3). Everything observable is ECProducer
state.

    class Agent(Actor):
        def set_goal(self, goal, reply_topic): ...   # goal is declarative data (see 2.2)
        def clear_goal(self, goal_id): ...
        def perceive(self, observation): ...         # push an observation (messages; streams
                                                     #   arrive via the existing Stream aspect)
        def decide(self): ...                        # request a deliberation cycle now
        def act(self): ...                           # request execution of pending intentions

Standard ECProducer keys (the agency self-model, IDE-visible for free): `agent.goals`,
`agent.intentions`, `agent.engine` (which backend, which model), `agent.activity`
(idle/perceiving/deliberating/acting). The default implementation of a reflexive element is
nearly empty. Its "policy" is `process_frame`, its goal list is static, and `decide`/`act` are
no-ops. The cost of agency for a dumb element is a few state keys. That is the whole tax, by
design.

### 2.2 Orthogonal agency aspects (composed, optional)

**`Goal`** — goals as declarative data (id, description, success criteria, priority, deadline,
parent goal), with CRUD through one-way messages and the current set in EC state. Goals are data on
the bus. As a result, agents can set goals *for each other* through ordinary Actor messages. The
Gatekeeper pattern from V4.1 generalizes to goal admission.

**`Memory`** — two tiers behind one interface: *working memory* (recent observations,
conversation, scratchpad — bounded, in-Actor) and *long-term memory* (RAG: `remember(item)`,
`recall(query, k, reply_topic)` — retrieval is reply-to, per P3). Storage backends are
pluggable. The edge default is local-first (SQLite-vec or LanceDB plus a small local embedding
model, per P9). A **MemoryStore Actor** makes shared memory a Service on the bus (P6). So a
fleet can share a brain with no shared process.

**`Reasoner`** — the seam to third-party frameworks (see §3). A composed Reasoner consumes
working memory, goals, and available tools, and produces intentions. `decide()` triggers it.

A lightweight Actor-Agent composes `Agent + Goal + Reasoner(NullEngine|rules)`. A sophisticated
one composes `Agent + Goal + Memory + Reasoner(LLM engine)` and can also *be* a Pipeline whose
elements are themselves agents. Same parts, any scale.

### 2.3 The boundary rule for third-party frameworks (the load-bearing decision)

**Third-party frameworks run *inside* the process of one Agent, and they own cognition only —
the think-loop, LLM calls, and tool-calling iteration. Aiko Services owns everything between
agents:** identity, discovery, messaging, goals, state publication, lifecycle, and multi-agent
topology. The frameworks therefore always run in *single-agent mode*. This plan explicitly does
**not** adopt their multi-agent orchestration layers (CrewAI crews, AutoGen conversations,
LangGraph multi-agent graphs), because that layer is what Aiko Services *is*. The Aiko Services
version is distributed, discoverable, and language-agnostic, and it runs on a Pi. None of their
layers can say that.

A mix of two multi-agent layers is architectural self-harm. This rule is what makes "switch
between frameworks" achievable at all, because adapters must cover only the (small) single-agent
surface.

### 2.4 The `AgentEngine` adapter interface

The Reasoner delegates to an engine behind a deliberately narrow seam:

    class AgentEngine(Interface):                 # local interface; not a wire protocol
        def start(self, system_context, tools): ...
        def submit(self, task, memory_snapshot, on_event): ...   # one deliberation episode
        def cancel(self, episode_id): ...
        def stop(self): ...

`on_event` streams engine events (thought/tool-call/tool-result/final) back to the mailbox of
the Actor. The Actor republishes them as `agent.activity` EC state. As a result, **the reasoning
of every engine is IDE-visible in the same way, for every vendor**. Engines declare capabilities
(streaming, local-model, code-execution, MCP), so a composition can state the capabilities that
it needs. `agent.engine` is a parameter: a framework switch is configuration, not code. The
conformance test for the abstraction is one agent task that passes on two engines.

**The ToolProjection layer projects tools once, and every engine uses them.** A single
ToolProjection layer exposes three tool sources to the loaded engine:

- (a) **Aiko Services as tools** — the Registrar becomes runtime tool discovery. The interface
  methods of any Service appear as callable tools, with the reply-to handling wrapped. This
  live discovery is the killer feature. No other framework has *live peer discovery* as a tool
  source.
- (b) **MCP servers** — the V4.1/Phase-5 bridge, now load-bearing.
- (c) Local Python functions.

Engines see one tool list. Aiko Services maintains it.

## 3. Engine posture and protocol posture

The comparative third-party framework survey, its assessment criteria and the specific
engine recommendations are recorded privately [Reserved for private item]. The binding
posture, in force:

1. **NullEngine first** (native, no LLM): rules/StateMachine-backed deliberation. It proves
   the agency-spectrum claim. It keeps LLMs strictly optional — an Aiko Services deployment
   with zero cloud dependency stays fully agentic. And it gives CI an engine that is fast,
   free, and deterministic.
2. **Then two maximally different third-party LLM engines** behind the AgentEngine seam,
   each in single-agent mode per the §2.3 boundary rule. When both engines pass the same
   conformance task suite, that result certifies the seam.
3. **A typed structured-output engine follows** where gate-facing proposals need it.

**Protocol posture — MCP and A2A are seams of their own, not engines.** MCP handles agent→tool
(the ToolProjection source, above). **A2A** (Linux Foundation, v1.0 early 2026, absorbed IBM's
ACP, 150+ orgs, native in Copilot Studio, Azure AI Foundry, Bedrock AgentCore) handles
agent↔agent interop. This plan adopts A2A as a **bridge Actor pair at the deployment edge** —
not behind the AgentEngine seam, because A2A has no cognition. Never use A2A as internal
messaging. HTTP/JSON-RPC for each on-device message violates P9. Also, A2A's deliberately
*opaque* agents are the philosophical inverse of P3/P6 transparency.

The mapping is clean and mostly mechanical:

- Agent Card ↔ ServiceFields + catalog entry
- A2A Task (submitted/working/input-required/completed/failed/canceled/rejected) ↔ Goal +
  StateMachine
- artifacts/streaming ↔ stream frames / `topic_out`

Also, the A2A v1.0 operations are themselves async-by-design (return immediately, updates through
stream/push). So the impedance mismatch is small.

- **A2AOutbound** (first): exposes selected Aiko Services Agents as A2A endpoints. The gateway
  generates signed Agent Cards *from the Registrar* — a projection of data that Aiko Services
  already holds. Inbound Tasks enter through the goal-admission gate (T8 — external requests
  pass the same constitutional check as internal requests). Task updates stream from EC state.
  One gateway makes a whole fleet reachable by the entire A2A ecosystem: Aiko Services as the
  physical-world fabric behind a standard endpoint.
- **A2AInbound** (second): proxy Agents for external A2A agents, registered in the Registrar as
  ordinary peers. Thus they are visible to ToolProjection. So any engine can call an external
  A2A agent, and the engine does not know that A2A exists.
- The gateway is the natural enforcement point for the A2A auth model (signed cards,
  OAuth/OIDC, mTLS, per-skill scopes). The gateway is thus the concrete forcing function for
  the security principle on the workstream E backlog. Use the official Python A2A SDK. The
  bridge is mapping code, not protocol code.

## 4. Sequencing (the refactor question, answered)

The chain insertion touches the base classes of everything. The Parameter/Stream extraction
touches the implementations of everything. To do either one without conformance coverage is to
restructure in the dark. So the pipeline traces of workstream D are the true prerequisite. The
order that minimizes risk is:

- **(1)** Conformance coverage of the current Pipeline/Element behavior (D, partly exists
  post-V4.1).
- **(2)** The *thin* Agent inserted into the chain with default implementations. The observable
  change is only new EC keys and the new protocol id — zero behavior change, traces still
  green.
- **(3)** The Parameter/Stream extraction into orthogonal aspects. This step is the planned
  refactor, now done under both trace coverage and the new interface layout, by agents,
  mechanically.
- **(4)** The agency aspects (Goal, Memory, Reasoner) + ToolProjection + NullEngine.
- **(5)** The SmolAgents and Strands adapters.
- **(6)** The V4.1 **Architect re-platformed as the first production Agent** on the new
  abstraction. Same demo, now on the real architecture. The engine switch (SmolAgents ↔
  Strands, one parameter, same behavior) becomes its own small filmable moment.

## 5. Execution task list

Owners as before (**A**/AI/A+AI). This plan runs as **workstream F** in the
g_02_ClaudeCodeOperatingGuide model (worktree `as-agents`, branch `agents/core`). Spec work can
start immediately. Implementation steps 2+ gate on V4.1 completion (Gatekeeper, catalog) and the
pipeline traces of D.

**Phase 0 — Specs (1 week elapsed — can start now)**
- T1 (AI, 1 session). Correct s_00_Specifications §4.3 and the s_02_InterfaceComposition
  catalog to the real chain. Record the hierarchy decision as ADR-006 (`Agent` in the chain,
  the thin-interface constraint, the boundary rule §2.3).
- T2 (AI, 2 sessions, A review). Normative specs: the `Agent` interface + EC keys, the `Goal`,
  `Memory` and `Reasoner` aspects, the `AgentEngine` seam + capability flags, and
  ToolProjection (Registrar-as-tools semantics, reply-to wrapping). RFC-2119 voice, into
  docs/plan + docs/interfaces.
- T3 (A, ½ day). Approve the goal data model and the five Agent methods. This is the API that
  you will keep — spend the red pen here.

**Phase 1 — Chain insertion (1 week)**
- T4 (AI, 1–2 sessions). Thin `Agent` + default implementation. Insert into the chain.
  Protocol ids. EC keys.
- T5 (AI, 1 session). Conformance: make the traces green again. Record the new `agent:0`
  discovery trace.

**Phase 2 — Parameter/Stream orthogonalization (1–2 weeks)**
- T6 (AI, 1 session, A review). Spec the aspect extraction: what moves out of
  PipelineImpl/PipelineElementImpl, and the composition defaults (into Actor by default,
  Service opt-in).
- T7 (AI, 2–4 sessions, subagents with worktree isolation for the mechanical moves). Execute.
  Keep the traces and the aiko_chat canary green throughout.

**Phase 3 — Agency (2 weeks)**
- T8 (AI, 2 sessions). Goal aspect + goal-admission hook (Gatekeeper-shaped).
- T9 (AI, 2 sessions). Memory aspect: working memory, a LanceDB/SQLite-vec + local-embedding
  long-term store, and the MemoryStore Actor. (The bench GPU hosts the embedding experiments.
  The Pi target uses the smallest viable model — measure, do not assume.)
- T10 (AI, 1–2 sessions). Reasoner aspect + `AgentEngine` seam + ToolProjection +
  **NullEngine**. Engine conformance task suite (same tasks, any engine).
- T11 (A+AI, ½ day). First lightweight agent end-to-end: rules-driven, with goals, no LLM,
  visible in dashboard/IDE.

**Phase 4 — Engines (1–2 weeks)**
- T12 (AI, 1–2 sessions). SmolAgents adapter. Local model on the bench. Engine conformance
  green.
- T13 (AI, 1–2 sessions). Strands adapter. MCP tools flow through ToolProjection. When the
  same suite is green, the seam is certified.
- T14 (AI, 1 session). Re-platform the Architect onto `Agent` + the engine of choice. Re-run
  the V4.1 scenario. Demonstrate the one-parameter engine switch and record its trace.
- T15 (A, ½ day). Write-up: the Society-of-Mind framing, the boundary rule, and the engine
  switch. This write-up is a strong standalone post, even before the IDE film.

**Phase 5 — A2A bridge (1–2 weeks, after T8 Goal aspect and T10 ToolProjection)**
- T16 (AI, 1 session, A review). Spec the bridge mappings as a normative doc: the
  Card↔ServiceFields projection, the Task↔Goal state mapping, and the artifact↔stream mapping.
  Include the auth posture at the gateway. Write ADR-007 to record the edge-only boundary (A2A
  never internal).
- T17 (AI, 1–2 sessions). **A2AOutbound** gateway Actor (official Python A2A SDK): card
  generation from the Registrar, task→goal admission through the T8 gate, EC-state→task-update
  streaming. Acceptance: an external A2A client (for example, an ADK or Claude agent) sets a
  goal on the testbed fleet and receives streamed completion.
- T18 (AI, 1 session). **A2AInbound** proxy Agents: external cards → Registrar peers → visible
  in ToolProjection. Demonstrate the round trip (an Aiko Services agent uses an external A2A
  agent as a tool).

**Acceptance:**

- The chain is inserted with zero trace regressions.
- Parameter/Stream are orthogonal, with aiko_chat green.
- A no-LLM agent and two LLM engines pass one conformance task suite.
- Tools come from the Registrar + MCP identically across engines.
- The Architect runs on the abstraction.
- The A2A round trip works in both directions through the edge gateway.

## 6. Risks, pre-answered

**Interface bloat in the chain** → the five-method budget is normative (T3 freezes it). Any
sixth method is an aspect. **Adapter rot** (third-party APIs churn fast) → adapters are leaf
packages with pinned versions and their own conformance suite. A broken engine never blocks
core. **The gravity of the frameworks** (each wants to own memory, tools, orchestration) → the
boundary rule is in the ADR and in the checklist of the principles reviewer. Engines get a tool
list and a task, never a topology. **Local RAG on edge underwhelms** → T9 measures this risk.
The stated fallback is a MemoryStore on the bench that serves the fleet — still on-bus, still
no cloud. **Sequencing temptation** — do not do the "fun" Phase 3 before the Phase 2
refactor. That order builds agency on the monolith that this plan dismantles. The order in
§4 exists because
extraction *under* a new feature is twice the cost of extraction *before* it.

## 7. Update 2026-07-05 — inputs from the concepts documentation

The composition concept documents (component.md, context.md, proxy.md) and
the Service-layer audit bear on the insertion of Agent into the interface
chain:

- **`init_args` are single-use**: `call_init()` marks the Context, so a
  reuse of init_args silently skips the whole `__init__` chain. The
  "compose once, create multiple instances" To Do is a prerequisite for
  cheap Agent instantiation.
- **The Interface default registry is process-wide** (one dict for all
  Interfaces). Composition depends on a filter, not on a scope. Examine
  this registry again before the interface chain grows an Agent layer.
- **Two proxy mechanisms persist** (`proxy.py` is unwired, and the live
  path is `discovery._make_service_proxy()`). Consolidation is already a
  source TODO. The recommendation is to land it before Agent-framework
  backends plug in.
- **ServicesCache scaling is the flagged CRITICAL**: every consumer receives
  every Registrar `/out` notification. Server-side filtering is a
  prerequisite for fleets of Agents.
- **Multiple Actors per Process** (shared ECConsumers) remains the
  prerequisite for in-process Pipeline → PipelineElements, and equally for
  lightweight Agent swarms.

## Update 2026-07-06 — examples documentation

`documentation/examples/llm/elements.md` documents the first in-repo
LLM PipelineElement. That element is LangChain over Ollama (gemma4) with
an optional OpenAI path. It has an S-expression system prompt that
commands the robot dog, and MQTT-fed detection context (currently
commented out). Audit notes for this plan: the element rebuilds the
LangChain object on every frame (llm/elements.py:118) and holds prompt
state as module globals. The speech→LLM→TTS round trip runs as three
Pipelines that cooperate. This round trip is a functional, if fragile,
precursor of the Agent-in-the-interface-chain architecture that this plan
formalizes. The OODA robot examples
(`documentation/examples/robot/ooda/elements.md`) sketch the
perceive/decide/act loop, but they currently hard-code the "decide" step.

## Alignment (action 5, 2026-07-07) — potential list and amended Design Principles

- **Sequencing confirmed and sharpened:** the §4 "conformance coverage first" is potential
  item 01 (Phase 0). The chain insertion also waits for the item-03 safety sweep (P11 adoption
  — Actor self-stop semantics matter when Agents manage goals/lifecycles). It also waits for
  the item-12 proxy consolidation, which §7 of this plan already needs before engine backends
  plug in.
- **Wire-visible specs go RFC-shaped:** author the T2 "RFC-2119 voice" specs for `agent:0`,
  Goal, and the A2A bridge mappings per `t_01_OkfRfcTemplate.md` (AS-RFC series, item 04). Use
  `[REQ-n]` numbering and conformance-trace appendices from day one. `AgentEngine` and
  ToolProjection remain local interfaces (not wire protocols) and stay in ordinary spec prose.
- **The A2A gateway is an externally-reachable surface:** the adopted CP-C shipping gate
  applies. A2AOutbound beyond the trusted LAN gates on item 08 (capability security). The §3
  observation of this plan, that the gateway "is the concrete forcing function for the security
  principle", is now normative, not aspirational. Agent identity in Agent Cards must build on
  item 07 (stable identity), not on topic paths.
- **ServicesCache scaling (the §7 CRITICAL):** the roadmap schedules it across items 05 (EC
  rebuild — the consumer-convergence machinery) and 12 (Registrar server-side filtering).
  Fleets of Agents are the workload that makes it urgent.
- **Society-of-Mind meets the calculus:** the item-06 expanded Definition/Graph direction
  (Data Flow + Behavior Trees + Subsumption + ECS, full-LISP definitions) is the natural
  substrate for agent societies. Examples: a Behavior Tree node whose leaves are Agents, and a
  subsumption layer that arbitrates reflexive compared with deliberative policies. Design the thin `Agent`
  interface so that it does not preclude that unification. Goals-as-declarative-data (§2.2)
  already points the correct way.
