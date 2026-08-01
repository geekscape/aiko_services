#!/usr/bin/env python3
"""ASD-STE100 lint for Aiko Services Markdown (rules per t_04).

Reports, per file:
  L  long sentences   (rule 5.1 <=20 procedural / 6.3 <=25 descriptive)
  S  semicolons       (rule 8.1)
  B  British spelling (rule 1.14)
  W  swap-list words  (t_04 section 4)
  X  Latin abbrevs    (GR-6)
  C  contractions     (rule 4.2)

Excluded from prose: YAML front matter, fenced code, HTML comments,
inline code spans, table rows, headings, ASCII diagrams, link targets.
Word count follows rules 8.4-8.7 (code span / parentheses / number = 1 word).
"""
import re
import sys
import os

BRITISH = {
    r"\borganis(e|es|ed|ing|ation|ations|ational)\b": "organiz",
    r"\bnormalis(e|es|ed|ing|ation)\b": "normaliz",
    r"\breorganis(e|es|ed|ing|ation)\b": "reorganiz",
    r"\bstandardis(e|es|ed|ing|ation)\b": "standardiz",
    r"\bformalis(e|es|ed|ing|ation)\b": "formaliz",
    r"\bgeneralis(e|es|ed|ing|ation)\b": "generaliz",
    r"\bspecialis(e|es|ed|ing|ation)\b": "specializ",
    r"\bprioritis(e|es|ed|ing|ation)\b": "prioritiz",
    r"\bserialis(e|es|ed|ing|ation)\b": "serializ",
    r"\binitialis(e|es|ed|ing|ation)\b": "initializ",
    r"\bsynchronis(e|es|ed|ing|ation)\b": "synchroniz",
    r"\bauthoris(e|es|ed|ing|ation)\b": "authoriz",
    r"\bcategoris(e|es|ed|ing|ation)\b": "categoriz",
    r"\brecognis(e|es|ed|ing)\b": "recogniz",
    r"\bminimis(e|es|ed|ing)\b": "minimiz",
    r"\bmaximis(e|es|ed|ing)\b": "maximiz",
    r"\bsummaris(e|es|ed|ing)\b": "summariz",
    r"\butilis(e|es|ed|ing)\b": "utiliz",
    r"\bemphasis(e|es|ed|ing)\b": "emphasiz",
    r"\bcharacteris(e|es|ed|ing)\b": "characteriz",
    r"\bmaterialis(e|es|ed|ing)\b": "materializ",
    r"\bcapitalis(e|es|ed|ing)\b": "capitaliz",
    r"\boptimis(e|es|ed|ing|ation|er|ers)\b": "optimiz",
    r"\binternalis(e|es|ed|ing|ation)\b": "internaliz",
    r"\brealis(e|es|ed|ing|ation)\b": "realiz",   # NOT "realistic" / "realistically"
    r"\bbehaviour(s|al)?\b": "behavior",
    r"\bcolour(s|ed|ing)?\b": "color",
    r"\bfavour(s|ed|ing|able)?\b": "favor",
    r"\bhonour(s|ed|ing)?\b": "honor",
    r"\blabour(s|ed|ing)?\b": "labor",
    r"\bcentre(s|d)?\b": "center",
    r"\bmetre(s)?\b": "meter",
    r"\bfibre(s)?\b": "fiber",
    r"\bdefence\b": "defense",
    r"\blicence\b": "license (n)",
    r"\bpractis(e|es|ed|ing)\b": "practic",
    r"\banalys(e|ed|ing)\b": "analyz",   # NOT "analyses" — correct US plural of analysis
    r"\bcatalogue(s|d)?\b": "catalog",
    r"\bdialogue(s)?\b": "dialog",
    r"\bjudgement(s)?\b": "judgment",
    r"\backnowledgement(s)?\b": "acknowledgment",
    r"\bmodelling\b": "modeling",
    r"\bmodelled\b": "modeled",
    r"\blabelled\b": "labeled",
    r"\blabelling\b": "labeling",
    r"\bcancelled\b": "canceled",
    r"\bcancelling\b": "canceling",
    r"\btravelled\b": "traveled",
    r"\bfulfil\b": "fulfill",
    r"\benrol\b": "enroll",
    r"\bwhilst\b": "while",
    r"\bamongst\b": "among",
    r"\btowards\b": "toward",
    r"\bgrey\b": "gray",
    r"\bstorey(s)?\b": "story",
    r"\bmanoeuvre(s|d)?\b": "maneuver",
    r"\bprogramme(s)?\b": "program",
    r"\bdisc\b": "disk",
    r"\bsceptic(al|ism)?\b": "skeptic",
}

