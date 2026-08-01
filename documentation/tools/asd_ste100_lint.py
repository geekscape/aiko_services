#!/usr/bin/env python3
"""ASD-STE100 lint for Aiko Services Markdown (rules per t_04).

Reports, per file:
  L  long sentences   (rule 5.1 <=20 procedural / 6.3 <=25 descriptive)
  S  semicolons       (rule 8.1)
  B  British spelling (rule 1.14)
  W  swap-list words  (t_04 section 4)
  X  Latin abbrevs    (GR-6)
  C  contractions     (rule 4.2)
  F  sentence shape   (a bad split left by asd_ste100_semisplit.py)

The L and S checks read prose only. Excluded from prose: YAML front
matter, fenced code, HTML comments, inline code spans, table rows,
headings, ASCII diagrams, link targets. Word count follows rules 8.4-8.7
(code span / parentheses / number = 1 word).

The word checks B, W, X and C additionally read **table cells** and the
prose-bearing **front-matter fields** (`title:`, `description:`). t_04
section 5 puts table-cell text in scope, and a `description:` is quoted
verbatim by the one-line summary in every `ReadMe.md` index. Before this,
those two regions were invisible to the gate, and roughly forty real
British spellings hid in them across `documentation/`.

The F check finds the two shapes that `asd_ste100_semisplit.py` can leave
behind when it turns "clause; clause" into "clause. Clause":
  - a sentence that starts in lowercase
  - a split inside parentheses, which reads as a fragment
Neither is a length or a semicolon, so the other checks cannot see them.

A W finding whose word is also used as a code span in the same file is
reported as `W!`. That is an identifier collision: the swap-list
replacement would rename something real (t_04 section 3, API names beat
the dictionary). Decide those by hand.
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
    r"\btravelling\b": "traveling",
    r"\bsignalling\b": "signaling",
    # the "-our" family: a closed set, so it is listed rather than generalized
    # ("four", "hour", "tour", "pour", "your", "source" must not match)
    r"\bneighbour(s|ed|ing|hood|hoods)?\b": "neighbor",
    r"\bharbour(s|ed|ing)?\b": "harbor",
    r"\brumour(s|ed)?\b": "rumor",
    r"\bvapour(s)?\b": "vapor",
    r"\bflavour(s|ed|ing)?\b": "flavor",
    r"\bendeavour(s|ed|ing)?\b": "endeavor",
    r"\bodour(s)?\b": "odor",
    r"\bhumour(s|ed)?\b": "humor",
    r"\bvalour\b": "valor",
    r"\bsavour(s|ed|ing)?\b": "savor",
    r"\barmour(s|ed)?\b": "armor",
    r"\btumour(s)?\b": "tumor",
    r"\bclamour(s|ed|ing)?\b": "clamor",
    r"\bsplendour\b": "splendor",
    r"\bvigour\b": "vigor",
    r"\brigour\b": "rigor",
    r"\bdemeanour\b": "demeanor",
    r"\bsaviour(s)?\b": "savior",
}

# The named stems above cannot keep up: this session alone found sanitise,
# synthesise, neighbour, tokenisation, deserialise, finalise, visualise,
# unrecognised, parameterise and stabilise, one at a time, by hand. This
# general rule catches the whole "-ise / -isation" family instead, and the
# allowlist below carries the words that are correct in American English.
ISE_GENERAL = re.compile(r"\b[a-z]+is(?:e|es|ed|ing|ation|ations|able)\b", re.I)

ISE_ALLOWED = {
    # -ise words that are NOT British-only spellings
    "advertise", "advertises", "advertised", "advertising",
    "advise", "advises", "advised", "advising",
    "apprise", "apprised", "arise", "arises", "arising",
    "chastise", "circumcise", "comprise", "comprises", "comprised", "comprising",
    "compromise", "compromises", "compromised", "compromising",
    "demise", "despise", "despised", "devise", "devises", "devised", "devising",
    "disguise", "disguised", "excise", "excised",
    "exercise", "exercises", "exercised", "exercising",
    "franchise", "franchises", "improvise", "improvised", "improvising",
    "incise", "incised", "merchandise", "premise", "premises",
    "prise", "prised", "promise", "promises", "promised", "promising",
    "revise", "revises", "revised", "revising",
    "rise", "rises", "rising", "supervise", "supervises", "supervised",
    "supervising", "surmise", "surmised", "surprise", "surprises",
    "surprised", "surprising", "televise", "televised",
    "wise", "likewise", "otherwise", "clockwise", "counterclockwise",
    "stepwise", "pairwise", "bitwise", "elsewise",
    "noise", "noises", "poise", "poised", "praise", "praised", "praises",
    "raise", "raises", "raised", "raising", "cruise", "cruises", "cruising",
    "bruise", "bruised", "guise", "paradise", "precise", "concise",
    "anise", "expertise", "malaise", "valise", "tortoise", "porpoise",
    "treatise", "treatises", "reprise", "appraise", "appraised", "appraises",
    "enterprise", "enterprises", "mise", "demised", "disguises",
    # "-isable" that is really "-is" + "able", or a plain word
    "disable", "disables", "disabled", "disabling",
    "advisable", "inadvisable", "sizable", "risable",
}


# a prefix does not make a word British: "unsupervised" is "supervised"
ISE_PREFIXES = ("un", "re", "dis", "pre", "non", "over", "under", "mis", "co",
                "inter", "multi", "sub", "super", "de")


def ise_allowed(word):
    w = word.lower()
    if w in ISE_ALLOWED:
        return True
    for p in ISE_PREFIXES:
        if w.startswith(p) and w[len(p):] in ISE_ALLOWED:
            return True
    return False


def ise_findings(line):
    """British "-ise / -isation" spellings that the named stems miss."""
    for m in ISE_GENERAL.finditer(line):
        w = m.group(0)
        if ise_allowed(w):
            continue
        yield m, re.sub(r"is(e|es|ed|ing|ation|ations|able)$",
                        lambda k: "iz" + k.group(1), w.lower())

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


def word_check_regions(text):
    """Return the lines the word checks read, preserving line numbers.

    This is the prose of strip_regions() PLUS two regions that t_04 keeps
    in scope but that the sentence checks must not read:
      - table cells (section 5: table-cell text obeys STE)
      - the prose-bearing front-matter fields, whose text a ReadMe index
        quotes verbatim
    A table's delimiter row and its pipes are removed, so a cell reads as
    ordinary text.
    """
    prose = strip_regions(text)
    lines = text.split("\n")
    out = list(prose)
    in_fm = False
    in_code = False
    for i, line in enumerate(lines):
        s = line.strip()
        if i == 0 and s == "---":
            in_fm = True
            continue
        if in_fm:
            if s == "---":
                in_fm = False
                continue
            if re.match(r"^(title|description):", s) or re.match(r"^\s+\S", line):
                out[i] = re.sub(r"^\s*(title|description):", "", line)
            continue
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if s.startswith("|"):
            if re.fullmatch(r"\|[\s:|-]*\|?", s):
                continue                      # delimiter row: |---|---|
            out[i] = s.strip("|").replace("|", " ")
    return out


# a sentence may legitimately start with one of these lowercase names
LOWER_START_OK = {"dora", "aiko", "xgo", "mqtt", "zmq", "ec", "eval", "exec",
                  "numpy", "opencv", "pytest", "git", "pip", "psutil", "arxiv",
                  "ros", "zenoh", "gst", "llm", "mcp", "repl", "cli", "iOS"}

ABBREV_SAFE = re.compile(r"\b(e\.g|i\.e|etc|vs|cf|Mr|Dr|St|No|al)\.", re.I)
FILE_EXT = re.compile(r"\.(md|py|json|sh|txt|yaml|yml|toml|pt|jsonl|cfg|ini)\b")


def shape_findings(lines):
    """F: bad sentence splits (see the module docstring)."""
    found = []
    for i, raw in enumerate(lines):
        if not raw.strip():
            continue
        s = re.sub(r"`[^`]*`", "CODE", raw)
        s = re.sub(r"\[([^]]*)\]\([^)]*\)", r"\1", s)
        s = ABBREV_SAFE.sub("ABBR", s)
        s = FILE_EXT.sub("EXT", s)
        # an ordered-list marker is not a sentence end: "1. text_io ..."
        s = re.sub(r"^(\s*)(\d+|[a-z])\.\s", r"\1", s)
        for m in re.finditer(r"\.\s+([a-z]{3,})", s):
            if m.group(1).lower() in LOWER_START_OK:
                continue
            # a path or directory name may legitimately start a sentence
            tail = s[m.end():m.end() + 1]
            if tail == "/":
                continue
            found.append((i + 1, "lowercase sentence start",
                          s[max(0, m.start() - 40):m.end() + 12].strip()))
        for m in re.finditer(r"\([^()]{0,90}?[a-z0-9\"'\]]\.\s+[A-Z\"'`\d]", s):
            found.append((i + 1, "split inside parentheses",
                          m.group(0).strip()))
    return found


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
    findings = {"L": [], "S": [], "B": [], "W": [], "X": [], "C": [], "F": [],
                "I": []}   # I = advisory, excluded from the gate counts
    # a word used as a code span anywhere in the file is a term of art here
    code_terms = {c.strip("`").lower()
                  for c in re.findall(r"`[^`\n]{1,40}`", text)}
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

    findings["F"] = [(n, kind, ctx) for n, kind, ctx in shape_findings(lines)]

    # the word checks read prose, table cells and front-matter prose fields
    for i, raw_line in enumerate(word_check_regions(text)):
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
        # Quoted text counts as one word (rule 8.6) and is never reworded, so
        # it is not a finding. asd_ste100_fix.py protects the same region:
        # if the gate reported a citation, the fixer would refuse to correct
        # it and the document could never reach zero
        line = re.sub(r"\"[^\"\n]{1,300}\"|“[^”\n]{1,300}”",
                      lambda m: '"' + "x" * (len(m.group(0)) - 2) + '"', line)
        seen_b = set()
        for pat, alt in BRITISH.items():
            for m in re.finditer(pat, line, re.I):
                seen_b.add(m.start())
                # The ClearName e_07_ConstitutionReorganisation is an
                # identifier and keeps its spelling, so only the lowercase
                # prose form is a finding. asd_ste100_fix.py makes exactly
                # the same exception (SPELLING_CASE_SENSITIVE): the gate and
                # the fixer must agree, or a document can never reach zero
                if m.group(0)[:1].isupper() and m.group(0).lower().startswith("reorganis"):
                    continue
                findings["B"].append((i + 1, m.group(0), alt))
        for m, alt in ise_findings(line):
            if m.start() not in seen_b:        # do not report a word twice
                findings["B"].append((i + 1, m.group(0), alt))
        for pat, alt in SWAPS.items():
            for m in re.finditer(pat, line, re.I):
                if m.group(0).isupper():
                    continue          # RFC 2119 keyword (MUST, REQUIRED) — quoted term
                a, b = m.start(), m.end()
                if (a > 0 and line[a-1] == "-") or (b < len(line) and line[b] == "-"):
                    continue          # hyphenated compound: AI-assisted, input-required
                # t_04 section 3: an API name beats the dictionary. If this
                # word is also a code span in this file, the swap would
                # rename something real — as "delete" -> "erase" nearly did
                # to the Expression element's command (elements.py:141)
                if m.group(0).lower() in code_terms:
                    # The word is also a code span in this file, so it names
                    # something real. t_04 section 3: an API name beats the
                    # dictionary. Advisory only — it must not block the gate,
                    # or the document could never reach zero without renaming
                    # a command, as "delete" -> "erase" nearly did
                    findings["I"].append((i + 1, m.group(0),
                                          alt + "   [identifier — verify, do not swap blindly]"))
                    continue
                findings["W"].append((i + 1, m.group(0), alt))
        for pat, alt in LATIN.items():
            for m in re.finditer(pat, line):
                findings["X"].append((i + 1, m.group(0), alt))
        for m in re.finditer(CONTRACTIONS, line, re.I):
            findings["C"].append((i + 1, m.group(0), ""))

    if verbose:
        name = os.path.basename(path)
        gate = [k for k in ("L", "S", "B", "W", "X", "C", "F")]
        counts = " ".join(f"{k}={len(findings[k])}" for k in gate)
        advisory = f"   (I={len(findings['I'])})" if findings["I"] else ""
        print(f"{name:46s} {counts}{advisory}")
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
            if k == "I":
                totals["I"] = totals.get("I", 0) + len(v)
                continue
            totals[k] = totals.get(k, 0) + len(v)
        if detail:
            print(f"\n===== {path}")
            for k, label in [("L", "LONG"), ("S", "SEMICOLON"), ("B", "BRITISH"),
                             ("W", "SWAP"), ("X", "LATIN"), ("C", "CONTRACTION"),
                             ("F", "SHAPE"), ("I", "IDENTIFIER?")]:
                for item in f[k]:
                    print(f"  {label:12s} line {item[0]:4d}  {item[1]}  {item[2] if len(item)>2 else ''}")
    if len(args) > 1:
        gate = [k for k in ("L", "S", "B", "W", "X", "C", "F")]
        print("\nTOTALS:", " ".join(f"{k}={totals.get(k, 0)}" for k in gate))
        if totals.get("I"):
            print(f"        advisory: I={totals['I']} identifier collision(s) "
                  f"— verify by hand, not counted by the gate")
