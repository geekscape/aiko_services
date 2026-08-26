---
title: Aiko Services — Claude Code Operating Guide
description: How to run the five workstreams with Claude Code — worktrees,
  context architecture, kickoff sequence and expected failure modes
type: guide
audience: [project-lead, ai-coding-agents]
status: operational
ste: adapted
related: [e_06_TestingStrategy]
last_updated: 2026-08-01
---

# Aiko Services — Claude Code Operating Guide

**Goal:** Run five concurrent workstreams across three repositories and three machines. The
workstreams are: (A) maintenance for existing users, (B) the V4.1 demonstration, (C) the IDE
MVP, (D) Phase 0/1 conformance + specs, and (E) design-principles stewardship. Claude Code is
the assistant for requirements, specification, design, implementation and each tier of
testing.

**Status:** Document g_02_ClaudeCodeOperatingGuide. Operational. Revise it freely as the
practice teaches.
Claude Code reference: https://code.claude.com/docs (worktrees: /en/worktrees).

---

## 1. The operating model in one paragraph

You stop being the implementer and become the **integrator and constitutional authority**. Each
workstream is a long-lived git worktree with its own standing context. Each task in a stream
is a Claude Code session, often in its own ephemeral worktree. The governing document of
every session is the
same. The seven plans now live *inside* the repo. Thus every session reads the same
constitution that you read. Your day is: morning dispatch (point sessions at tasks), midday
review-and-merge, evening integration on the testbed. The CI/conformance backbone (workstream D)
is what lets you merge agent work and not read every line. Until it exists, you read every
line — which is why D starts first, not alongside.

## 2. Machines: roles, not just hardware

**MacBook Pro M3 Max, 128 GB — "the cockpit."** Where you sit. Where most attended Claude Code
sessions run (it'll comfortably hold 3–4 concurrent sessions plus the IDE frontend toolchain).
Primary for workstreams B/C/E and all spec work.

**ASUS X, RTX 4070, 128 GB — "the bench."** The standing Aiko testbed head: mosquitto broker
(with the WebSockets listener for the IDE), a persistent multi-service Aiko deployment, GPU for
detector model preparation/conversion (V4.1 T3) and any local-model experiments. Claude Code
sessions here for hardware-adjacent tasks. If not, it runs the system that you build against.

**ASUS FX507ZM, RTX 3060, 32 GB — "the proving ground."** It is the self-hosted CI runner
(GitHub Actions). It serves the integration and conformance tiers, which need a real broker
and real concurrency. It also takes second-host duty in the multi-host Registrar/discovery tests.

With the Pi from V4.1, the bench, the proving ground and the Pi form a genuinely *distributed*
test fabric. Three heterogeneous hosts are the honest test environment for a framework whose
whole point is distribution.

## 3. Repositories and their roles

- **aiko_services** — the center. All five workstreams touch it.
- **aiko_chat** — downstream application and **compatibility canary, user zero**: its test suite
  runs in aiko_services CI against every merge, standing in for all external users (workstream A's
  promise made checkable). Maintenance work happens here too, same worktree pattern.
- **aiko_engine_mp** — the MicroPython engine: strategically, your *existing second protocol
  implementation*. As Phase 1 produces the wire-protocol spec, aiko_engine_mp becomes a
  conformance target against the golden traces — likely surfacing exactly the spec ambiguities
  worth fixing. Do not restructure it. Point the spec at it.

## 4. Git worktrees (a working primer, since they are new to you)

One repository, many simultaneous checkouts: `git worktree add <path> <branch>` creates a second
working directory sharing the same `.git` history — different branch, different files on disk, no
stashing, no clone duplication. Rules of thumb: a branch can be checked out in only one worktree
at a time. `git worktree list` shows them. `git worktree remove <path>` (or `prune`) cleans
up.
commits made in any worktree are instantly visible to all (shared object store).

Claude Code has first-class support: `claude --worktree <name>` creates an isolated
working directory under `.claude/worktrees/`, with a dedicated branch. Thus parallel sessions
never touch the files of each other. A `.worktreeinclude` file (gitignore syntax) copies the
necessary gitignored files, such as `.env`, into each new worktree automatically. Subagents can
also run in their own worktrees — set `isolation: worktree` in the agent frontmatter, or just ask
Claude to use worktrees for its agents.

**Proposed layout**. Use one long-lived worktree for each stream, in sibling directories, so
that the paths stay sensible.
ephemeral per-task worktrees through `--worktree` inside them):

    ~/aiko/aiko_services/            # main checkout: master — workstream A lives here
    ~/aiko/as-demo-v41/              # worktree, branch demo/v4-1        (B)
    ~/aiko/as-ide/                   # worktree, branch ide/mvp          (C, created after B ships)
    ~/aiko/as-conformance/           # worktree, branch phase0/conformance (D)
    ~/aiko/as-docs/                  # worktree, branch docs/specs       (D-specs + E)
    ~/aiko/aiko_chat/                # main checkout                     (A)
    ~/aiko/aiko_engine_mp/           # main checkout                     (D conformance target)

