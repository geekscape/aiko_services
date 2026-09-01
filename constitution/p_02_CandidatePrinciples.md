---
title: Aiko Services — Candidate Design Principles (July 2026)
description: The missing crucial Design Principles surfaced by the June 2026
  review and July 2026 critique — full draft wording, in-play assessments,
  adoption paths and prioritized adoption waves (action 3), awaiting ADRs
type: proposal
audience: [project-lead, architects, ai-coding-agents]
status: proposal
ste: adapted
related: [p_00_DesignPrinciples, p_01_PrinciplesGovernance,
  a_00_ArchitectureReview_2026-06]
last_updated: 2026-08-01
---

# Aiko Services — Candidate Design Principles (July 2026)

**Status:** Proposal (G4 stage 2). This is the list of the **missing crucial Design
Principles**. It comes from a review of the amended P1–P10 against three sources: the June
2026 review, the July 2026 critique (U1–U8/S1–S9) and the source audits. Each candidate gives draft wording, the G3 **in-play
assessment** (what is adoptable today compared with what needs a DA companion), its evidence, and its
adoption path. The candidates are grouped by theme. The prioritized adoption order — three waves —
is the "Prioritization (action 3)" section at the end.

**Method.** P1–P10 were tested for coverage against the failure classes the evidence exposed:
concurrency hazards, partial failure, reliability, security, protocol evolution, data handling,
observability, and ecosystem growth. A gap became a candidate only if it is (a) principle-shaped
— a decision rule that agents face many times, not a task. (b) Crucial — its absence caused
real, verified defects, or it blocks a stated ambition. (c) Not derivable from an existing
principle plus common sense.

**Review notes (project lead, 2026-07-07) incorporated inline:** CP-E carries the mobile-code
note (sandboxed LISP expressions compared with host-language code — unresolved, and
deliberately so). CP-F is reframed as in-band (control) / out-of-band (bulk). CP-H includes
the source-code reference
implementation in the source of truth. Per G7, unpromoted candidates are flagged for
re-justification but never dropped without the project lead's explicit instruction.

**Adoption-readiness classes** (feeds action 3):
- **Class 1 — adoptable now:** the rule passes G3 as-is for new code. The legacy violations
  are enumerable
  and schedulable.
- **Class 2 — adoptable with remediation:** rule passes G3 for new code, but adoption is only
  honest alongside fixing a small, known violation set.
- **Class 3 — needs mechanism:** the framework machinery to comply does not exist. Adopt an
  in-play slice now (if any) and file the rest as a DA companion.

---

## Theme: concurrency and failure

### P11 (candidate). All state mutation happens on the event-loop thread

**Rule (draft):** an Actor's state — including `self.share` — is mutated only on the event-loop
thread. Worker threads and MQTT-thread callbacks post work through `_post_message()`. They never
mutate shared data. An Actor stops itself only through the sanctioned lifecycle path (to be named in
the ADR), never by raising `SystemExit` inside a handler.
*Why:* eliminates the lock-based hazards flagged independently in `event.py`, `connection.py`,
`pipeline.py` and `utilities/lock.py`. It completes the P2 story inside the process.
*Forbidden:*
- To mutate `self.share` or Actor fields from a thread that is not the event-loop thread
- To notify handlers on the calling thread (possibly the MQTT thread)
- `SystemExit` in a message handler or a frame handler

**In-play assessment (Class 2):** new code can comply today (ProcessManager's reaper shows
the pattern). The known violations to correct at adoption are:
- The direct share writes in `ActorImpl.run()` and `PipelineImpl.set_parameter()`
- The calling-thread notification in `connection.py`
- The example `SystemExit` patterns (aloha_honua `ku()`, PE_WhisperX "terminate")
- The hand-rolled camera thread of xgo_robot
 The ADR must name the sanctioned self-stop.
**Evidence:** convergent TODOs in four modules. The concepts audit. The examples audit
(2026-07-05/06).
July audit — `event.py` `_handler_count` thread-unsafe, `mqtt.py` documented deadlock.

### CP-B (candidate). Supervision is part of the Actor Model

