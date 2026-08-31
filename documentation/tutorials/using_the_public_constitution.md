---
title: Working on Aiko Services — code, law, and the game
description: The three lanes of contribution — everyday coding (no ceremony), bumping into a rule, and making a move in the game — with full command and GitHub steps
type: guide
audience: [developers, ai-coding-agents]
status: operational
ste: adapted
last_updated: 2026-08-31
---

# Working on Aiko Services — code, law, and the game (a tutorial)

Preceded by [Tutorial: First project](first_project.md). Followed by
[Using a private Constitution](using_a_private_constitution.md).

For newcomers to Aiko Services, its SDLC, and its Nomic-style constitution.
One idea to hold before everything else:

> **Almost all work is ordinary coding. The constitution is the rulebook
> you follow, not a form you fill in. You only touch the rulebook itself
> on the rare day you want to change a rule. That change is a special,
> pleasant ceremony called "a move in the game".**

There are three lanes. Lane A is where you live. Lane B is a fork you hit
occasionally. Lane C is rare and deliberate.

---

## Lane A — Everyday coding (~90% of all work)

**Example task: fix a bug in `lease.py` and add a unit test.**

### One-time setup

```bash
git clone https://github.com/geekscape/aiko_services.git
cd aiko_services
pip install -e .
pytest                      # confirm the suite runs before you change anything
```

### The daily loop

```bash
# 1. Never work on master. Make a branch (one branch = one task):
git checkout -b yourname/fix-lease-timer

# 2. Edit code and tests. Run the tests:
pytest
flake8 . --select=E9,F63,F7,F82

# 3. Commit — stage files BY NAME, never a whole directory:
git add src/aiko_services/main/lease.py src/aiko_services/tests/unit/test_lease.py
git commit -m "Fix Lease extension-timer cadence; add regression test"

# 4. Push your branch and open a pull request:
git push origin yourname/fix-lease-timer
gh pr create --title "Fix Lease extension-timer cadence" \
             --body "Pins the bug with a regression test."

# 5. CI runs (flake8 + pytest). When green and approved, it merges.
#    Then update your local master:
git checkout master && git pull
```

### Where is the constitution in all this?

Invisible, and that is the point. It shaped your work without appearing:

- You followed the design principles (`constitution/p_00_DesignPrinciples.md`)
  — no `async def`, no methods returning values across the wire, no direct
  `self.share[...]` writes. A reviewer might say "rejected: violates P3" —
  that is the rulebook being *cited*, not changed.
- The pre-commit guard checked your staged files against the denylist and
  passed silently, because you did not stage anything private.
- The `constitution` CI check did not even run — your PR touched only code.

**You needed zero constitutional steps.** Most PRs, forever, look like this.

---

## Lane B — Coding that bumps into a rule (occasional)

Sometimes mid-task you hit a rule. There are exactly three shapes:

### B1. Your change would break a principle

Say you want `get_status()` to return a value over the wire. P3 forbids
RPC-style getters. Rule G1 gives you no third option:

- **Either** redesign (publish status as EC shared state — the compliant
  pattern), **and carry on in Lane A**.
- **or** you believe the *principle* is wrong — then you stop coding and
  make a **Lane C move** (propose amending P3 with an ADR). This is rare.

### B2. Your work implements a decision that deserves a durable record

You built something with a rationale worth keeping (a wire-format choice,
a boundary rule). That is an **ADR** — a small Lane C move, made *in the
same PR* as your code:

1. Open `constitution/adr/ReadMe.md`. Find the next **free** number.
2. Add the registry row **and** create `constitution/adr/ADR-NNN_YourName.md`
   (Context / Decision / Consequences / Evidence) **in the same commit**.
   The registry owns the numbers — never cite a number you have not
   claimed.
3. Add a dated entry to `constitution/log.md`.

### B3. You shipped a feature — update its docs

`documentation/concepts|elements|examples` docs for shipped behavior are
**Lane A** — ordinary committable work, same PR as the code, no ceremony.

---

## Lane C — A move in the game (rare, deliberate)

A **move** is a PR that changes the rulebook itself: anything under
`constitution/`, the `.constitution-guard` denylist, `Agents.md`, or the
CI gates. Every move has the same skeleton:

> **propose → check → ratify → enact → journal**

**Worked example — the smallest real queued move** (docket item 23:
add `ZZ*` case-variants to the denylist):

