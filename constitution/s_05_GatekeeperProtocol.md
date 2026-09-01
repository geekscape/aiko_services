---
title: "Gatekeeper Protocol and the Machine-Readable Constitution"
description: Pre-RFC specification of the generic proposal gate — wire
  protocol, the four-stage gate over registered definition kinds, rollback
  semantics, and the declarative constitution document the gate enforces
type: specification
audience: [project-lead, architects, developers, implementers,
  ai-coding-agents]
status: draft-for-verification
ste: adapted
related: [s_04_GoalAcceptanceImprovementLoop, s_03_SelfAwarenessTelemetry,
  p_00_DesignPrinciples, p_01_PrinciplesGovernance, p_02_CandidatePrinciples,
  t_01_OkfRfcTemplate]
last_updated: 2026-07-31
---

# Gatekeeper Protocol and the Machine-Readable Constitution

## 1. Abstract

This document specifies the **Gatekeeper**. The Gatekeeper is the sole
authority that applies any change to a live Aiko Services Concept. It
generalizes the V4.1 demonstration's pipeline-only gate (e_01 §3.1
[Privately maintained]) into one protocol over **registered definition kinds**
(PipelineDefinitions, process definitions, storage mutations, goals). This
document also specifies the **machine-readable constitution**: the
versioned declarative document of whitelists, protections, bounds and the
autonomy level of the deployment. Stage 2 of the gate enforces that
document.

This document is the formalization that e_01 §3.2 called for. It is also
the seed of the DA-3 general invariant-preserving rewrite machinery
(e_01 §10, potential item 06 action 6). This document has the RFC shape of
t_01_OkfRfcTemplate. Its wire-visible content is destined for the AS-RFC
series when potential item 04 opens it. The definition-schema material
joins AS-RFC-5 territory, and the authority material joins AS-RFC-6.

## 2. Terminology

RFC 2119 keywords in all capitals are normative. A "definition" is a
declarative document that describes a desired Concept state. A "kind"
names a registered definition type with its validator and applier. A
"proposer" is any Service that submits a definition. "The machine
constitution" is the runtime document of §6. The "autonomy level" is the
deployment's staged-autonomy level, per the autonomy ladder
[Privately maintained].

## 3. Authority model

**[REQ-1]** The Gatekeeper holds the only authority to apply definitions
to live Concepts (the sole-authority decision, recorded in the private
ADR register). No Agent, engine,
human tool, IDE, MCP gateway, A2A bridge or Posix projection applies
directly. Each of them proposes. A direct mutation path is a defect,
whoever the caller is.

**[REQ-2]** The Gatekeeper is an ordinary Actor (P6) with no privileged
plane. Its authority is a capability: it alone holds the apply channel to
each governed Concept. The interim form is a deployment convention on the
trusted LAN. The target form is a CP-C capability, once potential item 08
lands. The staged trust boundary is labeled honestly, per e_01 §10.

**[REQ-3]** One Gatekeeper governs a declared scope (a deployment, a
namespace or a Concept set). Multiple Gatekeepers MUST NOT share authority
over one Concept. The machine constitution declares the scope.

## 4. Wire protocol

All methods are one-way (P1/P3). The proposer observes outcomes as EC
state ("command, then observe", CP-A). The protocol id ends with
`gatekeeper:0`.

**[REQ-4]** `propose(kind, definition, rationale, reply_topic)` — submit
a definition of a registered kind. The `definition` is data, never code
(CP-E). The `rationale` is free text that the ledger records. The
`reply_topic` receives the decision id immediately, and then the decision
events as they occur. The timeout is at the proposer, per P3 discipline.

**[REQ-5]** `withdraw(decision_id)` — a proposer MAY withdraw a proposal
before apply. After apply, reversion is a new proposal or a health-watch
rollback, never an un-apply.

**[REQ-6]** Decisions are EC state:

- `gatekeeper.decisions` — a ring of recent decisions. Each entry holds
  the id, the kind, the proposer, the stage reached, the verdict
  `accepted | rejected | rolled_back`, and the reason.

- `gatekeeper.stack` — the rollback stack: the last K applied definitions
  per governed Concept.

- `gatekeeper.constitution` — the version and hash of the loaded machine
  constitution.

