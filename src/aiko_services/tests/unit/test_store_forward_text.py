# Usage
# ~~~~~
# pytest [-s] unit/test_store_forward_text.py
#
# Generic StoreForward elements (store_forward_base.py) with TextCodec
# (store_forward_io.py).  No MQTT broker and no SegmentStoreForward Actor:
# the writer's outbox is the reader's inbox, which is what the Actors
# produce once a segment is delivered.
#
# Most tests drive SegmentWriter and SegmentReader directly, with an
# explicit "now", so that order, gaps and retries need no sleeping.  Two
# tests run the elements in-process Pipelines: TextFrames ->
# TextWriteStoreForward, then TextReadStoreForward -> CommitStoreForward
# -> TextSink (text_store_forward_helpers.py)
#
# To Do
# ~~~~~
# - None, yet !

import gzip
import json
import os

import pytest

from aiko_services.elements.media.store_forward_base import (
    SegmentReader, SegmentWriter, parse_segment_name, segment_name
)
from aiko_services.elements.media.store_forward_io import (
    TEXT_HEADER, TextCodec
)
from aiko_services.tests.unit import do_create_pipeline
from aiko_services.tests.unit.text_store_forward_helpers import (
    do_results_initialize, frame_text
)

FIELDS = {"group": "group \"A\"",
          "location": "room 1 — west", "sensor": "thermometer"}

def _frame(index, **extra):
    return dict(FIELDS, text=frame_text(index), **extra)

def _dirs(tmp_path):
    outbox = tmp_path / "outbox"
    work = tmp_path / "work"
    state = tmp_path / "state"
    for directory in (outbox, work, state):
        directory.mkdir()
    return str(outbox), str(work), str(state)

# Names -------------------------------------------------------------------- #

def test_segment_name_round_trip():
    name = segment_name("host3", 17, ".csv.gz")
    writer, utc, sequence, extension = parse_segment_name(name)
    assert (writer, sequence, extension) == ("host3", 17, ".csv.gz")
    assert len(utc) == len("2026-11-23_01-02-03-413882")
    assert name.endswith("_000017.csv.gz")

@pytest.mark.parametrize("name", [
    "2026-09-15_03-00-07-413882.mp4",          # VideoWriteStoreForward name
    "host_3_2026-11-23_01-02-03-413882_000001.csv",
    ".host3_2026-11-23_01-02-03-413882_000001.csv",
    "host3_2026-11-23_01-02-03-413882.csv", "notes.txt"])
def test_parse_segment_name_rejects_foreign_names(name):
    assert parse_segment_name(name) is None

def test_writer_id_must_be_a_token(tmp_path):
    outbox, _, state = _dirs(tmp_path)
    with pytest.raises(ValueError):
        SegmentWriter(outbox, "host_3", TextCodec(), state)

# TextCodec ---------------------------------------------------------------- #

@pytest.mark.parametrize("compress", ["none", "gzip"])
def test_text_codec_round_trip(tmp_path, compress):
    outbox, _, state = _dirs(tmp_path)
    codec = TextCodec(compress=compress)
    writer = SegmentWriter(outbox, "host3", codec, state)
    text = "﻿" + frame_text(1)
    [name] = writer.write(dict(FIELDS, text=text))
    assert name.endswith(".csv.gz" if compress == "gzip" else ".csv")
    header, [frame] = codec.read(os.path.join(outbox, name))
    assert frame == dict(FIELDS, text=frame_text(1))   # BOM gone, CRLF kept
    assert header["writer"] == "host3" and header["sequence"] == 1
    assert codec.read_header(os.path.join(outbox, name))["fields"] == FIELDS

def test_text_codec_gzip_file_is_gzip(tmp_path):
    outbox, _, state = _dirs(tmp_path)
    writer = SegmentWriter(outbox, "host3", TextCodec(compress="gzip"), state)
    [name] = writer.write(_frame(0))
    with gzip.open(os.path.join(outbox, name), "rt", encoding="utf-8") as file:
        assert file.readline().startswith(TEXT_HEADER)

def test_text_codec_empty_text_writes_nothing(tmp_path):
    outbox, _, state = _dirs(tmp_path)
    writer = SegmentWriter(outbox, "host3", TextCodec(), state)
    assert writer.write(dict(FIELDS, text="")) == []
    assert writer.write(dict(FIELDS, text=None)) == []
    assert os.listdir(outbox) == []

