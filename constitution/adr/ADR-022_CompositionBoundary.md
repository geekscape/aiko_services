---
title: "ADR-022 — The composition boundary and retrospective normalization"
description: Defines which public APIs must use the Interface / Implementation
  composition pattern (P7) and the three exempt categories — value types,
  presentation and CLI shells, pre-composition bootstrap — and records the
  decision to fix the pre-gate source code retrospectively through
  the public-API composition rollout rather than weaken the principle
type: adr
audience: [project-lead, architects, developers, ai-coding-agents]
status: normative
ste: adapted
related: [ReadMe, ADR-021_SynthesizedDefaultInit,
  ../constitution/p_00_DesignPrinciples,
  ../constitution/p_01_PrinciplesGovernance,
  ../constitution/s_02_InterfaceComposition]
last_updated: 2026-08-01
---

# ADR-022 — The composition boundary and retrospective normalization

**Accepted by the project lead 2026-07-13.**

## Context

P7's amendment (2026-07-07) rules that "every framework capability must be an
Interface with a registered Implementation — no 'plain class' exceptions",
and named two standing violations. The full audit of `src/aiko_services/main/`
(2026-07-13, e_10 §1) found the real boundary is undecidable at the margins:
read literally, the rule condemns `ServiceFilter` and the `Stream`/`Frame`
dataclasses (value objects with no behavioral contract), the asciimatics
Dashboard (a UI shell), and `process.py`/`message/` (which *construct* the
machinery composition depends on, so cannot themselves be composed at import
time). Meanwhile roughly a third of the public surface genuinely violates
P7. Three shapes occur: plain-class capabilities
(`ECProducer`/`ECConsumer`, `ServiceDiscovery`, `Lease`, the event
functions), implementation inheritance
(`DataSource(PipelineElementImpl)`), and empty marker Interfaces
(`Registrar`, `Recorder`). All of it was written before the Design Principles,
the ADR gate and the G-rules existed.

Two questions follow. First, where exactly does the composition mandate
stop? Second, what must be done about legacy non-compliance? The choice is
to weaken the principle to match the source (per the G3 "current, not
aspirational" default), or to correct the source to match the principle.

## Decision

1. **The composition mandate covers every public behavioral capability.**
   A capability is public API whose behavior a caller depends on. It is also
   API that could meaningfully be substituted — anything a test double, an alternative
   backend or an embedded build might replace. All such APIs use the full
   pattern: abstract Interface, `Interface.default` registration, `…Impl`
   with cooperative init, `compose_instance` construction.
2. **Three categories are exempt** — and only these:
   - **Value and data types**: dataclasses, filters, parsers, constants
     namespaces (`ServiceFields`, `ServiceFilter`, `Stream`, `Frame`,
     `ServiceTopicPath`, …). State plus accessors, no behavioral contract.
   - **Presentation and CLI shells**: the asciimatics Dashboard frames and
     plug-in dict, Click command plumbing (`cli.py`, per-module `main()`s).
     Their framework contact is *through* composed APIs, never as one.
   - **Pre-composition bootstrap**: `process.py` and the `message/`
     construction path, which exist before the composition machinery can
     run. Where their surface is public they still declare an Interface *as
     contract* (type-checkable, documented, substitutable in tests), but
     registration and `compose_instance` are not required.
3. **Every exempt file carries a header note naming its category** —
   "Not part of the Interface composition pattern (ADR-022 category N) —
   see e_10 §2.16." An exemption without the note is a P7 violation. The
   drift audit checks the note, making compliance decidable.
4. **Legacy non-compliance is fixed retrospectively, not grandfathered.**
   Project-lead decision: the pre-gate source is brought up to the
   principle through the composition rollout plan [Privately maintained],
   approved 2026-07-13. The principle is not re-scoped down to the
   source. This is a
   deliberate, bounded exception to the G3 default (which would file
   deferred amendments and wait): the violations are enumerated (e_10 §1),
   the remediation is scheduled (e_10 §5 waves), and the exception closes
   when the last phase lands. Until then, e_10 §1 is the authoritative list
   of known violations. The drift audit tracks it to closure.
5. **In the future, compliance is at introduction.** New public APIs comply
   with P7 in the change that introduces them, or they carry a categorized
   exemption note. The Design Principles, the ADRs and the constitution in
   general apply consistently from 2026-07-13 onward.

## Consequences

- P7's boundary is now decidable: composed, categorized-exempt, or
  violation. The absurd readings (interface-wrapping a dataclass) are
  foreclosed.
- g_03_AgentContext stops the description of violations as "by current
  design". Agents are pointed at e_10 for every gap that it lists.
- Evidence trail: P7 with its 2026-07-07 amendment, G3 (p_01), the e_10 §1
  audit, and the s_02 verification record 2026-07-13.

## Standing concerns — C1–C4 (review at every e_10 phase kickoff)

The retrospective approach carries four named concerns. **This ADR does not
resolve them.** At the kickoff of every e_10 phase, the human architect
(project lead) is reminded of all four. Any that bite at that
point are dealt with then, and the disposition is recorded in the e_10 §6
Decision record. An agent starting an e_10 phase without this review is
violating this ADR.

- **C1 — the G3 inversion.** The constitution knowingly carries named
  violations until e_10 completes — explicit, bounded and tracked rather
  than silent. The risk is schedule slip: if e_10 stalls, P7 becomes
  exactly the aspirational principle G3 exists to prevent. Kickoff check:
  is e_10 §1 still an honest, current compliance record?
- **C2 — blast radius of the runtime core.** Phase 3 touches the
  least-tested, most load-bearing code (event, process, message — the
  bootstrap), and the composition engine has two known latent bugs.
  Containment: the P7 test-first precondition, one commit per file,
  `pytest` and critical-lint green per phase. Kickoff check: are the
  preconditions actually met — and resist reordering waves to "get the big
  ones done first".
- **C3 — downstream churn.** `ECProducer(service, share)` is constructed
  positionally throughout `elements/` and the examples. The wire protocol
  is untouched (other-language implementations unaffected) but Python API
  compatibility is not. Kickoff check: shim in place, duration decided,
  release notes updated.
- **C4 — retrospective fixing must not become rewriting.** The exemption
  taxonomy is the guard against "compliance" conversions that add ceremony
  without substitutability (dataclasses, the Dashboard, the bootstrap). If
  a file resists composition, the right move is arguing its category — not
  forcing the pattern. Kickoff check: has any task drifted from
  normalizing an API to redesigning it? If so, stop and split it out.
