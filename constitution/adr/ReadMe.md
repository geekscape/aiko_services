---
title: Aiko Services Architectural Decision Records — registry and index
description: The append-only ADR registry — every ADR number, its status
  (written, claimed by a plan, reserved, or free) and the numbering
  discipline
type: index
audience: [project-lead, architects, developers, ai-coding-agents]
status: operational
ste: adapted
related: [../p_01_PrinciplesGovernance, ../p_00_DesignPrinciples]
last_updated: 2026-09-01
---

# Aiko Services Architectural Decision Records

This directory holds the ADRs, which are append-only records of architectural decisions.
Governance rule **G2** needs one for every Design Principles change (adoption, amendment,
deferral promotion, retirement). Use one for any decision worth a durable rationale.

## Conventions

- **Naming:** `ADR-NNN_ClearName.md` (three-digit number, CamelCase ClearName — consistent with
  the constitution's `G_II_ClearName` and the `AS-RFC-NNN` conventions).
- **Numbers are owned by this registry**, not by memory or by plans: claim a number by adding a
  row here in the same change that creates the file. Numbers are never reused. A superseded ADR
  keeps its number and gains `status: superseded` plus a pointer to its successor.
- **Reserved rows:** an ADR maintained in the private constitution keeps its registry row
  here as "[Reserved for private item]". The number stays claimed, append-only integrity
  holds, and the record publishes if and when its subject matter does.
- **Front-matter:** `type: adr`. `status: proposal` → `normative` (accepted) → `superseded`,
  per the closed vocabulary (`../t_02_OkfTaxonomy.md`).
- **Body:** Context, Decision, Consequences, and the evidence trail (principle numbers,
  critique U/S items, review sections) per G5.

## Registry

| ADR | Title / subject | Status | Claimed by |
|-----|-----------------|--------|------------|
| 001 | *(released 2026-07-13 — was only a placeholder series-anchor citation, never written; number retired unused)* | released | — |
| [002](ADR-002_SExpressionWireEncoding.md) | S-expressions over JSON/protobuf (wire encoding rationale) | normative (founding decision; backfill record written 2026-07-13) | s_00_Specifications §1.1 |
| [003](ADR-003_UidAddressSpaces.md) | HyperSpace/Storage UID address-space allocation — 48-bit MAC-style spaces [leading nibble 0 = Aiko Services development, f = Aiko Services future, 1–e third parties], class-octet / identity-octets split, space-fill extension embedding | normative (accepted 2026-09-01) | Storage UID mode 3 rollout — shared specification with the CRC-cards session |
| 004 | — | free | |
| 005 | — | free | |
| 006 | Agent in the interface chain; thin-interface constraint; cognition boundary rule | claimed | e_03_FirstClassAgents T1 |
| 007 | A2A adopted at the edge only, never internal | claimed | e_03_FirstClassAgents T16 |
| 008 | [Reserved for private item] | claimed | [Reserved for private item] |
| 009 | [Reserved for private item] | claimed | [Reserved for private item] |
| 010 | [Reserved for private item] | claimed | [Reserved for private item] |
| 011 | [Reserved for private item] | claimed | [Reserved for private item] |
| 012 | Test by methodology, not by habit (M1–M4) | claimed | e_06_TestingStrategy §8 |
| 013 | Golden traces are blessed recordings | claimed | e_06_TestingStrategy §8 |
| 014 | Self-exercising tests assert negative and boundary facts | claimed | e_06_TestingStrategy §8 |
| 015 | Foundational primitives are tested directly and adversarially | claimed | e_06_TestingStrategy §8 |
| 016 | The wire protocol is a cross-language contract; conformance is mandatory | claimed | e_06_TestingStrategy §8 |
| 017 | [Reserved for private item] | normative (accepted 2026-07-08) | [Reserved for private item] |
| 018 | [Reserved for private item] | normative (accepted 2026-07-08; amended 2026-07-09) | [Reserved for private item] |
| 019 | [Reserved for private item] | normative (accepted 2026-07-09) | [Reserved for private item] |
| 020 | [Reserved for private item] | normative (accepted 2026-07-09) | [Reserved for private item] |
| [021](ADR-021_SynthesizedDefaultInit.md) | Synthesized default `__init__` for composed components; `PROTOCOL` class attribute; explicit constructors always win | normative (accepted 2026-07-13) | [Privately maintained rollout] |
| [022](ADR-022_CompositionBoundary.md) | The composition boundary (three exempt categories) and retrospective normalization of pre-gate source through e_10 | normative (accepted 2026-07-13) | p_00 P7 amendment 2026-07-13 [rollout privately maintained] |
| [023](ADR-023_GuardedEvalDefaultDeny.md) | Guarded evaluation and default-deny method exposure — adopts CP-E (mobile code only through the sandboxed interpreter, never unguarded `eval()`) and mints **P12**; per-method allow/deny lists, CRUD at runtime under governed control | normative (accepted 2026-07-13; decision 6 added at acceptance — isolated dev deployments may run allow-all, policy only, advertised, never externally reachable) | p_00 P12 / p_02 CP-E adoption record |
| 024+ | next free numbers | free | |
