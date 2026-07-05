---
title: video_example CLI
description: Legacy stand-alone command-line demonstration that copies video
  between any combination of file and network stream endpoints using the
  GStreamer wrapper classes, with optional OpenCV display and overlay
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/gstreamer/video_example.py
related: [utilities, video_file_reader, video_file_writer,
  video_stream_reader, video_stream_writer, video_reader]
version: "0.6"
last_updated: 2026-07-06
---

# video_example CLI

## Overview

**`video_example.py`** is the **legacy** demonstration and manual-test
harness for the pre-PipelineElement GStreamer wrapper family. It wires
one *reader* ([VideoFileReader](video_file_reader.md) or
[VideoStreamReader](video_stream_reader.md)) to one *writer*
([VideoFileWriter](video_file_writer.md) or
[VideoStreamWriter](video_stream_writer.md)) and pumps frames between
them with [utilities](utilities.md) `process_video()` — optionally
displaying the video locally and overlaying the frame id via OpenCV.

It is a plain script with an `argparse` `__main__` — no
[Pipeline](../../concepts/pipeline.md), no Actor, no MQTT. The
current-style equivalent of what it demonstrates is an `aiko_pipeline`
PipelineDefinition such as `pipelines/rtsp_pipeline_1.json`
(see [rtsp_io](rtsp_io.md)).

**Why you'd use it**: a quick end-to-end check that GStreamer, the
platform codecs and a camera/network path all work, before involving
the Aiko Services framework:

```bash
./video_example.py -if ../data/football_test_0.mp4 -os 192.168.1.65:5000 \
  -r 1280 720 -f 30/1 -cv
```

## For application developers

### Command-line usage

The four input/output combinations (from the usage header):

```bash
# file → file
./video_example.py -if input_filename      -of output_filename  \
  -r width height -f framerate [-cv]

# stream → stream
./video_example.py -is input_hostname:port -os output_hostname:port  \
  -r width height -f framerate -cv  [--RTP]

# file → stream
./video_example.py -if input_filename      -os output_hostname:port  \
  -r width height -f framerate -cv

# stream → file
./video_example.py -is input_hostname:port -of output_filename  \
  -r width height -f framerate -cv  [--RTP]
```

Options:

| Option | Meaning |
|--------|---------|
| `-if` / `--input_filename` | Video input file (MP4/QuickTime — see [video_file_reader](video_file_reader.md)) |
| `-is` / `--input_stream` | Video input `hostname:port` (RTSP by default) |
| `-of` / `--output_filename` | Video output file |
| `-os` / `--output_stream` | Video output `hostname:port` (RTP/UDP) |
| `-r` / `--resolution` | Two values: width height |
| `-f` / `--framerate` | GStreamer fraction, e.g. `30/1` |
| `-cv` / `--opencv` | Display locally and overlay the frame id (press `q` to quit) |
| `--RTP` | Input stream uses RTP (`udpsrc`) instead of the default RTSP |

Exactly one input (`-if` xor `-is`) and one output (`-of` xor `-os`)
must be given; otherwise the script prints a usage message and exits
with status -1. A worked camera-to-host session from the header:

```bash
CAMERA_IP=192.168.1.89:554
TARGET_IP=192.168.1.155:5000
./video_example.py -is $CAMERA_IP -os $TARGET_IP -r 640 480 -f 25/1 -cv
```

Note: RTSP input relies on the credential template hard-wired in
[video_stream_reader](video_stream_reader.md)
(`rtsp://USERNAME:PASSWORD@host:port`) — edit that module to match your
camera before RTSP input will authenticate.

### Public API

None — the module defines no classes or functions; everything is inside
`if __name__ == "__main__":`. Its "API" is the reader/writer queue
contract it demonstrates:

```python
video_reader = VideoFileReader(filename, width, height)        # or
video_reader = VideoStreamReader(host, port, width, height, rtp=args.RTP)

video_writer = VideoFileWriter(filename, width, height, framerate)  # or
video_writer = VideoStreamWriter(host, port, width, height, framerate)

utilities.process_video(video_reader, video_writer)   # blocking copy loop
```

Errors: `ValueError` (bad paths / arguments) and `GStreamerError`
(pipeline failures) are caught and printed — the latter with a TODO
admitting the diagnostic needs improvement.

## For framework developers (internals)

### Design

```
        -if file ──► VideoFileReader ─┐               ┌─► VideoFileWriter ──► -of file
                                      ├► VideoReader  │
        -is host:port ─► VideoStream ─┘   Queue(30)   │
           [--RTP]        Reader            │         │
                                            ▼         │
                              process_video() loop ───┴─► VideoStreamWriter ─► -os host:port
                              (optional cv2 display
                               + frame-id overlay)
```

A pure composition script: argument validation, one reader, one writer,
then delegate to `process_video()`. Its only design significance is
that it *defines* the informal legacy contract — any object with
`read_frame(timeout)` can feed any object with `write_frame(frame)`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| *(script `__main__`)* | Parse arguments; enforce one-input/one-output; construct the matching reader and writer; enable OpenCV on `-cv`; run the copy loop; report `ValueError` / `GStreamerError` | [VideoFileReader](video_file_reader.md), [VideoStreamReader](video_stream_reader.md), [VideoFileWriter](video_file_writer.md), [VideoStreamWriter](video_stream_writer.md), [utilities](utilities.md) (`enable_opencv()`, `process_video()`) |

## Current limitations and roadmap

From the source To Do list:

- **Turn this into a CI test!** — currently the only executable
  exercise of the legacy wrapper family, and it requires a human (and
  often a camera)

Additional observed gaps:

- `GStreamerError` handling "needs better diagnostic" (source TODO)
- No graceful termination: `process_video()` only exits via the OpenCV
  `q` key (with `-cv`) or process kill; EOS handling with `-cv` hits
  the `KeyError` noted in [utilities](utilities.md)
- RTSP input credentials are hard-wired in
  [video_stream_reader](video_stream_reader.md), not options here
- `-f/--framerate` help text is a copy-paste of the resolution help
- Long-term, this script's role is superseded by `aiko_pipeline`
  PipelineDefinitions over [DataSource /
  DataTarget](../../concepts/data_source_target.md) elements

## Related concepts

- [video_file_reader](video_file_reader.md) /
  [video_file_writer](video_file_writer.md) — the file endpoints
- [video_stream_reader](video_stream_reader.md) /
  [video_stream_writer](video_stream_writer.md) — the network endpoints
- [video_reader](video_reader.md) — the shared reader core underneath
- [utilities](utilities.md) — `process_video()` loop and OpenCV
  enablement
- [rtsp_io](rtsp_io.md) — the current-style way to run camera-to-file
  flows with `aiko_pipeline`
