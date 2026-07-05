---
title: DataSchemeFile
description: The file DataScheme — resolves file URLs, directory globs
  and path templates into per-Stream frame generation and target paths
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media/scheme_file.py
related: [scheme, data_source_target, pipeline_element, stream, parameters,
  text_io, image_io, video_io, scheme_tty, scheme_zmq]
version: "0.6"
last_updated: 2026-07-06
---

# DataSchemeFile

## Overview

**`DataSchemeFile`** implements the `file` URL scheme of the
[DataScheme](../../concepts/scheme.md) plug-in design — it is the
default scheme (a URL with no `scheme:` prefix is treated as `file`)
and the workhorse behind every file-based
[DataSource / DataTarget](../../concepts/data_source_target.md) element:
`TextReadFile` / `TextWriteFile` ([text_io](text_io.md)),
`ImageReadFile` / `ImageWriteFile` ([image_io](image_io.md)),
`VideoReadFile` / `VideoWriteFile` ([video_io](video_io.md)) and the
`AudioReadFile` scaffold ([audio_io](audio_io.md)).

It resolves `data_sources` URLs into an ordered list of `Path`s
(single files, whole directories, or `{}` glob templates), chooses
between one-shot `create_frame()` and a paced frame-generator thread,
batches paths per frame, and prepares template state for
`data_targets`.

**Why you'd use it**: you don't invoke it directly — you select it with
a URL:

```bash
aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
  -p TextReadFile.data_sources file:data_in/in_{}.txt     \
  -p TextWriteFile.data_targets file:data_out/out_{:02d}.txt
```

## For application developers

### Command-line usage

`DataSchemeFile` has no CLI of its own — it is exercised through
`aiko_pipeline` `-p` parameters on any file-based element (worked
sessions in [text_io](text_io.md), [image_io](image_io.md) and
[video_io](video_io.md)):

```bash
cd src/aiko_services/elements/media

# Directory glob template: one file per frame, sorted order
aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
  -p TextReadFile.data_sources file:data_in/in_{}.txt

# Batch 8 matched files per frame
aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
  -p TextReadFile.data_batch_size 8

# Pace frame generation at 1 frame per second
aiko_pipeline create pipelines/text_pipeline_0.json -s 1 -p rate 1.0
```

### Public API

URL grammar accepted in `data_sources` (from the source header):

```
(file:pathname_0 file:pathname_1 ...)   explicit file list
(file:data_in/in_{}.txt)                directory + filename template
(file:data_in/in_{}.jpeg)
(file:data_in/in_{}.mp4)
```

and in `data_targets`:

```
(file:pathname_0 file:pathname_1 ...)
(file:data_out/out_{}.txt)              per-frame-data template
(file:data_out/out_{:02d}.jpeg)         Python format specs allowed
```

Source-side semantics:

- A path that **is a file** contributes itself.
- A path (after stripping a `{}` template basename) that **is a
  directory** contributes every file matching the template's glob
  (`in_{}.txt` → `in_*.txt`), in sorted order; each match gets a
  `file_id` — the text the `*` matched (e.g. `00` from `in_00.txt`).
- A non-existent path, or one that is neither file nor directory,
  returns `StreamEvent.ERROR` from `start_stream()` with a
  `diagnostic`.
