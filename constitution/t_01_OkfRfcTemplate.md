---
title: OKF RFC template — Aiko Services specification documents
description: Template and conventions for Internet-RFC-style specification
  documents (AS-RFC series) that remain Open Knowledge Format compatible
type: template
audience: [architects, developers, ai-coding-agents]
status: operational
ste: adapted
related: [t_00_OkfConceptTemplate, p_01_PrinciplesGovernance,
  p_02_CandidatePrinciples, s_00_Specifications]
last_updated: 2026-07-31
---

# OKF RFC template — Aiko Services specification documents

Aiko Services uses Internet-RFC-style documents (the **AS-RFC series**) for anything a second
implementation must conform to. This template defines the conventions. It exists because three
RFC-culture properties solve verified project problems:

- Numbered requirements give conformance golden traces something to bind to (CP-H)
- The updates/obsoletes discipline applies compatible evolution (CP-G) to the documents
  themselves
- A mandatory Security Considerations section institutionalizes the critique-U4 lesson

## When to use this template — and when not to

**Use AS-RFC form for:**

- The wire protocol grammar and the topic namespace
- The Registrar, EC-state, lease and lifecycle protocols
- The out-of-band bulk channel
- Capability addressing, flow control and identity
- The protocol/version registries
- The element package format

Test: *if it needs a conformance trace, it is an RFC.*

**Do not use it for:** design principles, governance, concepts documentation, execution plans,
analyses, guides. Those remain audience-first OKF prose. Test: *if it needs to persuade or
teach, it is not an RFC.*

## OKF compatibility

Every AS-RFC keeps the standard OKF YAML front-matter, extended with an `rfc:` block:

```yaml
---
title: AS-RFC-2 — Aiko Services Registrar Protocol
description: Discovery, registration, query and death-notice protocol
type: rfc
audience: [implementers, architects, ai-coding-agents]
status: draft-for-verification   # maps to RFC maturity, see below
ste: adapted                     # AS-RFC default; see the STE profile [Privately maintained]
related: [AS-RFC-1, p_00_DesignPrinciples]
last_updated: 2026-07-07
rfc:
  number: 2                      # immutable once assigned
  category: standards-track      # standards-track | informational | experimental
  updates: []                    # AS-RFC numbers this document updates
  obsoletes: []                  # AS-RFC numbers this document replaces
---
```

**Status ladder (OKF `status` ↔ RFC maturity):** `draft-for-verification` (internet-draft
equivalent — you can edit it freely) → `proposal` (last call — content-frozen, and it gathers
review) → `normative` (published — **never edited again**). A change to a published AS-RFC
mints a successor that `updates:` or `obsoletes:` this one, per CP-G. The
`informational`/`experimental` categories can also reach `normative` status (which means
"published"). They bind no one.

## Document structure

1. **Abstract** — one paragraph. It states what this protocol does and who must conform.
2. **Status of This Memo** — category, maturity, what it updates/obsoletes.
3. **Terminology** — RFC 2119/8174 boilerplate ("The key words MUST, MUST NOT, REQUIRED, SHALL,
   SHOULD, MAY … are to be interpreted as described in RFC 2119 when, and only when, they appear
   in all capitals"), plus project terms used normatively.
4. **Body sections** — numbered (`## 4. Message grammar`, `### 4.1 …`). The anchors are
   stable. Never renumber them within a published RFC.
5. **Security Considerations** — REQUIRED, never "none": trust model, what CP-C capabilities
   confine, what an attacker on the bus can do, residual risks.
6. **Registry Considerations** — the IANA-considerations analogue: what this RFC adds to the
   protocol-id / version / command registries (supports CP-G).
7. **References** — split **Normative** (needed to implement) / **Informative**.
8. **Appendix: Conformance traces** — the golden-trace fixtures (or pointers to them in the test
   tree) that certify an implementation against this RFC's requirements.

## Requirement numbering

Every normative statement carries a stable identifier: `[REQ-n]`, unique within the RFC, never
reused or renumbered. External citation form: `AS-RFC-2 [REQ-12]` (with §-references as a
courtesy). Golden traces and test names cite REQ identifiers, giving mechanical
spec-to-test traceability in both directions.

Example:

> **[REQ-12]** A Registrar MUST publish `(primary absent)` as its Last Will and Testament on the
> bootstrap topic before publishing `(primary found …)`.

## Style rules

- RFC 2119 keywords in ALL CAPS carry normative force. Lower-case "must/should" is prose and
  carries none. Reword the sentence to prevent the ambiguity.
- One protocol (or one coherent registry/format) for each RFC. Compose by reference, not by
  inclusion.
- Wire examples are exact: real S-expressions, real topic paths, byte-accurate where it matters.
- State machines get both a table and a diagram. The table is normative.
- Per CP-H: the RFC, its conformance traces and the reference implementation change **in the
  same commit** when wire-visible behavior changes. The project lead resolves a disagreement
  among the three, explicitly.
- Naming: files are `AS-RFC-NNN_short_name.md`. Write "Aiko Services" in full, never "Aiko".
  The document home is `documentation/specifications/` (decided 2026-07-08). Its `ReadMe.md`
  is the AS-RFC number registry.
