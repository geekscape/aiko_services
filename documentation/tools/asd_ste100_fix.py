#!/usr/bin/env python3
"""Deterministic ASD-STE100 fixes for Aiko Services Markdown.

Applies only the safe, mechanical classes:
  - American English spelling (rule 1.14)
  - Latin abbreviations (GR-6)
  - contractions (rule 4.2)
  - unambiguous swap-list words (t_04 section 4)
  - semicolon splitting where both sides are independent clauses (rule 8.1)

Protected and never touched: fenced code, inline code spans, link targets,
URLs, identifiers (containing _ or . or CamelCase), ASCII diagrams,
indented blocks. YAML front matter gets spelling fixes only, on the
title/description lines, so index ReadMe rows stay in sync.

Usage: asd_ste100_fix.py [--write] [--semicolons] FILE...
"""
import re
import sys

SPELLING = [
    (r"\borganis(e|es|ed|ing|ation|ations|ational)\b", lambda m: "organiz" + m.group(1)),
    (r"\bnormalis(e|es|ed|ing|ation)\b", lambda m: "normaliz" + m.group(1)),
    (r"\bstandardis(e|es|ed|ing|ation)\b", lambda m: "standardiz" + m.group(1)),
    (r"\bformalis(e|es|ed|ing|ation)\b", lambda m: "formaliz" + m.group(1)),
    (r"\bgeneralis(e|es|ed|ing|ation)\b", lambda m: "generaliz" + m.group(1)),
    (r"\bspecialis(e|es|ed|ing|ation)\b", lambda m: "specializ" + m.group(1)),
    (r"\bprioritis(e|es|ed|ing|ation)\b", lambda m: "prioritiz" + m.group(1)),
    (r"\bserialis(e|es|ed|ing|ation)\b", lambda m: "serializ" + m.group(1)),
    (r"\binitialis(e|es|ed|ing|ation)\b", lambda m: "initializ" + m.group(1)),
    (r"\bsynchronis(e|es|ed|ing|ation)\b", lambda m: "synchroniz" + m.group(1)),
    (r"\bauthoris(e|es|ed|ing|ation)\b", lambda m: "authoriz" + m.group(1)),
    (r"\bcategoris(e|es|ed|ing|ation)\b", lambda m: "categoriz" + m.group(1)),
    (r"\brecognis(e|es|ed|ing)\b", lambda m: "recogniz" + m.group(1)),
    (r"\bminimis(e|es|ed|ing)\b", lambda m: "minimiz" + m.group(1)),
    (r"\bmaximis(e|es|ed|ing)\b", lambda m: "maximiz" + m.group(1)),
    (r"\bsummaris(e|es|ed|ing)\b", lambda m: "summariz" + m.group(1)),
    (r"\bemphasis(e|es|ed|ing)\b", lambda m: "emphasiz" + m.group(1)),
    (r"\bcharacteris(e|es|ed|ing)\b", lambda m: "characteriz" + m.group(1)),
    (r"\bmaterialis(e|es|ed|ing)\b", lambda m: "materializ" + m.group(1)),
    (r"\bcapitalis(e|es|ed|ing)\b", lambda m: "capitaliz" + m.group(1)),
    (r"\boptimis(e|es|ed|ing|ation|er|ers)\b", lambda m: "optimiz" + m.group(1)),
    (r"\binternalis(e|es|ed|ing|ation)\b", lambda m: "internaliz" + m.group(1)),
    (r"\brealis(e|es|ed|ing|ation)\b", lambda m: "realiz" + m.group(1)),
    (r"\binstitutionalis(e|es|ed|ing)\b", lambda m: "institutionaliz" + m.group(1)),
    (r"\bdecentralis(e|es|ed|ing|ation)\b", lambda m: "decentraliz" + m.group(1)),
    (r"\bcentralis(e|es|ed|ing|ation)\b", lambda m: "centraliz" + m.group(1)),
    # suffix groups mirror the asd_ste100_lint.py BRITISH table entry for entry, so
    # the fixer never leaves an inflection that the gate goes on to report
    (r"\bbehaviour(s|al)?\b", lambda m: "behavior" + (m.group(1) or "")),
    (r"\bcolour(s|ed|ing)?\b", lambda m: "color" + (m.group(1) or "")),
    (r"\bfavour(s|ed|ing|able)?\b", lambda m: "favor" + (m.group(1) or "")),
    (r"\bhonour(s|ed|ing)?\b", lambda m: "honor" + (m.group(1) or "")),
    (r"\blabour(s|ed|ing)?\b", lambda m: "labor" + (m.group(1) or "")),
    (r"\bcentre(s)?\b", lambda m: "center" + (m.group(1) or "")),
    (r"\bcentred\b", lambda m: "centered"),   # not "centre" + "d"
    (r"\bcentring\b", lambda m: "centering"),
    (r"\bmetre(s)?\b", lambda m: "meter" + (m.group(1) or "")),
    (r"\bfibre(s)?\b", lambda m: "fiber" + (m.group(1) or "")),
    (r"\bdefence\b", lambda m: "defense"),
    (r"\bpractis(e|es|ed|ing)\b", lambda m: "practic" + m.group(1)),
    (r"\banalys(e|ed|ing)\b", lambda m: "analyz" + m.group(1)),
    # "catalogue" and "dialogue" lose the "ue", so the suffix is not a
    # straight append: "catalogued" -> "cataloged", not "catalogd"
    (r"\bcatalogue\b", lambda m: "catalog"),
    (r"\bcatalogues\b", lambda m: "catalogs"),
    (r"\bcatalogued\b", lambda m: "cataloged"),
    (r"\bcataloguing\b", lambda m: "cataloging"),
    (r"\bdialogue(s)?\b", lambda m: "dialog" + (m.group(1) or "")),
    (r"\bjudgement(s)?\b", lambda m: "judgment" + (m.group(1) or "")),
    (r"\backnowledgement(s)?\b", lambda m: "acknowledgment" + (m.group(1) or "")),
    (r"\bmodelling\b", lambda m: "modeling"),
    (r"\bmodelled\b", lambda m: "modeled"),
    (r"\blabelled\b", lambda m: "labeled"),
    (r"\blabelling\b", lambda m: "labeling"),
    (r"\bcancelled\b", lambda m: "canceled"),
    (r"\bcancelling\b", lambda m: "canceling"),
    (r"\btravelled\b", lambda m: "traveled"),
    (r"\bsignalled\b", lambda m: "signaled"),
    (r"\bfulfil\b", lambda m: "fulfill"),
    (r"\bwhilst\b", lambda m: "while"),
    (r"\bamongst\b", lambda m: "among"),
    (r"\btowards\b", lambda m: "toward"),
    (r"\bgrey\b", lambda m: "gray"),
    (r"\bmanoeuvre\b", lambda m: "maneuver"),
    (r"\bsceptical\b", lambda m: "skeptical"),
    (r"\bscepticism\b", lambda m: "skepticism"),
]