```bash
# 1. PROPOSE — a branch and the change:
git checkout -b yourname/proposal-guard-zz-variants
$EDITOR .constitution-guard          # add the [Zz][Zz]* patterns

# 2. JOURNAL — every substantive rulebook change logs itself, same commit:
$EDITOR constitution/log.md          # add under a "## 2026-MM-DD" heading:
#   - **Update** — .constitution-guard: added [Zz][Zz]* case-variant
#     patterns so the denylist matches the working-tree ignore rule.

# 3. Run the gates locally (optional but polite — CI runs them anyway):
python3 documentation/tools/check_self_containment.py \
    --future-stems documentation/tools/constitution_stems.txt \
    constitution/ Agents.md documentation/ReadMe.md

# 4. Commit (explicit file list!) and open the PR, titled as a proposal:
git add .constitution-guard constitution/log.md
git commit -m "Proposal: denylist case-variant patterns [Zz][Zz]*"
git push origin yourname/proposal-guard-zz-variants
gh pr create --title "Proposal: denylist case-variant patterns" \
             --body "Adds [Zz][Zz]* to .constitution-guard. Evidence: five
ZZZZZ*-prefixed personal notes found uncovered on 2026-08-31."
```

**Then GitHub takes over — the constitutional steps:**

5. **CHECK** — the `gates` CI job runs automatically: the self-containment
   scan (no references to private material) and the STE lint. Red gates
   block the merge. No human can skip them.
6. **RATIFY** — the project lead reviews. The lead's approval is the
   ratification (Code Owners rule). A PR author can never approve their
   own PR. So the lead merging their own proposal uses the visible admin
   allowance — on the record, in the PR timeline.
7. **ENACT** — the merge *is* the enactment. GitHub's PR number is the
   proposal's number in the ledger, adopted or not, forever.

That is a complete Nomic move: the rules changed *by* the rules. Five
minutes of work, permanently on the record.

**Second example — promoting private material** (docket item 22, the
prepared g_01 update): identical skeleton, plus the content comes *from*
the private repo:

```bash
git checkout -b yourname/proposal-g01-v08-update
# copy the prepared full text from the private repo:
git -C ~/projects/aiko_services_future show andyg/future:future/pending/g_01_v08_update.md \
    > constitution/g_01_ReleaseProcessGuide.md
$EDITOR constitution/log.md          # journal entry
git add constitution/g_01_ReleaseProcessGuide.md constitution/log.md
git commit -m "Proposal: g_01 v0.8 release-process update"
# ... push, PR, gates, ratify, merge — as above.
# Afterward, in the private repo: delete future/pending/g_01_v08_update.*
# and sync (see below). Never `git merge` between the two repos.
```

---

## The two repositories, in one breath

- **`aiko_services`** (public): all code, all public docs, the public
  rulebook. You work here.
- **`aiko_services_future`** (private): the private rulebook (`future/`).
  Only the project lead works here, only on branch `andyg/future`.
  - Sync **down** (routine): `git fetch upstream && git merge upstream/master`
    on `andyg/future`, then `git push origin andyg/future`.
  - Promote **up** (always a Lane C move): copy content into a fresh
    public proposal PR. Never merge or cherry-pick across the repos.

## "A session's turn" (for multi-AI-session work)

When several Claude Code sessions work in parallel, **code work runs in
parallel** (separate branches/worktrees — ordinary Lane A). But the
*rulebook* is a shared resource, so **rulebook changes take turns**: one
session at a time holds custody, ports its constitutional updates together
with its code merge, and hands off. If you are a solo human contributor,
you can ignore this section entirely.

## Cheat sheet — "am I making a move?"

| You are… | Lane | Constitutional steps |
|---|---|---|
| Fixing code, adding tests/features | A | None. Branch → PR → merge |
| Writing docs for shipped behavior | A | None |
| Blocked by a principle | B1 | Comply and continue — or escalate to a Lane C amendment proposal |
| Recording a durable design decision | B2 | Claim ADR number + file + journal entry, in your code PR |
| Changing anything in `constitution/`, the denylist, `Agents.md`, or the gates | **C** | Proposal PR + registry rows + journal entry → gates → lead ratifies → merge |

## Mini-glossary

- **Move / proposal** — a PR that changes the rulebook, played by the rules.
- **Gates** — the automatic CI checks every proposal must pass (stage-1 of
  the ceremony): self-containment + STE lint.
- **Ratify** — the project lead's review approval. Nothing becomes law
  without it.
- **Journal** — `constitution/log.md`. Every rulebook change writes one
  dated line about itself, in the same commit.
- **Registry** — the table that owns identifier numbers (ADRs,
  principles). Claim the number in the same change that uses it. Numbers
  are never reused.
- **Guard** — the local git hooks that refuse private material and
  unreviewed pushes. If a guard refuses you, it is working: stop and ask,
  never `--no-verify`.
