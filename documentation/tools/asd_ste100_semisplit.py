#!/usr/bin/env python3
"""Split prose semicolons into sentences, protecting code and identifiers.

Reports every capitalization it made, so identifiers wrongly capitalized
(xgo -> Xgo) can be reviewed by hand.

Regions this tool must never touch, each learned from a defect:
  - YAML front matter. A `description:` field feeds the one-line summary in
    every `ReadMe.md` index, so a split there silently desynchronizes the
    index from the document.
  - Table rows. `asd_ste100_lint.py` does not inspect a table, so a rewrite
    there is invisible to the gate, and the converted trees deliberately
    keep their table-cell semicolons.
  - A clause inside parentheses. "(clause; clause)" would become
    "(clause. Clause)", which reads as a fragment and which a
    sentence-start scan cannot see.
  - Fenced code, and inline code spans.
"""
import re
import sys

# words that must never be capitalized by the split (identifiers / API names)
LOWER = {"xgo", "aiko", "mqtt", "ec", "zmq", "pytest", "hatch", "avro", "json",
         "eval", "exec", "pickle", "async", "await", "stdout", "stderr", "git",
         "psutil", "sqlite", "grep", "sed", "cli", "repl", "llm", "mcp", "otlp",
         "dora", "ros", "zenoh", "numpy", "opencv", "gst", "arxiv", "pip"}


def split_outside_parens(text):
    """Replace "; " with ". " only where the semicolon is not inside ()."""
    out = []
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            m = re.match(r";\s+", text[i:])
            if m:
                out.append(". ")
                i += m.end()
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def process(path, write=False):
    lines = open(path).read().split("\n")
    out, in_code, caps, changed, skipped = [], False, [], 0, 0
    in_fm = False
    for n, line in enumerate(lines):
        s = line.strip()
        # YAML front matter: never touched (a description: feeds index rows)
        if n == 0 and s == "---":
            in_fm = True
            out.append(line)
            continue
        if in_fm:
            if s == "---":
                in_fm = False
            if ";" in line:
                skipped += 1
            out.append(line)
            continue
        if s.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code or ";" not in line:
            out.append(line)
            continue
        # a table row is out of this tool's scope (the gate cannot see it)
        if s.startswith("|"):
            skipped += 1
            out.append(line)
            continue
        parts = re.split(r"(`[^`]*`)", line)
        new = []
        for i, pt in enumerate(parts):
            if i % 2 == 1:
                new.append(pt)
                continue
            new.append(split_outside_parens(pt))
        nl = "".join(new)

        def cap(m):
            w = m.group(1)
            if re.match(r"^[easgtp]_\d", w) or "_" in w or w.lower() in LOWER or w.islower() is False:
                return m.group(0)
            caps.append((w, line.strip()[:60]))
            return ". " + w[0].upper() + w[1:]

        nl = re.sub(r"(?<=[a-z),\]`*])\. ([a-z]\w*)", cap, nl)
        if nl != line:
            changed += 1
        out.append(nl)
    if write and changed:
        open(path, "w").write("\n".join(out))
    note = f", {skipped} protected lines left alone" if skipped else ""
    print(f"{path}: {changed} lines changed, {len(caps)} capitalizations{note}")
    for w, ctx in caps[:40]:
        print(f"    {w:16s} | {ctx}")
    return changed


if __name__ == "__main__":
    write = "--write" in sys.argv
    for p in [a for a in sys.argv[1:] if not a.startswith("--")]:
        process(p, write)
