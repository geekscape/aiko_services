---
title: OKF front-matter taxonomy — Aiko Services documentation
description: The closed type/status/audience vocabularies and front-matter
  field rules for all Aiko Services OKF documentation
type: governance
audience: [project-lead, architects, developers, ai-coding-agents]
status: proposal
ste: adapted
related: [t_00_OkfConceptTemplate, t_01_OkfRfcTemplate,
  p_01_PrinciplesGovernance]
last_updated: 2026-07-31
---

# OKF front-matter taxonomy — Aiko Services documentation

**Status:** Proposal. It was drafted under the action 6 pre-work, and it promotes to
operational on project-lead approval. It applies to every OKF document under
`documentation/`: constitution, concepts, elements, examples, potential, adr and
specifications. A doc-lint can enforce it (potential item 19).

## Required fields

Every OKF document carries exactly these front-matter fields, in this order:
`title`, `description`, `type`, `audience`, `status`, `ste`, `related`, `last_updated` — plus
`rfc:` (AS-RFC series only). Nothing else without amending this taxonomy.

## `type` — closed vocabulary (12 values)

| type | Meaning | Typical home |
|------|---------|--------------|
| `index` | directory index / registry | any directory's ReadMe.md |
| `principles` | binding design principles | constitution group p |
| `governance` | meta-rules about how documents/decisions work | constitution group p |
| `adr` | one architectural decision record | constitution/adr/ |
| `specification` | normative-intent design/wire prose (pre-RFC) | constitution group s |
| `rfc` | AS-RFC series document | the AS-RFC series [Privately maintained until it publishes] |
| `design` | architecture/design exposition | constitution group s |
| `plan` | transition or execution plan | constitution group e |
| `guide` | operating guide for humans/agents | constitution group g |
| `agent-context` | drop-in AI-assistant context | constitution group g |
| `analysis` | review, comparison, critique, roadmap analysis | constitution group a |
| `template` | document-format definition | constitution group t |
| `concept` | one concept document | documentation/concepts/ and more |
| `potential` | one potential-list item | the potential list [Privately maintained] |

(Folded and retired: `roadmap` → `analysis`. Also `proposal` and `release-notes` as *types* —
proposal is a status. Release notes keep `type: release-notes` as the one grandfathered
exception in `documentation/release_notes.md`.)

## `status` — closed vocabulary (7 values)

`normative` | `operational` | `execution-plan` | `draft-for-verification` | `proposal` |
`informational` | `superseded`

- Exactly one value. Do not put an inline comment on the line.
- ADRs use `proposal` → `normative` (accepted) → `superseded`.
- AS-RFCs map maturity onto the same ladder (`draft-for-verification` → `proposal` (last call)
  → `normative` (published, immutable)).
- `superseded` documents gain a `superseded_by:` pointer as the one permitted extra field.

## `ste` — closed vocabulary (3 values)

`full` | `adapted` | `false` — whether the document is written in ASD-STE100 Simplified
Technical English (adopted 2026-07-31). The rules digest, the project profile and the global
STE switch are in the project STE profile [Privately maintained].

- `full` — part 1 writing rules plus part 2 dictionary discipline (every word approved,
  registered as a technical word, or quoted text).
- `adapted` — part 1 writing rules plus the t_04 swap list. Per-word dictionary proof is
  not necessary.
- `false` — STE not applied.
- Declare `full`/`adapted` only when the text actually complies (G3 "current, not
  aspirational"). Existing documents stay `ste: false` until they are converted.
  "Complies" means `documentation/tools/asd_ste100_lint.py` reads zero on all seven
  counts. Re-run the gate rather than trust the field, because a hardened check can
  retire a declaration that was honest when it was made.
- New documents default to `full` (concepts, elements, examples, guides, procedures) or
  `adapted` (AS-RFCs, ADRs, dense normative prose). No document declares `full` yet
  (t_04 §1).
- The five documents that keep `ste: false` on purpose are the historical records: the
  dated analyses a_00, a_01 and a_02, the executed record e_07, and `release_notes.md`
  for its v0.6 and v0.7 sections.

## `audience` — closed vocabulary

Any subset of: `project-lead`, `architects`, `developers`, `implementers`,
`ai-coding-agents`, `application-developers`.

## Field rules

- **`related:`** — document names only, with no `.md` extension. For the same directory,
  use the bare name (`p_00_DesignPrinciples`). For a different directory, use the relative
  path without the extension (`../constitution/p_00_DesignPrinciples`). Link liberally, but
  every entry must resolve.
- **`description:`** — one sentence. It is the single source for the index one-liners. A
  directory ReadMe derives its table from these, never the reverse.
- **`last_updated:`** — ISO `YYYY-MM-DD`. Update it in the same change as any content edit.
- **Dated analyses** carry an `_YYYY-MM` filename suffix. An undated document must be current.
- **Identity is the ClearName** (project-lead decision, 2026-07-08). Cite a document by
  name, not by numeric prefix. The prefixes order and group the documents, and they can
  change at a reorganization. The same day showed this: the group letters of the
  constitution became mnemonic (p/s/e/g/a/t, project-lead direction), and no ClearName
  reference broke.
