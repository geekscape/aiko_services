---
title: Audio I/O elements
description: PipelineElements for audio frames — a pass-through AudioOutput,
  a scaffold AudioReadFile DataSource, and a disabled legacy microphone /
  FFT / speaker element suite awaiting refactoring
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media/audio_io.py
related: [pipeline_element, data_source_target, scheme, stream, parameters,
  scheme_file, video_io, text_io]
version: "0.6"
last_updated: 2026-07-06
---

# Audio I/O elements

## Overview

The **audio I/O elements** are the audio counterpart of
[text_io](text_io.md), [image_io](image_io.md) and
[video_io](video_io.md) — but unlike those families, this module is
largely **work-in-progress scaffolding**. What exists today:

- `AudioOutput` — a working pass-through
  [PipelineElement](../../concepts/pipeline_element.md) for placing at
  the tail of a Pipeline so the response carries the processed audio.
- `AudioReadFile` — a
  [DataSource](../../concepts/data_source_target.md) *scaffold*, cloned
  from `VideoReadFile` ([video_io](video_io.md)) and not yet converted
  to real audio decoding (it still opens files with
  `open_video_capture()` and its iterator body is commented out).
- A large **disabled** (string-quoted) legacy suite — `PE_AudioFilter`,
  `PE_AudioResampler`, `PE_FFT`, `PE_GraphXY`, `PE_MicrophonePA`,
  `PE_MicrophoneSD`, `PE_Speaker` — a microphone → FFT → spectrum-graph
  / speaker chain from an earlier framework generation, kept as
  reference for the planned Speech-To-Text / Text-To-Speech refactor.

**Why you'd (eventually) use it**: the intended shape mirrors the other
media families — `data_sources file:...mp3` in, transforms, and
`data_targets` out:

```bash
# Intended usage from the source header (audio_pipeline_0.json is not
# yet committed — see Current limitations and roadmap)
aiko_pipeline create pipelines/audio_pipeline_0.json -s 1 -sr -ll debug
```

## For application developers

### Command-line usage

Installation prerequisites (Ubuntu), from the source header:

```bash
sudo apt-get install portaudio19-dev  # Provides "portaudio.h"
pip install pyaudio sounddevice
```

The usage header documents the intended CLI — **all of these are
planned, not currently runnable**, because
`pipelines/audio_pipeline_0.json` is not among the committed
PipelineDefinitions:

```bash
aiko_pipeline create pipelines/audio_pipeline_0.json -s 1 -sr -ll debug

aiko_pipeline create pipelines/audio_pipeline_0.json -s 1  \
  -p AudioReadFile.data_batch_size 8

aiko_pipeline create pipelines/audio_pipeline_0.json -s 1  \
  -p AudioReadFile.data_sources file:data_in/in_{}.mp3

aiko_pipeline create pipelines/audio_pipeline_0.json -s 1  \
  -p AudioWriteFile.path "file:data_out/out_{:02d}.mp3"
```

(The header also references an `AudioResample` element and an
`AudioWriteFile` element — neither exists yet; `AudioWriteFile` appears
commented out in the module `__all__`.)

The disabled legacy suite documents its own usage:

```bash
aiko_pipeline create ../../examples/pipeline/pipeline_mic_fft_graph.json
# On "Spectrum" window, press "x" to exit
```

### Public API

Implemented classes:

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `AudioOutput` | pass-through | `audio_samples` → `audio_samples` | (none) |
| `AudioReadFile` | DataSource (scaffold) | `images` → `images` *(sic — still video-shaped)* | `data_sources` (`file:` URL, required), `rate` |

Service protocols: `audio_output:0`, `audio_read_file:0`.

`AudioReadFile`'s documented intent: individual audio files, a
directory of audio files with an optional filename filter, and
(TODO) archives — with `data_sources` as the read path and an
`audio_id` format variable, mirroring `TextReadFile` /
`ImageReadFile` / `VideoReadFile`. Its **current** behaviour does not
match that intent (see Implementation notes) — treat this element as
not yet usable.

Disabled legacy classes (inside the module's quoted block; **not
importable**): `PE_AudioFilter` (amplitude/frequency band-pass on FFT
output), `PE_AudioResampler` (consolidate spectrum into 8 bands and
publish LED drawing commands over MQTT), `PE_FFT` (NumPy FFT →
`amplitudes` / `frequencies`), `PE_GraphXY` (pygal spectrum plot via
OpenCV window), `PE_MicrophonePA` (PyAudio capture),
`PE_MicrophoneSD` (sounddevice capture with a remotely callable
`mute(duration)`), `PE_Speaker` (sounddevice playback that mutes the
discovered microphone while speaking).

## For framework developers (internals)

### Design