**Rule (draft):** every Actor has a defined failure policy. A failure is an observable event, never
a silent one. Links/monitors exist as protocol concepts so that one Service can watch another's
death. A stream whose element fails has defined semantics (restart element / skip frames / kill
stream), declared in the PipelineDefinition.
*Why:* the Actor Model without supervision is half the Actor Model (Erlang/OTP). "Let it crash"
only works because someone is watching. Today a handler exception is logged and the message is
lost silently. A dead remote element leaves a stream in an undefined state.
*Forbidden:*
- A new `except Exception` block that swallows the error and publishes no diagnostic
- A stream state or a lifecycle state that you can reach but cannot observe
- Failure semantics that exist only as comments

**In-play assessment (Class 3):** links/monitors and declared stream policies need protocol and
runtime machinery → DA companion.

**In-play slice adoptable now:** "failures are observable events". New code never swallows
an error silently, and it always publishes a diagnostic. This extends the bus-as-ground-truth
stance of the P6 amendment. To narrow the Actor dispatch catch (review §4.6) is the
first remediation.
**Evidence:** critique S4, shortfall §2.2. Review §4.6. The July audit (silent message loss in
`actor.py` dispatch, and no restart/escalation anywhere).

## Theme: reliability

### CP-A (candidate). Command, then observe

**Rule (draft):** the sanctioned reliability idiom is to send the one-way command. Then
confirm its *effect*: observe the EC state of the target converge. Never await a reply, and
never assume delivery (P1: at-most-once). A command that can be retried is idempotent. Once DA-5
lands, correlation tokens double as idempotency tokens.
*Why:* the end-to-end argument (critique U7): the transport cannot guarantee delivery, so
confirmation must live at the endpoints — and the framework already owns the machinery
(ECProducer/ECConsumer). This is the answer to "how do I know it worked?" that P1/P3 currently
leave unstated, and it is what examples silently get wrong.
*Forbidden:*
- Framework or example code that assumes an unobserved command took effect
- A confirmation pattern built on reply messages, where state observation belongs
- To retry
non-idempotent commands.
**In-play assessment (Class 2):** the idiom is usable today — EC state exists and P3 already
names observation as the canonical pattern. Adoption needs reworking examples and concept
docs to demonstrate it (today none do), plus DA-5 (idempotency tokens) for the retry half.
**Evidence:** critique U7, S7. Review §2.4. Shortfall §2.1 (nothing tells application code about
at-most-once).

## Theme: security

### CP-C (candidate). Authority is a capability, not an ACL

> **2026-07-13 note (ADR-023/P12):** the adopted per-method default-deny exposure lists are
> a *surface definition*. The dispatch layer and the projection gateways enforce them. They
> are not the broker-enforced ACL authority that this candidate rejects. CP-C's capability mechanism remains
> the pending authority answer. The two compose as defense in depth.

