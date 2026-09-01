---
title: Working with a private constitution repository
description: Developing future code, docs and law in a private downstream repository — routine sync from public, and the promotion ceremony that makes things public
type: guide
audience: [project-lead, developers, ai-coding-agents]
status: operational
ste: adapted
last_updated: 2026-08-31
---

# Working with the private repository — future code, docs and law (a tutorial)

Companion to [Working on Aiko Services — code, law, and the game](using_the_public_constitution.md).
That tutorial covers the public repo, where you live. This one covers the
private repo, where the future lives. One idea to hold first:

> **The private repo is a vault with a one-way window. Public changes flow
> IN routinely (a plain `git merge`). Nothing flows OUT except through the
> ceremony — content is always COPIED into a fresh public proposal, never
> merged across.**

## What `aiko_services_future` is — and is not

| It IS | It is NOT |
|---|---|
| The private constitution (`future/` — private law, roadmaps, designs) | The everyday code workshop (that is the public repo) |
| The vault of originals + redaction records + the promotions register | A place whose history may ever reach the public repo |
| The home of prepared-but-unpublished proposals (`future/pending/`) | A second copy of anything public (the public copy is canonical) |

The map, on branch `andyg/future`:

```
future/
  <ClearName>.md        whole private documents (law, designs, roadmaps)
  adr/                  private ADRs + the full-titles registry
  potential/            the private roadmap items
  pending/              prepared public proposals, awaiting their PR
  originals/            pre-redaction versions of trimmed public docs
  redactions/*.diff     the exact record of every excision
  promotions.md         WHAT publishes WHEN, and how to restore it
  log.md                the private journal
constitution/           the public law (read-only here; synced from upstream)
```

## One-time setup

```bash
git clone git@github.com:geekscape/aiko_services_future.git
cd aiko_services_future
git checkout andyg/future

# The public repo as a FETCH-ONLY upstream (pushing to it is disabled):
git remote add upstream https://github.com/geekscape/aiko_services.git
git remote set-url --push upstream no-push-upstream-is-fetch-only

# Install the guard and declare the private remote pattern:
cp <path-to>/guards/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push
git config constitution.privateremotepattern aiko_services_future
```

---

## Part 1 — Routine: keep the private repo in sync (public → private)

Do this after any public merge that matters, and before a private work
session. It is plain plumbing — no ceremony:

```bash
cd ~/projects/aiko_services_future
git checkout andyg/future
git fetch upstream
git merge upstream/master        # public law + code flow IN
git push origin andyg/future
```

Now `constitution/` (public law) and `future/` (private law) sit side by
side, and private documents can cite public ones by ordinary relative
paths.

---

## Part 2 — Daily private work: writing future docs and law

**Example: draft a new private design document, `future/s_20_QuantumBus.md`.**

```bash
cd ~/projects/aiko_services_future
git checkout andyg/future

$EDITOR future/s_20_QuantumBus.md      # OKF front-matter, as usual
$EDITOR future/log.md                  # journal it — same commit, same rule
                                       #   as the public side
git add future/s_20_QuantumBus.md future/log.md
git commit -m "future: draft s_20_QuantumBus design"
git push origin andyg/future           # guard verifies: private remote only
```

The same registry discipline applies privately: a new private ADR claims
its number in `future/adr/ReadMe.md` (the full-titles registry) in the
same commit. Reserved numbers in the PUBLIC registry ("[Reserved for
private item]") resolve here. If the new document should publish one day,
**add a row to `future/promotions.md`** with its publish-when condition.
That row is how future-you finds out it is time.

---

## Part 3 — Private CODE (two options)

Code is normally public from birth (Lane A of the first tutorial). For
genuinely not-yet-public code, pick one:

**Option 1 — simplest (solo, short-lived):** develop in the *public* repo
on a local branch and just do not push it until ready. Private-by-omission.
No backup, single machine — fine for days, not months.

**Option 2 — durable (backed up, multi-machine): a code branch in the
private repo, based on public master, that NEVER touches `future/`:**

```bash
cd ~/projects/aiko_services_future
git fetch upstream
git checkout -b andyg/secret-widget upstream/master   # clean public ancestry!
# ...develop: edit src/, tests; commit code files only...
git push origin andyg/secret-widget                    # backed up privately
```

The "never touches `future/`" rule is what keeps this branch's history
publishable later.

**(a) Making the code public**, when the day comes:

```bash
# 1. In the PUBLIC working repo, fetch the branch one-shot by local path
#    (no standing remote to the private repo — deliberate):
cd ~/projects/aiko_services
git fetch ~/projects/aiko_services_future andyg/secret-widget:andyg/widget

# 2. LEAK-CHECK every commit is tree before any push (non-negotiable):
git rev-list master..andyg/widget | while read c; do
  git ls-tree -r --name-only $c | grep -E '^future/' && echo "LEAK in $c"
done          # expect silence

# 3. Then it is ordinary Lane A: push the branch, open the PR:
git push origin andyg/widget
gh pr create --title "Add widget subsystem" --body "..."
```

