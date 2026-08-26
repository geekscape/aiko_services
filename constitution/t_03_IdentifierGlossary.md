---
title: Identifier glossary — every identifier family and its owning document
description: One-page map of the identifier families used across the
  Aiko Services documentation (P, CP, DA, G, U/S, ADR, AS-RFC, REQ, M, I,
  L/B, T, potential items, waves, horizons) — what each means and which
  document defines and owns it
type: guide
audience: [project-lead, architects, developers, ai-coding-agents]
status: operational
ste: adapted
related: [ReadMe, g_04_ModelHandoffGuide, p_00_DesignPrinciples,
  p_01_PrinciplesGovernance, p_02_CandidatePrinciples, t_01_OkfRfcTemplate,
  t_02_OkfTaxonomy]
last_updated: 2026-07-31
---

# Identifier glossary — every identifier family and its owning document

The Aiko Services documentation defines its identifiers in a distributed way: each family
has exactly one **owning document** (the registry pattern). Two conventions bind them all
(`g_04_ModelHandoffGuide.md` rules 8–9):

1. **Registries own identifier numbers.** Never mint a number in prose or a plan. Add the
   registry row in the same change that creates the document, or do not use the number.
2. **Identifiers are frozen.** Never renumber, merge or re-letter them: later documents cite
   them, and renumbering breaks the reference graph.

## The families

| Identifier | Meaning | Owning document |
|------------|---------|-----------------|
| **P1–P10, P12** | The adopted framework design principles — the constitution of the framework (P12 adopted 2026-07-13, ADR-023: guarded evaluation + default-deny method exposure — candidate CP-E's promotion) | [p_00_DesignPrinciples.md](p_00_DesignPrinciples.md), one section per principle (rule, reasoning, forbidden anti-patterns) |
| **P11** | Candidate eleventh principle (all state mutation on the event-loop thread) — number reserved, unadopted; hence the gap in the adopted sequence | Stub in p_00 "Candidate principles awaiting ADR"; full draft in [p_02_CandidatePrinciples.md](p_02_CandidatePrinciples.md) |
| **CP-A…CP-I** | **C**andidate **P**rinciples — the missing principles awaiting ADR adoption (CP-E adopted 2026-07-13 as P12) | Stubs in p_00; full wording, in-play assessments and adoption paths in [p_02_CandidatePrinciples.md](p_02_CandidatePrinciples.md) |
| **Phase 0, 1, …** | The ordered, gate-conditioned segments of one execution plan — **the standard term** (project-lead direction, 2026-07-19): "Stage" and plan-internal "Wave" were retired and renamed to Phase throughout, numbers unchanged. Scoped **per plan** — always cite as "e_03 Phase 0", never bare | Each `e_NN` plan document; convention here and g_04 rule 12 |
| **Waves 1–3** | The candidate-principle adoption batches — after the 2026-07-19 Phase standardization, **the only sanctioned "Wave" usage**; the only sanctioned "Stage" usages are gate-internal stage numbering and external organizations' own terms | [Privately maintained — prioritization register] |
| **DA-1…DA-5** | **D**eferred **A**mendments — strengthenings of P1–P10 held in the roadmap until the artifacts comply (per G3); DA-1→P4, DA-2→P5, DA-3→P8, DA-4→P1, DA-5→P3 | p_00 § "Deferred amendments" |
| **G1–G7** | Governance rules for how principles are adopted, amended and audited | [p_01_PrinciplesGovernance.md](p_01_PrinciplesGovernance.md) |
| **U1–U8** | "Unknown unknowns" — the July 2026 critique's gap findings | [Privately maintained register] |
| **S1–S9** | The same critique's suggestions (unrelated to the `s_NN` file-name prefix) | [Privately maintained register] |
| **review §n.n** | June 2026 architecture-review sections, cited as evidence | [a_00_ArchitectureReview_2026-06.md](a_00_ArchitectureReview_2026-06.md) |
| **ADR-NNN** | Architectural Decision Records | Registry: [adr/ReadMe.md](adr/ReadMe.md) (owns the numbers); one `ADR-NNN_ClearName.md` file per record |
| **AS-RFC-N** | The Aiko Services RFC series — normative wire-protocol specifications | Registry: [Privately maintained until the series publishes]; conventions in [t_01_OkfRfcTemplate.md](t_01_OkfRfcTemplate.md) |
| **[REQ-n]** | Numbered normative requirements inside a specification | Scoped **per document** (t_01 convention) — s_04 [REQ-5] and s_07 [REQ-5] are unrelated; always cite with the document name |
| **M1–M4** | The four test methodologies (golden traces; boundary; foundational primitives; cross-language conformance) | [e_06_TestingStrategy.md](e_06_TestingStrategy.md), bound by ADR-012 |
| **I1–I6** | Design principles of a private-track plan | [Privately maintained] |
| **L0–L3, B0–B3** | Autonomy-staging identifier families | [Privately maintained — ADR registry rows reserved] |
| **T1, T2, …** | Task numbers inside an execution plan | Scoped **per plan document** — always cite as "e_01 T4", never bare (playbook rule [Privately maintained]) |
| **C1–C4** | ADR-022's standing concerns for the e_10 retrospective normalization (G3 inversion; runtime-core blast radius; downstream churn; retrospective-fixing-is-not-rewriting) — reviewed with the project lead at every e_10 phase kickoff | [../adr/ADR-022_CompositionBoundary.md](../adr/ADR-022_CompositionBoundary.md) §Standing concerns; dispositions recorded in e_10 §6. Scoped to ADR-022/e_10 (registered 2026-07-19, correcting a same-change omission) |
| **Items 01–21** | The prioritized potential list; the `NN` prefix is the current priority rank | [Privately maintained] |
| **Horizons A–D** | Roadmap eras | [Privately maintained] |
| **Actions 1–10** | The July 2026 constitution rework plan's numbered actions | [Privately maintained] |
| **p/s/e/g/a/t/z** | Constitution file-group letters (principles, specifications, plans, guides, analyses, templates, working notes) | [ReadMe.md](ReadMe.md) |
| **CP-J** | Reserved — letter registered so it is never reused | [Privately maintained]; deliberately **not** in p_02 |

## Citation style

Cite identifiers tersely and by number. Add the owning document when the scope is ambiguous.
Examples: "rejected: violates P3, introduces a blocking getter" (G6), "e_01 T4",
"s_04 [REQ-5]", "critique U7", "review §4.5". Scoped families (T-numbers, REQ-numbers) have
no meaning without their document name — never cite them bare.

## Maintaining this glossary

To add a new identifier family: give it one owning document, then add a row here in the same
change. Never re-letter an existing family to make room. To retire a family, use the same
discipline as for a principle: project-lead instruction, recorded (G7).