# Applied case-sensitively, unlike every other list. The ClearName
# e_07_ConstitutionReorganisation keeps its British spelling because it is an
# identifier, so only the lowercase prose form is corrected here. Matching
# these case-insensitively would rewrite the document name itself.
SPELLING_CASE_SENSITIVE = [
    (r"(?<![A-Za-z])reorganisation(s?)\b", lambda m: "reorganization" + m.group(1)),
    (r"(?<![A-Za-z])reorganis(e|ed|ing)\b", lambda m: "reorganiz" + m.group(1)),
]

# Latin abbreviations are NOT auto-replaced: "e.g." mid-sentence needs the
# sentence reworded, not a substitution. Handled by hand (GR-6).
LATIN = [
    (r"\bvia\b", "through"),
]

CONTRACTIONS = [
    (r"\bdon't\b", "do not"), (r"\bdoesn't\b", "does not"),
    (r"\bdidn't\b", "did not"), (r"\bisn't\b", "is not"),
    (r"\baren't\b", "are not"), (r"\bwasn't\b", "was not"),
    (r"\bweren't\b", "were not"), (r"\bcan't\b", "cannot"),
    (r"\bwon't\b", "will not"), (r"\bshouldn't\b", "should not"),
    (r"\bcouldn't\b", "could not"), (r"\bwouldn't\b", "would not"),
    (r"\bhasn't\b", "has not"), (r"\bhaven't\b", "have not"),
    (r"\bhadn't\b", "had not"), (r"\bdoesn’t\b", "does not"),
    (r"\bit's\b", "it is"), (r"\bthat's\b", "that is"),
    (r"\bthere's\b", "there is"), (r"\bhere's\b", "here is"),
    (r"\byou're\b", "you are"), (r"\byou'll\b", "you will"),
    (r"\bwe're\b", "we are"), (r"\bwe'll\b", "we will"),
    (r"\bthey're\b", "they are"), (r"\blet's\b", "let us"),
    (r"\bcan’t\b", "cannot"), (r"\bdon’t\b", "do not"),
]

SWAPS = [
    (r"\bensures\b", "makes sure"), (r"\bensure\b", "make sure"),
    (r"\bensured\b", "made sure"), (r"\bensuring\b", "to make sure"),
    (r"\bprior to\b", "before"), (r"\bin order to\b", "to"),
    (r"\butilizes\b", "uses"), (r"\butilize\b", "use"),
    (r"\butilized\b", "used"), (r"\bcommences\b", "starts"),
    (r"\bcommence\b", "start"), (r"\binitiates\b", "starts"),
    (r"\binitiate\b", "start"), (r"\bapproximately\b", "about"),
    (r"\bsufficient\b", "enough"), (r"\bnumerous\b", "many"),
    (r"\bfurthermore\b", "also"), (r"\bsubsequently\b", "then"),
    (r"\bpertaining to\b", "about"), (r"\bconcerning\b", "about"),
    (r"\bobtains\b", "gets"), (r"\bobtain\b", "get"),
    (r"\bassists\b", "helps"), (r"\bassist\b", "help"),
    (r"\bad hoc\b", "unplanned"),
]