If the leak-check ever speaks, stop — rebuild the branch by copying files
onto a fresh public branch instead.

---

## Part 4 — Promotion (b): future DOCUMENTATION becomes public

**Example: `future/pending/g_01_v08_update.md` (a prepared update to the
public release guide).** Promotion is a **move in the game** — the content
is COPIED out. The repos never merge upward:

```bash
# In the PUBLIC repo — the proposal:
cd ~/projects/aiko_services
git checkout -b andyg/proposal-g01-v08
git -C ~/projects/aiko_services_future show \
    andyg/future:future/pending/g_01_v08_update.md \
    > constitution/g_01_ReleaseProcessGuide.md
$EDITOR constitution/log.md            # public journal entry
git add constitution/g_01_ReleaseProcessGuide.md constitution/log.md
git commit -m "Proposal: g_01 v0.8 release-process update"
git push origin andyg/proposal-g01-v08
gh pr create --title "Proposal: g_01 v0.8 release-process update" --body "..."
# → gates run → lead ratifies → merge = enactment
```

**Afterward, close the loop in the private repo:**

```bash
cd ~/projects/aiko_services_future
git checkout andyg/future
git fetch upstream && git merge upstream/master   # the promotion arrives
git rm future/pending/g_01_v08_update.md future/pending/g_01_v08_update.diff
$EDITOR future/promotions.md                      # erase the row
$EDITOR future/log.md                             # journal the promotion
git commit -am "future: g_01 v0.8 update promoted — pending entry retired"
git push origin andyg/future
```

## Part 5 — Promotion (c): future CONSTITUTION becomes public

The same skeleton, plus **restoration** — reserved numbers get their real
titles back, and redacted text returns to the published documents.
**Example: publishing a private ADR when its subject matter ships:**

```bash
cd ~/projects/aiko_services
git checkout -b andyg/proposal-publish-adr-NNN

# 1. The document itself:
git -C ~/projects/aiko_services_future show \
    andyg/future:future/adr/ADR-NNN_ItsRealName.md \
    > constitution/adr/ADR-NNN_ItsRealName.md

# 2. RESTORE the registry row: replace "[Reserved for private item]"
#    with the real title — same number, never a new one:
$EDITOR constitution/adr/ReadMe.md

# 3. RESTORE redacted references: find every bracket marker the
#    redaction left behind, and reverse the matching hunk from the
#    private repo's future/redactions/*.diff record:
grep -rn "Privately maintained\|Reserved for private item" constitution/ \
    | grep -i <topic>                  # locate the sites
$EDITOR constitution/<each-affected-file>.md

# 4. TRIM the stems so CI *proves* the restoration is complete:
$EDITOR documentation/tools/constitution_stems.txt   # remove this item's stems

# 5. Index row + journal, commit everything TOGETHER, propose:
$EDITOR constitution/ReadMe.md constitution/log.md
git add constitution/adr/ADR-NNN_ItsRealName.md constitution/adr/ReadMe.md \
        documentation/tools/constitution_stems.txt constitution/ReadMe.md \
        constitution/log.md <each-affected-file>
git commit -m "Proposal: publish ADR-NNN (promotion — subject matter shipped)"
git push origin andyg/proposal-publish-adr-NNN
gh pr create --title "Proposal: publish ADR-NNN" --body "Promotion per
future/promotions.md; condition met: <the condition>."
# → gates enforce completeness (a leftover reference to a trimmed stem
#   now FAILS CI) → lead ratifies → merge
```

Private-side closure, as in Part 4: sync down, `git rm` the promoted file
from `future/`, retire its redaction record, erase its register row,
journal, push.

---

## Cheat sheet

| You want to… | Where | How |
|---|---|---|
| Pull public changes into the vault | private | `fetch upstream && merge upstream/master && push origin` — routine |
| Write/edit private law or future docs | private, `andyg/future` | Edit + `future/log.md` entry, same commit; push origin |
| Develop not-yet-public code | private, code branch off `upstream/master` | Never touch `future/` on that branch |
| Publish that code (a) | public | One-shot fetch by path → **leak-check** → ordinary PR |
| Publish a future doc (b) | public | COPY content → proposal PR → gates → ratify → private cleanup |
| Publish future law (c) | public | Copy + restore registry rows + reverse redactions + trim stems → proposal PR → private cleanup |

## The pitfalls (each one guarded, but know them)

- **Never `git merge` or cherry-pick from private into public.** Content
  crosses by copy, into fresh public commits, only. (The push URL to
  upstream is disabled and the guard blocks `andyg/future` everywhere but
  the private origin — but the rule is yours to keep, not just the guard's.)
- **Anything fetched from the private repo into a public working clone
  must be leak-checked before any push from that clone.**
- **`future/` paths can never appear in a public commit** — the public
  repo's pre-commit denylist refuses them. If it fires, it is working.
- **Every promotion updates `future/promotions.md`** — the register
  shrinking is the measure of the private constitution publishing itself.
