#!/usr/bin/env python3
"""Split prose semicolons into sentences, protecting code and identifiers.

Reports every capitalization it made, so identifiers wrongly capitalized
(xgo -> Xgo) can be reviewed by hand.
"""
import re
import sys

# words that must never be capitalized by the split (identifiers / API names)
LOWER = {"xgo", "aiko", "mqtt", "ec", "zmq", "pytest", "hatch", "avro", "json",
         "eval", "exec", "pickle", "async", "await", "stdout", "stderr", "git",
         "psutil", "sqlite", "grep", "sed", "cli", "repl", "llm", "mcp", "otlp"}


def process(path, write=False):
    lines = open(path).read().split("\n")
    out, in_code, caps, changed = [], False, [], 0
    for line in lines:
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code or ";" not in line:
            out.append(line)
            continue
        parts = re.split(r"(`[^`]*`)", line)
        new = []
        for i, pt in enumerate(parts):
            if i % 2 == 1:
                new.append(pt)
                continue
            pt = re.sub(r";\s+", ". ", pt)
            new.append(pt)
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
    print(f"{path}: {changed} lines changed, {len(caps)} capitalizations")
    for w, ctx in caps[:40]:
        print(f"    {w:16s} | {ctx}")
    return changed


if __name__ == "__main__":
    write = "--write" in sys.argv
    for p in [a for a in sys.argv[1:] if not a.startswith("--")]:
        process(p, write)