def test_text_codec_splits_at_line_boundaries(tmp_path):
    outbox, _, state = _dirs(tmp_path)
    codec = TextCodec(max_segment_bytes=1024)
    lines = [f"row {index:04d}\t{'x' * 90}\n" for index in range(40)]
    writer = SegmentWriter(outbox, "host3", codec, state)
    names = writer.write(dict(FIELDS, text="".join(lines)))
    assert len(names) > 1
    sequences = [parse_segment_name(name)[2] for name in names]
    assert sequences == list(range(1, len(names) + 1))
    texts = [codec.read(os.path.join(outbox, name))[1][0]["text"]
             for name in names]
    assert "".join(texts) == "".join(lines)
    assert all(text.endswith("\n") for text in texts)

def test_text_codec_rejects_bad_header(tmp_path):
    path = tmp_path / "host3_2026-11-23_01-02-03-413882_000001.csv"
    path.write_text("2024-09-01T00:00:00Z,1\n")
    with pytest.raises(ValueError):
        TextCodec().read_header(str(path))

@pytest.mark.parametrize("arguments", [
    {"compress": "zip"}, {"extension": "c.sv"}, {"max_segment_bytes": 10}])
def test_text_codec_rejects_bad_parameters(arguments):
    with pytest.raises(ValueError):
        TextCodec(**arguments)

# SegmentWriter ------------------------------------------------------------ #

def test_writer_leaves_no_temporary_file(tmp_path):
    outbox, _, state = _dirs(tmp_path)
    writer = SegmentWriter(outbox, "host3", TextCodec(), state)
    for index in range(3):
        writer.write(_frame(index))
    names = sorted(os.listdir(outbox))
    assert len(names) == 3
    assert not [name for name in names if name.startswith(".")]

def test_writer_sequence_persists_and_epoch_resets(tmp_path):
    outbox, _, state = _dirs(tmp_path)
    first = SegmentWriter(outbox, "host3", TextCodec(), state)
    first.write(_frame(0))
    first.write(_frame(1))
    second = SegmentWriter(outbox, "host3", TextCodec(), state)
    assert second.epoch == first.epoch
    [name] = second.write(_frame(2))
    assert parse_segment_name(name)[2] == 3

    os.remove(os.path.join(state, "store_forward_write_host3.json"))
    third = SegmentWriter(outbox, "host3", TextCodec(), state)
    [name] = third.write(_frame(3))
    assert parse_segment_name(name)[2] == 1          # new epoch, from 1
    header = TextCodec().read_header(os.path.join(outbox, name))
    assert header["epoch"] == third.epoch

def test_writer_failure_reuses_the_sequence(tmp_path):
    outbox, _, state = _dirs(tmp_path)

    class FailingCodec(TextCodec):
        fail = True
        def close(self):
            if FailingCodec.fail:
                raise OSError("disk full")
            super().close()

    writer = SegmentWriter(outbox, "host3", FailingCodec(), state)
    with pytest.raises(OSError):
        writer.write(_frame(0))
    assert os.listdir(outbox) == []                  # temporary removed
    FailingCodec.fail = False
    [name] = writer.write(_frame(0))
    assert parse_segment_name(name)[2] == 1

# SegmentReader ------------------------------------------------------------ #

def _write(outbox, state, count, writer_id="host3"):
    writer = SegmentWriter(outbox, writer_id, TextCodec(), state)
    return [writer.write(_frame(index))[0] for index in range(count)]

def _drain(reader, now=0.0):
    """Poll and commit until nothing is ready; the names in order."""

    names = []
    while True:
        result = reader.poll(now)
        if result is None:
            return names
        name, frames = result
        for frame in frames:
            assert frame["segment"] == name
            reader.commit(name)
        names.append(name)

def test_reader_applies_in_sequence_order(tmp_path):
    outbox, work, state = _dirs(tmp_path)
    names = _write(outbox, state, 3)
    reader = SegmentReader(outbox, work, TextCodec())
    assert _drain(reader) == names
    assert sorted(os.listdir(os.path.join(work, "done"))) == names
    assert os.listdir(outbox) == []
    with open(os.path.join(work, "store_forward_read.json")) as file:
        assert list(json.load(file).values()) == [3]

