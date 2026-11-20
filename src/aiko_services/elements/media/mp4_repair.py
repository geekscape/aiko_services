# Usage
# ~~~~~
# from aiko_services.elements.media.mp4_repair import (
#     merge_leading_parameter_sets)
#
# if merge_leading_parameter_sets("segment.mp4"):
#     print("repaired")
#
# Repairs one defect in an H.264 MP4 file: a first sample that holds only
# the stream's parameter sets, SPS and PPS, and no picture.
#
# On a Raspberry Pi, cv2.VideoWriter "avc1" encodes with the hardware
# encoder (bcm2835-codec, through FFmpeg h264_v4l2m2m).  FFmpeg sets that
# encoder to deliver the parameter sets as a separate buffer, and the MP4
# muxer stores the buffer as a sample of its own, with a duration of 0,
# ahead of the first key frame.  Measured 2026-11-20: every segment written
# that way has it.  Readers handle it differently.  FFmpeg reports
# "missing picture in access unit" for some files and skips the sample in
# others.  cv2.VideoCapture.read() fails on the first call for some files,
# so a "while ok" read loop reads no frame at all.
#
# The repair joins sample 1 (the parameter sets) and sample 2 (the key
# frame) into one sample, which is then a complete access unit.  Only the
# sample tables in "moov" change: the two samples are next to each other
# in "mdat", so no media byte moves and nothing is encoded again.  The file
# becomes shorter by the size of the table entries removed.
#
# The repair acts only on the exact shape described above.  Any other file
# is left byte for byte as it was, and the function returns False.  So it
# can run on every file a writer closes, and a second run does nothing.
#
# The shape: "moov" is the last box and follows "mdat" (no "faststart"),
# one track, sample 1 holds only SPS and PPS NAL units and has a
# duration of 0, sample 2 is the first sync sample, samples 1 and 2 are in
# the first chunk, and the sample table holds no box this repair would
# need to change and does not know ("ctts", "sdtp", sample groups).
#
# Cost, measured on a Raspberry Pi 4: about 1 ms per 1 s segment
#
# To Do
# ~~~~~
# - Fragmented MP4 ("moof"): not produced by cv2.VideoWriter, not handled

import struct

__all__ = ["merge_leading_parameter_sets"]

_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}
_NAL_SPS, _NAL_PPS = 7, 8
# Sample table boxes the repair reads or changes.  Any other box in "stbl"
# might be indexed by sample number, so its presence refuses the repair
_STBL_KNOWN = {b"stsd", b"stts", b"stss", b"stsc", b"stsz", b"stco", b"co64"}

class _Refuse(Exception):
    """This file is not the shape that the repair is for"""

def _boxes(data, start, end):
    """[[type, start, end, children or None]] for the boxes in a range"""

    boxes = []
    offset = start
    while offset < end:
        if offset + 8 > end:
            raise _Refuse("truncated box header")
        size, kind = struct.unpack(">I4s", data[offset:offset + 8])
        if size < 8 or offset + size > end:   # 64-bit, "to end" or damaged
            raise _Refuse("unsupported box size")
        children = None
        if kind in _CONTAINERS:
            children = _boxes(data, offset + 8, offset + size)
        boxes.append([kind, offset, offset + size, children])
        offset += size
    return boxes

def _child(box, kind):
    found = [child for child in box[3] if child[0] == kind]
    if len(found) != 1:
        raise _Refuse(f"{len(found)} {kind.decode()} boxes")
    return found[0]

def _u32(data, offset):
    return struct.unpack(">I", data[offset:offset + 4])[0]

def _table(data, box, width):
    """The entries of a full box table: version, flags, count, entries"""

    count = _u32(data, box[1] + 12)
    start = box[1] + 16
    if start + 4 * width * count > box[2]:
        raise _Refuse(f"{box[0].decode()} shorter than its count")
    values = struct.unpack(f">{width * count}I",
        data[start:start + 4 * width * count])
    return [values[i:i + width] for i in range(0, len(values), width)]

def _full_box(kind, header, entries):
    """A full box: the original version and flags, then a count and rows"""

    body = header + struct.pack(">I", len(entries))
    for entry in entries:
        body += struct.pack(f">{len(entry)}I", *entry)
    return struct.pack(">I4s", 8 + len(body), kind) + body

def _nal_length_size(data, stsd):
    """The size in bytes of each NAL unit length field, from "avcC" """

    entry = stsd[1] + 16                      # first sample entry
    if data[entry + 4:entry + 8] != b"avc1":
        raise _Refuse("not an avc1 sample entry")
    entry_end = entry + _u32(data, entry)
    offset = entry + 86                       # past VisualSampleEntry fields
    while offset + 8 <= entry_end:
        size, kind = struct.unpack(">I4s", data[offset:offset + 8])
        if size < 8:
            break
        if kind == b"avcC":
            return (data[offset + 12] & 0x03) + 1
        offset += size
    raise _Refuse("no avcC")

