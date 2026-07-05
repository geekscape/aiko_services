---
title: Text I/O elements
description: PipelineElements that read, transform, sample and write frames
  of text — via files, an interactive terminal or ZeroMQ sockets
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media/text_io.py
  - src/aiko_services/elements/media/pipelines/text_pipeline_0.json
  - src/aiko_services/elements/media/pipelines/text_pipeline_1.json
  - src/aiko_services/elements/media/pipelines/text_pipeline_2.json
  - src/aiko_services/elements/media/pipelines/text_pipeline_3.json
  - src/aiko_services/elements/media/pipelines/text_tty_pipeline_0.json
  - src/aiko_services/elements/media/pipelines/text_zmq_pipeline_0.json
  - src/aiko_services/elements/media/pipelines/text_zmq_pipeline_1.json
related: [pipeline_element, data_source_target, scheme, stream, parameters,
  scheme_file, scheme_tty, scheme_zmq, image_io, video_io]
version: "0.6"
last_updated: 2026-07-06
---

# Text I/O elements

## Overview

The **text I/O elements** are the simplest complete family of media
[PipelineElements](../../concepts/pipeline_element.md) in Aiko Services:
sources that read text (from files, an interactive terminal or a ZeroMQ
socket), transforms that change or sample it, and targets that write it
back out. Because text needs no optional native libraries, this module is
the best starting point for learning the
[DataSource / DataTarget](../../concepts/data_source_target.md) and
[DataScheme](../../concepts/scheme.md) design — the image and video
families ([image_io](image_io.md), [video_io](video_io.md)) follow the
same shape.

The frame data convention is `texts: [str]` — every element consumes
and/or produces a *list* of text strings per frame, so
`data_batch_size > 1` and multi-record ZeroMQ frames "just work".

**Why you'd use it**: transform a directory of text files, changing only
URL parameters to switch between file, terminal and network transports:

```bash
cd src/aiko_services/elements/media

aiko_pipeline create pipelines/text_pipeline_0.json -s 1 \
  -p TextReadFile.data_sources file:data_in/in_00.txt    \
  -p TextTransform.transform titlecase                   \
  -p TextWriteFile.data_targets file:data_out/out_00.txt
```

## For application developers

### Command-line usage

All commands run from `src/aiko_services/elements/media` via the
`aiko_pipeline` CLI. Common options: `-s 1` creates Stream 1, `-sr`
shows the Pipeline response, `-ll debug` raises the log level,
`-gt 10` sets the Stream frame-receive grace time (seconds) and
`-p ELEMENT.name value` sets element parameters (`-sp` is deprecated
in favour of `-p`).

File pipelines (from the `text_io.py` usage header):

```bash
# Files in, titlecase transform, files out (one file per frame)
aiko_pipeline create pipelines/text_pipeline_0.json -s 1 -sr -ll debug

# Pace frame creation at 1 frame per second
aiko_pipeline create pipelines/text_pipeline_0.json -s 1 -p rate 1.0

# Batch 8 files per frame
aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
  -p TextReadFile.data_batch_size 8

# Directory of files matching a "{}" template
aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
  -p TextReadFile.data_sources file:data_in/in_{}.txt

# Explicit single-file in / out with a chosen transform
aiko_pipeline create pipelines/text_pipeline_0.json -s 1 \
  -p TextReadFile.data_sources file:data_in/in_00.txt  \
  -p TextTransform.transform titlecase                   \
  -p TextWriteFile.data_targets file:data_out/out_00.txt
```

Drop-frame tests — `TextSample` locally, then split across two processes
with a remote element (start `text_pipeline_3.json` first; see
[PipelineElement](../../concepts/pipeline_element.md) for remote
deployment):

```bash
aiko_pipeline create pipelines/text_pipeline_1.json -s 1 -ll debug

aiko_pipeline create pipelines/text_pipeline_2.json -s 1 -ll debug  # local
aiko_pipeline create pipelines/text_pipeline_3.json      -ll debug  # remote
```

Interactive terminal REPL-style pipeline (type `/?` for help, `/x` to
exit):

```bash
aiko_pipeline create pipelines/text_tty_pipeline_0.json -s 1
```

ZeroMQ between hosts — run the server (reader) first, then the client
(writer):

```bash
# Server: bind and receive text records, write to a file
aiko_pipeline create pipelines/text_zmq_pipeline_0.json -s 1 -sr  \
           -ll debug -gt 10
aiko_pipeline create pipelines/text_zmq_pipeline_0.json -s 1 -sr  \
           -p TextReadZMQ.data_sources zmq://0.0.0.0:6502

# Client: read files, send text records to the server
aiko_pipeline create pipelines/text_zmq_pipeline_1.json -s 1 -sr  \
           -ll debug                                              \
           -p TextReadFile.rate 2.0                               \
           -p TextWriteZMQ.data_targets zmq://192.168.0.1:6502
```

