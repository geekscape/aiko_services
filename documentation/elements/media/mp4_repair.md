---
title: MP4 repair of a leading parameter-sets sample
description: merge_leading_parameter_sets() — repairs an H.264 MP4 file
  whose first sample holds only the parameter sets (SPS and PPS), as the
  Raspberry Pi hardware encoder writes it, by changing only the sample
  tables
type: concept
audience: [developers]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/media/mp4_repair.py
  - src/aiko_services/tests/unit/test_mp4_repair.py
related: [store_forward_io, video_io]
version: "0.8-dev"
last_updated: 2026-11-20
---

# MP4 repair of a leading parameter-sets sample

## Overview

**`merge_leading_parameter_sets(path)`** repairs one defect in an H.264
MP4 file: a first sample that holds only the parameter sets (SPS and
PPS) and no picture. It joins that sample to the key frame after it, so
the first sample is a complete access unit. Only the sample tables
change. No media byte moves, and nothing is encoded again.

It returns `True` when it repaired the file. It returns `False` for a
file of any other shape, and then the file is not changed. So a writer
can call it on every file that it closes.
[`VideoWriteStoreForward`](store_forward_io.md) calls it on each segment
before the segment becomes visible. [`VideoWriteFile` and
`VideoWriteFiles`](video_io.md) call it on each file after they release
the writer. [`VideoReadFile`](video_io.md) also reads files that were
not repaired: it does not stop at a failed read while the file has more
frames.

## For application developers

### Why the defect occurs

On a Raspberry Pi, `cv2.VideoWriter` with `avc1` encodes with the
hardware encoder (`bcm2835-codec`, through FFmpeg `h264_v4l2m2m`).
FFmpeg sets the encoder to send the parameter sets as a separate buffer.
The MP4 muxer then stores that buffer as a sample, with a duration of 0,
before the first key frame. Measured on 2026-11-20, every file written
in this way has the sample.

Readers do not all handle the sample in the same way:

- FFmpeg reports `missing picture in access unit` for some files, and
  skips the sample in other files.
- OpenCV's first `read()` fails for some files. A loop that stops at the
  first failed `read()` then gets no frame at all.
- The frame count of the container is one more than the frames that
  decode.

### Usage

```python
from aiko_services.elements.media.mp4_repair import (
    merge_leading_parameter_sets)

if merge_leading_parameter_sets("segment.mp4"):
    print("repaired")
```

The function changes the file in place. Call it before the file is
published, for example before the rename that makes a segment visible.
It raises `OSError` for a file that it cannot read or write.

## For framework developers (internals)

### The shape that is repaired

The repair acts only when all of these conditions are true:

- `moov` is the last box, after `mdat`. So `moov` can become shorter
  without a change to any chunk offset.
- `moov` holds one track, with an `avc1` sample entry and an `avcC` box.
  `avcC` gives the size of each NAL unit length field.
- Sample 1 holds only SPS (type 7) and PPS (type 8) NAL units, and its
  duration is 0.
- Sample 2 is the first sync sample (`stss`).
- Samples 1 and 2 are in chunk 1, so their bytes are next to each other.
- The sample table holds only `stsd`, `stts`, `stss`, `stsc`, `stsz`,
  and `stco` or `co64`. A box such as `ctts`, `sdtp` or a sample group
  might give data for each sample, and the repair does not change it.

### The changes

| Box | Change |
|-----|--------|
| `stsz` | The sizes of samples 1 and 2 become one size |
| `stts` | The entry for sample 1, with a duration of 0, is removed |
| `stss` | Each sync sample number decreases by 1 |
| `stsc` | Chunk 1 has one sample fewer. If its row also applies to more chunks, chunk 1 gets a row of its own |
| `moov` and its containers | The sizes are calculated again, and the file is truncated |

The function parses `moov` into a tree, replaces the four tables, and
writes `moov` again at the same offset. A second call returns `False`,
because sample 1 is then a complete access unit.

### Cost

About 1 ms for a 1 s segment (8 frames) on a Raspberry Pi 4, measured on
100 segments. The encoder takes about 190 ms of CPU time for the same
segment.

### Alternatives that were measured

| Alternative | Result |
|-------------|--------|
| A remux with FFmpeg `filter_units=remove_types=7\|8` | Correct, but 370 ms for each segment, almost all of it to start `ffmpeg` |
| PyAV, to remux in the process | About 53 MB more in the virtual environment |
| The V4L2 control `sequence_header_mode` | FFmpeg sets it each time that it opens the encoder |
| The system `python3-opencv` 4.10 | It encodes with software x264, 166 ms for each 1080p frame: too slow for 8 frames each second |
| A GStreamer writer: `v4l2h264enc ! h264parse ! mp4mux` | No defect, because `h264parse` makes complete access units. But about two times the CPU time of `cv2` |

## Current limitations and roadmap

- Fragmented MP4 (`moof`) is not repaired. `cv2.VideoWriter` does not
  write it.

## Related concepts

- [store_forward_io](store_forward_io.md), the writer that calls the
  repair
- [video_io](video_io.md), `VideoWriteFile` and `VideoWriteFiles`,
  which call the repair, and `VideoReadFile`, which reads files that
  were not repaired