def _parameter_sets_only(data, start, size, length_size):
    """Whether a sample holds only SPS and PPS NAL units"""

    offset, end = start, start + size
    while offset < end:
        if offset + length_size > end:
            return False
        length = int.from_bytes(data[offset:offset + length_size], "big")
        offset += length_size
        if length == 0 or offset + length > end:
            return False
        if data[offset] & 0x1F not in (_NAL_SPS, _NAL_PPS):
            return False
        offset += length
    return offset == end and end > start

def _serialize(data, box, replace):
    """Box bytes, with replacements, and every container size recomputed"""

    if box[3] is None:
        return replace.get(box[1], data[box[1]:box[2]])
    body = b"".join(_serialize(data, child, replace) for child in box[3])
    return struct.pack(">I4s", 8 + len(body), box[0]) + body

def _repaired_moov(data):
    """The new "moov" bytes and its offset, or raise _Refuse"""

    top = _boxes(data, 0, len(data))
    moov, mdat = _child([b"", 0, 0, top], b"moov"), \
                 _child([b"", 0, 0, top], b"mdat")
    if top[-1] is not moov or moov[1] < mdat[1]:
        raise _Refuse('"moov" is not the last box after "mdat"')
    stbl = _child(_child(_child(_child(moov, b"trak"), b"mdia"),
        b"minf"), b"stbl")
    kinds = {child[0] for child in stbl[3]}
    if not kinds <= _STBL_KNOWN:
        raise _Refuse(f"sample table holds {sorted(kinds - _STBL_KNOWN)}")
    stsd, stts, stss, stsc, stsz = (_child(stbl, kind) for kind in
        (b"stsd", b"stts", b"stss", b"stsc", b"stsz"))
    chunk_box = _child(stbl, b"co64" if b"co64" in kinds else b"stco")

    if _u32(data, stsz[1] + 12) != 0:         # one size for every sample
        raise _Refuse("fixed sample size")
    sample_count = _u32(data, stsz[1] + 16)
    if sample_count < 2 or stsz[1] + 20 + 4 * sample_count > stsz[2]:
        raise _Refuse("too few samples")
    sizes = list(struct.unpack(f">{sample_count}I",
        data[stsz[1] + 20:stsz[1] + 20 + 4 * sample_count]))
    chunk_count = _u32(data, chunk_box[1] + 12)
    if chunk_count < 1:
        raise _Refuse("no chunks")
    if chunk_box[0] == b"co64":
        first_chunk = struct.unpack(">Q", data[chunk_box[1] + 16:
            chunk_box[1] + 24])[0]
    else:
        first_chunk = _table(data, chunk_box, 1)[0][0]

    length_size = _nal_length_size(data, stsd)
    if not _parameter_sets_only(data, first_chunk, sizes[0], length_size):
        raise _Refuse("sample 1 is not parameter sets only")

    times = _table(data, stts, 2)
    if not times or times[0][0] < 1 or times[0][1] != 0:
        raise _Refuse("sample 1 has a duration")
    syncs = [row[0] for row in _table(data, stss, 1)]
    if not syncs or syncs[0] != 2:
        raise _Refuse("sample 2 is not the first sync sample")
    chunks = _table(data, stsc, 3)
    if not chunks or chunks[0][0] != 1 or chunks[0][1] < 2:
        raise _Refuse("samples 1 and 2 are not in chunk 1")

    # The changes: sample 1 is now the parameter sets and the key frame
    sizes[:2] = [sizes[0] + sizes[1]]
    times = ([(times[0][0] - 1, 0)] if times[0][0] > 1 else []) + times[1:]
    syncs = [sync - 1 for sync in syncs]
    _, per_chunk, description = chunks[0]
    if chunk_count == 1 or (len(chunks) > 1 and chunks[1][0] == 2):
        chunks[0] = (1, per_chunk - 1, description)
    else:       # the first row covers chunks 1, 2, ...: chunk 1 gets its own
        chunks[:1] = [(1, per_chunk - 1, description),
                      (2, per_chunk, description)]

    def header(box):
        return data[box[1] + 8:box[1] + 12]   # version and flags

    replace = {
        stts[1]: _full_box(b"stts", header(stts), times),
        stss[1]: _full_box(b"stss", header(stss), [(s,) for s in syncs]),
        stsc[1]: _full_box(b"stsc", header(stsc), chunks),
        stsz[1]: struct.pack(">I4s", 20 + 4 * len(sizes), b"stsz")
            + header(stsz) + struct.pack(">II", 0, len(sizes))
            + struct.pack(f">{len(sizes)}I", *sizes),
    }
    return moov[1], _serialize(data, moov, replace)

def merge_leading_parameter_sets(path):
    """Join a leading parameter-sets-only sample to the key frame after it.

    Returns True when the file was repaired, and False when it was not the
    shape described in the module header, in which case it is unchanged.
    The file is changed in place: call it before the file is published,
    for example before the rename that makes a segment visible.
    OSError is raised for a file that cannot be read or written"""

    with open(path, "rb") as file:
        data = file.read()
    try:
        offset, moov = _repaired_moov(data)
    except (_Refuse, struct.error, IndexError):
        return False
    with open(path, "r+b") as file:
        file.seek(offset)
        file.write(moov)
        file.truncate()
    return True