**Rule (draft):** possession of a Service's address is authorization to message it. Addresses are
therefore unguessable (sparse capability topics). The Registrar grants addresses under policy.
infrastructure Services hold no privileged bypass (P6). Until this mechanism exists, the MQTT
broker is the trust boundary — and **no externally-reachable surface (MCP gateway, shell, bridge)
ships before capability security does**.
*Why:* bolting ACLs onto an open method-dispatch bus is the pattern that failed CORBA, DCOM and
early ROS. The lineage of the Actor Model (Hewitt, the E language, Cap'n Proto) already contains
the answer, and it fits this architecture instead of fighting it (critique U4). Today any MQTT
client can invoke any method on any Service.
*Forbidden:*
- To ship an externally-reachable surface before capability security
- A new security mechanism that makes a special case of an infrastructure Service
- A design that assumes that the broker will enforce per-method authorization

**In-play assessment (Class 3):** capability topics and Registrar-mediated grants need protocol
design (S1) → DA companion.

**In-play slice adoptable now:** the trust-boundary statement and the shipping gate. You
comply today when you do not ship. This turns the ordering of the MCP plan into a principle,
not a hope.
**Evidence:** critique U4, S1. Review §4.7 (no authn/authz found, and the "largest
unstarted work"). The July audit (arbitrary method invocation through the proxy, and
guessable topics).

### CP-E (ADOPTED 2026-07-13 as P12 — ADR-023). Payloads are data, never code

> **Adoption record:** the project lead resolved the mobile-code tension below, exactly as
> the 2026-07-07 note expected. Host-language `eval`/`exec`/pickle of bus input is forbidden.
> Mobile LISP expressions stay a supported capability that evaluates **only** in
> the sandboxed, capability-bounded interpreter (never an unguarded `eval()`). ADR-023 also
> added the default-deny per-method exposure rule. Full normative text: p_00 **P12**. The text
> below is retained as the candidate's history.

**Rule (draft):** nothing arriving from the bus — payloads, parameters, PipelineDefinitions,
frame data — is ever executed or deserialized into executable objects. Conversions use safe
parsers (`ast.literal_eval`, schema-validated JSON/Avro, `allow_pickle=False`). Parameters are
coerced and validated at the element boundary before use.
*Why:* the bus is (today) unauthenticated, and even under CP-C a capability holder must not gain
code execution. Verified surfaces exist now: `eval()` on Expression `define` parameters,
`np.load(..., allow_pickle=True)` on frame data, uncoerced string parameters (`"false"` is
truthy) steering element behavior.
*Forbidden:*
- `eval`/`exec` on bus-derived input
- Pickle (or `allow_pickle=True`) on bus-derived input
- To steer control flow with a parameter that is not coerced and not validated

**In-play assessment (Class 1):** new code can comply fully today. Nothing in the framework
prevents compliance. The remediation set is small and known: two code-execution surfaces,
plus parameter coercion in `get_parameter()`. Thus this is the cheapest crucial adoption
available.

**Evidence:** the July audit / CLAUDE.md sharp edges (`elements/utilities/elements.py`
`eval()`,
`examples/pipeline` PE_DataDecode `allow_pickle=True`, and uncoerced parameters). Critique
U4 context. Review §4.6.

**Note for consideration (project lead, 2026-07-07):** the rule as drafted is too strong in one
important direction. S-expression payloads carrying *LISP code* enable **mobile code** — sending
the code to where the data is, rather than hard-coding every behavior into every Service. For
example, a Registrar `(share …)` request could carry a new *filter expression* instead of the
Registrar pre-defining every possible filter type. The ADR must reconcile security with this
capability. The probable resolution is a distinction. Payloads are never **host-language**
code: no `eval`/`exec`/pickle of Python, so that half of CP-E stands. But a
**capability-bounded, sandboxed interpreter** for a defined expression language is a
legitimate framework capability, and a strategically important one. Ties to the LISP-shell direction [Privately maintained], the full-LISP
Definition/Graph direction for DA-3, and CP-C (capabilities confine what mobile code may reach).
CP-E remains a proposal with this tension unresolved.

## Theme: protocol and data

### CP-F (candidate). In-band control, out-of-band bulk data

**Rule (draft):** the **in-band** plane (the control plane) carries small, human-readable
S-expressions over MQTT. Data too large for in-band — frames, tensors, audio, large blobs —
travels **out-of-band** on a binary bulk plane (ZMQ today, with shared memory / Zenoh as future
transports), referenced from in-band messages. Neither plane carries the other's traffic.
*Why:* this is the architectural answer to the serialization-overhead critique the dora-rs
lineage aims at message-passing middleware — and it is *already the practice*
(`ImageReadZMQ`/`ImageWriteZMQ`, `pyzmq` core dependency). Stating it as principle protects it
and directs the spec work (S1: make the out-of-band channel a normative wire concept).
Human-readable in-band traffic is also what keeps the bus observable (CP-I) and the system
legible to agents.
*Forbidden:* to encode bulk binary data into S-expressions (base64 or a different encoding)
in-band. Also, a new
elements that stream media frames over MQTT topics. Also, control commands routed
out-of-band.
**In-play assessment (Class 2):** the pattern exists and is compliable now. Known violations to
schedule: examples publishing video frames over MQTT (xgo_robot video topics). Spec promotion is
S1 work, but the design rule itself passes G3 today.
**Evidence:** review §2.5. The comparison document, takeaway 2. Critique S1. The elements
audit.

### CP-G (candidate). Protocols are versioned and evolve compatibly

**Rule (draft):** every protocol identifier carries a version (existing convention, kept). A
breaking change to a protocol's commands or semantics mints a new version identifier — the old
one is never silently redefined. Receivers are tolerant readers: unknown commands are logged
diagnostics and never crashes (the existing behavior, kept). Additive evolution (new optional trailing
parameters, new commands) is always preferred to redefinition.
*Why:* the multi-language-standard ambition lives or dies on schema/protocol evolution — the
lesson of protobuf field numbers and Avro reader/writer schemas. Today the Registrar protocol has
had three versions with no migration path, and there is no compatibility rule at all: a version
bump strands old clients (the review, and the July audit).
*Forbidden:*
- To change the wire behavior of a protocol and mint no version
- A receiver that crashes on an unknown command or on an extra trailing parameter
- To commit a protocol change without
updating its specification entry (once s_00_Specifications is promoted).
**In-play assessment (Class 2):** the versioning and tolerant-reader halves are compliable today
(and partially practiced). Version *negotiation* and mechanical compatibility checking need spec
and tooling → DA companion.
**Evidence:** the July audit (Registrar v0/v1/v2, with no migration, and "no version
negotiation"). Review §4.4. Critique S1.

### CP-H (candidate). The specification — with its reference implementation — is the source of truth

**Rule (draft):** the source of truth for the wire protocol is the **specification, together
with its conformance traces and the designated source-code reference implementation**
(Python now, with `aiko_engine_mp` as implementation #2). The wire protocol covers the
S-expression grammar, the topic namespace, the Registrar/EC/lease/lifecycle protocols and
the out-of-band bulk channel. The
specification states the intent. The reference implementation demonstrates it executably.
The traces bind the two.

A behavior difference among the three is a defect. The project lead resolves it explicitly,
never silently. Never treat one of the three as automatically correct.

Until the specification is promoted, the Python reference implementation is the acknowledged
source of truth in practice. Promotion transfers the normative authority
to the spec + traces. The reference implementation stays the executable exemplar.
Wire-visible behavior changes update spec, traces and reference implementation in the same
change.
*Why:* the language-neutrality claim (P1) is real only when you can build a Rust or C
implementation and read no Python. But a spec that is separate from a living reference
implementation decays as surely as code that is separate from a spec. This is the G3 drift
argument, applied to specifications.
The spec is overdue (review §4.4) and golden traces are the only way to certify implementation
#2 and safely refactor #1.
*Forbidden:*
- A wire-visible behavior change with no spec/trace update
- To resolve a spec / reference-implementation disagreement silently, in either direction
- Spec text that cannot be
checked by a trace.
**In-play assessment (Class 3):** `s_00_Specifications.md` is draft-for-verification and the
golden-trace harness (e_06_TestingStrategy plan) does not exist yet — the rule cannot bind until they do.
**In-play slice adoptable now:** wire-visible changes must update the s_00_Specifications draft. Full adoption
lands with S1 / testing Phase 0.
**Evidence:** review §4.1, §4.4, §5.3. Critique S1. The comparison document (it named the
missing normative artifact).

## Theme: observability

### CP-I (candidate). Observable by default — if it happened, it is on the bus

**Rule (draft):** every Service exposes its significant state through its ECProducer. Every failure
publishes a diagnostic (the CP-B slice). Nothing important occurs only on stdout, or only in
a local log.
The bus traffic *is* the system's ground truth: diagnosis, testing (golden traces), replay and
simulation all derive from it, and the Recorder is the seed of that capability.
*Why:* this property already powers the Dashboard and is why "everything is a Service" pays off
(the P6 amendment). It is also the distinctive answer of the framework to observability tooling that
rivals bolt on externally. Protecting it is cheaper than restoring it.
*Forbidden:* significant state kept only in Python attributes invisible to remote observers
(the class of bug from a direct `self.share[…]` write). Also, failures reported only to
stdout, and new
capabilities whose behavior cannot be observed from the bus.
**In-play assessment (Class 2):** largely true today and fully compliable for new code. Known
violations: `process.py` printing tracebacks to stdout, direct share writes (overlaps P11),
silent excepts (overlaps CP-B slice). Record/replay as first-class capability is roadmap work,
but the discipline passes G3 now.
**Evidence:** review §2.6, §4.9. Critique U7 context, and the S1/S3 dependencies. The July
audit (stdout
tracebacks, share-write invisibility).

## Theme: ecosystem

### CP-D (candidate). The ecosystem unit is the shareable element

**Rule (draft):** the unit of ecosystem growth is the third-party PipelineElement: packaged,
schema-carrying (declared ports, parameters, protocol id, dependencies), independently
distributable and installable without touching the framework tree. Framework evolution must not
break the element packaging contract once it exists.
*Why:* ecosystems grow on a distribution unit (npm, ROS packages, HuggingFace models — critique
U8): architecture attracts admirers, a package registry attracts contributors. Today elements
are in-tree Python modules with hard-coded paths and undeclared optional dependencies.
*Forbidden (after the format exists):*
- An element that you can distribute only by a copy into the tree
- An element whose dependencies or schemas are not declared
- A framework change that breaks published
elements without a version bump (ties to CP-G).
**In-play assessment (Class 3):** the package format and registry do not exist → the core rule
needs mechanism (S6). **In-play slice adoptable now:** new elements declare their schemas,
protocol ids and optional dependencies, and take no hard-coded paths — the hygiene half of the
contract. Note for the ADR: this may be a *project* principle rather than a *framework* design
principle. The ADR must decide its home.
**Evidence:** critique U8, S6. The elements/examples audit (hard-coded model paths, undeclared ML
dependencies, commented-out optional extras in `pyproject.toml`).

---

## Considered and not proposed

- **"New behavior lands with tests."** Crucial, but it is an SDLC/engineering practice, not
  a design decision rule. It belongs in the transition plan / testing strategy
  (e_06_TestingStrategy), where it already has a home. To list it here would blur what the
  Design Principles are for.
- **"Bounded work per message" (deadlines on handlers).** Real concern (P2 amendment names it),
  but as a principle it duplicates the P2 amendment plus P11. Revisit it only if a per-Actor
  executor
  isolation (critique S8) becomes a mechanism.
- **"Persistence/replay as a right."** Folded into the CP-I Recorder direction. A standalone
  principle would fail G3 by a wide margin today.
- **Renumbering note:** CP-A…CP-D keep the identifiers assigned in `p_00_DesignPrinciples.md`.
  CP-E…CP-I are new in this proposal. Adopted candidates take the next P-number at ADR time
  (P11 keeps its number).

## Summary table

| Candidate | Theme | Class | Needs DA companion? | Blocks / gates |
|-----------|-------|-------|---------------------|----------------|
| P11 event-loop mutation | concurrency | 2 | no | many latent thread bugs |
| CP-B supervision | failure | 3 | yes (links/monitors, stream policy) | production credibility |
| CP-A command-then-observe | reliability | 2 | DA-5 (idempotency) | honest reliability story |
| CP-C capability authority | security | 3 | yes (capability topics, grants) | **gates MCP/shell/bridges** |
| CP-E payloads are data | security | 1 | no | cheapest crucial adoption |
| CP-F in-band / out-of-band | protocol | 2 | no (spec promotion = S1) | performance narrative |
| CP-G protocol evolution | protocol | 2 | yes (negotiation/tooling) | multi-language ambition |
| CP-H spec + reference impl are truth | protocol | 3 | yes (S1 spec + traces) | second implementation |
| CP-I observable by default | observability | 2 | no | golden traces, replay |
| CP-D ecosystem unit | ecosystem | 3 | yes (package format, S6) | contributor growth |

---

## Prioritization (action 3, 2026-07-07)

Adoption is ordered in **three waves** — Wave 1 safety and honesty (adopt now), Wave 2
protocol readiness, Wave 3 mechanism-gated. The full wave assignments, their rationale and
the cross-check against the deferred-amendment order are maintained privately
[Reserved for private items]. Adoption records land here as they occur — CP-E was adopted
2026-07-13 as P12 (ADR-023), exactly as drafted, plus the default-deny per-method exposure
rule. Per G7, unpromoted candidates are flagged for re-justification but never dropped
without the project lead's explicit instruction.
