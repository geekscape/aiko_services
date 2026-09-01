---
title: Aiko Services — Design Principles Governance
description: The governance rules (G1–G7) for the Design Principles — how
  principles are adopted, amended, deferred and kept aligned with the code
type: governance
audience: [project-lead, architects, developers, ai-coding-agents]
status: normative
ste: adapted
related: [p_00_DesignPrinciples, p_02_CandidatePrinciples]
last_updated: 2026-07-31
---

# Aiko Services — Design Principles Governance

**Status:** Normative. The project lead adopted these rules on 2026-07-07. These rules govern
how `p_00_DesignPrinciples.md` changes. They exist so that the principles stay the constitution
of the framework — binding, checkable, and never in drift from the artifacts that they govern.

---

## G1. Principles are binding

When a specification is silent, agents (human or AI) decide by appeal to the principles. If a
proposed change conflicts with a principle, then the change is wrong, or the principle needs an
ADR. There is no third option.

## G2. Every principle change requires an ADR approved by the project lead

Four changes need an Architectural Decision Record that the project lead approves. These are:
add a principle, amend a principle, retire a principle, or promote a deferred amendment. A direct
instruction from the project lead in a working session counts as approval. The change log in
`p_00_DesignPrinciples.md` records the approval.

## G3. Principles are current, not aspirational (the in-play test)

The Design Principles document always reflects the design *currently in play*. The test for any
proposed rule: **"can an agent comply with this today, in this codebase, without waiting for a
framework rebuild?"**

- **Yes** → the rule can be normative. Honest statements of current semantics ("delivery is
  at-most-once") pass this test. Disciplines for new code ("no new unbounded buffers") also
  pass, even when legacy violations remain. But the project must enumerate and schedule those
  violations.
- **No** → the rule becomes a **deferred amendment (DA-n)**. The "Deferred amendments" section
  of `p_00_DesignPrinciples.md` records the DA. The roadmap carries the DA, marked
  **critically important**. The project promotes the DA into its principle only when the
  source, tests, documentation and examples comply. Promotion *is* the work that makes the
  artifacts comply — never a paper change.

A principle that the code does not satisfy is not a principle. It is an aspiration that drifts.

## G4. Lifecycle of a new principle

candidate → proposal → prioritization → ADR → adoption.

1. **Candidate** — evidence (reviews, audits, convergent TODOs) surfaces the candidate. A stub
   in `p_00_DesignPrinciples.md`, under "Candidate principles awaiting ADR", lists it with a
   CP-x (or next P-number) identifier.
2. **Proposal** — `p_02_CandidatePrinciples.md` holds the full draft wording (rule, why,
   forbidden), the in-play assessment per G3, the evidence trail, and the adoption path.
3. **Prioritization** — the project lead orders the candidates against the roadmap.
4. **ADR + adoption** — adoption splits the draft per G3 into the normative rule (in play at
   adoption) and any DA companion. The team fixes or schedules the enumerated violations. The
   same change updates the examples and the documentation.

## G5. Every rule carries its evidence

Amendments and principles cite their sources and carry their date. A source is a review
section, a critique U/S number, an audit finding, or a set of convergent source-code TODOs. A
future reader must be able to reconstruct *why* each rule exists. Identifier conventions:
**P-n** adopted principles, **CP-x** candidates, **DA-n** deferred amendments, **G-n**
governance rules, **U-n/S-n** critique items.

## G6. Citation style in review

In review, cite a principle by number ("rejected: violates P3, introduces a blocking getter").
This style is expected: terse, checkable, and teachable. The same style applies to governance
("deferred: fails G3 in-play test — file as DA").

## G7. The quarterly review audits drift, both ways

The quarterly aesthetic review (P10) also audits principle–artifact alignment in both
directions. One direction is code that drifted from the principles (violations to schedule).
The other direction is principles that drifted from reality (rules that no ADR would re-adopt
today — candidates for amendment or retirement). The review **flags to the project lead for
re-justification** each deferred amendment or candidate principle that stays unpromoted after
two consecutive reviews. No one ever removes an item from this document, the candidates list,
or the roadmap without the explicit instruction of the project lead (the human architect).