SWAPS = {
    r"\bensure(s|d)?\b": "make sure",
    r"\bensuring\b": "make sure",
    r"\bprovide(s|d)?\b": "give",
    r"\bproviding\b": "give",
    r"\bperform(s|ed)?\b": "do",
    r"\bcarry out\b": "do",
    r"\bcarries out\b": "does",
    r"\bprior to\b": "before",
    r"\bin order to\b": "to",
    r"\butilize(s|d)?\b": "use",
    r"\bemploy(s|ed)?\b": "use",
    r"\bcommence(s|d)?\b": "start",
    r"\binitiate(s|d)?\b": "start",
    r"\brenew(s|ed|al)?\b": "extend",
    r"\bhowever\b": "but",
    r"\bdelete(s|d)?\b": "erase",
    r"\brequire(s|d)?\b": "need / must",
    r"\bindicate(s|d)?\b": "show",
    r"\bobtain(s|ed)?\b": "get",
    r"\battempt(s|ed)?\b": "try",
    r"\bassist(s|ed)?\b": "help",
    r"\bpermit\b": "let",
    r"\bnumerous\b": "many",
    r"\bsufficient\b": "enough",
    r"\bapproximately\b": "about",
    r"\bsubsequently\b": "then",
    r"\bfurthermore\b": "also",
    r"\bnevertheless\b": "but",
    r"\bregarding\b": "about",
    r"\bconcerning\b": "about",
    r"\bpertaining to\b": "about",
    r"\bvia\b": "with / through",
}

LATIN = {
    # the trailing period is optional: "e.g" without it is the same GR-6
    # abbreviation, and it must not pass the gate.  The negative lookahead
    # stops a false positive on a longer token ("e.golf", "etcetera")
    r"\be\.g\.?(?!\w)": "for example",
    r"\bi\.e\.?(?!\w)": "that is",
    r"\betc\.?(?!\w)": "and more",
    r"\bvs\.?\b": "compared with",
    r"\bet al\.": "and others",
    r"\bcf\.": "compare",
    r"\bN\.B\.": "note",
    r"\bad hoc\b": "unplanned",
    r"\bde facto\b": "in practice",
    r"\bvice versa\b": "the opposite way",
}

CONTRACTIONS = r"\b(don't|doesn't|didn't|isn't|aren't|wasn't|weren't|can't|won't|shouldn't|couldn't|wouldn't|it's|that's|there's|here's|you'd|you're|you'll|we're|we'll|they're|hasn't|haven't|hadn't|let's)\b"


def strip_regions(text):
    """Return text with non-prose regions blanked, preserving line numbers."""
    lines = text.split("\n")
    out = []
    in_fm = False
    in_code = False
    in_html = False
    for i, line in enumerate(lines):
        s = line.strip()
        if i == 0 and s == "---":
            in_fm = True
            out.append("")
            continue
        if in_fm:
            out.append("")
            if s == "---":
                in_fm = False
            continue
        if s.startswith("```"):
            in_code = not in_code
            out.append("")
            continue
        if in_code:
            out.append("")
            continue
        if "<!--" in s:
            in_html = True
        if in_html:
            out.append("")
            if "-->" in s:
                in_html = False
            continue
        if s.startswith("|") or re.match(r"^#{1,6} ", s):
            out.append("")
            continue
        if re.match(r"^\s{4,}\S", line) and not re.match(r"^\s*[-*+] ", line):
            out.append("")            # indented block / diagram
            continue
        if re.search(r"[│┌└├─►▼▲]", line):
            out.append("")            # ASCII diagram
            continue
        out.append(line)
    return out


def normalize(sent):
    sent = re.sub(r"`[^`]*`", "CODE", sent)
    # rule 8.6: quoted text counts as one word (and is never reworded)
    sent = re.sub(r"\u201c[^\u201d]{8,}\u201d", "QUOTE", sent)
    sent = re.sub(r'"[^"]{8,}"', "QUOTE", sent)
    sent = sent.replace("**", " ").replace("*", " ")   # emphasis: '.**' must split
    sent = re.sub(r"\[([^]]*)\]\([^)]*\)", r"\1", sent)
    sent = re.sub(r"\([^)]*\)", "PAREN", sent)
    sent = re.sub(r"\b\d[\d,:%×/-]*(?:\.\d+)*", "NUM ", sent)   # keep a trailing "." — it ends a sentence
    return sent