Created with for example, `git worktree add ../as-demo-v41 -b demo/v4-1`. Within a stream, fire ephemeral
parallel tasks with `claude --worktree fix-registrar-race` — Claude branches, works, you merge,
it cleans up.

**Merge discipline (the part that keeps five streams sane):** master is always releasable for
existing users. A merges to master continuously. D merges to master weekly, at minimum,
because tests and docs have few conflicts and give an immediate benefit. B and C rebase onto
master at least
weekly. Never let the demo branch become old. The V4.1 code (Gatekeeper, schema) is *itself*
destined for master soon after the film. Conflicts between streams are rare by construction:
A touches existing code, B adds new modules, D adds tests/docs.

## 5. Context architecture (what every session reads)

**Task zero, before anything else: commit the constitution documents into the repo** as `docs/plan/00-…md`
through `06-…md`. Context that lives outside the repo does not exist as far as sessions are
concerned.

Then the hierarchy:

- **Root `CLAUDE.md`** (checked in, ~1 page, compressed as much as possible). It contains
  what Aiko Services is, in three sentences. It gives the ten principles, one line each, with
  "full text: docs/plan/01". It gives the rules of engagement (run `pytest` and conformance
  before you claim done, never edit `docs/plan/` or
  `docs/adr/` without explicit instruction — that is the germline. Also: all-methods-one-way,
  no async/await, and cite P-numbers in a design discussion). The commands (test, lint, run a local
  deployment). Pointers to the per-package context.

  Have Claude Code draft it *from* docs/plan in your first session. Then cut it in half
  yourself. The quality of CLAUDE.md is leverage on every
  future session.
- **Per-package `AGENTS.md`** as the restructure lands (per 03). Until then, a short
  `src/aiko_services/main/CLAUDE.md` noting invariants and the forbidden patterns.
- **Per-stream task context**: each long-lived worktree gets a worktree-local
  `CLAUDE.local.md` (gitignored) stating the stream's mission, its plan document, and its
  boundaries — for example, for as-demo-v41: "Implement docs/plan/05. Touch only new modules plus the
  Pipeline swap path. The element catalog is frozen at eight."
- **`.claude/` checked in**: shared slash commands, subagents and hooks (below).
  `settings.local.json` gitignored.

## 6. Claude Code as the full-lifecycle assistant

Map the Phase-4 roles onto concrete Claude Code mechanics. The principle underneath all of them:
**one task, one session** — start clean, finish, commit, end. Long meandering sessions accumulate
stale context and produce drift.

**Requirements & specification.** Plan-mode sessions in `as-docs`. Create two slash commands:
`/spec <topic>` — "draft a normative spec section per docs/plan/02 conventions (RFC-2119 voice,
[VERIFY] markers for anything not confirmed in the source), from the source code and the plan
documents".
and `/adr <decision>` — short ADR in docs/adr following the template. You review prose, not
diffs, here — this is where your hours go, by design.

**Design.** Before a non-trivial implementation task, tell the session to produce a
half-page design *in the chat* citing P-numbers, and approve it before code. Make it a habit, not
a ceremony: "design first, cite principles, then build" belongs in CLAUDE.md.

**Implementation.** Use attended sessions for novel work (the V4.1 Gatekeeper, the swap
semantics).
Use `claude --worktree` parallel sessions for separable tasks. Use subagents with
`isolation: worktree` when one session fans out mechanical work (the Phase-3 package moves,
later, are the canonical
case — batched mechanical changes across many files).

**The adversarial test author.** This role only works if it is genuinely blind to the
implementation. Practical approximation: a custom subagent `test-author` whose instructions are
"read ONLY docs/plan/02, docs/interfaces, and the public interface files. Write tests from
the spec. Do not open implementation modules." Run it in a session separate from the
implementer,
ideally before or in parallel with implementation (spec-first makes test-first natural). Where
implementer and test author disagree, the spec was ambiguous: that is a finding, and it goes back
to a `/spec` session, not into a quiet fix.

**The principles reviewer.** A custom subagent `principles-reviewer`. Its input is a diff.
Its output is
verdict per principle, citing P-numbers, terse. Run it on every B/C merge candidate and on any A
change that touches a public surface. Sometimes it is wrong. But it also catches the blocking
getter at 11 pm that you would not have. You remain the appellate court.

**Hooks and gates (mechanical honesty).** A pre-commit/stop hook that runs the unit suite and
(after it exists) the conformance replay. Thus a "done" claim is checked, not asserted. A hook
denying edits under `docs/plan/` and `docs/adr/` outside the docs worktree — the germline,
enforced in tooling rather than etiquette. Headless mode (`claude -p "…"`) is the tool for
scripted jobs: the nightly interface-drift check (regenerate catalog, diff, open an issue on
mismatch) is a cron job on the proving ground.

**Test tiers, owned by CI rather than memory:**
1. *Unit* — every commit, every machine, no broker (mock transport).
2. *Integration* — a broker is necessary: GitHub Actions with a mosquitto service container,
   plus the
   self-hosted RTX 3060 runner for multi-process tests.