```
 Implemented                     Disabled legacy suite (quoted out)
 ───────────                     ─────────────────────────────────
 AudioReadFile (scaffold,        PE_MicrophonePA / PE_MicrophoneSD
   cloned from VideoReadFile)         │ create_frame() from a
      │                               │ daemon capture thread
      ▼                               ▼
 AudioOutput (pass-through)      PE_FFT ─► PE_AudioFilter
                                     │         │
                                     ▼         ▼
                                 PE_GraphXY  PE_AudioResampler
                                 (spectrum)  (LED bands via MQTT)
                                 PE_Speaker (playback + mic mute)
```

- The module reserves the file-family slot for audio; the real design
  decision — which decode library replaces the `open_video_capture()`
  placeholder, and whether formats are `.mp3` / `.ogg` / `.wav` — is
  still open (module To Do).
- The legacy microphone elements predate the
  [Stream](../../concepts/stream.md)-centric DataSource design: they
  open hardware in `__init__()`, spawn their own daemon threads and
  push frames with `create_frame()` — exactly what
  `start_stream()` / frame generators now standardise. They are kept
  as the source material for the planned Speech-To-Text /
  Text-To-Speech refactor.

### Implementation notes

Sharp edges in the *implemented* code (all consequences of the
unfinished clone from `VideoReadFile`):

- `AudioReadFile.frame_generator()` returns
  `{"images": [image_rgb]}` and `process_frame(self, stream, images)`
  passes `images` through — the frame data is still named for video.
- `audio_frame_iterator()` has its body commented out and executes a
  bare `yield` in an infinite loop — every "audio sample" is `None`.
- `start_stream()` does **not** initialise
  `stream.variables["audio_capture"]` (the line is commented out), so
  `stop_stream()` raises `KeyError` if the Stream stops before a file
  was opened, and would raise `AttributeError` on a `None` capture —
  compare `VideoReadFile.stop_stream()`, which guards both.
- The optional-import guards are placeholders: `_XXX_IMPORTED` guards a
  commented-out `import xxx`, awaiting a real audio dependency.
- `audio_io.py` imports `open_video_capture` from
  `aiko_services.elements.media` (its own package `__init__`); this
  works only because `audio_io` is imported last in that `__init__` —
  an import-order fragility worth knowing before reordering.
- In the disabled suite: `PE_Speaker.process_frame()` references
  `self._microphone_topic_path`, which is never assigned
  (`self._microphone_service` is), and several `return` statements
  split tuples across lines in a way that would be a syntax error if
  the block were ever un-quoted verbatim.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `AudioOutput` | Pass audio samples through as the Pipeline response tail | [PipelineElement](../../concepts/pipeline_element.md) |
| `AudioReadFile` (scaffold) | *Intended*: iterate audio files from `data_sources`, emit audio-sample frames | [DataSource](../../concepts/data_source_target.md), [DataSchemeFile](scheme_file.md), `open_video_capture()` ([video_io](video_io.md) — placeholder), [Stream](../../concepts/stream.md) |
| `PE_Microphone*`, `PE_FFT`, `PE_AudioFilter`, `PE_AudioResampler`, `PE_GraphXY`, `PE_Speaker` (disabled) | Legacy capture → FFT → visualise/playback chain; reference for refactor | [PipelineElement](../../concepts/pipeline_element.md) (old idioms), `ECProducer`, MQTT publishing |

## Current limitations and roadmap

- **No working audio DataSource/DataTarget yet** — `AudioReadFile` is a
  scaffold and `AudioWriteFile` does not exist (commented out of
  `__all__`); `src/aiko_services/elements/media/__init__.py` imports
  only `AudioOutput`.
- **No committed audio PipelineDefinition** — the usage header's
  `pipelines/audio_pipeline_0.json` (and the `AudioResample` element it
  parameterises) are yet to be written.
- Module To Do list: decide supported formats (`.mp3`, `.ogg`,
  `.wav`?), and refactor the Speech-To-Text / Text-To-Speech
  PipelineElements out of the disabled legacy suite.
- Legacy-suite To Dos (recorded in the quoted block): ensure Registrar
  interaction occurs before flooding the Pipeline; move
  `PE_Microphone*` `__init__()` hardware setup into `start_stream()`;
  promote the many module-level literals (sample rates, chunk sizes,
  band counts) into [Parameters](../../concepts/parameters.md) and
  shared state.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  these elements implement
- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  base design `AudioReadFile` is being fitted into
- [DataScheme](../../concepts/scheme.md) / [scheme_file](scheme_file.md)
  — `file:` URL resolution the scaffold already relies on
- [Stream](../../concepts/stream.md) — per-Stream state rules the
  scaffold does not yet follow
- [video_io](video_io.md) — the template `AudioReadFile` was cloned
  from, and the source of `open_video_capture()`
- [text_io](text_io.md) — the finished exemplar of this element-family
  shape
