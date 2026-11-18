---
title: "ADR-029 — Path handling: pathlib is the standard"
description: Proposes pathlib.Path as the standard mechanism for filesystem
  paths in Aiko Services and records the operational rules and permitted
  exceptions.
type: adr
audience: [project-lead, architects, developers, ai-coding-agents]
status: proposal
ste: adapted
related: [ReadMe, ../p_00_DesignPrinciples]
last_updated: 2026-11-13
---

# ADR-029 — Path handling: `pathlib` is the standard

**Proposed 2026-11-12** by Nicolas Simonds. The number is claimed in this move. This standard
applies to `src/aiko_services/`, including its tests, and to `documentation/tools/`. It does
not apply to examples or to the archive directory (`src/aiko_services/archive/`).

## Context

Aiko Services has no defined standard for handling filesystem paths. The source freely uses
`os.path` and `pathlib` in an ad-hoc manner, often mixing their use in the same module. This causes
unnecessary friction when dealing with pathnames. It is far simpler to use `pathlib` objects
internally and serialize them as strings for information interchange. P10 asks for the smallest
design that composes. One path mechanism is smaller than three. The tests already supply `Path`
objects to the source, so a `str` round-trip in the source is visible there.

## Decision

A filesystem path is a `pathlib.Path`.

Build a path with `/`. Read it with `.name`, `.parent`, `.suffix`, `.exists()`, `.is_file()`,
`.is_dir()`, `.is_symlink()`, `.resolve()`, `.stat()` and `.expanduser()`. Create it with
`.mkdir(parents=True, exist_ok=True)`. Change it with `.unlink()`, `.rmdir()`, `.rename()`,
`.replace()`, `.symlink_to()` and `.chmod()`. Enumerate with `.iterdir()` for a plain
listing. Select with `.glob()` or `.rglob()` by pattern. Open with builtin `open()` given a
`Path`. Use `.read_text()`, `.write_text()`, `.read_bytes()` and `.write_bytes()` for
whole-file input and output. Take the working directory as `Path.cwd()`.

Use `os.path.relpath` where a relative path must contain `..`, because `pathlib` has no
equivalent below Python 3.12: plain `Path.relative_to()` cannot produce `..`, and
`Path.relative_to(walk_up=True)` starts in Python 3.12. The supported floor is Python 3.9.
Wrap each call in a helper that accepts a `Path` for each argument, coerces each with `str()`,
and returns a `Path`. Give the helper a one-line reason.

Do not use any other `os.path` operation on a path.

Pass a `Path` as a `Path`. Convert to `str` only at an external boundary: a serialized value, a
protocol path, a log or display message, or a function that accepts only a string. Make a `Path`
with `Path(value)` where outside text becomes a path.

Use `Path.is_relative_to()` for a containment check, not `os.path.commonpath()`. Resolve both
operands first when either path came from outside, because the check is lexical and does not
follow symbolic links.

Test for a symbolic link with `path.exists() or path.is_symlink()`, not with
`os.path.lexists()`. Use `Path.iterdir()`, not `os.scandir()`. For a scan that must not follow
symbolic links, pair `.is_file()` with `.is_symlink()` and read metadata with `.lstat()`.
Filter on `.name.startswith(".")` when a listing must exclude hidden entries, because
`Path.glob()` matches dotfiles. Keep `dir_base_name()` hand-written because it parses protocol
paths, which are always "/"-separated.

`Path(os.devnull)` is permitted. This standard does not cover file-descriptor work (`os.open`,
`os.read`, `os.write`, `os.close` and `os.fdopen`) or the `os` services that are not paths
(`os.environ`, `os.pathsep` and `os.urandom`).

## Consequences

- One mechanism replaces three. A reviewer checks one pattern.
- Path separators follow the host. A hand parse of "/" no longer decides behavior.
- `Path` objects cross function boundaries without a `str` round-trip. A conversion appears only
  at an external boundary, where review can see it.
- The test fixtures broker exclusively in `Path` objects, so we can inject "native" values into
  tests, which should improve the fidelity and trustworthiness of results.

## Evidence trail

- P10 (elegance is a requirement): one mechanism replaces three.
