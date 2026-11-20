# Usage
# ~~~~~
# pytest [-s] unit/test_mp4_repair.py
#
# Unit tests for elements/media/mp4_repair.py and its use by
# VideoWriteStoreForward._repair_segment().
#
# The Raspberry Pi hardware encoder, through cv2.VideoWriter "avc1", writes
# a first sample that holds only the H.264 parameter sets (SPS and PPS).
# The repair joins it to the key frame that follows.  These tests build
# small MP4 files in memory, so they need no OpenCV, no encoder and no
# video file: the encoder's shape, its variants, and every shape the
# repair must leave alone.

import struct

from aiko_services.elements.media.mp4_repair import (
    merge_leading_parameter_sets
)
from aiko_services.elements.media.store_forward_io import (
    VideoWriteStoreForward
)

# MP4 construction ----------------------------------------------------------- #

def box(kind, body):
    return struct.pack(">I4s", 8 + len(body), kind) + body

def full_box(kind, rows, width=1):
    body = struct.pack(">II", 0, len(rows))
    for row in rows:
        row = row if isinstance(row, tuple) else (row,)
        assert len(row) == width
        body += struct.pack(f">{width}I", *row)
    return box(kind, body)

def nal(payload, length_size=4):
    return len(payload).to_bytes(length_size, "big") + payload

def parameter_sets(length_size=4):
    return nal(b"\x27\x64\x00\x28\xac\x2b", length_size)  \
         + nal(b"\x28\xee\x02\x5c", length_size)

def key_frame(length_size=4):
    return nal(b"\x25" + b"\x88" * 40, length_size)

def frame(index, length_size=4):
    return nal(b"\x21" + bytes([index % 256]) * 12, length_size)

def avc1(length_size=4):
    avcc = box(b"avcC", bytes([1, 0x64, 0x00, 0x28,
        0xFC | (length_size - 1), 0xE0, 0x00]))
    return box(b"avc1", bytes(78) + avcc)     # VisualSampleEntry fields

def build(samples, durations, syncs, chunks, length_size=4,
          faststart=False, extra_stbl=b""):
    """MP4 bytes: samples in "mdat", then "moov" (or before, "faststart").
    "chunks" is the stsc rows; the chunk count is what they describe"""

    ftyp = box(b"ftyp", b"isom\x00\x00\x02\x00isomavc1")
    mdat = box(b"mdat", b"".join(samples))
    per_chunk, row = [], 0           # samples per chunk, from the stsc rows
    remaining = len(samples)
    chunk = 1
    while remaining > 0:
        if row + 1 < len(chunks) and chunks[row + 1][0] == chunk:
            row += 1
        count = min(chunks[row][1], remaining)
        per_chunk.append(count)
        remaining -= count
        chunk += 1
    offsets, offset, index = [], len(ftyp) + 8, 0
    for count in per_chunk:
        offsets.append(offset)
        offset += sum(len(s) for s in samples[index:index + count])
        index += count
    stts = []                             # run-length (count, duration)
    for duration in durations:
        if stts and stts[-1][1] == duration:
            stts[-1] = (stts[-1][0] + 1, duration)
        else:
            stts.append((1, duration))
    stsz = box(b"stsz", struct.pack(">III", 0, 0, len(samples))  # flags, size
        + struct.pack(f">{len(samples)}I", *(len(s) for s in samples)))
    stbl = box(b"stbl",
        box(b"stsd", struct.pack(">II", 0, 1) + avc1(length_size))
        + full_box(b"stts", stts, 2)
        + full_box(b"stss", syncs)
        + full_box(b"stsc", chunks, 3)
        + stsz
        + full_box(b"stco", offsets)
        + extra_stbl)
    moov = box(b"moov", box(b"mvhd", bytes(100)) + box(b"trak",
        box(b"tkhd", bytes(84)) + box(b"edts", box(b"elst", bytes(20)))
        + box(b"mdia", box(b"mdhd", bytes(24)) + box(b"hdlr", bytes(25))
        + box(b"minf", box(b"vmhd", bytes(12)) + stbl))))
    if faststart:
        return ftyp + moov + mdat
    return ftyp + mdat + moov

def encoder_shape(frames=10, chunks=None, length_size=4, **options):
    """The shape the Raspberry Pi hardware encoder writes"""

    samples = [parameter_sets(length_size), key_frame(length_size)]  \
        + [frame(i, length_size) for i in range(frames - 1)]
    durations = [0] + [2048] * frames
    return build(samples, durations, [2], chunks or [(1, frames + 1, 1)],
                 length_size, **options), samples

