---
title: Aiko Services documentation — reading guide and index
description: Top-level orientation for the documentation tree — what each
  directory is for, a complete reading order, fast paths by role, and a
  terminology glossary linking to the owning descriptions
type: index
audience: [project-lead, architects, developers, application-developers,
  ai-coding-agents]
status: operational
ste: adapted
related: [../constitution/ReadMe, ../constitution/adr/ReadMe,
  concepts/ReadMe, elements/ReadMe, examples/ReadMe, tools/ReadMe,
  ../constitution/t_03_IdentifierGlossary]
last_updated: 2026-08-27
---

# Aiko Services documentation — reading guide and index

This guide orients newcomers to the Aiko Services documentation tree. It
also reminds experienced developers where everything lives, and which
rules bind it. It **complements** the per-directory `ReadMe.md` indexes
and never repeats their content. Each directory index stays the authority
for its own documents, their one-line summaries and their statuses. What
this guide adds is the *cross-directory* picture: what each area is for,
one order in which to read everything, and a glossary of Aiko Services
terminology that links to the owning descriptions.

## The map

| Area | What it holds | Start at |
|------|---------------|----------|
| [concepts/](concepts/ReadMe.md) | The framework itself — 46 OKF concept documents (32 plus 14 in the utilities sub-index), from the per-process event loop to the distributed structural model | [design_overview.md](concepts/design_overview.md) |
| [elements/](elements/ReadMe.md) | The PipelineElement library (`src/aiko_services/elements/`) — one document per module, plus the example PipelineDefinitions | its reading paths |
| [examples/](examples/ReadMe.md) | The example applications (`src/aiko_services/examples/`) — hello-world Actor tutorial through vision, speech, LLM and robots | [aloha_honua/](examples/aloha_honua/ReadMe.md) |
| [../constitution/](../constitution/ReadMe.md) | The documents that govern development — principles (p), specifications (s), plans (e), operating guides (g), analyses (a), templates (t), plus the ADR registry, diagrams and the public journal | its index |
| [tools/](tools/ReadMe.md) | The ASD-STE100 command-line tools — `asd_ste100_lint.py` (the gate), `asd_ste100_fix.py` (the mechanical pass) and `asd_ste100_semisplit.py` | its ReadMe |
| [release_notes.md](release_notes.md) | Per-release features, testing and bug fixes | the newest release |

Forward-looking material lives in the private constitution. This includes
prioritization, unpublished designs, and the private registers that some
public documents cite as "[Privately maintained]". That material promotes
into `constitution/` through the governance process.

## How the areas relate

The **code-facing** documentation forms one stack.
[concepts/](concepts/ReadMe.md) explains the framework.
[elements/](elements/ReadMe.md) documents the processing-node library
built *on* those concepts. [examples/](examples/ReadMe.md) shows both
assembled into runnable applications. All three follow the audience-first
OKF Concept template
([t_00_OkfConceptTemplate.md](../constitution/t_00_OkfConceptTemplate.md)),
and they separate implemented behavior from planned behavior.

The **governance** documentation is the
[constitution](../constitution/ReadMe.md): the binding principles, the
specifications and plans, and the [ADR registry](../constitution/adr/ReadMe.md)
that records the decisions those principles need.

[tools/](tools/ReadMe.md) serves both stacks. It holds the tools that
verify the project's ASD-STE100 Simplified Technical English rules
[profile privately maintained]. Every
document in this tree carries an `ste:` front-matter field, and
`asd_ste100_lint.py` is the gate that earns that declaration.

## The complete reading order

### Stage 1 — Orientation

1. The repository root [ReadMe.md](../ReadMe.md) — what Aiko Services is,
   installation, first commands.
