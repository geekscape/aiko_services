---
title: OKF Concepts documentation template
description: The necessary structure and section-by-section guidance for
  every document in documentation/concepts/ — audience-first ordering, from
  brief overview through application-developer usage to framework internals
type: template
audience: [developers, ai-coding-agents]
status: operational
ste: adapted
related: [g_03_AgentContext]
last_updated: 2026-07-31
---

# OKF Concepts documentation template

Every concept document in `documentation/concepts/` follows the Open
Knowledge Format (OKF) conventions: one concept for each file, YAML
front matter and explicit cross-links. It also follows the section
structure defined here.

The ordering principle is **audience-first**: the most brief and
broadly useful material comes first, and each subsequent section serves a
narrower, more specialized audience. A reader stops when their questions
are answered.

## Front-matter

```yaml
---
title: <Concept name>
description: <One sentence — what it is and its role in the system>
type: concept
audience: [architects, developers, end-users]
status: work-in-progress | draft | operational
ste: full | adapted | false
source:
  - src/aiko_services/main/<source file>.py
related: [design_overview, <other concept file stems>]
version: "<matching src/aiko_services/__init__.py>"
last_updated: <YYYY-MM-DD>
---
```

`ste:` declares whether the document is written in ASD-STE100 Simplified
Technical English. New concept documents default to `full`. Declare the
level only when the text complies. The levels, the rules digest and the
project profile are in
the project STE profile [Privately maintained].

## Required section structure

```markdown
# <Concept>

## Overview

## For application developers

### Command-line usage

### Public API

## For framework developers (internals)

### Design

### Implementation notes        (optional)

### CRC card

## Current limitations and roadmap

## Related concepts
```

Use these headings verbatim — identical wording and levels in every
concept document, so readers can navigate any concept the same way.

## Section-by-section guidance

### 1. Overview

A brief concept description: the purpose, what it does and why you would
want to use it. State where the concept fits among the other concepts,
with cross-links.

Then give a short *motivating example*: a few lines of shell or Python
that show the concept in use. Introduce the example with a
"**Why you would use it**" sentence that describes a concrete scenario.

### 2. Command-line usage

Everything an application developer needs at the shell:

- The console-script name (and the module fallback)
- The target-selection options and their defaults
- Command synopses grouped by task (lifecycle first, then data operations)
- At least one worked example session, with the expected output as comments

Mark each planned-but-unimplemented command explicitly.

### 3. Public API

The Aiko Services Interface and the protocol an application developer
programs against:

- The Interface class definition (or an operations table) — the public
  contract, not the implementation.
- Construction and usage examples: in-process (`compose_instance` /
  factory class methods) and remote (`do_command()` / `do_request()`
  discovery idiom).
- The **wire protocol**: message formats such as
  `(item_count N)` / `(response …)`, record grammars and sentinels
  (for example, `0:` for *None*). The wire protocol is part of the public
  contract — it belongs here, not under internals.
- A **sequence diagram** (ASCII) where a genuine multi-party exchange
  exists (request/response round-trips, write-through persistence). Do
  not diagram simple one-way commands.

### 4. Design

The executive overview for system and framework developers. Give a
**conceptual diagram** (ASCII) of the runtime structure. Then give the key
design points: the pattern applied (for example, Composite), the location
of the state, the cardinality conventions (for example, one for each
host), and the design direction of the roadmap.

### 5. Implementation notes (optional)

Internals that a framework developer must know before modifying the
source: threading/concurrency rules, normalization and merge semantics,
private helper behavior, startup/replay sequences, and any "follow this
rule when extending" guidance. Omit the section if the concept has no
internals worth recording beyond Design and the CRC card.

### 6. CRC card

One row per class — Classes, Responsibilities and Collaborators:

```markdown
| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `<Concept>` (Interface) | Declare the contract: … | Parent Interfaces |
| `<Concept>Impl` | … | Other classes and [concepts](…) it works with |
```

Include the Interface and the Impl as separate rows (plus any helper
classes, for example `ProcessCurrent`). Collaborators link to the other concept
documents wherever the collaborator *is* another documented concept.

### 7. Current limitations and roadmap

An honest digest of the source `To Do` lists: what is unimplemented,
provisional or planned. An accurate section here lets the remainder of the
document describe implemented behavior with confidence. Always separate
**implemented** from **planned / work-in-progress**.

### 8. Related concepts

A linked list of the other concept documents, each with a phrase saying
*how* it relates (for example, "— the container that holds Dependencies").

## Style rules

- Write "Aiko Services" in full — never abbreviate to "Aiko".
- Diagrams are ASCII (box-drawing characters), kept narrow enough to
  avoid horizontal scrolling.
- Code and command examples must come from the source files listed in
  `source:`, or you must be able to verify them against those files. When
  behavior is planned and not implemented, say so at the point of use.
- Cross-link the first mention of another concept in each major section.
  Do not link every mention again.
- Each directory of OKF documents has a `ReadMe.md` index (CamelCase
  name, per the repository convention).