# MP4 reading, independent of the code under test ---------------------------- #

def table(data, kind, width=1):
    offset = data.rindex(kind) - 4
    count = struct.unpack(">I", data[offset + 12:offset + 16])[0]
    first = 20 if kind == b"stsz" else 16
    if kind == b"stsz":
        count = struct.unpack(">I", data[offset + 16:offset + 20])[0]
    values = struct.unpack(f">{width * count}I",
        data[offset + first:offset + first + 4 * width * count])
    return [values[i:i + width] if width > 1 else values[i]
            for i in range(0, len(values), width)]

def sample_bytes(data, number):
    """Sample "number" (1-based), for a file whose samples are contiguous"""

    sizes = table(data, b"stsz")
    start = table(data, b"stco")[0] + sum(sizes[:number - 1])
    return data[start:start + sizes[number - 1]]

def write(tmp_path, data, name="segment.mp4"):
    path = tmp_path / name
    path.write_bytes(data)
    return path

# The encoder's shape -------------------------------------------------------- #

def test_the_encoder_shape_is_repaired(tmp_path):
    data, samples = encoder_shape()
    path = write(tmp_path, data)
    assert merge_leading_parameter_sets(path) is True

def test_the_first_sample_becomes_parameter_sets_and_key_frame(tmp_path):
    data, samples = encoder_shape()
    path = write(tmp_path, data)
    merge_leading_parameter_sets(path)
    repaired = path.read_bytes()
    assert sample_bytes(repaired, 1) == samples[0] + samples[1]
    assert sample_bytes(repaired, 2) == samples[2]

def test_the_tables_lose_the_parameter_sets_sample(tmp_path):
    data, samples = encoder_shape(frames=10)
    path = write(tmp_path, data)
    merge_leading_parameter_sets(path)
    repaired = path.read_bytes()
    assert len(table(repaired, b"stsz")) == 10
    assert table(repaired, b"stts", 2) == [(10, 2048)]
    assert table(repaired, b"stss") == [1]
    assert table(repaired, b"stsc", 3) == [(1, 10, 1)]

def test_no_media_byte_moves(tmp_path):
    data, samples = encoder_shape()
    path = write(tmp_path, data)
    merge_leading_parameter_sets(path)
    repaired = path.read_bytes()
    mdat_end = data.index(b"moov") - 4
    assert repaired[:mdat_end] == data[:mdat_end]

def test_the_file_shrinks_by_the_entries_removed(tmp_path):
    data, _ = encoder_shape()
    path = write(tmp_path, data)
    merge_leading_parameter_sets(path)
    assert len(path.read_bytes()) == len(data) - 12   # stsz 4, stts 8

def test_every_container_size_is_consistent(tmp_path):
    data, _ = encoder_shape()
    path = write(tmp_path, data)
    merge_leading_parameter_sets(path)
    repaired = path.read_bytes()
    offset = 0
    while offset < len(repaired):                     # top-level boxes
        size = struct.unpack(">I", repaired[offset:offset + 4])[0]
        offset += size
    assert offset == len(repaired)
    for kind in (b"trak", b"mdia", b"minf", b"stbl"):
        start = repaired.index(kind) - 4
        size = struct.unpack(">I", repaired[start:start + 4])[0]
        assert start + size <= len(repaired)

def test_a_second_run_changes_nothing(tmp_path):
    data, _ = encoder_shape()
    path = write(tmp_path, data)
    merge_leading_parameter_sets(path)
    once = path.read_bytes()
    assert merge_leading_parameter_sets(path) is False
    assert path.read_bytes() == once

def test_a_two_byte_nal_length_is_read_from_avcc(tmp_path):
    data, samples = encoder_shape(length_size=2)
    path = write(tmp_path, data)
    assert merge_leading_parameter_sets(path) is True
    assert sample_bytes(path.read_bytes(), 1) == samples[0] + samples[1]

def test_a_second_chunk_with_its_own_row_keeps_its_count(tmp_path):
    data, _ = encoder_shape(frames=12, chunks=[(1, 10, 1), (2, 3, 1)])
    path = write(tmp_path, data)
    assert merge_leading_parameter_sets(path) is True
    assert table(path.read_bytes(), b"stsc", 3) == [(1, 9, 1), (2, 3, 1)]

