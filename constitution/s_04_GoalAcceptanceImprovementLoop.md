---
title: "Goals, Acceptance Criteria and the Improvement Loop"
description: Pre-RFC specification of the goal record with declarative
  acceptance criteria, the sandboxed predicate language, the improvement-loop
  state machine, its supervision and the experiment ledger
type: specification
audience: [project-lead, architects, developers, implementers,
  ai-coding-agents]
status: draft-for-verification
ste: adapted
related: [e_03_FirstClassAgents,
  s_03_SelfAwarenessTelemetry, s_05_GatekeeperProtocol,
  p_00_DesignPrinciples, p_02_CandidatePrinciples, t_01_OkfRfcTemplate]
last_updated: 2026-07-31
---

# Goals, Acceptance Criteria and the Improvement Loop

## 1. Abstract

This document specifies how Aiko Services expresses goals with
machine-checkable acceptance criteria. It also specifies the state machine
with which an Agent pursues a goal. The states are: establish a baseline,
propose a change, observe, evaluate, and then adopt, roll back or
escalate. This document
extends the Goal record of e_03_FirstClassAgents §2.2.

This document is a **companion to e_03 T2** (the normative Agent/Goal
specs). Authors MUST author or revise this document and e_03 T2 in the same
session, to prevent divergence. The goal data-model freeze belongs to
e_03 T3. This document has the RFC shape of t_01_OkfRfcTemplate, for later
AS-RFC promotion (potential item 04).

One document covers both the criteria and the loop, and this coverage is
deliberate. Acceptance criteria have no meaning outside the loop that
evaluates them. The loop has no governance without the criteria.

## 2. Terminology

RFC 2119 keywords in all capitals are normative. A "Goal" is the e_03 §2.2
declarative record. A "criterion" is a predicate over observable state.
A "baseline window" and an "evaluation window" are bounded time spans over
which the loop measures the criteria. "The gate" is the Gatekeeper of
s_05_GatekeeperProtocol. The "loop runner" is the Agent that runs the
improvement loop.

## 3. The goal record, extended

**[REQ-1]** A goal is declarative data on the bus (CP-E). It has the e_03
base fields: `id`, `description`, `success_criteria`, `priority`,
`deadline` and `parent`. This specification gives `success_criteria` its
normative form:

```
(goal
  (id: g_0042)
  (description: "Hold pipeline p_video FPS at minimal CPU cost")
  (priority: 2)
  (deadline: "2026-08-01T00:00:00Z")
  (parent: nil)
  (criteria
    (target    (>= (median (window pipeline.p_video.fps 60)) 10))
    (target    (<= (mean (window host.cpu.percent 60)) 70))
    (invariant (>= (min (window pipeline.p_video.fps 60)) 5))
    (invariant (absent-never host.power.battery_percent 20)))
  (windows (baseline: 300) (evaluation: 300))
  (admission (proposed_by: <topic_path>) (admitted_by: <gate decision id>)))
```

**[REQ-2]** Criteria have two classes, and the classes are not
interchangeable. A **`target`** is what the goal improves, and the loop
optimizes the targets. An **`invariant`** is what may never regress. The
gate and the loop MUST reject or revert any change that violates an
invariant, regardless of target gains. Invariants are the Goodhart guard:
an optimizer cannot trade them away, because it never gets to weigh them.

**[REQ-3]** Goals enter an Agent only through the goal-admission gate.
This gate realizes the e_03 §2.2 note that the "Gatekeeper pattern
generalizes to goal admission", as an s_05 definition kind `goal`.
Self-established goals (the highest deployment autonomy level
[Privately maintained ladder]) pass the same admission
check as external goals. The `admission` fields record the provenance.

**[REQ-4]** The goal lifecycle is a StateMachine with the states
`proposed → admitted → active → (achieved | failed | withdrawn)`. The
Agent publishes the lifecycle as EC state (`agent.goals`). The states map
mechanically onto the A2A task states, per e_03 §3
(submitted/working/completed/failed/canceled). This mapping keeps e_03 T16
a projection.

