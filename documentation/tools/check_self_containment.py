#!/usr/bin/env python3
"""Aiko Services Nomic(Law): public self-containment checker.

The public constitution must be self-contained: no document in the public
set may reference material classified as private/future. This is stage-1
(schema validation) material for the documentary gate, and a required CI
check from the first public push.

Usage:
  check_self_containment.py --future-stems FUTURE.txt PATH [PATH ...]

FUTURE.txt lists one private stem per line (blank lines and '#' comments
ignored). A "stem" is a ClearName or path fragment that identifies private
material, e.g.:
    e_08_SelfDirectedAgency
    a_03_LinuxFoundationRoadmap
    potential/08_capability_security
Each given PATH (file or directory, .md/.txt files scanned recursively) is
searched for any stem as a substring. Matches are violations.

A line may declare a sanctioned exception with the marker
    <!-- future-ref-ok: REASON -->
on the same line as the reference; such lines are reported as exceptions,
not violations (the drift audit reviews them).

Exit status: 0 = clean, 1 = violations found, 2 = usage error.
Standard library only (P9).
"""

import argparse
import pathlib
import sys

SCAN_SUFFIXES = {".md", ".txt", ".yml", ".yaml", ".json"}
EXCEPTION_MARKER = "future-ref-ok:"


def load_stems(path):
    stems = []
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            stems.append(line)
    return stems


def iter_files(paths):
    for raw in paths:
        p = pathlib.Path(raw)
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix in SCAN_SUFFIXES:
                    yield child
        elif p.is_file():
            yield p
        else:
            print(f"warning: no such path: {p}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--future-stems", required=True,
                        help="file listing private stems, one per line")
    parser.add_argument("paths", nargs="+",
                        help="public files/directories to scan")
    args = parser.parse_args()

    stems = load_stems(args.future_stems)
    if not stems:
        print("warning: empty stem list — nothing to check", file=sys.stderr)
        return 0

    violations, exceptions = [], []
    for file in iter_files(args.paths):
        try:
            lines = file.read_text(errors="replace").splitlines()
        except OSError as error:
            print(f"warning: cannot read {file}: {error}", file=sys.stderr)
            continue
        for number, line in enumerate(lines, 1):
            for stem in stems:
                if stem in line:
                    record = (file, number, stem, line.strip())
                    if EXCEPTION_MARKER in line:
                        exceptions.append(record)
                    else:
                        violations.append(record)

    for file, number, stem, text in violations:
        print(f"VIOLATION {file}:{number} references private stem"
              f" '{stem}':\n    {text[:120]}")
    for file, number, stem, _text in exceptions:
        print(f"exception {file}:{number} sanctioned reference to '{stem}'")

    print(f"\nself-containment: {len(violations)} violation(s),"
          f" {len(exceptions)} sanctioned exception(s),"
          f" {len(stems)} private stems checked")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
