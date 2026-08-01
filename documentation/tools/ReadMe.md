---
title: Documentation scripts — ASD-STE100 lint and mechanical fixer
description: The three command-line tools that verify and prepare Aiko
  Services documentation for ASD-STE100 Simplified Technical English —
  what each one checks, how to run it, and what it cannot do
type: index
audience: [project-lead, architects, developers, ai-coding-agents]
status: operational
ste: adapted
related: [../constitution/t_04_SimplifiedTechnicalEnglish,
  ../constitution/t_02_OkfTaxonomy, ../constitution/g_04_ModelHandoffGuide]
last_updated: 2026-08-01
---

# Documentation scripts — ASD-STE100 lint and mechanical fixer

Three tools support the ASD-STE100 Simplified Technical English (STE)
conversion of the documentation. The rules that they apply are in
[t_04_SimplifiedTechnicalEnglish.md](../constitution/t_04_SimplifiedTechnicalEnglish.md).
The tools use only the Python standard library.

**Status (project-lead decision, 2026-08-01).** This directory is
committed and pushed, because the STE conversion of `documentation/` is
complete. The tools stay in the repository, because a future document, or
a future issue of the standard, can need them again. They are the only
part of the governance tooling that is public.

**File modes.** A file here is mode 600. An executable file is mode 700.

| Tool | What it does | Safe to run without review? |
|---|---|---|
| `asd_ste100_lint.py` | Reports violations. Changes no file | Yes — it is read-only |
| `asd_ste100_fix.py` | Applies the mechanical fixes | Yes with `--write`, but read the diff |
| `asd_ste100_semisplit.py` | Divides prose semicolons into sentences | No — read the diff and the capitalization report |

## asd_ste100_lint.py — the verification gate

```bash
python3 documentation/tools/asd_ste100_lint.py documentation/constitution/*.md
```

Each line of the report gives one file and seven counts:

| Code | Rule | Meaning |
|---|---|---|
| `L` | 5.1 / 6.3 | Sentences longer than the limit |
| `S` | 8.1 | Semicolons in prose |
| `B` | 1.14 | British spelling |
| `W` | t_04 §4 | Words on the swap list |
| `X` | GR-6 | Latin abbreviations |
| `C` | 4.2 | Contractions |
| `F` | 4.1 | Sentence shape — a bad split left by the semicolon tool |

One more line can appear, and it is **advisory only**. `I` counts a
swap-list word that is also a code span in the same file. That is an
identifier collision, and the swap would rename something real (§3, API
names beat the dictionary). The gate does not count `I`. Decide each by
hand.

The `X` check does not need the trailing period of an abbreviation. It
reports `e.g` and `e.g.` alike, because both break GR-6. A longer token
that only starts the same way is safe: `e.golf` and `etcetera` are not
reported. (Each example here sits in a code span, which the tool correctly
ignores.)

**A file is converted when all seven counts are 0.** Only then can you set
its `ste:` front matter to `adapted` (rule 13 of
[g_04_ModelHandoffGuide.md](../constitution/g_04_ModelHandoffGuide.md)).
The `I` advisory does not block that, but read it first.

Options:

- `-d` — show each violation with its line number and text
- `--limit=20` — use the procedural sentence limit (rule 5.1). The
  default limit is 25 words (rule 6.3, descriptive writing)

The `L` and `S` checks exclude these regions from the prose that they
examine: YAML front matter, fenced code blocks, inline code spans,
tables, headings, link targets, ASCII diagrams and indented blocks. They
count words by rules 8.4 through 8.7: a code span, a text in
parentheses, a number and an identifier each count as one word.

**The word checks read more than the prose.** `B`, `W`, `X` and `C` also
read **table cells** and the prose-bearing **front-matter fields**
(`title:`, `description:`). t_04 §5 puts table-cell text in scope, and a
`description:` is quoted verbatim by the one-line summary in each
`ReadMe.md` index. Before 2026-08-01 those two regions were invisible,
and about forty real British spellings hid in them across
`documentation/`.

**Quoted text is never a finding.** Rule 8.6 counts a quotation as one
word, and t_04 §1 forbids rewording a citation. Both this tool and
`asd_ste100_fix.py` protect `"..."` spans, so the gate never asks for a
change that the fixer refuses to make.

**British spelling is now a rule, not a list.** A general `-ise` /
`-isation` pattern with an allowlist replaces the endless named stems.
Before it, `sanitise`, `synthesise`, `tokenisation`, `deserialise`,
`finalise`, `visualise`, `unrecognised`, `parameterise` and `stabilise`
each had to be found by hand, one at a time. The `-our` family stays an
explicit list, because it is closed and "four", "hour" and "source" must
not match.

**Declare an exemption in the document, never in your head.** A document
that teaches the rules must quote them, and a quotation is not a finding
(rule 8.6). Two markers say so, and both are HTML comments, so neither
renders:

```markdown
<!-- ste-exempt: GR-6 must show the abbreviations that it forbids -->
- GR-6 Do not use Latin abbreviations (e.g., i.e., etc., et al.).
<!-- ste-exempt-end -->

<!-- ste-swap-table: left column is intentionally non-STE -->
```

