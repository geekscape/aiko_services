---
title: Model handoff guide — operating the constitution with less capable models
description: Hard rules, checklists and verification recipes that let Claude
  Opus, Sonnet or Haiku work on the Aiko Services documentation safely —
  judgment from the July 2026 Claude Fable 5 sessions encoded as procedure
type: guide
audience: [ai-coding-agents, project-lead]
status: operational
ste: adapted
related: [g_03_AgentContext, g_02_ClaudeCodeOperatingGuide,
  p_00_DesignPrinciples, p_01_PrinciplesGovernance, p_02_CandidatePrinciples,
  t_02_OkfTaxonomy]
last_updated: 2026-08-01
---

# Model handoff guide — operating the constitution with less capable models

Written by Claude Fable 5 on 2026-07-08, at the project lead's direction, before the
project transitions to Claude Opus 4.8 (and, for smaller tasks, Sonnet 5 or Haiku 4.5).
The constitution rework (actions 1–6) was executed with a model that could hold the
whole document graph and its governance in working memory at once. Successor models
must not try that. Instead: **follow this guide as procedure.** Every judgment
call that recurred during actions 1–6 is reduced here to a rule, a checklist or a
grep recipe. When a situation is not covered, stop and ask the project lead — that
is the designed behavior, not a failure.

This guide governs work on the governed documentation trees: `constitution/` (including
`constitution/adr/`) and `documentation/concepts/` (plus `elements/` and `examples/`,
which follow the same OKF rules). Private governance trees are maintained in the private
constitution [Reserved for private items] under the same rules. For source-code work,
`g_03_AgentContext.md` remains the entry point.

## 1. Hard rules — never violate, never "improve"

1. **Never `git push`.** Prepare commits when asked. The project lead pushes.
2. **Never commit private or future material to the public repository.** The
   `.constitution-guard` denylist and the pre-commit guard enforce this mechanically —
   never bypass them (`--no-verify` is a project-lead-only act). Always stage from an
   explicit file list, never `git add <directory>`.
3. **Never touch any `z_*` file, anywhere in the working tree.** They are the project
   lead's personal
   scratch. Do not read them for context, reformat them, or reference them.
4. **Root `CLAUDE.md` is a symlink to `Agents.md`.** Edit `Agents.md`, never the symlink
   (in-place edits on it fail, and "fixing" that by replacing the symlink is worse).
5. Always write **"Aiko Services"** in full — never bare "Aiko".
6. ReadMe files are named **`ReadMe.md`** (CamelCase) — never `README.md`.
7. **Identity is the ClearName.** Cite documents by name (`p_00_DesignPrinciples.md`
   or "the Design Principles"), never by bare numeric prefix ("doc 00"). Prefixes
   order and group and may change at a reorganization.
8. **Registries own identifier numbers.** ADR numbers come from
   `constitution/adr/ReadMe.md` (001–023 mapped, 024+ free). AS-RFC numbers come from
   the AS-RFC registry [Privately maintained until the series publishes]. Never mint a
   number in prose or a plan —
   claim it in the registry in the same change, or do not use it.
9. **These identifiers are frozen** — never renumber, merge or re-letter them:
   P1–P11, CP-A…CP-I, DA-1…DA-5, G1–G7, U1–U8, S1–S9, ADR-NNN, AS-RFC-N, REQ-n,
   M1–M4, potential items 01–21. Later documents cite them. To renumber breaks the graph.
10. **Candidate principles are never dropped.** An unpromoted candidate (P11, CP-A…CP-I)
    may be *flagged* as stale in a review, but only the project lead's explicit
    instruction removes or demotes one (rule G7).
11. **One action at a time.** The rework plan runs one numbered action per approval,
    with project-lead review between. Confirm which action is next before you start it.
    Never start the following action because the current one "went well".
12. **"Phase" is the one term for plan-internal segments** (project-lead direction,
    2026-07-19): never introduce "Stage" or "Wave" for a plan's ordered segments — the
    2026-07-19 standardization renamed all of them to Phase. The numbers are unchanged, and
    citations like "e_03 Phase 0" stay plan-scoped. "Wave" is reserved for the p_02
    candidate-adoption batches (Waves 1–3). "Stage" survives only inside gate-internal
    stage numbering, and in the terminology of external organizations.