2. This guide, including a first skim of the [glossary](#glossary) below.
3. [Design overview](concepts/design_overview.md) — the one-document
   executive summary of the distributed structural model.
4. [examples/aloha_honua/](examples/aloha_honua/ReadMe.md) — the
   four-stage hello-world Actor tutorial. Run it, do not only read it. It
   introduces Service, Actor, discovery and remote invocation in four
   short files.

### Stage 2 — The framework, concept by concept

5. [concepts/ReadMe.md](concepts/ReadMe.md), then its sections in table
   order. The index is already layered bottom-up: process runtime
   foundations → composition → messaging → Services → Pipelines →
   structure and persistence → tools. Finish with the
   [utilities sub-index](concepts/utilities/ReadMe.md), and read
   [parser](concepts/utilities/parser.md) first, because the S-expression
   wire format appears everywhere.

### Stage 3 — Elements and examples

6. [elements/ReadMe.md](elements/ReadMe.md) and its five package indexes,
   which follow its *Reading paths* (first Pipeline → cameras and video →
   writing a new PipelineElement). Then read the remaining module
   documents, package by package.
7. [examples/ReadMe.md](examples/ReadMe.md) and its eleven package
   indexes, which follow its *Reading paths*.

### Stage 4 — Governance

8. [../constitution/ReadMe.md](../constitution/ReadMe.md) — the map of the
   governing documents, their groups (p/s/e/g/a/t) and their statuses.
   Read the principles first
   ([p_00](../constitution/p_00_DesignPrinciples.md),
   [p_01](../constitution/p_01_PrinciplesGovernance.md),
   [p_02](../constitution/p_02_CandidatePrinciples.md)). Keep the
   [Identifier Glossary (t_03)](../constitution/t_03_IdentifierGlossary.md)
   open as the decoder ring. Then follow the constitution index's own
   reading order through the specifications, plans and ADRs.

### Stage 5 — Working on the project

9. The repository root `CLAUDE.md` / `Agents.md`, then
   [g_03_AgentContext.md](../constitution/g_03_AgentContext.md) — the
   conventions that every contributor, human or agent, must follow.
10. The operating guides:
    [g_02_ClaudeCodeOperatingGuide.md](../constitution/g_02_ClaudeCodeOperatingGuide.md),
    [g_04_ModelHandoffGuide.md](../constitution/g_04_ModelHandoffGuide.md)
    and, when releasing,
    [g_01_ReleaseProcessGuide.md](../constitution/g_01_ReleaseProcessGuide.md).
11. [release_notes.md](release_notes.md) and the constitution's
    [public journal](../constitution/log.md). Keep reading the journal
    routinely — it is how any session catches up on what changed.

## Fast paths

- **One hour, evaluating the framework**: Stage 1, then the *Architects /
  evaluators* reading path in [concepts/ReadMe.md](concepts/ReadMe.md).
- **Application developer building a Pipeline**: Stages 1–3. Use the
  *Application developers* path in
  [concepts/ReadMe.md](concepts/ReadMe.md) and the *Building a first
  Pipeline* path in [elements/ReadMe.md](elements/ReadMe.md). Return for
  Stage 4 before you contribute documentation or code.
- **Framework contributor**: all stages. Stage 4 and Stage 5 are not
  optional, because the constitution binds every change.
- **AI coding session**: root `CLAUDE.md`,
  [g_03_AgentContext.md](../constitution/g_03_AgentContext.md) and
  [g_04_ModelHandoffGuide.md](../constitution/g_04_ModelHandoffGuide.md)
  first. Then the newest [journal](../constitution/log.md) entries. Then
  whatever stage the task touches.

## Reminders for experienced developers

The rules most often forgotten, each one owned by the linked document:

- Every substantive documentation change appends a
  [journal](../constitution/log.md) entry **in the same change**
  ([g_04 §4](../constitution/g_04_ModelHandoffGuide.md)).
- Registries own identifier numbers. Claim an ADR number by adding the
  registry row in the change that creates the file. Never renumber
  anything ([t_03](../constitution/t_03_IdentifierGlossary.md)).
- Identity is the ClearName. Cite documents by name, not by numeric prefix
  ([../constitution/ReadMe.md](../constitution/ReadMe.md)).
- Principles are current, not aspirational. A strengthening that the
  artifacts do not yet satisfy becomes a deferred amendment, not an edit
  ([p_01 G3](../constitution/p_01_PrinciplesGovernance.md)).
- Front matter uses the closed vocabularies. The `description:` field is
  the single source for index one-liners
  ([t_02](../constitution/t_02_OkfTaxonomy.md)).
- Write "Aiko Services" in full, never the bare "Aiko". ReadMe files are
  `ReadMe.md`, not `README.md`
  ([g_03](../constitution/g_03_AgentContext.md)).
- Scoped identifiers (plan T-numbers, specification REQ-numbers) are never
  cited bare ([t_03](../constitution/t_03_IdentifierGlossary.md)).
- An `ste:` declaration is earned, never claimed. Set it to `adapted` only
  when `asd_ste100_lint.py` reads zero on all seven counts
  ([tools/](tools/ReadMe.md); profile privately maintained).
- An exemption is declared in the document, with an
  `<!-- ste-exempt: reason -->` marker, and it covers the smallest region
  that quotes the standard [STE profile privately maintained].
- Historical records keep their original words. A dated analysis and an
  executed plan record are never converted to STE, and a verbatim
  quotation is never reworded [STE profile privately maintained].
- Stage a commit from an explicit file list, never `git add <directory>`.
  The `.constitution-guard` denylist and the pre-commit guard enforce the
  boundary ([g_04 §8](../constitution/g_04_ModelHandoffGuide.md)).

## Glossary

Aiko Services terminology, linked to the document that describes it.
Follow the link for the real definition. For identifier *families*
(P1–P12, DA-n, CP-x, ADR-NNN, REQ-n, T-n and more) see the
[Identifier Glossary (t_03)](../constitution/t_03_IdentifierGlossary.md).
They are deliberately not repeated here.

### Framework terminology

| Term | In brief | Described in |
|------|----------|--------------|
| Actor | A Service following the Actor Model — mailbox messages processed one at a time on the event-loop thread | [concepts/actor.md](concepts/actor.md) |
| Category | An Actor grouping Entries (Dependencies, other Categories) into a named, observable collection | [concepts/category.md](concepts/category.md) |
| Component / composition | Building concrete classes from Interface contracts through `compose_class()` / `compose_instance()` | [concepts/component.md](concepts/component.md) |
| Connection | The per-process ladder of connectivity states, from no network up to Registrar available | [concepts/connection.md](concepts/connection.md) |
| Context | The single constructor argument of composed components. Also the Interface base class machinery | [concepts/context.md](concepts/context.md) |
| Dashboard | The terminal user interface for observing and controlling running Services, extensible through plug-ins | [concepts/dashboard.md](concepts/dashboard.md), [dashboard_plugin.md](concepts/dashboard_plugin.md) |
| DataSource / DataTarget | PipelineElement base classes that load and store frames of data at URL-named locations | [concepts/data_source_target.md](concepts/data_source_target.md) |
| Dependency | A reference to a distributed Service — discovery filter, LifeCycleManager URL, Storage URL | [concepts/dependency.md](concepts/dependency.md) |
| Discovery | Finding and invoking remote Services — ServiceDiscovery, remote proxies, `do_command` / `do_request` | [concepts/discovery.md](concepts/discovery.md) |
| ECProducer / ECConsumer | The eventual-consistency shared-state pair — live state published by a Service and replicated by any number of watchers | [concepts/share.md](concepts/share.md) |
| Event loop | The cooperative per-process loop — timer, mailbox, queue and flat-out handlers on one thread | [concepts/event.md](concepts/event.md) |
| Frame | One unit of data flowing through a Stream, processed by `process_frame()` | [concepts/stream.md](concepts/stream.md) |
| Graph Path | Selecting alternative routes through the graph of a PipelineDefinition | [examples/pipeline/ReadMe.md](examples/pipeline/ReadMe.md) |
| Hook | A named extension point inside the framework that third-party handler functions attach to | [concepts/hook.md](concepts/hook.md) |
| HyperSpace | The root Category and LifeCycleManager of Categories — the unified, persistent, navigable graph | [concepts/hyperspace.md](concepts/hyperspace.md) |
| Lease | A time-limited claim on a resource that expires unless extended — the keep-alive primitive | [concepts/lease.md](concepts/lease.md) |
| LifeCycleManager / LifeCycleClient | The pair for creating, tracking and destroying fleets of client Actors | [concepts/lifecycle.md](concepts/lifecycle.md) |
| Message | The publish/subscribe abstraction — MQTT implementation plus the Castaway null implementation | [concepts/message.md](concepts/message.md) |
| Multitude | The scale stress-test example chaining many Pipelines together | [examples/pipeline/multitude/ReadMe.md](examples/pipeline/multitude/ReadMe.md) |
| Pipeline | An Actor executing a graph of PipelineElements from a PipelineDefinition, locally or distributed | [concepts/pipeline.md](concepts/pipeline.md) |
| PipelineDefinition | The validated JSON file defining the graph, elements, deployment and parameters of a Pipeline | [concepts/pipeline.md](concepts/pipeline.md) |
| PipelineElement | The unit of work — the `start_stream` / `process_frame` / `stop_stream` contract | [concepts/pipeline_element.md](concepts/pipeline_element.md) |
| Parameters | Declaration in the PipelineDefinition, per-Stream override, resolution by `get_parameter()` | [concepts/parameters.md](concepts/parameters.md) |
| Process | The per-OS-process framework singleton — the `aiko` global, MQTT connection, dispatch, registration | [concepts/process.md](concepts/process.md) |
| ProcessManager | Create, list and destroy operating-system processes in a unified, distributed fashion | [concepts/process_manager.md](concepts/process_manager.md) |
| Proxy | Transparent method interception — routing every public method call through a proxy function | [concepts/proxy.md](concepts/proxy.md) |
| Recorder | A Service that ring-buffers log topics and republishes them as shared state for the Dashboard | [concepts/recorder.md](concepts/recorder.md) |
| Registrar | The Service discovery hub — live directory, add/remove streams, queries, primary election | [concepts/registrar.md](concepts/registrar.md) |
| Scheme (DataScheme) | The pluggable mapping from URL schemes (`file:`, `zmq:`, `rtsp:` and more) to data access code | [concepts/scheme.md](concepts/scheme.md) |
| Service | The distributed component primitive — topic path, name, protocol, transport, owner, tags | [concepts/service.md](concepts/service.md) |
| S-expression | The wire format for messages and shared state, chosen over JSON and protobuf (ADR-002) | [concepts/utilities/parser.md](concepts/utilities/parser.md), [ADR-002](../constitution/adr/ADR-002_SExpressionWireEncoding.md) |
| Storage | The persistence SPI and its file-system implementation (directories, files, symbolic links) | [concepts/storage.md](concepts/storage.md) |
| Stream | A leased flow of Frames — Stream/Frame dataclasses, StreamEvent / StreamState semantics | [concepts/stream.md](concepts/stream.md) |
| Transport | The layer above Message turning remote Services into callable Python objects | [concepts/transport.md](concepts/transport.md) |

### Governance and documentation terminology

| Term | In brief | Described in |
|------|----------|--------------|
| ADR | Architectural Decision Record — append-only record of a decision and its rationale | [adr/ReadMe.md](../constitution/adr/ReadMe.md) |
| AS-RFC | An Aiko Services RFC — formal, language-neutral specification with numbered requirements; series conventions in the template | [t_01](../constitution/t_01_OkfRfcTemplate.md) |
| Candidate principle | A missing design principle awaiting ADR adoption (CP-A…CP-I, P11) | [p_02](../constitution/p_02_CandidatePrinciples.md) |
| ClearName | The CamelCase name of a document — its identity. Numeric prefixes only order and group | [../constitution/ReadMe.md](../constitution/ReadMe.md) |
| Composition boundary | The decidable P7 rule — which public APIs must compose, and the three exempt categories that carry a header note | [ADR-022](../constitution/adr/ADR-022_CompositionBoundary.md) |
| Constitution | The set of documents governing development — principles, specifications, plans, guides, analyses, templates | [../constitution/ReadMe.md](../constitution/ReadMe.md) |
| Deferred amendment | A principle strengthening held in the roadmap until the artifacts comply (DA-1…DA-5) | [p_00](../constitution/p_00_DesignPrinciples.md) |
| Design principles | P1–P10 and P12 — the binding constitution of the framework, with precedence tiers | [p_00](../constitution/p_00_DesignPrinciples.md) |
| Gatekeeper | The sole authority that applies any change to a live Concept — the four-stage proposal gate and its machine-readable constitution | [s_05](../constitution/s_05_GatekeeperProtocol.md) |
| Improvement loop | The goal record, declarative acceptance criteria, state machine and experiment ledger | [s_04](../constitution/s_04_GoalAcceptanceImprovementLoop.md) |
| Golden trace | A blessed recording used as a conformance test — test by methodology M1–M4 | [e_06](../constitution/e_06_TestingStrategy.md) |
| Governance rules | G1–G7 — how principles are adopted, amended, deferred and audited | [p_01](../constitution/p_01_PrinciplesGovernance.md) |
| Guarded evaluation / default-deny | P12 — mobile code runs only in the sandboxed interpreter, never an unguarded `eval()`. Every public API is deny-all per method | [p_00 P12](../constitution/p_00_DesignPrinciples.md), [ADR-023](../constitution/adr/ADR-023_GuardedEvalDefaultDeny.md) |
| OKF | Open Knowledge Format — one document per file, YAML front matter, audience-first sections, explicit cross-links | [../constitution/ReadMe.md](../constitution/ReadMe.md), [t_00](../constitution/t_00_OkfConceptTemplate.md), [t_02](../constitution/t_02_OkfTaxonomy.md) |
| STE | ASD-STE100 Simplified Technical English — the controlled language for documentation and technical communications. Each document declares `ste: full\|adapted\|false`, and `asd_ste100_lint.py` earns that declaration | [tools/](tools/ReadMe.md); profile privately maintained |

## Maintaining this guide

This guide derives from the per-directory indexes, and it never overrides
them. When an area gains or loses documents, its own `ReadMe.md` is
updated first. Update this guide only when the *cross-directory* picture
changed: a new area, a changed reading order, or a new term. The glossary
one-liners paraphrase the `description:` front matter of the owning
documents. Correct them there first. Every change here appends a
[journal](../constitution/log.md) entry, per the same-change rule. This
guide is written in STE at the `adapted` level, so run
`python3 tools/asd_ste100_lint.py ReadMe.md` before you declare it done.