The gate and `asd_ste100_fix.py` both honor them.
`t_04_SimplifiedTechnicalEnglish.md` uses both, for the rule 8.1 semicolon,
the GR-6 abbreviations and the §4 swap table.

**Caution: an exemption is not a way to silence a finding.** Until
2026-08-01 this section instead told the reader to remember that the whole
of t_04 §2 and §4 was exempt. That blanket hid a real defect for weeks — a
table cell that read "per-word dictionary proof is not required". Mark the
smallest region that quotes the standard, and nothing more.

**Findings the tool reports that are correct as they stand.** Report these
in review, do not "fix" them:

- The link *text* of a Markdown link is prose, and the tool examines it.
  Only the link target is out of scope. Thus `[behaviour](behaviour.md)`
  reports one finding, for the text, not two
- Protocol state names keep their words (for example, the A2A state
  `input-required`)
- RFC 2119 keywords in capitals (MUST, REQUIRED) are quoted terms. The
  tool already skips them, together with hyphenated compounds

## asd_ste100_fix.py — the mechanical pass

```bash
python3 documentation/tools/asd_ste100_fix.py documentation/constitution/*.md    # dry run
python3 documentation/tools/asd_ste100_fix.py --write documentation/constitution/*.md
git diff documentation/                                                     # review
```

The fixer applies only the deterministic classes: American English
spelling, contractions, and the unambiguous swap-list words. It protects
fenced code, inline code, link targets, URLs and identifiers. In YAML
front matter it corrects spelling only, so that the one-line summaries in
each `ReadMe.md` index stay in agreement.

**Capitalization.** Matching is case-insensitive, and each replacement
keeps the capitalization of the word that it replaces. A word at the
start of a sentence keeps its initial capital, and a word in full
capitals stays in full capitals. Before 2026-08-01 the rules matched
lowercase only. A capitalized British spelling, contraction or swap-list
word was then skipped in silence, and the gate reported it afterward.

**One exception, on purpose.** The British form behind the ClearName
`e_07_ConstitutionReorganisation` is corrected in lowercase prose only,
because that ClearName is an identifier and keeps its spelling. Thus
`asd_ste100_lint.py` can report a capitalized instance that this tool does not
correct. Decide that one by hand: correct it when it is prose, and leave
it when it names the document.

**Caution: do not run the fixer over these files.**

- The exempt historical records — the dated `_YYYY-MM` analyses and the
  executed plan records. They keep their original words (t_04 §1)
- `documentation/log.md`, which quotes British spellings and swap-list
  words as examples of what was corrected. To "fix" the journal destroys
  the record of the fix

Always name the files that you intend to change. Never give the fixer a
whole directory.

**The fixer does not touch sentence length or semicolons.** Those need
judgment, and a script makes bad prose from them. Refer to the semicolon
rules in
[t_04_SimplifiedTechnicalEnglish.md](../constitution/t_04_SimplifiedTechnicalEnglish.md)
§4.1.

## asd_ste100_semisplit.py — the mechanical semicolon split

```bash
python3 documentation/tools/asd_ste100_semisplit.py <file>            # dry run
python3 documentation/tools/asd_ste100_semisplit.py --write <file>    # apply
```

It divides `clause; clause` into two sentences, and it capitalizes the
second clause. It protects fenced code, inline code spans, document ids
(`e_08`), snake_case identifiers and a list of product names (`xgo`,
`aiko`, `mqtt` and more). It prints each capitalization that it made.

**Three regions are protected, each after a defect.**

- **YAML front matter.** A `description:` field is quoted verbatim by the
  one-line summary in every `ReadMe.md` index, so a split there
  desynchronizes the index in silence. The tool now skips front matter,
  and reports how many protected lines it left alone.
- **Table rows.** `asd_ste100_lint.py` does not inspect a table, so a
  rewrite there is invisible to the gate. The converted trees keep their
  table-cell semicolons on purpose.
- **A clause inside parentheses.** `(clause; clause)` would become
  `(clause. Clause)`, which reads as a fragment.

**Always read that report and the diff.** The tool still cannot see that
a semicolon separates the items of an enumeration. Such a list must
become a vertical list (rule 4.3), and this tool makes sentence fragments
from it. Correct those by hand. Errors seen in use: a wrongly capitalized
identifier, and a duplicated phrase after a bulk substitution. The `F`
count of the gate now catches the two split shapes automatically.

## The conversion procedure for one document

1. Run `asd_ste100_fix.py --write` on the document, then read the diff.
2. Run `asd_ste100_lint.py -d` on the document.
3. Correct each `S` finding, then each `L` finding. Usually the same
   edit corrects both.
4. Correct the `X`, `W`, `B`, `C` and `F` findings that remain.
5. Read any `I` advisory line. An identifier collision is a decision, not
   a defect: keep the word when it names a real command or method.
6. Run `asd_ste100_lint.py` again. When all seven counts are 0, set
   `ste: adapted` in the front matter and set `last_updated` to today.
7. Add an entry to [../log.md](../log.md).

**When a `description:` field changes, check its `ReadMe.md` index row in
the same change.** The row quotes that field, and the two must agree.