def sentences_of(block):
    block = normalize(block)
    # a sentence may start with a quote, markup, an identifier (lowercase)
    # or a section mark; never split after a known abbreviation
    parts = re.split(r"(?<=[.!?:])\s+(?=[\"'“*`\[(§A-Za-z])", block)
    return [p for p in parts if re.search(r"[A-Za-z]{2}", p)]


def wc(sent):
    return len([w for w in re.split(r"\s+", sent.strip()) if w.strip("*_-•>")])


def lint(path, limit=25, verbose=True):
    text = open(path).read()
    lines = strip_regions(text)
    findings = {"L": [], "S": [], "B": [], "W": [], "X": [], "C": []}
    # blocks: a bullet item or a paragraph run
    block, block_start = [], 0
    blocks = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            if block:
                blocks.append((block_start, " ".join(block)))
                block = []
            continue
        if re.match(r"^\s*([-*+]|\d+\.|[A-Za-z]\.)\s", line) and block:
            blocks.append((block_start, " ".join(block)))
            block = []
        if not block:
            block_start = i + 1
        block.append(s)
    if block:
        blocks.append((block_start, " ".join(block)))

    for start, blk in blocks:
        for sent in sentences_of(blk):
            n = wc(sent)
            if n > limit:
                findings["L"].append((start, n, sent[:100]))
        prose_only = re.sub(r"`[^`]*`", "CODE", blk)   # code spans are not prose
        if ";" in prose_only:
            findings["S"].append((start, prose_only.count(";"), blk[:100]))

    prose = "\n".join(lines)
    for i, raw_line in enumerate(lines):
        # An inline code span and a link target are not prose (t_04 section
        # 5), so the word checks must not read them.  Without this, the
        # Unix path "/etc/inittab" reads as the Latin "etc", and an
        # identifier such as "serialise_data()" reads as British spelling.
        # The replacement keeps the column count, so the hyphen test below
        # still looks at the correct neighbouring characters
        line = re.sub(r"`[^`]*`", lambda m: "`" + "x" * (len(m.group(0)) - 2) + "`",
                      raw_line)
        line = re.sub(r"\]\(([^)]*)\)",
                      lambda m: "](" + "x" * len(m.group(1)) + ")", line)
        for pat, alt in BRITISH.items():
            for m in re.finditer(pat, line, re.I):
                findings["B"].append((i + 1, m.group(0), alt))
        for pat, alt in SWAPS.items():
            for m in re.finditer(pat, line, re.I):
                if m.group(0).isupper():
                    continue          # RFC 2119 keyword (MUST, REQUIRED) — quoted term
                a, b = m.start(), m.end()
                if (a > 0 and line[a-1] == "-") or (b < len(line) and line[b] == "-"):
                    continue          # hyphenated compound: AI-assisted, input-required
                findings["W"].append((i + 1, m.group(0), alt))
        for pat, alt in LATIN.items():
            for m in re.finditer(pat, line):
                findings["X"].append((i + 1, m.group(0), alt))
        for m in re.finditer(CONTRACTIONS, line, re.I):
            findings["C"].append((i + 1, m.group(0), ""))

    if verbose:
        name = os.path.basename(path)
        counts = " ".join(f"{k}={len(v)}" for k, v in findings.items())
        print(f"{name:46s} {counts}")
    return findings


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    detail = "-d" in sys.argv
    limit = 25                      # rule 6.3, descriptive writing
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])    # use --limit=20 for procedures (rule 5.1)
    totals = {}
    for path in args:
        f = lint(path, limit=limit, verbose=not detail)
        for k, v in f.items():
            totals[k] = totals.get(k, 0) + len(v)
        if detail:
            print(f"\n===== {path}")
            for k, label in [("L", "LONG"), ("S", "SEMICOLON"), ("B", "BRITISH"),
                             ("W", "SWAP"), ("X", "LATIN"), ("C", "CONTRACTION")]:
                for item in f[k]:
                    print(f"  {label:12s} line {item[0]:4d}  {item[1]}  {item[2] if len(item)>2 else ''}")
    if len(args) > 1:
        print("\nTOTALS:", " ".join(f"{k}={v}" for k, v in totals.items()))
