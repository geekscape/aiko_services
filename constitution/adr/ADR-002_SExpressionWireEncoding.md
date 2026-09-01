---
title: "ADR-002 — S-expressions as the wire encoding"
description: Backfill record of the founding decision — every Aiko Services
  control message is an S-expression "(command argument ...)" encoded as
  UTF-8 text, chosen over JSON and protobuf. JSON appears only inside
  specific transported payloads, never for control messages
type: adr
audience: [project-lead, architects, developers, ai-coding-agents]
status: normative
ste: adapted
related: [ReadMe, ../constitution/s_00_Specifications,
  ../constitution/p_00_DesignPrinciples]
last_updated: 2026-08-01
---

# ADR-002 — S-expressions as the wire encoding

**Backfill record, written 2026-07-13.** The decision itself is a founding
one: it has been in force since the framework's origin, predating the
constitution, the Design Principles and this registry. It was cited as
"ADR-002" by s_00_Specifications §1.1 before this record existed. The
registry note directed the backfill at the next ADR-writing session, which
was 2026-07-13 (ADR-021/ADR-022). Nothing here changes behavior — this
record captures the rationale so it stops living only in the source and
the project lead's head (the s_08 Naur discipline, applied to the
project's own oldest decision).

## Context

Every remote interaction in Aiko Services is a one-way message published to
an MQTT topic (P1, P3). The message encoding is the single most
wire-visible choice in the framework. Every other-language implementation
(MicroPython `aiko_engine_mp`, future implementations) must parse it
first. Humans see it when they subscribe to a topic to debug. Size- and
CPU-constrained microcontrollers must handle it. The obvious
contemporary candidates were JSON (ubiquitous, schema-loose) and protobuf
(compact, schema-bound, but requiring code generation and versioned schema
distribution across every implementation and language).

## Decision

Control messages are **S-expressions encoded as UTF-8 text**:
`(command argument ...)`, arguments being atoms or nested S-expressions.
The canonical tokenization, quoting and escaping rules are defined by the
reference parser/generator (`utilities/parser.py:parse()/generate()`), to
be extracted into an EBNF grammar in the specifications (s_00 §1.1).

Chosen over JSON/protobuf because S-expressions are:

- **homoiconic** — a message is a data structure is a message. The same
  form serves commands, Pipeline graph definitions and future
  agent-authored topology (P8's "topology is data" and the e_05 LISP-shell
  direction fall out of this choice)
- **trivially parsed on microcontrollers** — a recursive-descent parser in
  a few dozen lines, no library dependency, no schema compiler (P9)
- **human-readable on the wire** — `mosquitto_sub` output is directly
  legible. Observability costs nothing (the CP-I instinct, decades early)
- **LISP heritage** — a proven notation for exactly this
  code-as-data/data-as-code role (P10: stand on established theory)

**JSON is not banned — it is scoped.** JSON appears only *inside* specific
payloads where a structured document is being transported (for example, a
PipelineDefinition file's content), never for control messages themselves.

## Consequences

- Language-agnosticism at the wire level is cheap: a conforming
  implementation needs an S-expression parser and an MQTT client, nothing
  more. This is load-bearing for P1's "asynchronous by protocol, not by
  language".
- The parser/generator pair is foundational — it merits the direct,
  adversarial testing of ADR-015 and the cross-language conformance traces
  of ADR-016. The exact quoting and escape rules must still be extracted
  as normative grammar (s_00 §1.1 [VERIFY]).
- Values that contain spaces or nesting must always round-trip through
  `generate()`, and never through f-string assembly. The known ECProducer
  incremental-update deviation (g_03 sharp edge) is a bug against this
  decision, and not a competing convention.
- Evidence trail: s_00 §1.1 (rationale as previously cited). P1, P8, P9,
  P10. e_05 (LISP shell). `utilities/parser.py`. `aiko_engine_mp`
  (MicroPython implementation as existence proof of the microcontroller
  claim).