- Exactly **one** resulting path with `use_create_frame=True` (the
  element's choice) → a single thread-less
  `create_frame(stream, {"paths": [path]})`. Otherwise the paths are
  parked in `stream.variables["source_paths_generator"]` and a frame
  generator runs on a thread, paced by the element's `rate` parameter
  (default `None` = as fast as downstream allows).

Frame data delivered to the owning element's `process_frame()`:
`{"paths": [Path, ...]}` with up to `data_batch_size` (default 1)
paths per frame; when the paths are exhausted the generator returns
`StreamEvent.STOP` (`"All frames generated"`), ending the Stream
gracefully.

Target-side semantics — `create_targets()` stores per-Stream variables
that DataTarget elements use in `process_frame()`:

| Stream variable | Meaning |
|-----------------|---------|
| `target_path` | Path (or template) from the first `data_targets` URL |
| `target_path_template` | `True` when the path contains `{}` |
| `target_file_id` | Counter (starts 0) the element formats into the template and increments per written item |

Registration (module import side-effect):

```python
aiko.DataScheme.add_data_scheme("file", DataSchemeFile)
```

## For framework developers (internals)

### Design

```
create_sources(stream, data_sources)
  │  for each URL: parse_url_path()
  │    "in_{}.txt" ─► glob "in_*.txt" over the directory
  │    file ─► [(path, None)]   dir ─► [(path, file_id), …] sorted
  ▼
  1 path & use_create_frame ──► create_frame({"paths": [path]})
  else ──► stream.variables["source_paths_generator"] = iter(paths)
           create_frames(frame_generator, rate)
                 │ each call: pull ≤ data_batch_size paths
                 ▼
           {"paths": [...]} ── STOP when exhausted
```

- **The canonical scheme.** `DataSchemeFile` is the exemplar cited by
  the [DataScheme](../../concepts/scheme.md) concept for the
  frame-creation policy: the *scheme* (not the element) decides between
  `create_frame()` and `create_frames()`.
- **`file_id` recovery.** `_file_glob_difference(file_glob, filename)`
  extracts the substring the `*` matched by stripping the glob's
  prefix/suffix — this is what lets a target template number its
  outputs to correspond with source files.
- All mutable state (`source_paths_generator`, `target_*`) is stored in
  `stream.variables`, honouring the one-scheme-instance-per-
  [Stream](../../concepts/stream.md) rule.

### Implementation notes

- Single-file sources record `(path, None)` — the `None` should
  probably be a `file_id` (the module's only To Do).
- In `create_sources()` the directory branch reuses the name `path` as
  its loop variable, and the later single-path
  `create_frame(stream, {"paths": [path]})` call relies on that
  variable holding the intended path — correct for the common cases,
  but fragile; prefer `paths[0][0]` if refactoring.
- `create_targets()` only inspects `data_targets[0]` — additional
  target URLs are ignored (consistent with the first-URL-selects-scheme
  rule described in
  [DataSource / DataTarget](../../concepts/data_source_target.md)).
- `frame_generator()` re-reads `data_batch_size` every call, so it can
  be changed per-Stream via
  [Parameters](../../concepts/parameters.md); a partially filled final
  batch is still delivered before `STOP`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeFile` | Resolve `file:` URLs — single file, directory, `{}` glob template — into ordered `(path, file_id)` pairs; choose `create_frame()` vs paced `create_frames()`; batch paths per frame via `data_batch_size`; prepare `target_path` / `target_path_template` / `target_file_id` for DataTargets | [DataScheme](../../concepts/scheme.md) (base, registry), [DataSource / DataTarget](../../concepts/data_source_target.md) (owners), [PipelineElement](../../concepts/pipeline_element.md) (`create_frame(s)()`, `get_parameter()`), [Stream](../../concepts/stream.md) (per-Stream variables) |

## Current limitations and roadmap

- Source To Do: fix `paths.append((path, None))` — the `None` should be
  a `file_id`, so single-file sources behave like glob matches.
- Inherited from the [DataScheme](../../concepts/scheme.md) roadmap:
  replace hand-rolled URL parsing with `urllib.parse.urlparse()`;
  `parse_url_path()` currently returns authority and path combined.
- Archive sources (`tgz`, `zip`) with filename filters are To Dos on
  each consuming element ([text_io](text_io.md),
  [image_io](image_io.md), [video_io](video_io.md)) and would land
  here.
- No recursive directory traversal — a directory's files only, one
  level.

## Related concepts

- [DataScheme](../../concepts/scheme.md) — the plug-in base class and
  registry
- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  elements that instantiate this scheme per Stream
- [PipelineElement](../../concepts/pipeline_element.md) —
  `create_frame()` / `create_frames()` invoked by the scheme
- [Stream](../../concepts/stream.md) — scope of all scheme state
- [Parameters](../../concepts/parameters.md) — `data_sources`,
  `data_targets`, `data_batch_size`, `rate`
- [scheme_tty](scheme_tty.md), [scheme_zmq](scheme_zmq.md) — sibling
  schemes for terminals and sockets
- [text_io](text_io.md), [image_io](image_io.md),
  [video_io](video_io.md) — the element families built on this scheme