13. **STE declarations are earned, not aspirational** (adopted 2026-07-31): a document's
    `ste:` front-matter (`full | adapted | false`, defined in `t_02_OkfTaxonomy.md`,
    rules in the project STE profile [Privately maintained]) may say `full`/`adapted` only when
    the text actually complies — converting a document and declaring it happen in the
    same change. "Complies" means `asd_ste100_lint.py` reads zero on all **seven**
    counts, measured at the time you declare it. A hardened check can retire a
    declaration that was honest when it was made: re-run the gate, do not trust the
    field. New documents are written to their default level from birth. The
    dictionary PDF `documentation/z_asd-ste100-issue-9.pdf` is licensed and gitignored: <!-- future-ref-ok: never-commit instruction for a local-only licensed file -->
    never commit it, never reproduce its dictionary or examples. It is always
    "ASD-STE100", American English spelling, and `remove` ≠ `destroy` in Aiko Services
    APIs and prose.

## 2. What to read before editing (keep it minimal)

Do not read the whole constitution. Load only:

- **Always:** this guide, and `constitution/ReadMe.md` (the index — it gives
  you the status and the one-liner of each document, and you do not open it).
- **Editing any OKF document:** `t_02_OkfTaxonomy.md` (front-matter law).
- **Touching principles, candidates or DAs:** `p_01_PrinciplesGovernance.md` (G1–G7),
  then only the specific principle sections you are changing in `p_00` / `p_02`.
- **Executing an execution plan:** its playbook [Privately maintained],
  then the plan document itself in full (its updates and
  Alignment sections carry decisions the body predates).
- **Renaming or restructuring anything:** the constitution maintenance protocol
  [Privately maintained].

## 3. The G3 test, as a checklist

The Design Principles state only what is **currently in play**. Before writing or
amending any principle text, apply this test to each normative sentence:

1. Can an agent in today's codebase comply with this sentence *today*? It must not have
   to wait for framework code, docs or tests.
2. **Yes** → it may be principle text.
3. **No** → it is a **deferred amendment**: record it in the deferred-amendments
   register and the matching roadmap item [Privately maintained],
   marked critically important. It is promoted into the principle only when the
   artifacts comply — promotion *is* the act of bringing them into compliance.
4. Honesty notes ("Known gap: …") and disciplines that bind *new* code only are
   fine to keep normative.

When in doubt between principle and DA, choose DA and say so — the project lead
promotes, and agents defer.

## 4. Front-matter checklist (every OKF edit)

Per `t_02_OkfTaxonomy.md` — verify on every document you create or edit:

- [ ] Fields exactly: `title`, `description`, `type`, `audience`, `status`, `ste`,
      `related`, `last_updated` — in that order. Add the `rfc:` block for an AS-RFC, and
      `superseded_by:` when the status is `superseded`. Nothing else.
- [ ] `type`, `status` and `ste` values come from the closed vocabularies in `t_02` —
      never invent a value. Use `ste: full`/`adapted` only when the text complies (rule 13).
- [ ] `description` is one sentence. Index ReadMe tables are *derived from* the
      descriptions, and are never written independently. If you change a description,
      update the row in the `ReadMe.md` of that directory, in the same change.
- [ ] `related:` entries are ClearNames without `.md`. A cross-directory entry is a
      relative path. Every entry must resolve to a real file (check with `ls`).
- [ ] `last_updated` bumped to today in the same change as any content edit.
- [ ] A dated entry appended to the journal `constitution/log.md`
      (`**Creation**`/`**Update**` bullet under today's `## YYYY-MM-DD` heading, newest
      first) for every substantive documentation change — not for typo-level fixes.

## 5. Reference-integrity protocol (after any rename or new document)

References take exactly four forms. After renaming, adding or removing a document,
sweep all four. You must get **zero stale hits** before you finish:

```bash
cd /Users/andyg/projects/aiko_services
# 1+2+3: old stem anywhere (front-matter related:, markdown links, backtick names)
grep -rn "OLD_STEM" constitution/ documentation/ Agents.md ReadMe.md --include="*.md"
# 4: bare prose ordinals — only if the old name had a bare number form
grep -rn "document NN\|doc NN" constitution/ documentation/ --include="*.md"
```

Exclude `z_notes.txt`, `z_nvidia_notes.txt` and `z_*` backups from any fix-ups
(rule 3). Fix hits with targeted `Edit` calls, not bulk `sed` (a July 2026 bulk sed
partially misfired on table rows and had to be repaired by hand. Also, `sed -i` fails
outright on the `CLAUDE.md` symlink). Re-run the grep until it is silent, and state
in your summary that the sweep exited clean.

## 6. Model routing — who does what

- **Opus 4.8:** any plan playbook [Privately maintained],
  executed as written, one playbook step (or one plan
  T-task) per review checkpoint. Also: new ADRs, new AS-RFC drafts, principle amendments
  (with the §3 checklist). Do not redesign the playbooks. A deviation is a stop-and-ask.
- **Sonnet 5:** single-document tasks with an explicit file list. Examples: the interface
  section of one concept document, one potential item update, one ADR from a decision
  already made, and front-matter fixes. Give it the template and one worked example. Batch
  at most ~5 documents in each session.