### Public API

Every class is a PipelineElement; sources extend `aiko.DataSource`,
targets extend `aiko.DataTarget`, transforms extend
`aiko.PipelineElement` directly. Frame data types below use the
PipelineDefinition notation.

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `TextReadFile` | DataSource | `paths: [Path]` → `texts: [str]` | `data_sources` (`file:` URL, required), `data_batch_size` (default 1), `rate` |
| `TextReadTTY` | DataSource | `records: [str]` → `texts: [str]` | `data_sources` (`tty://`), `tty_prompt` (default `"> "`), `rate` (default 20.0) |
| `TextReadZMQ` | DataSource | `records: [bytes]` → `texts: [str]` | `data_sources` (`zmq://host:port_range`), `data_batch_size` |
| `TextSample` | transform | `texts: [str]` → `texts: [str]` | `sample_rate` (default 1): keep frames where `frame_id % sample_rate == 0`, else `DROP_FRAME` |
| `TextTransform` | transform | `texts: [str]` → `texts: [str]` | `transform` (**required**): `lowercase`, `none`, `titlecase`, `uppercase` |
| `TextWriteFile` | DataTarget | `texts: [str]` → (none) | `data_targets` (`file:` URL, required) |
| `TextWriteTTY` | DataTarget | `texts: [str]` → (none) | `data_targets` (`tty://`), `tty_prompt` (default `"> "`) |
| `TextWriteZMQ` | DataTarget | `texts: [str]` → (none) | `data_targets` (`zmq://host:port`) |
| `TextOutput` | pass-through | `texts: [str]` → `texts: [str]` | (none) — placed last so the Pipeline response carries the processed text |

Service protocols: `text_read_file:0`, `text_read_tty:0`,
`text_read_zmq:0`, `text_sample:0`, `text_transform:0`,
`text_write_file:0`, `text_write_tty:0`, `text_write_zmq:0`,
`text_output:0`.

**URL forms** (the first `data_sources` / `data_targets` URL selects the
[DataScheme](../../concepts/scheme.md)):

```
file:data_in/in_00.txt        single file            (scheme_file.md)
file:data_in/in_{}.txt        directory glob template
tty://                        interactive terminal   (scheme_tty.md)
zmq://0.0.0.0:6502            ZeroMQ bind / connect  (scheme_zmq.md)
zmq://*:6502-6510             bind: any port in range (sources only)
```

**Stream lifecycle behaviour:**