def test_reader_waits_for_a_gap_then_skips(tmp_path):
    outbox, work, state = _dirs(tmp_path)
    names = _write(outbox, state, 3)
    held = os.path.join(tmp_path, names[1])
    os.replace(os.path.join(outbox, names[1]), held)  # sequence 2 is late

    reader = SegmentReader(outbox, work, TextCodec(), gap_timeout=100)
    assert _drain(reader, now=0.0) == [names[0]]      # 3 waits for 2
    assert _drain(reader, now=50.0) == []
    os.replace(held, os.path.join(outbox, names[1]))  # 2 arrives
    assert _drain(reader, now=60.0) == [names[1], names[2]]

    more = _write(outbox, state, 2)                   # sequences 4 and 5
    os.remove(os.path.join(outbox, more[0]))          # 4 never arrives
    assert _drain(reader, now=70.0) == []
    assert _drain(reader, now=169.0) == []
    assert _drain(reader, now=171.0) == [more[1]]     # gap_timeout passed
    assert reader.counters["gaps"] == 1

def test_reader_moves_duplicates_to_done(tmp_path):
    outbox, work, state = _dirs(tmp_path)
    names = _write(outbox, state, 2)
    reader = SegmentReader(outbox, work, TextCodec())
    _drain(reader)
    os.replace(os.path.join(work, "done", names[0]),
               os.path.join(outbox, names[0]))        # delivered again
    assert _drain(reader) == []
    assert reader.counters["duplicates"] == 1
    assert names[0] in os.listdir(os.path.join(work, "done"))

def test_reader_writers_and_epochs_are_independent(tmp_path):
    outbox, work, state = _dirs(tmp_path)
    host3 = _write(outbox, state, 2, "host3")
    host4 = _write(outbox, state, 2, "host4")
    os.remove(os.path.join(state, "store_forward_write_host3.json"))
    host3_new = _write(outbox, state, 1, "host3")     # new epoch, sequence 1
    reader = SegmentReader(outbox, work, TextCodec())
    assert sorted(_drain(reader)) == sorted(host3 + host4 + host3_new)
    assert reader.counters["duplicates"] == 0

def test_reader_emits_processing_again_after_restart(tmp_path):
    outbox, work, state = _dirs(tmp_path)
    names = _write(outbox, state, 2)
    reader = SegmentReader(outbox, work, TextCodec())
    name, _ = reader.poll(0.0)                        # claimed, no commit
    assert name == names[0]
    assert os.listdir(os.path.join(work, "processing")) == [names[0]]

    restarted = SegmentReader(outbox, work, TextCodec())
    assert _drain(restarted) == names

def test_reader_retries_then_rejects_an_uncommitted_segment(tmp_path):
    outbox, work, state = _dirs(tmp_path)
    [name] = _write(outbox, state, 1)
    reader = SegmentReader(outbox, work, TextCodec(), commit_timeout=10,
                           max_attempts=2)
    assert reader.poll(0.0)[0] == name
    assert reader.poll(5.0) is None                   # still in flight
    assert reader.poll(11.0)[0] == name               # attempt 2
    assert reader.poll(22.0) is None                  # rejected
    assert os.listdir(os.path.join(work, "rejected")) == [name]
    assert reader.counters["retries"] == 1

def test_reader_rejects_bad_names_and_headers(tmp_path):
    outbox, work, state = _dirs(tmp_path)
    [good] = _write(outbox, state, 1)
    bad_name = "host3_2026-11-23_01-02-03-413882.csv"
    bad_header = "host4_2026-11-23_01-02-03-413882_000001.csv"
    with open(os.path.join(outbox, bad_name), "w") as file:
        file.write("x\n")
    with open(os.path.join(outbox, bad_header), "w") as file:
        file.write("no header\n")
    with open(os.path.join(outbox, ".partial.csv"), "w") as file:
        file.write("ignored\n")
    reader = SegmentReader(outbox, work, TextCodec())
    assert _drain(reader) == [good]
    assert sorted(os.listdir(os.path.join(work, "rejected"))) ==  \
        sorted([bad_name, bad_header])
    assert os.listdir(outbox) == [".partial.csv"]

def test_reader_sweeps_old_done_segments(tmp_path):
    outbox, work, state = _dirs(tmp_path)
    names = _write(outbox, state, 2)
    reader = SegmentReader(outbox, work, TextCodec(), done_max_age=60)
    _drain(reader, now=0.0)
    old = os.path.join(work, "done", names[0])
    os.utime(old, (1.0, 1.0))
    reader.poll(now=4000.0)                           # past SWEEP_PERIOD
    assert os.listdir(os.path.join(work, "done")) == [names[1]]