## 4. The predicate language (sandboxed, shared)

**[REQ-5]** Criteria, gate health-watch conditions (s_05 stage 4) and loop
verdicts use **one predicate language**: S-expressions over EC keys and
windowed metric queries. Evaluation occurs exclusively in the
capability-bounded sandboxed interpreter of potential item 06, action 5.
Host-language `eval` of any bus-derived expression is non-conformant
(CP-E).

**[REQ-6]** The language surface is v0 and closed (an extension mints a
new version, CP-G):

- Atoms: numbers, strings, booleans, and EC key references
  (`host.cpu.percent`, `pipeline.<name>.fps`, `loop.state`, …).

- Aggregates over history: `(window <key> <seconds>)`, which resolves
  through the MetricsStore of s_03_SelfAwarenessTelemetry [REQ-13]. The
  reducers are `median`, `mean`, `min`, `max`, `p95` and `count`.

- Comparators and logic: `>=`, `<=`, `>`, `<`, `=`, `and`, `or`, `not`.

- Guards: `(absent-never <key> <threshold>)` — true unless the key drops
  below the threshold, or unless its producer goes absent. Stale or absent
  data fails safe, per s_03 [REQ-9].

**[REQ-7]** Evaluation is total and bounded. A predicate over stale,
absent or ill-typed data evaluates to a **failure verdict with a reason** —
never an exception, never a default pass. Cost bounds (expression size,
window span, evaluation time) are capability limits of the sandbox. The
machine constitution declares the default limits (s_05 §6).

## 5. The improvement loop

**[REQ-8]** The loop is a StateMachine that a loop-runner Agent owns. The
loop runner has the composition `Agent + Goal + Reasoner`, per e_03 §2.2,
and is NullEngine-capable by construction. The states and the transitions
follow (the table is normative):

| State | Does | Exits to |
|-------|------|----------|
| `BASELINE` | Measure all criteria over the baseline window. Persist the measurements to the ledger. | `PLAN`. `ESCALATE` if the invariants are already violated. |
| `PLAN` | The Reasoner produces a candidate change (a definition, per s_05 kinds) with a predicted target improvement. | `PROPOSE`. `ESCALATE` if there is no candidate. |
| `PROPOSE` | Submit the candidate to the gate: `propose(kind, definition, rationale, reply_topic)`. | `OBSERVE` on accept. `PLAN` on reject (bounded retries). `ESCALATE` on rate limit. |
| `OBSERVE` | Wait for the end of the evaluation window, while the gate health watch runs. | `EVALUATE`. `ROLLBACK` if the gate did an automatic rollback. |
| `EVALUATE` | Evaluate all criteria over the evaluation window, against the baseline. | `ADOPT` (targets improved, invariants held) or `ROLLBACK` (otherwise). |
| `ADOPT` | Record the verdict and the provenance in the ledger. Iteration is optional. | `BASELINE` (next iteration) or goal `achieved`. |
| `ROLLBACK` | Request reversion **through the gate**. Record the verdict. | `PLAN` (bounded retries) or goal `failed`. |
| `ESCALATE` | Publish the reason. Human or parent-agent input is necessary to continue. | Terminal for this iteration. |

**[REQ-9]** All loop state is EC state under `loop.*`: `loop.state`,
`loop.goal`, `loop.baseline`, `loop.experiment` (the in-flight proposal
id), `loop.verdict` and `loop.iteration`. Everything that the loop knows,
the Dashboard shows (CP-I). All mutation occurs on the event-loop thread
of the loop runner (P11).

**[REQ-10]** The loop holds no apply or rollback authority. `PROPOSE` and
`ROLLBACK` are messages to the gate. The gate alone applies, reverts and
keeps the rollback stack (the sole-authority decision, recorded in the
private ADR register). A loop that mutates a live Concept
directly is non-conformant.