def test_chunk_1_gets_its_own_row_when_the_row_is_shared(tmp_path):
    data, _ = encoder_shape(frames=11, chunks=[(1, 6, 1)])  # chunks 1, 2
    path = write(tmp_path, data)
    assert merge_leading_parameter_sets(path) is True
    assert table(path.read_bytes(), b"stsc", 3) == [(1, 5, 1), (2, 6, 1)]

# Shapes the repair leaves alone --------------------------------------------- #

def assert_unchanged(tmp_path, data):
    path = write(tmp_path, data)
    assert merge_leading_parameter_sets(path) is False
    assert path.read_bytes() == data

def test_a_file_that_starts_with_its_key_frame(tmp_path):
    samples = [parameter_sets() + key_frame()] + [frame(i) for i in range(9)]
    assert_unchanged(tmp_path,
        build(samples, [2048] * 10, [1], [(1, 10, 1)]))

def test_a_faststart_file(tmp_path):
    data, _ = encoder_shape(faststart=True)
    assert_unchanged(tmp_path, data)

def test_a_table_the_repair_does_not_know(tmp_path):
    ctts = full_box(b"ctts", [(11, 0)], 2)
    data, _ = encoder_shape(extra_stbl=ctts)
    assert_unchanged(tmp_path, data)

def test_a_first_sample_that_has_a_duration(tmp_path):
    samples = [parameter_sets(), key_frame()] + [frame(i) for i in range(9)]
    assert_unchanged(tmp_path,
        build(samples, [2048] * 11, [2], [(1, 11, 1)]))

def test_a_first_sample_that_holds_a_picture_too(tmp_path):
    samples = [parameter_sets() + frame(0), key_frame()]  \
        + [frame(i) for i in range(9)]
    assert_unchanged(tmp_path,
        build(samples, [0] + [2048] * 10, [2], [(1, 11, 1)]))

def test_a_second_sample_that_is_not_the_key_frame(tmp_path):
    samples = [parameter_sets(), frame(0), key_frame()]  \
        + [frame(i) for i in range(8)]
    assert_unchanged(tmp_path,
        build(samples, [0] + [2048] * 10, [3], [(1, 11, 1)]))

def test_samples_1_and_2_in_different_chunks(tmp_path):
    samples = [parameter_sets(), key_frame()] + [frame(i) for i in range(9)]
    assert_unchanged(tmp_path,
        build(samples, [0] + [2048] * 10, [2], [(1, 1, 1), (2, 10, 1)]))

def test_a_truncated_file(tmp_path):
    data, _ = encoder_shape()
    assert_unchanged(tmp_path, data[:len(data) - 30])

def test_an_empty_file(tmp_path):
    assert_unchanged(tmp_path, b"")

def test_bytes_that_are_not_mp4(tmp_path):
    assert_unchanged(tmp_path, b"not a video file at all" * 10)

# VideoWriteStoreForward._repair_segment() ----------------------------------- #

class FakeProducer:
    def __init__(self):
        self.updates = {}

    def update(self, name, value):
        self.updates[name] = value

class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)

class Element:
    """Only what _repair_segment() touches.  The method is called unbound,
    so the code under test is the real one"""

    def __init__(self):
        self._segments_repaired = 0
        self.ec_producer = FakeProducer()
        self.logger = FakeLogger()

    def my_id(self):
        return "element"

def test_the_writer_counts_a_repaired_segment(tmp_path):
    element = Element()
    data, _ = encoder_shape()
    VideoWriteStoreForward._repair_segment(element, write(tmp_path, data))
    assert element._segments_repaired == 1
    assert element.ec_producer.updates == {"segments_repaired": "1"}

def test_the_writer_counts_nothing_for_a_clean_segment(tmp_path):
    element = Element()
    samples = [parameter_sets() + key_frame()] + [frame(i) for i in range(9)]
    path = write(tmp_path, build(samples, [2048] * 10, [1], [(1, 10, 1)]))
    VideoWriteStoreForward._repair_segment(element, path)
    assert element._segments_repaired == 0
    assert element.ec_producer.updates == {}

def test_a_segment_that_cannot_be_read_is_logged_not_raised(tmp_path):
    element = Element()
    VideoWriteStoreForward._repair_segment(element, tmp_path / "missing.mp4")
    assert element._segments_repaired == 0
    assert len(element.logger.warnings) == 1
