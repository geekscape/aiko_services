---
title: Aiko Services Constitution — index
description: Index of the public constitution — the normative artifacts,
  operating guides, execution plans and analyses that govern Aiko Services
  development
type: index
audience: [project-lead, architects, developers, ai-coding-agents]
status: operational
ste: adapted
last_updated: 2026-08-27
---

# Aiko Services Constitution

This directory is the **constitution**: the set of documents that govern
Aiko Services development. Every AI coding session and every human
contributor reads the same documents. When a specification is silent,
decisions appeal to the design principles.

This is the **public constitution** — the rules and designs in play today.
Forward-looking material (aspirations, prioritization, commercially
sensitive designs) is maintained in a private constitution and promotes
into this directory through the governance process as it lands. Documents
here mark such material "[Privately maintained]" or "[Reserved for private
item]" where a reference would otherwise dangle.

Files follow the **`G_II_ClearName.md`** naming scheme. The group letters
match the initials of the document type:

- **p** — principles and governance
- **s** — specifications and design
- **e** — plans (execution and transition)
- **g** — operating guides and agent context
- **a** — analyses
- **t** — templates and documentation conventions

The sections below carry the reading order (p → s → e → g → a → t).
**Identity is the ClearName**: cite documents by name. The numeric prefix
orders and groups the documents, and it can change at a future
reorganization. Gaps in a group's number sequence are documents maintained
privately — the numbers stay reserved.

The documents follow the Open Knowledge Format (OKF) conventions: one
document per file, YAML front-matter (per the closed vocabularies in
[t_02_OkfTaxonomy.md](t_02_OkfTaxonomy.md)) and explicit cross-references.
Statuses distinguish **normative** (binding), **operational** (in daily
use), **draft-for-verification** / **proposal** (pending promotion),
**execution-plan** (committed roadmaps), **informational** (analyses and
records) and **superseded**.

## p — Principles and governance

| Document | Status | One-line summary |
|----------|--------|------------------|
| [Framework Design Principles](p_00_DesignPrinciples.md) | normative | The framework design principles (P1–P10, P12) — the constitution of the framework; when a specification is silent, decisions appeal to these |
| [Design Principles Governance](p_01_PrinciplesGovernance.md) | normative | The governance rules (G1–G7) for the Design Principles — how principles are adopted, amended, deferred and kept aligned with the code |
| [Candidate Design Principles](p_02_CandidatePrinciples.md) | proposal | The missing crucial Design Principles — full draft wording, in-play assessments and adoption paths, awaiting ADRs |

## s — Specifications and design

| Document | Status | One-line summary |
|----------|--------|------------------|
| [Specifications: Runtime, Services, Actors, Agents](s_00_Specifications.md) | draft-for-verification | RFC 2119 normative voice; decomposing into the AS-RFC series |
| [Repository Layout](s_01_RepositoryLayout.md) | proposal | Target `src/aiko_services/` layout and one-way layering rules |
| [Design by Composition of Interfaces](s_02_InterfaceComposition.md) | draft-for-verification | Interfaces, Implementations, binding, and the interface catalog (P7) |
| [Self-Awareness Telemetry](s_03_SelfAwarenessTelemetry.md) | draft-for-verification | The HostMonitor Actor and host.* EC keys for resource monitoring, and the OpenTelemetry model for logs, metrics and traces |
| [Goals, Acceptance Criteria and the Improvement Loop](s_04_GoalAcceptanceImprovementLoop.md) | draft-for-verification | The goal record with declarative acceptance criteria, the sandboxed predicate language, the improvement-loop state machine, its supervision and the experiment ledger |
| [Gatekeeper Protocol and the Machine-Readable Constitution](s_05_GatekeeperProtocol.md) | draft-for-verification | The generic proposal gate — wire protocol, four-stage gate over registered definition kinds, rollback semantics, and the declarative constitution document the gate enforces |

## e — Plans

| Document | Status | One-line summary |
|----------|--------|------------------|
| [Transition Plan](e_00_TransitionPlan.md) | proposal | Move the project's truth from code into normative artifacts |
| [First-Class Agents](e_03_FirstClassAgents.md) | execution-plan | Agent enters the interface chain, with pluggable agent-framework backends |
| [Testing Strategy](e_06_TestingStrategy.md) | execution-plan | Golden traces where self-exercising is strong; ADR-012…ADR-016 |

## g — Operating guides and agent context

| Document | Status | One-line summary |
|----------|--------|------------------|
| [Release Process Guide](g_01_ReleaseProcessGuide.md) | operational | The eight-step release lifecycle: test, documentation, release notes, version bump, tag, clean-clone build, release page, announcements |
| [Claude Code Operating Guide](g_02_ClaudeCodeOperatingGuide.md) | operational | Worktrees, context architecture, kickoff sequence, failure modes |
| [Agent Context (CLAUDE.md / AGENTS.md)](g_03_AgentContext.md) | operational | Drop-in agent context, "Conventions an agent must follow", sharp edges |
| [Model Handoff Guide](g_04_ModelHandoffGuide.md) | operational | Hard rules, checklists and verification recipes for less capable successor models working on the documentation |

## a — Analyses

| Document | Status | One-line summary |
|----------|--------|------------------|
| [Architecture Review](a_00_ArchitectureReview_2026-06.md) | informational | Senior-architect review of v0.6, June 2026, re-derived from source — the as-built architecture and interface catalog |

## t — Templates and documentation conventions

| Document | Status | One-line summary |
|----------|--------|------------------|
| [OKF Concept Template](t_00_OkfConceptTemplate.md) | operational | The necessary section structure and guidance for `documentation/concepts/` |
| [OKF RFC Template](t_01_OkfRfcTemplate.md) | operational | AS-RFC series conventions — Internet-RFC-style specifications, OKF-compatible; numbered REQs bind to conformance traces |
| [OKF Front-matter Taxonomy](t_02_OkfTaxonomy.md) | proposal | Closed type/status/audience vocabularies and field rules for all OKF documentation |
| [Identifier Glossary](t_03_IdentifierGlossary.md) | operational | One-page map of every identifier family to its owning document, plus citation style |

The project's ASD-STE100 profile is maintained privately
[Reserved for private item]. That profile holds the rules digest, the
word register and the global STE switch behind the `ste:` front-matter
levels. The STE lint in
[../documentation/tools/](../documentation/tools/ReadMe.md) is the public
gate that earns every declaration.

## Related

- [ADR registry](adr/ReadMe.md) — Architectural Decision Records
  (`ADR-NNN_ClearName.md`). The registry owns the numbers.
- [Diagrams](diagrams/ReadMe.md) — architecture overview, architecture
  detail and HyperSpace structure, with rendered-view links (GitHub shows
  raw HTML source, so use the View links there).
- [Public journal](log.md) — the dated journal of changes to this tree.
  Every substantive change appends an entry.
- [Documentation reading guide](../documentation/ReadMe.md) — the
  orientation for the `documentation/` tree: concepts, elements, examples
  and tools.
- Repository root `CLAUDE.md` (a symlink to `Agents.md`) — echoes the
  naming and ReadMe conventions from
  [g_03_AgentContext.md](g_03_AgentContext.md).
- `.constitution-guard` (repository root) — the staged-path denylist
  enforced by the pre-commit guard. An amendment to it is a constitutional
  change.