Every verdict carries a machine-readable reason. Act 3 of e_01 ("the gate
says no, on camera") is the Dashboard rendering of this key.

**[REQ-7]** The v0 kinds are:

- `pipeline_definition` — applied through the `Pipeline.update_definition`
  blue/green swap, per e_01 §3.1.

- `process_definition` — applied through the ProcessManager.

- `storage_mutation` — HyperSpace/Storage writes.

- `goal` — admission per s_04_GoalAcceptanceImprovementLoop [REQ-3].

A new kind registers a validator, an applier and a rollback strategy.
Registration extends the registry (§9). It never special-cases the
protocol.

## 5. The four-stage gate

**[REQ-8]** Every proposal passes the stages in order. The first failure
rejects the proposal, and the gate publishes the stage and the reason. The
stages are those of e_01 §3.1, made generic:

1. **Schema validation** — the definition is well-formed for its kind, and
   the gate honors the validation result. For `pipeline_definition`, this
   means the Avro `validate()` result and the port-type checks of the near
   half of potential item 06 (the "toothless gate" fixed). Each referenced
   element must exist in the catalog, with typed I/O that matches.

2. **Constitution check** — the definition obeys the machine
   constitution (§6). The gate checks these five conditions:
   - The kind is a member of the whitelist
   - The protected entities stay unchanged
   - The size and the complexity are within the bounds
   - The proposer is within its rate limits
   - The requested action is within the deployment autonomy level

3. **Shadow run** — for kinds with runtime behavior, the gate instantiates
   the definition cold and processes recorded fixtures (potential item
   14). This run must succeed before the definition touches anything live.
   A kind without a meaningful shadow (for example, `goal`) declares this
   in its registration. To skip the shadow run is per-kind policy, never
   per-proposal discretion.

4. **Apply + health watch** — the gate applies the definition through the
   applier of the kind. It then monitors the health conditions for a
   constitution-declared watch period (the e_01 default is 15 s). The
   health conditions are s_04 predicates ([REQ-5] there — one language
   everywhere). On a violation, the gate does an automatic rollback to the
   retained previous definition and gives a `rolled_back` verdict.

**[REQ-9]** The rollback stack retains the previous K applied definitions
per governed Concept (K is set in the machine constitution). A rollback is
itself an apply of a retained definition — the same mechanism, no special
path (P10).

**[REQ-10]** As the far half of potential item 06 matures, proposals
SHOULD move from whole definitions toward **rewrite operations** that
state what they preserve. Stage 1 and stage 2 of the gate then check the
declared invariants directly. The protocol shape ([REQ-4]) already
accommodates this move: a rewrite operation is a definition of kind
`pipeline_rewrite`, registered when the calculus lands. The design here
follows e_01 §10: the demo machinery grows into the general mechanism, and
is not replaced by it.

## 6. The machine-readable constitution

**[REQ-11]** The machine constitution is a versioned declarative
document — data, never code (CP-E). Its form is S-expression or
Avro-validated JSON, consistent with PipelineDefinition practice. Where a
rule needs a predicate, the predicate is in the s_04 sandboxed language.
The document is loaded and validated like a PipelineDefinition, and each
deployment can override it. It lives in the tracked code tree at
`src/aiko_services/main/constitution/` (schema + default document),
because the runtime consumes it.

**[REQ-12]** The v0 fields are closed (an extension bumps the document
version, CP-G):

| Field | Meaning |
|-------|---------|
| `version`, `constitution_id` | document identity — hash published as `gatekeeper.constitution` |
| `scope` | the namespace/Concepts that this Gatekeeper governs ([REQ-3]) |
| `autonomy_level` | the deployment's staged-autonomy level [Privately maintained ladder] — a proposal that exceeds it is a stage-2 rejection |
| `whitelist` | per kind: admissible elements/modules/commands |
| `protected` | elements, Services, topics and storage paths that MUST be present and unmodified |
| `bounds` | definition size/complexity limits and predicate cost limits (s_04 [REQ-7]) |
| `rate_limits` | proposals per proposer per period, and concurrent experiments per deployment |
| `resource_ceilings` | host budgets (per s_03 keys) that a definition may not exceed |
| `health` | the default watch period, the per-kind health predicates and the rollback stack depth K |

**[REQ-13]** The schema carries a **traceability table** that maps every
field to the principle that the field operationalizes. The mappings
include: P8/DA-3 for contracts and bounds, CP-C for authority scope, CP-E
for data-not-code, P9 for ceilings, and the autonomy ladder for
`autonomy_level`.
Thus the machine document and p_00_DesignPrinciples cannot diverge
silently.

**[REQ-14]** Governance hook: an amendment to the machine-constitution
**schema** follows the same ADR discipline as an amendment to
p_00_DesignPrinciples (rules G1–G7 of p_01_PrinciplesGovernance). An
amendment to the **document** of one deployment (for example, an increase
of its autonomy level) is a deployment decision. But this decision is
observable: the Gatekeeper publishes the new version and hash, and records
the change in its decision ring.

## 7. Security Considerations

This document is mostly Security Considerations. The trust model is as
follows. Proposers are untrusted by design. The gate exists so that
*nothing* depends on the good behavior of a proposer. The Gatekeeper and
its machine constitution are the trusted computing base. They are small,
declarative and auditable on purpose.

An attacker on the bus can do these things today (pre-item-08):

- Submit proposals. Rate limits and the whitelist bound this action, and
  the gate publishes every try.

- Forge telemetry to steer health verdicts. Protected invariants bound
  this action (see s_03 §8).

- Impersonate the Gatekeeper EC state. This impersonation is unbounded
  until CP-C. This gap is the reason the autonomy ladder gates any
  externally-reachable surface on item 08.

The apply channel is the crown jewel. Interim deployments MUST keep broker
access trusted-LAN. The CP-C capability form of [REQ-2] is the real fix.

The shadow run executes candidate graphs. It MUST run with the same CP-E
posture as production: no `eval`-bearing elements. The `eval()` surface of
the Expression element is a blocking item-03 fix, per e_01 §10. The shadow
run SHOULD also run resource-bounded.

Residual risk: a whitelisted element with a vulnerability is inside the
perimeter. The whitelist bounds *topology*, not *code quality*. Element
admission (e_08 T20) exists to keep that bar explicit.

## 8. Registry Considerations

This document adds `gatekeeper:0` to the protocol registry. It adds the
reserved EC key prefix `gatekeeper.` and the definition-kind registry with
the initial kinds of [REQ-7]. It also adds the verdict vocabulary
`accepted | rejected | rolled_back` and the machine-constitution field
vocabulary of [REQ-12]. New kinds and fields extend these registries per
CP-G.

## 9. References

**Normative:**

- The V4.1 demonstration plan §3.1 (the four stages, blue/green swap)
  [Privately maintained].
- s_04_GoalAcceptanceImprovementLoop (predicate language, goal admission).
- The sole-authority and autonomy-ladder decisions (private ADR register).
- p_00_DesignPrinciples (P6, P8/DA-3, P9, P10).
- p_01_PrinciplesGovernance (G1–G7) and t_01_OkfRfcTemplate (form).

**Informative:**

- p_02_CandidatePrinciples (CP-A, CP-C, CP-E, CP-G).
- The pipeline-calculus, capability-security and record/replay roadmap
  items [Privately maintained].
- The Posix-projection posture: Posix is never an authority
  [Privately maintained].

## Appendix: Conformance traces (stubs — recorded at the gate milestone exit — the demonstration's three golden traces, generalized)

1. **Accept trace:** a valid `pipeline_definition` proposal passes all
   four stages. Assert the stage progression, the `accepted` verdict, a
   blue/green cutover within budget, and a clean health watch.

2. **Reject trace:** a non-whitelisted element and, separately, a
   type-mismatched edge. Assert the stage-1/stage-2 rejection with
   machine-readable reasons, and assert that the live Concept is
   untouched.

3. **Rollback trace:** an accepted definition violates a health predicate
   inside the watch period. Assert the automatic rollback to the stack
   head, the `rolled_back` verdict with a reason, and the recovery of the
   health keys.

4. **Autonomy trace:** a proposal exceeds the deployment `autonomy_level`.
   Assert the stage-2 refusal that cites the autonomy ladder — the Act-3
   property, generalized.
