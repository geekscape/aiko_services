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

**Status (project-lead decision, 2026-08-01).** This directory is not
committed yet. It becomes a git commit when the STE conversion is
complete. The tools stay in the repository after that, because a future
document, or a future issue of the standard, can need them again.

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

Each line of the report gives one file and six counts:

| Code | Rule | Meaning |
|---|---|---|
| `L` | 5.1 / 6.3 | Sentences longer than the limit |
| `S` | 8.1 | Semicolons in prose |
| `B` | 1.14 | British spelling |
| `W` | t_04 §4 | Words on the swap list |
| `X` | GR-6 | Latin abbreviations |
| `C` | 4.2 | Contractions |

The `X` check does not need the trailing period of an abbreviation. It
reports `e.g` and `e.g.` alike, because both break GR-6. A longer token
that only starts the same way is safe: `e.golf` and `etcetera` are not
reported. (Each example here sits in a code span, which the tool correctly
ignores.)

**A file is converted when all six counts are 0.** Only then can you set
its `ste:` front matter to `adapted` (rule 13 of
[g_04_ModelHandoffGuide.md](../constitution/g_04_ModelHandoffGuide.md)).

Options:

- `-d` — show each violation with its line number and text
- `--limit=20` — use the procedural sentence limit (rule 5.1). The
  default limit is 25 words (rule 6.3, descriptive writing)

The tool excludes these regions from the prose that it examines: YAML
front matter, fenced code blocks, inline code spans, tables, headings,
link targets, ASCII diagrams and indented blocks. It counts words by
rules 8.4 through 8.7: a code span, a text in parentheses, a number and
an identifier each count as one word.

**Known exemptions that the tool cannot see.** Report these in review,
do not "fix" them:

- `t_04_SimplifiedTechnicalEnglish.md` §2 quotes the semicolon and the
  Latin abbreviations as rule text (rule 8.6, quoted text)
- The link *text* of a Markdown link is prose, and the tool examines it.
  Only the link target is out of scope. Thus `[behaviour](behaviour.md)`
  reports one finding, for the text, not two
- Protocol state names and quoted text (for example, the A2A state
  `input-required`) keep their words
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

**Always read that report and the diff.** The tool cannot see that a
semicolon separates the items of an enumeration. Such a list must become a
vertical list (rule 4.3), and this tool makes sentence fragments from it.
Correct those by hand. Two errors seen in use: a wrongly capitalized
identifier, and a duplicated phrase after a bulk substitution. Scan for
both after each run.

## The conversion procedure for one document

1. Run `asd_ste100_fix.py --write` on the document, then read the diff.
2. Run `asd_ste100_lint.py -d` on the document.
3. Correct each `S` finding, then each `L` finding. Usually the same
   edit corrects both.
4. Correct the `X`, `W`, `B` and `C` findings that remain.
5. Run `asd_ste100_lint.py` again. When all counts are 0, set `ste: adapted` in
   the front matter and set `last_updated` to today.
6. Add an entry to [../log.md](../log.md).