- `TextReadFile.process_frame(stream, paths)` reads each `Path` whole —
  one file becomes one string; a read failure returns
  `StreamEvent.ERROR` with a `diagnostic`. End of files stops the Stream
  (`StreamEvent.STOP` from the scheme's frame generator).
- `TextWriteFile.start_stream()` opens `target_path` once when the URL
  is *not* a `{}` template (all frames append to one file, no separators
  added); with a template each text is written to its own formatted
  path (`target_file_id` increments per text). `stop_stream()` closes
  the single file.
- `TextReadTTY.start_stream()` installs a small command interpreter over
  the [tty scheme](scheme_tty.md): `/?` help, `//` escape a leading `/`,
  `/h` list history, `/h N` re-execute line N, `/x` exit (raises
  `SystemExit`). Non-command lines are appended to
  `stream.variables["tty_command_lines"]` and emitted as `texts`.
- `TextWriteTTY.process_frame()` prints each text, then reprints the
  prompt as `NNN:PROMPT` where `NNN` is the history length — it reads
  `stream.variables["tty_command_lines"]`, so it only works downstream
  of `TextReadTTY` in the same Stream.
- `TextReadZMQ` decodes each received `bytes` record with `.decode()`;
  `TextWriteZMQ` sends `text.encode()` — one ZeroMQ message per text
  string, out-of-band from MQTT.

`TextOutput` exists so that `aiko_pipeline ... -sr` (show response) can
display the final `texts` — Pipeline output is taken from the last
element's declared `output`.

## For framework developers (internals)

### Design

```
 TextReadFile   TextReadTTY   TextReadZMQ        DataSources
      │file:        │tty://       │zmq://    (scheme via first URL)
      └─────────────┴─────┬───────┘
                          ▼
              texts: [str]  (frame data)
                          │
        TextTransform / TextSample                transforms
                          │
      ┌─────────────┬─────┴───────┐
 TextWriteFile  TextWriteTTY  TextWriteZMQ        DataTargets
      │file:        │tty://       │zmq://
                          │
                     TextOutput                   response tail
```

- The module is the *reference implementation* of the
  [DataSource / DataTarget](../../concepts/data_source_target.md)
  Template Method: sources implement only `process_frame()` (decode) and
  targets only `process_frame()` plus optional `start_stream()` /
  `stop_stream()` overrides that call `super()` first.
- Per-Stream state (`target_file`, `tty_command_lines`,
  `target_zmq_socket`) always lives in `stream.variables`, never on
  `self` — the scheme prepared it there in `start_stream()`.
- `text_pipeline_2.json` / `text_pipeline_3.json` demonstrate that a
  text element (`TextSample`) is remotable unchanged: `p_text_2`
  declares `deploy.remote` with a `service_filter` naming `p_text_3`.

### Implementation notes

- `TextTransform` treats `transform: none` as an identity optimisation
  (no per-string calls). An unknown transform or a missing `transform`
  parameter is a Stream `ERROR`, not a silent pass-through.
- `TextReadTTY._parse_command_line()` implements the `//` escape as
  `text[3:]` — it assumes the form `"// rest"` (three characters before
  the payload). A `process_frame()` TODO notes that a consumed command
  (returning `None`) should probably `DROP_FRAME` instead of emitting an
  empty `texts` list.
- `TextWriteFile` in non-template mode writes `f"{text}"` with **no**
  record separator; streaming/CR-LF record options are on the To Do
  list.
- `TextReadTTY` and `TextWriteTTY` are **not** listed in the module
  `__all__` nor imported by
  `src/aiko_services/elements/media/__init__.py` — they are only
  reachable via the PipelineDefinition `deploy.local.module` loader
  (as `text_tty_pipeline_0.json` does).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `TextReadFile` | Read whole text files given `paths`; emit `texts` | [DataSource](../../concepts/data_source_target.md), [DataSchemeFile](scheme_file.md), [Stream](../../concepts/stream.md), [Parameters](../../concepts/parameters.md) |
| `TextReadTTY` | Command interpreter over terminal input; history in `stream.variables`; emit `texts` | [DataSource](../../concepts/data_source_target.md), [DataSchemeTTY](scheme_tty.md), [Stream](../../concepts/stream.md) |
| `TextReadZMQ` | Decode received ZeroMQ `records` into `texts` | [DataSource](../../concepts/data_source_target.md), [DataSchemeZMQ](scheme_zmq.md) |
| `TextSample` | Keep every Nth frame (`sample_rate`), else `DROP_FRAME` | [PipelineElement](../../concepts/pipeline_element.md), [Stream](../../concepts/stream.md) |
| `TextTransform` | Apply case transform selected by `transform` parameter | [PipelineElement](../../concepts/pipeline_element.md), [Parameters](../../concepts/parameters.md) |
| `TextWriteFile` | Write texts to one file or per-text template paths; manage file handle over the Stream lifecycle | [DataTarget](../../concepts/data_source_target.md), [DataSchemeFile](scheme_file.md) |
| `TextWriteTTY` | Print texts and re-issue the numbered prompt | [DataTarget](../../concepts/data_source_target.md), [DataSchemeTTY](scheme_tty.md), `TextReadTTY` (shared `tty_command_lines`) |
| `TextWriteZMQ` | Send each text as a ZeroMQ message via `stream.variables["target_zmq_socket"]` | [DataTarget](../../concepts/data_source_target.md), [DataSchemeZMQ](scheme_zmq.md) |
| `TextOutput` | Pass `texts` through as the Pipeline response tail | [PipelineElement](../../concepts/pipeline_element.md) |

## Current limitations and roadmap

From the source To Do list — all **planned**, not implemented:

- ZeroMQ as a full remote-PipelineElement transport: send `content`
  out-of-band via ZeroMQ, compared with the default in-band MQTT remote
- Media-type encoding for text records, e.g. `text:length:content` or
  `text/zip:length:content` (commented stubs exist in `TextReadZMQ` /
  `TextWriteZMQ`)
- `TextReadFile(s)` / `TextWriteFile(s)`: per-line records (streaming);
  CR/LF, JSON, XML, CSV formats
- `TextFilter` (line/word/character counts) and richer `TextTransform`
  operations (`strip()`, …)
- `TextSample` by text count within `texts`, rather than by frame
- Speech pre/post-processing (abbreviations, acronyms, pronunciation)
  and text framing for LLMs
- `TextReadTTY`: `tty_history` size limit and prompt templates are
  declared in `text_tty_pipeline_0.json` but not yet implemented (see
  [scheme_tty](scheme_tty.md))

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  every class here implements
- [DataSource / DataTarget](../../concepts/data_source_target.md) — base
  classes for the read/write elements
- [DataScheme](../../concepts/scheme.md) — URL-scheme plug-ins; see
  [scheme_file](scheme_file.md), [scheme_tty](scheme_tty.md),
  [scheme_zmq](scheme_zmq.md)
- [Stream](../../concepts/stream.md) — lifecycle and `stream.variables`
- [Parameters](../../concepts/parameters.md) — how `-p` values reach
  elements
- [image_io](image_io.md), [video_io](video_io.md) — the same design for
  images and video