# In-process Pipelines ----------------------------------------------------- #

WRITER_PIPELINE = """{
  "version": 0, "name": "p_test_text_write_store_forward", "runtime": "python",
  "graph": ["(TextFrames TextWriteStoreForward TextSink)"],
  "parameters": {"_create_stream_": "1"},
  "elements": [
    { "name": "TextFrames", "parameters": {"frame_count": 3},
      "input":  [{"name": "text", "type": "str"},
                 {"name": "group", "type": "str"},
                 {"name": "location", "type": "str"},
                 {"name": "sensor", "type": "str"}],
      "output": [{"name": "text", "type": "str"},
                 {"name": "group", "type": "str"},
                 {"name": "location", "type": "str"},
                 {"name": "sensor", "type": "str"}],
      "deploy": {"local": {
        "module": "aiko_services.tests.unit.text_store_forward_helpers"}} },
    { "name": "TextWriteStoreForward",
      "parameters": {"data_targets": "(store_forward://OUTBOX)",
                     "segment_prefix": "host0", "state_directory": "STATE",
                     "compress": "gzip"},
      "input":  [{"name": "text", "type": "str"},
                 {"name": "group", "type": "str"},
                 {"name": "location", "type": "str"},
                 {"name": "sensor", "type": "str"}],
      "output": [],
      "deploy": {"local": {
        "module": "aiko_services.elements.media.store_forward_io"}} },
    { "name": "TextSink", "parameters": {"expected": 0},
      "input":  [{"name": "text", "type": "str"},
                 {"name": "sensor", "type": "str"}],
      "output": [],
      "deploy": {"local": {
        "module": "aiko_services.tests.unit.text_store_forward_helpers"}} }
  ]
}
"""

READER_PIPELINE = """{
  "version": 0, "name": "p_test_text_read_store_forward", "runtime": "python",
  "graph": ["(TextReadStoreForward CommitStoreForward TextSink)"],
  "parameters": {"_create_stream_": "1"},
  "elements": [
    { "name": "TextReadStoreForward",
      "parameters": {"data_sources": "(store_forward://INBOX)",
                     "work_directory": "WORK", "compress": "gzip",
                     "rate": 20.0},
      "input":  [{"name": "text", "type": "str"},
                 {"name": "group", "type": "str"},
                 {"name": "location", "type": "str"},
                 {"name": "sensor", "type": "str"},
                 {"name": "segment", "type": "str"}],
      "output": [{"name": "text", "type": "str"},
                 {"name": "group", "type": "str"},
                 {"name": "location", "type": "str"},
                 {"name": "sensor", "type": "str"},
                 {"name": "segment", "type": "str"}],
      "deploy": {"local": {
        "module": "aiko_services.elements.media.store_forward_io"}} },
    { "name": "CommitStoreForward", "parameters": {},
      "input":  [{"name": "segment", "type": "str"}], "output": [],
      "deploy": {"local": {
        "module": "aiko_services.elements.media.store_forward_base"}} },
    { "name": "TextSink", "parameters": {"expected": 3},
      "input":  [{"name": "text", "type": "str"},
                 {"name": "sensor", "type": "str"}],
      "output": [],
      "deploy": {"local": {
        "module": "aiko_services.tests.unit.text_store_forward_helpers"}} }
  ]
}
"""

def test_pipelines_write_then_read(tmp_path):
    outbox, work, state = _dirs(tmp_path)

    results = do_results_initialize()
    do_create_pipeline(WRITER_PIPELINE
        .replace("OUTBOX", outbox).replace("STATE", state), frame_data=None)
    assert results["stopped"] and not results["watchdog"]
    names = sorted(os.listdir(outbox))
    assert len(names) == 3 and all(name.endswith(".csv.gz") for name in names)

    results = do_results_initialize()
    do_create_pipeline(READER_PIPELINE
        .replace("INBOX", outbox).replace("WORK", work), frame_data=None)
    assert not results["watchdog"], "reader did not deliver three frames"
    assert [frame["text"] for frame in results["frames"]] ==  \
        [frame_text(index) for index in range(3)]
    assert {frame["sensor"] for frame in results["frames"]} == {"thermometer"}
    assert sorted(os.listdir(os.path.join(work, "done"))) == names
    assert os.listdir(outbox) == []