3. *Conformance* — golden-trace replay (Phase 0 product), on every PR.
4. *Regression / compatibility* — the aiko_chat suite against the merge, and the
   `aiko_services.main` shim
   import tests once the restructure starts.
5. *Complete system* — nightly on the fabric (bench + proving ground + Pi): bring up Registrar,
   spawn the standing deployment, run the V4.1 scenario end-to-end, record the trace, diff
   against golden. A nightly that exercises three real hosts is rare and is itself a credibility
   artifact — publish its badge.

## 7. Workstream-specific notes

**A — Maintenance.** It runs in the main checkout. The sessions are the smallest and the
merges are the fastest. Every fix gets
a regression test in the same PR (CI backbone grows as a side effect of maintenance — free Phase
0 progress). aiko_chat canary in CI is the contract with existing users.

**B — V4.1 demo.** The task list of the 05 plan maps directly: T4 (specs) in as-docs. T6–T8
and T10–T12
as separate sessions in as-demo-v41, with T7 (swap) attended and everything else largely
delegated. The bench hosts the broker and the rehearsals. The Pi joins from T9 onward.

**C — IDE.** Opens after B films. New top-level `ide/` directory means near-zero conflict with
everything else. Frontend tasks run in parallel unusually well across `--worktree` sessions
(one for each
view) once aiko-ts lands. The Mac is the natural home.

**D — Conformance & specs.** The first session of the whole effort: trace-capture harness
(Recorder-based) + the first golden trace (bootstrap/Registrar handshake), in as-conformance.
Then one trace each week, as a standing habit. Also `/spec` sessions that convert the 02
[VERIFY]
markers into confirmed normative text — each [VERIFY] is a perfectly-sized session: "read the
source, confirm or correct this section, show evidence."

**E — Principles stewardship.** Principles change *only* by ADR — run `/adr`, you approve,
then you edit the principle text. The constitution stays slow on purpose. The improvement
backlog to
seed it: a security/trust principle (the bus's trust boundary, made explicit — the IDE work will
force this anyway). A testability principle (every MUST is observable on the wire). The
I1–I6 of the IDE folded in as a second chapter. And a worked-example appendix for each
principle (the
anti-patterns sections, grown from real reviewer-subagent verdicts — the constitution learning
from its own case law). Quarterly aesthetic review per P10: a standing calendar entry, you plus
one fresh Claude session whose only input is the public API surface.

## 8. Kickoff sequence (first ~10 days)

1. **Day 1:** Update Claude Code on all three machines. Clone the three repos under
   `~/aiko/`. Commit docs/plan/00–06. Create the four long-lived worktrees. Write
   `.worktreeinclude`.
2. **Day 1–2:** The first Claude Code session drafts the root `CLAUDE.md` from docs/plan.
   You edit it down. Add `/spec`, `/adr`, `test-author` and `principles-reviewer` to
   `.claude/`. Add the
   test-before-done hook and the germline-protection hook.
3. **Day 2:** Prepare the bench: mosquitto (+WS) and the standing deployment. Confirm the
   dashboard. Register the RTX 3060 as a self-hosted runner. Get minimal GitHub Actions
   (unit + lint) green.
4. **Day 3–4:** Workstream D session 1 — the trace harness + the first golden trace. Wire
   the conformance
   replay into CI. Workstream A resumes normally in the main checkout (it never stopped).
5. **Day 3–5 (parallel):** V4.1 T1–T3 (hardware freeze, detector validation on the bench GPU,
   then the Pi) are yours. At the same time, a `/spec` session drafts the three V4.1 specs
   (T4) for your review.
6. **Day 6–10:** B implementation starts (T6–T8 delegated, T7 attended). One
   [VERIFY]-retirement session and one new golden trace land in D. The first
   principles-reviewer verdict occurs on a real merge.

By day 10 you have four things: the constitution in-repo and enforced by hooks. A green
three-tier CI with the first conformance traces. Maintenance that flows, with a canary. The
demo build under way. All five streams are live, and none blocks another.

## 9. Failure modes to expect (so they do not surprise you)

**Too many sessions.** Attended sessions have a cap of three. More than that, and you do not
review, you hope. Background/headless work does not count against the cap, but merges do.

**Context drift in long sessions** — one task, one session. If a session is on its third
unrelated topic, end it.

**The shared-history surprise** — worktrees share commits immediately. Two sessions on the
*same branch* is the one configuration that still collides, and the `--worktree` flag exists
to prevent it.

**Agent-claimed "done"** — hooks make the claim checkable. Never merge on
assertion. **D starving** — conformance work has no demo and no deadline, so it loses every
scheduling fight unless protected: the weekly trace and the weekly D-merge are appointments, not
aspirations.

**You, reviewing code instead of specs** — the leverage inversion (transition plan §3) fails
quietly if you go back to diff-reading. The reviewer subagent and CI exist precisely
so your reading hours stay on the normative documents.