- **Haiku 4.5:** mechanical verification only. Examples: the §5 grep sweeps, a §4
  front-matter lint over a directory, and an index table regenerated from the
  descriptions. Give exact commands
  and the expected output. Haiku reports findings. It does not decide the fixes.

Any model, any tier: a task that weighs two constitution documents against each other, to
decide which one is wrong, is a project-lead question.

## 7. Stop and ask the project lead when…

- A change would alter principle text, a document's `status`, or anything in §1's
  frozen-identifier list.
- Promoting anything: DA → principle, candidate → principle, `proposal` → `operational`
  or `normative`.
- Deleting or renaming any file in the five documentation trees.
- Two documents contradict each other (report both locations, and do not select a winner).
- A sweep finds a reference that you cannot resolve to an existing document. It can be a
  deliberate forward reference. Flag it, and do not "fix" it.
- You are tempted to do the *next* action's work early (rule 11).

## 8. Known failure modes (observed, so successors avoid them)

- **Aspirational drift:** principle text that describes the system as it *should* be.
  Section 3 exists because this occurred. Apply it mechanically.
- **Partial sweeps:** fixing the markdown links but missing front-matter `related:`
  entries or bare prose mentions. Always all four forms, always the zero-hit exit check.
- **Eating the history:** a rename sweep once rewrote *both* columns of a historical
  mapping table, destroying the record of the old names. Mapping tables, change logs
  and execution records intentionally contain old names — exclude them from sweeps.
- **Invented numbers:** citing "ADR-024" or "AS-RFC-7" without claiming it in the
  registry. The registry is the source of truth (rule 8).
- **Edit-anchor misses:** `Edit` fails when you paraphrase the anchor text from memory.
  Read the exact lines first. After a rename, `Read` the file at its *new* path before you
  edit it.
- **Helpful destruction:** "tidying" the project lead's `z_*` scratch files or backups.
  Rule 3 is absolute.
- **`git add` of a directory** (observed 2026-08-01). `git add documentation/` swept
  then-untracked governance trees and vim swap files into the index, and the commit that
  followed contained all of them. The pre-commit guard and `.constitution-guard` now
  refuse denylisted paths mechanically, but the discipline stands. Always
  stage from an explicit file list:
  `git diff --name-only <ref> > /tmp/files.txt`, then
  `git add --pathspec-from-file=/tmp/files.txt`. Before every commit, review
  `git diff --cached --name-only` against your intended list and confirm no strays.
  The recovery, when nothing is pushed, is
  `git reset --soft HEAD~1` then `git reset`.
- **A file mode that stops an edit.** If a write fails with `Permission denied`, do not
  "fix" it by a chmod that you keep. Every file in `constitution/` is mode
  600. Restore that mode after the edit. (One analysis document was mode
  400 until 2026-08-01, when the project lead normalized it to 600 with the others.)
- **A green gate that measures the wrong thing** (observed 2026-08-01, five times). The
  ASD-STE100 conversion of all of `documentation/` reached zero on every count while real
  defects remained. The checks did not cover the regions, or the shapes, where the defects
  were. Each one is now a check, not a habit. The general lesson outlives the tool:
  **a tool that rewrites text needs one check for every shape that it can produce, and one
  for every region that it can reach.** A check for the shape that it produced last time is
  not enough.
    - A mechanical fixer expanded contractions **inside quotations**, which falsified five
      cited source comments. Quoted text is never rewritten (rule 8.6).
    - A splitting tool edited **YAML front matter**, where a `description:` is quoted
      verbatim by a `ReadMe.md` index row, so the index desynchronized in silence.
    - The gate never read **table cells or front matter**, and about forty British
      spellings hid there.
    - A swap-list rule nearly renamed a **real command name** (`delete`, in the Expression
      element). Section 3 of t_04 says an API name beats the dictionary. A word that is
      also a code span is a decision, not a defect.
- **A remembered exemption.** An exemption can live in a reviewer's head, or in a
  "known exemptions" list. It then grows to cover more than it should, and it hides a real
  defect.
  Declare it in the document, at the smallest region that needs it. For ASD-STE100 that is
  the `<!-- ste-exempt: reason -->` marker (t_04 §5).
- **An instruction that is wider than it was meant to be** (observed 2026-08-01). "Stage
  the modified files and commit" arrived when every modified file was in
  `documentation/constitution/`, which the then-standing rule 2 held out of the
  repository. The correct
  response was to ask, and the project lead confirmed that the tree stayed uncommitted.
  A hard rule survives an explicit-looking instruction. Ask, and say what you will do
  instead.