**[REQ-11]** Iteration counts, retry counts, evaluation-window minimums
and concurrent-experiment limits are bounded (P9). Each loop runner has at
most one in-flight experiment, and the machine constitution sets the
per-deployment total. When the loop exhausts a bound, it exits to
`ESCALATE`, never to a silent retry.

## 6. Supervision

**[REQ-12]** The loop runner runs as a LifeCycleManager client (handshake
and deletion leases). Its failure policy (CP-B) is declared, not implied.
If the loop runner dies in the middle of an experiment, the gate health
watch and rollback stack already bound the blast radius. The
LifeCycleManager restarts the runner. The runner MUST resume from the
ledger, not from `BASELINE` amnesia. The runner persists its state at
every transition.

**[REQ-13]** An **independent watchdog Actor** watches `loop.*` for
staleness and for experiment-duration overruns. The watchdog is a
different process from the loop runner and from any Agent that proposes.
On a violation, the watchdog publishes an escalation, and it MAY request
reversion through the gate. The experimenter never supervises its own
experiment.

## 7. The experiment ledger

**[REQ-14]** Every iteration appends one ledger record with these fields:

- the goal id and the iteration number.
- the baseline measurements and the evaluation measurements.
- the proposal (kind, definition hash, rationale).
- the gate decision ids, their verdicts, and the final verdict.
- the identity of the agent that acts.

Records are append-only, and they persist through MetricsStore/HyperSpace
storage. The ledger thus always explains the current shape of the live
system. The question "why is the system like this?" has a replayable
answer, and potential item 14 supplies the replay.

## 8. Security Considerations

The loop converts observations into authority requests, so its integrity
depends on its inputs. Forged telemetry (s_03 §8) or a compromised
Reasoner can generate hostile proposals. This risk is precisely why
[REQ-10] denies the loop apply authority. It is also why invariants live
in the machine constitution, not only in the agent-supplied goal.

The predicate sandbox is a code-execution boundary. Its capability limits
([REQ-7]) are load-bearing. Any extension of the language surface needs a
security review.

Goal admission ([REQ-3]) is the injection point for external actors. These
actors include A2A inbound tasks per e_03 §3. Goal admission MUST enforce the
same constitution checks as definition proposals. Until item 08 (CP-C)
lands, loop runners are trusted-LAN components, and the deployment
autonomy levels are gated accordingly [Privately maintained ladder].

## 9. Registry Considerations

This document adds the reserved EC key prefix `loop.` and the goal
lifecycle states of [REQ-4]. It also adds the predicate-language v0
surface of [REQ-6] and the ledger record fields of [REQ-14].
s_05_GatekeeperProtocol registers the `goal` definition kind.

## 10. References

**Normative:**

- e_03_FirstClassAgents §2.2 (base Goal record, five-method Agent budget).
- s_05_GatekeeperProtocol (proposal protocol, machine constitution).
- s_03_SelfAwarenessTelemetry (keys and windows).
- p_00_DesignPrinciples (P3, P4, P9) and t_01_OkfRfcTemplate (form).

**Informative:**

- p_02_CandidatePrinciples (P11, CP-A, CP-B, CP-E, CP-I).
- The sandbox and record/replay roadmap items [Privately maintained].

## Appendix: Conformance traces (stubs — recorded at the improvement-loop milestone exits)

1. **Goal lifecycle trace:** propose → admit → activate → achieve. Assert
   the `agent.goals` EC transitions, per [REQ-4].

2. **Full-loop trace (NullEngine):** one complete BASELINE→…→ADOPT
   iteration on a rules Reasoner, deterministic in CI. Run the same suite
   again on one LLM engine to certify the seam (the e_03
   engine-conformance rule).

3. **Invariant trace:** an experiment that improves the targets and
   violates an invariant. Assert the `ROLLBACK` verdict and the gate
   reversion, per [REQ-2]/[REQ-10].

4. **Supervision trace:** kill the loop runner in `OBSERVE`. Assert the
   lease-driven restart with ledger resume, per [REQ-12]. Assert the
   watchdog escalation, per [REQ-13].
