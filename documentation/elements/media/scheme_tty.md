---
title: DataSchemeTTY
description: The tty DataScheme — line-oriented interactive terminal input
  and output for Pipelines, one record per line with a configurable prompt
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media/scheme_tty.py
related: [scheme, data_source_target, pipeline_element, stream, parameters,
  text_io, scheme_file, scheme_zmq]
version: "0.6"
last_updated: 2026-07-06
---

# DataSchemeTTY

## Overview

**`DataSchemeTTY`** implements the `tty` URL scheme of the
[DataScheme](../../concepts/scheme.md) plug-in design: it turns the
interactive terminal into a
[DataSource](../../concepts/data_source_target.md) (each line typed
becomes a record) and, nominally, a DataTarget (elements print
directly). It is what makes a REPL-style Pipeline possible — the
`TextReadTTY` / `TextWriteTTY` elements in [text_io](text_io.md) build
a small command interpreter (help, history, exit) on top of it.

**Why you'd use it**: interactively drive any text-processing Pipeline
from the keyboard — the same graph that reads files reads your typing
when the URL changes to `tty://`:

```bash
cd src/aiko_services/elements/media
aiko_pipeline create pipelines/text_tty_pipeline_0.json -s 1
# 000:# hello world          <- you type
# Hello World                <- titlecased by TextTransform
```

## For application developers

### Command-line usage

`DataSchemeTTY` has no CLI of its own — it is selected by `tty://` in
`data_sources` / `data_targets`. The committed exemplar:

```bash
cd src/aiko_services/elements/media
aiko_pipeline create pipelines/text_tty_pipeline_0.json -s 1
```

`text_tty_pipeline_0.json` wires
`TextReadTTY → TextTransform → TextWriteTTY → TextOutput` with
`data_sources: (tty://)`, `data_targets: (tty://)` and
`tty_prompt: "# "`. In the running pipeline, type `/?` for help and
`/x` to exit (commands are `TextReadTTY` behaviour — see
[text_io](text_io.md)).

### Public API

URL forms (from the source header) — each list should contain a single
entry:

```
data_sources: "(tty://)"
data_targets: "(tty://)"
```

Parameters read by the scheme (via the owning element — see
[Parameters](../../concepts/parameters.md)):

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `rate` | 20.0 | Polls per second of the input queue (frame-generator pacing) |
| `tty_prompt` | `"> "` | Prompt printed before the first input line |

Source behaviour (`create_sources()`):

- Starts a daemon thread that loops on blocking `input()`, pushing each
  line into an internal queue; end-of-input (Ctrl-D / `EOFError`)
  pushes a `None` sentinel.
- The frame generator polls the queue at `rate` Hz: a queued line
  yields `{"records": [line]}` — **one line per frame**, delivered to
  the owning element's `process_frame(stream, records)`; an empty queue
  returns `StreamEvent.NO_FRAME`; the `None` sentinel returns
  `StreamEvent.STOP` (`"All frames generated"`), ending the Stream —
  with `_destroy_stream_exit_` set (as in `text_tty_pipeline_0.json`),
  Ctrl-D exits the Pipeline cleanly.
- The prompt is printed once, prefixed `000:` (the line-number style
  that `TextWriteTTY` then maintains).

Target behaviour: `create_targets()` is a no-op — output elements
simply `print()`; there are no `target_*` stream variables for this
scheme.

Registration (module import side-effect):

```python
aiko.DataScheme.add_data_scheme("tty", DataSchemeTTY)
```

## For framework developers (internals)

### Design

```
 keyboard ──► input() loop          daemon thread (blocking reads)
                  │ queue.put(line)         EOF ─► put(None)
                  ▼
            queue.Queue ◄── frame_generator polls at rate Hz
                  │
      line ─► {"records": [line]}     empty ─► NO_FRAME
      None ─► STOP "All frames generated"
```

- **Thread-decoupled blocking input.** `input()` must block, and frame
  generators must not — so the scheme owns a reader thread plus a
  queue, and the generator only ever polls. The same
  thread-plus-queue shape appears in [scheme_zmq](scheme_zmq.md).
- Scheme state (`queue`, `terminate`) lives on `self` rather than in
  `stream.variables` — acceptable here because one DataScheme instance
  exists per [Stream](../../concepts/stream.md), and a process has only
  one terminal anyway.

### Implementation notes

- `destroy_sources()` sets `self.terminate`, but the reader thread is
  usually blocked inside `input()` and only observes the flag after one
  more line (or EOF); being a daemon thread, it cannot prevent process
  exit.
- The initial prompt hard-codes the `000:` history-count prefix,
  duplicating `TextWriteTTY`'s prompt format — change both together.
- A commented-out `non_blocking_keyboard_input()` sketch (raw-mode
  `termios` / one-character reads) is kept at the bottom of the file as
  the starting point for the planned character-per-record mode.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeTTY` | Run the blocking-`input()` reader thread and queue; generate one `records` frame per typed line at `rate` Hz; `STOP` on EOF; print the initial prompt | [DataScheme](../../concepts/scheme.md) (base, registry), [DataSource / DataTarget](../../concepts/data_source_target.md) (owners), [PipelineElement](../../concepts/pipeline_element.md) (`create_frames()`, `get_parameter()`), [Stream](../../concepts/stream.md), `TextReadTTY` / `TextWriteTTY` ([text_io](text_io.md)) |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Character-per-record option, e.g. `tty://mode=raw` (see the
  commented-out raw-mode sketch)
- `TextReadTTY` parameter `tty_history: N` — maximum command lines
  kept, `N=0` (default) meaning no history. Note
  `text_tty_pipeline_0.json` already declares `tty_history: 16`, which
  is currently ignored.
- Prompt `{}` template that inserts the current history length,
  replacing the hard-coded `000:` prefix

Also note: output via this scheme is plain `print()` — interleaving
with log output on the same terminal is unmanaged, so run TTY
pipelines with MQTT logging (the default) rather than console logging.

## Related concepts

- [DataScheme](../../concepts/scheme.md) — the plug-in base class and
  registry
- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  elements that instantiate this scheme per Stream
- [PipelineElement](../../concepts/pipeline_element.md) —
  `create_frames()` pacing
- [Stream](../../concepts/stream.md) — lifecycle; EOF maps to a
  graceful `STOP`
- [Parameters](../../concepts/parameters.md) — `rate`, `tty_prompt`
- [text_io](text_io.md) — `TextReadTTY` / `TextWriteTTY`, the command
  interpreter built on this scheme
- [scheme_file](scheme_file.md), [scheme_zmq](scheme_zmq.md) — sibling
  schemes
