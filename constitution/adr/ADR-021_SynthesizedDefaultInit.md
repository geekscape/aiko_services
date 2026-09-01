---
title: "ADR-021 — Synthesized default __init__ for composed components"
description: compose_class() synthesizes the cooperative constructor when a
  developer's Service, Actor, PipelineElement or Pipeline subclass declares
  no __init__ of its own — context.call_init() per direct Interface base,
  with an optional PROTOCOL class attribute. Explicit constructors always win
type: adr
audience: [project-lead, architects, developers, ai-coding-agents]
status: normative
ste: adapted
related: [ReadMe, ADR-022_CompositionBoundary,
  ../constitution/s_02_InterfaceComposition,
  ../constitution/p_00_DesignPrinciples]
last_updated: 2026-08-01
---

# ADR-021 — Synthesized default `__init__` for composed components

**Accepted by the project lead 2026-07-13.** Implementation lands in
the public-API composition rollout [Privately maintained] Phase 1. Until it lands, the explicit constructor
stays necessary (g_03_AgentContext teaches the current truth).

## Context

`context.py` exists to "reduce the constructor `__init__()` arguments to just
one" — yet every developer-facing Service, Actor, PipelineElement and Pipeline
still carries the same two mechanical lines:

    def __init__(self, context):
        context.call_init(self, "Actor", context)

The 2026-07-13 audit (e_10 §1) found this boilerplate repeated identically
across the framework, the elements library and every example. It conveys no
per-class information: the interface alias is always the name of the direct
Interface base, which the composition engine already knows. `compose_class()`
(component.py) already owns the seam, because it sets the composed class's
`__init__` from the seed class. A class that omits `__init__` today
fails at composition with `TypeError: <Class>() takes no arguments`, so no
existing code can depend on the omitted case: the change is backward
compatible by construction.

A proof of concept (2026-07-13, against `master`, Python 3.12, and preserved
in e_10 §4) validated three cases: an `Actor` subclass with no `__init__`
composes with correct protocol, logger and share state and dispatches remote
calls. A sibling with an explicit `__init__` is untouched. The unpatched
engine raises the predicted `TypeError`.

## Decision

1. **`compose_class()` synthesizes the constructor when the seed class
   declares none** — detected as `impl_seed_class.__init__ is
   object.__init__`. The synthesized `__init__(self, context, **kwargs)`
   does `context.call_init(self, base.__name__, context, **kwargs)` for
   each direct base in `__bases__` order. That base must be an Interface
   with a registered implementation. This is byte-for-byte what developers write by hand,
   including the dual-parent case (`CategoryImpl` style). `call_init`'s
   `is_initialized` guard keeps diamond bases initialized once, as now.
2. **A `PROTOCOL` class attribute replaces the one non-mechanical
   constructor line.** When present on the seed class, the synthesized
   constructor does `context.set_protocol(cls.PROTOCOL)` before
   cooperative init. This converges with the standing service.py To Do that
   every Service define its own static ServiceProtocol.
3. **An explicit `__init__` anywhere in the seed's MRO always wins.** The
   feature is purely additive. Nothing existing changes behavior.
4. **P7 test discipline is a hard precondition.** P7 (amended 2026-07-07)
   forbids a change to `component.py` or `context.py` without accompanying
   unit tests. It also needs regression tests for the two flagged latent
   bugs of the composition engine (`_check_interfaces_implemented()`, and
   over-broad default-implementation pickup). Those come before any
   further refactoring builds on it.
   Those tests land first, then this feature, in e_10 Phase 1.
5. **The explicit form stays first in the teaching path.** The `call_init`
   line is most newcomers' only visible contact with the composition
   machinery. g_03 and the aloha_honua sequence present the convenience as
   "what you may erase", not "what you never learn". g_03 and
   `documentation/concepts/component.md` / `context.md` are updated in the
   same commit that implements the feature.

## Consequences

- Most example Actors and, after e_10 §2.7 (DataSource/DataTarget
  Interfaces), most media elements lose their constructors entirely. A
  minimal Actor becomes a class with only its remotely-callable methods.
- The composition engine gains its first real unit-test coverage (the ADR's
  precondition), reducing the "most load-bearing, least-tested" exposure P7
  names.
- The wire protocol is unaffected. Nothing observable changes for remote
  callers or other-language implementations.
- Evidence trail: P7 and P10 (the smallest design that composes). e_10 §4
  (design, proof of concept, guardrails). Audit e_10 §1 (boilerplate
  prevalence).
