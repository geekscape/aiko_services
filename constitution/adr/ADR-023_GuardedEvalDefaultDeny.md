---
title: "ADR-023 — Guarded evaluation and default-deny method exposure (P12)"
description: Adopts candidate CP-E with the mobile-code tension resolved —
  mobile LISP expressions never reach an unguarded eval(), only the
  sandboxed capability-bounded interpreter — and rules that every public
  API is deny-all by default per method, with declarative allow/deny lists
  updatable (CRUD) at runtime under governed, observable control
type: adr
audience: [project-lead, architects, developers, ai-coding-agents]
status: normative
ste: adapted
related: [ReadMe, ADR-022_CompositionBoundary, ../p_00_DesignPrinciples,
  ../p_02_CandidatePrinciples]
last_updated: 2026-08-01
---

# ADR-023 — Guarded evaluation and default-deny method exposure (P12)

**Accepted by the project lead 2026-07-13** (directed during the e_10 / e_04 MCP-A2A
projection and ECCache work. Amended at acceptance with the decision-6 development-mode
provision). Mints principle **P12** — the next free P-number. P11 stays reserved for its own
candidate (event-loop state mutation) per the frozen identifier families.

## Context

Two facts collided with one strategic direction. The facts: the bus is (today)
unauthenticated and any MQTT client can invoke any public method on any Service (July audit
— mailbox dispatch `getattr`s into the object. The only exposure control, ADR-008's MCP
opt-in, is Service-granularity and MCP-only). And two verified host-language code-execution
surfaces exist (`elements/utilities/elements.py` `eval()` on Expression parameters,
`examples/pipeline` `np.load(..., allow_pickle=True)` on frame data). The direction:
**mobile code** is LISP-style filter and predicate expressions that travel in payloads. It
is strategically important (Registrar `(share …)` filters, the ECCache subscription and
water-mark filters of e_10 §2.1, and the e_05 LISP shell). Candidate CP-E was left
unresolved on exactly this tension by the project lead's 2026-07-07 note.

There is also a named tension with candidate CP-C ("Authority is a capability, not an
ACL"), whose rationale rejects bolting ACLs onto an open method-dispatch bus. This ADR
resolves it by separating two questions the word "ACL" conflates: what is *offered*
(exposure — this ADR), and who may *invoke* what is offered (authority — CP-C, unchanged).

## Decision

1. **Guarded evaluation (CP-E adopted, tension resolved).** Nothing arriving from the bus
   is ever executed or deserialized into executable objects in the host language: no
   `eval`/`exec`, no pickle of bus-derived input, safe parsers only (`ast.literal_eval`,
   schema-validated JSON/Avro), parameters coerced and validated at the boundary. Mobile
   code is a *supported capability* — and it evaluates **only** in the sandboxed,
   capability-bounded expression interpreter (the s_04 predicate language, and
   potential item 06). **Mobile LISP code must never result in an unguarded, insecure `eval()`.**
   Until the sandbox ships, the compliant behavior is refusal: hard-coded filters only.
2. **Default-deny method exposure.** Every public API is **deny-all by default, per
   method**. The composed Interface declaration seeds the allowed surface: message dispatch
   never reaches a method not declared on a composed Interface — P7's "the public surface
   *is* its interfaces" made enforceable, and it closes the arbitrary-invocation hole. Optional
   **allow / deny lists** refine exposure per API and per method.
3. **Policy is governed, live data.** The allow/deny lists are declarative data (P8), and
   they are updatable (CRUD) at runtime. The policy-update surface is itself a public API
   under the same default-deny. It is grantable only to operator-authenticated or
   gate-governed channels. Every policy change is published as observable state
   (CP-I) and auditable. An access list that anyone can update is not an access list.
4. **Enforcement lives at the dispatch layer and the gateways, never the broker.** The
   Service's own dispatch enforces the policy for bus traffic. Every projection gateway
   (MCP, A2A) enforces it for external traffic — refining ADR-008's Service-granularity
   opt-in to method granularity. Nothing assumes the MQTT broker enforces per-method
   authorization (CP-C's forbidden clause, preserved).
5. **Composition with CP-C.** Exposure lists bound the offered surface. Capabilities
   (CP-C, still a candidate) will govern who may invoke it. Defense in depth: even a future
   capability holder cannot reach an unexposed method, and P10's "capabilities rather than
   bolted-on ACLs" stands — P12's lists are dispatch-layer surface definition, not
   broker-enforced authority.
6. **Development-mode provision** (project-lead amendment at acceptance, 2026-07-13).
   Deny-all is the *default* — and defaults are what production gets. In a **simple,
   isolated development environment**, a developer prototyping or running the ordinary
   edit/run/debug cycle may set the guard posture to **allow-all** for efficiency. Bounds:
   the mode is an explicit, per-deployment configuration value, never the shipped default
   and never reachable by a code change alone. The deployment **advertises** the permissive
   mode as observable state (for example, a ServiceFields tag / EC key — mechanism settled at
   implementation) so a Dashboard or auditor sees it at a glance (CP-I). Externally-reachable
   surfaces (the MCP/A2A gateways beyond localhost / trusted LAN) refuse to run allow-all —
   the CP-C shipping gate already bounds them. And allow-all relaxes *policy only* — what is
   exposed and whether mobile code is accepted — never the *mechanism*: mobile code still
   evaluates only in the sandboxed interpreter, and an unguarded `eval()` remains forbidden
   in every mode, everywhere. A permissive dev mode must never become the reason an eval
   code path exists.

## Consequences

- **P12 enters p_00** ("the public API surface is guarded by default"), Tier 2. Deny-by-
  default makes the principle in play immediately (G3): a Service that evaluates no mobile
  code and dispatches only declared Interface methods complies today.
- **Remediation set, named:** the two host-language execution surfaces (item 03 sweep,
  already g_03 sharp edges). Parameter coercion in `get_parameter()`. The dispatch guard
  lands with e_10 (declared-Interface surfaces become checkable exactly as e_10 promotes
  the empty Interfaces — e_10 §2.15 actor.py carries the task). The gateways bind at birth
  (e_04 T19 spec, T21/T22 implementation).
- **ECCache and Registrar mobile filters gate on the sandbox** — they ship with hard-coded
  filters first, mobile predicates when item 06 lands.
- p_02's Wave-1 adoption path is partially executed: CP-E adopted (this ADR). CP-C's
  in-play slice (the shipping gate) was already adopted policy (e_04 Alignment,
  2026-07-07). CP-C's capability mechanism remains a candidate with its DA companion.
- Evidence trail: critique U4, review §4.6/§4.7, the July audit, and the p_02 CP-E note
  (project lead, 2026-07-07). Also the 2026-07-13 e_10 audit and ECCache directive, and the
  project-lead directive 2026-07-13 (this ADR).