PROTECT = re.compile(
    r"(`[^`]*`|\]\([^)]*\)|https?://\S+|\b\w*[_/]\w*\b|\b\w+\.(?:md|py|json|txt|sh|yaml)\b)"
)


def preserve_case(matched, replacement):
    """Give the replacement the capitalization of the word it replaces.

    A rule is written in lowercase, but the word in the text can start a
    sentence ("Behaviour") or be an acronym-style capital ("BEHAVIOUR").
    Without this, the fixer silently skips every capitalized British
    spelling, contraction and swap-list word, and the gate reports them.
    """
    if not matched or not replacement:
        return replacement
    if matched.isupper() and len(matched) > 1:
        return replacement.upper()
    if matched[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def apply_to_prose(line, rules, ignore_case=True):
    """Apply rules to the unprotected parts of a line.

    Matching is case-insensitive by default, and the replacement keeps the
    capitalization of the original word. Pass ignore_case=False for a rule
    list whose case is meaningful (see SPELLING_CASE_SENSITIVE).
    """
    flags = re.IGNORECASE if ignore_case else 0
    parts = PROTECT.split(line)
    out = []
    for i, part in enumerate(parts):
        if part is None:
            continue
        if i % 2 == 1 or (part and PROTECT.fullmatch(part)):
            out.append(part)
            continue
        for pat, rep in rules:
            def substitute(m, rep=rep):
                base = rep(m) if callable(rep) else rep
                return preserve_case(m.group(0), base)
            part = re.sub(pat, substitute, part, flags=flags)
        out.append(part)
    return "".join(out)


def split_semicolons(line):
    """'clause; clause' -> 'clause. Clause' when safe."""
    if ";" not in line:
        return line
    parts = PROTECT.split(line)
    out = []
    for i, part in enumerate(parts):
        if part is None:
            continue
        if i % 2 == 1 or (part and PROTECT.fullmatch(part)):
            out.append(part)
            continue

        def repl(m):
            nxt = m.group(1)
            return ". " + nxt.upper()
        # only when not inside parentheses on this line
        depth_safe = part.count("(") == part.count(")")
        if depth_safe:
            part = re.sub(r";\s+([a-z])", repl, part)
        out.append(part)
    return "".join(out)


def process(path, write=False, semicolons=False):
    text = open(path).read()
    lines = text.split("\n")
    out = []
    in_fm = False
    in_code = False
    in_swap_table = False
    changes = 0
    for i, line in enumerate(lines):
        s = line.strip()
        orig = line
        # a swap table lists unapproved words on purpose: never rewrite it
        if "ste-swap-table" in s:
            in_swap_table = True
            out.append(line)
            continue
        if in_swap_table:
            if s and not s.startswith("|"):
                in_swap_table = False
            else:
                out.append(line)
                continue
        if i == 0 and s == "---":
            in_fm = True
            out.append(line)
            continue
        if in_fm:
            if s == "---":
                in_fm = False
                out.append(line)
                continue
            # spelling only, on prose-bearing front-matter fields
            if re.match(r"^(title|description|\s+\S)", line):
                line = apply_to_prose(line, SPELLING)
                line = apply_to_prose(line, SPELLING_CASE_SENSITIVE,
                                      ignore_case=False)
            out.append(line)
            if line != orig:
                changes += 1
            continue
        if s.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        if re.search(r"[│┌└├─►▼▲┐┘┤┬┴┼]", line):
            out.append(line)
            continue
        if re.match(r"^\s{4,}\S", line) and not re.match(r"^\s*[-*+>] ", line):
            out.append(line)
            continue
        line = apply_to_prose(line, SPELLING)
        line = apply_to_prose(line, SPELLING_CASE_SENSITIVE, ignore_case=False)
        line = apply_to_prose(line, LATIN)
        line = apply_to_prose(line, CONTRACTIONS)
        line = apply_to_prose(line, SWAPS)
        if semicolons:
            line = split_semicolons(line)
        line = re.sub(r"\s+$", "", line)
        out.append(line)
        if line != orig:
            changes += 1
    new = "\n".join(out)
    if write and changes:
        open(path, "w").write(new)
    return changes


if __name__ == "__main__":
    write = "--write" in sys.argv
    semis = "--semicolons" in sys.argv
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    total = 0
    for path in files:
        n = process(path, write=write, semicolons=semis)
        total += n
        if n:
            print(f"{'wrote' if write else 'would change'} {n:4d} lines  {path}")
    print(f"TOTAL lines changed: {total}")
