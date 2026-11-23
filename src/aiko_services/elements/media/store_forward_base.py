# Usage
# ~~~~~
# Generic StoreForward PipelineElements.  A media type supplies a
# SegmentCodec (store_forward_io.py: TextCodec) and a two-line subclass of
# WriteStoreForward and ReadStoreForward that names it.
#
#   Sending host     (... XWriteStoreForward)    writes segments to OUTBOX
#   SegmentStoreForward Actors (main/store_forward) move OUTBOX -> INBOX
#   Receiving host   (XReadStoreForward ... CommitStoreForward)
#
# Segment file name, for every media type, one token that sorts in write
# order and passes the Actor's name rule:
#
#   <writer>_<UTC open time to the microsecond>_<sequence><extension>
#   host3_2026-11-23_01-02-03-413882_000017.csv.gz
#
# Directories are the only seam with the Actor.  The writer creates each
# segment as a dot-prefixed temporary file in the outbox, which the
# Actor's watcher ignores, and renames it into place when it is complete.
# The reader claims a segment by moving it from the inbox into
# "processing/", emits its frames, and CommitStoreForward moves it into
# "done/" after every element before it has returned.  A segment that is
# still in "processing/" when the Pipeline restarts is emitted again, so
# delivery is at-least-once: the consumer must apply a segment
# idempotently.
#
# ADR-022 categorized exemption, value/data type: SegmentCodec,
# SegmentWriter and SegmentReader are in-process helpers of the
# PipelineElements below.  They are never on the message bus.  The
# PipelineElements are composed as usual.
#
# To Do
# ~~~~~
# - Move VideoWriteStoreForward onto WriteStoreForward with a video codec
# - Per-segment metadata in the Actor's upload description, so that a
#   binary codec needs no in-file header
#   (documentation/elements/media/store_forward_base.md, generality gaps)

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import logging
import os
import re
import threading
import time
from typing import Dict, List, Optional, Tuple
import uuid

import aiko_services as aiko
from aiko_services.main.store_forward.store_forward_message import (
    utc_now, valid_segment_name
)
import aiko_services.elements.media.scheme_store_forward  # "store_forward://"

__all__ = [
    "CommitStoreForward", "ReadStoreForward", "SegmentCodec",
    "SegmentReader", "SegmentWriter", "WriteStoreForward",
    "parse_segment_name", "segment_name"
]

_LOGGER = logging.getLogger(__name__)

WRITER_RE = re.compile(r"^[A-Za-z0-9-]{1,24}$")
_NAME_RE = re.compile(
    r"^(?P<writer>[A-Za-z0-9-]{1,24})"
    r"_(?P<utc>\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d-\d{6})"
    r"_(?P<sequence>\d{6,12})"
    r"(?P<extension>(\.[A-Za-z0-9]{1,8}){1,3})$")

DEFAULT_COMMIT_TIMEOUT = 600.0      # seconds before a claimed segment retries
DEFAULT_DONE_MAX_AGE = 2592000.0    # 30 days in "done/"; 0 keeps every one
DEFAULT_GAP_TIMEOUT = 900.0         # seconds to wait for a missing sequence
DEFAULT_MAX_ATTEMPTS = 3            # emissions of one segment, then rejected
DEFAULT_RATE = 1.0                  # inbox polls per second
REPLACE_RETRY_SECONDS = 5.0         # Windows: target held by another process
SWEEP_PERIOD = 3600.0               # seconds between "done/" sweeps

STATE_WRITER = "store_forward_write_{writer}.json"
STATE_READER = "store_forward_read.json"

# --------------------------------------------------------------------------- #
# Segment names

def segment_name(writer, sequence, extension, now=None) -> str:
    """Segment file name "<writer>_<UTC>_<sequence><extension>"."""

    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S-%f")
    return f"{writer}_{stamp}_{int(sequence):06d}{extension}"

def new_epoch() -> str:
    """A writer epoch: UTC to the microsecond and a random suffix, one
    token.  Unique, so that a writer whose state is lost and recreated in
    the same second is never mistaken for its predecessor."""

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"

def parse_segment_name(name) -> Optional[Tuple[str, str, int, str]]:
    """(writer, utc, sequence, extension), or None for a foreign name."""

    if not valid_segment_name(name):
        return None
    match = _NAME_RE.match(name)
    if not match:
        return None
    return (match["writer"], match["utc"], int(match["sequence"]),
            match["extension"])

# --------------------------------------------------------------------------- #
# Small file helpers

def _write_json_atomic(path, data):
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(data, file, sort_keys=True)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)

def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as error:
        _LOGGER.warning(f"store_forward: state {path} not readable: {error}")
        return default

def _replace_with_retry(source, target, seconds=REPLACE_RETRY_SECONDS):
    """os.replace(), retried while Windows reports the target in use."""

    deadline = time.monotonic() + seconds
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)

def _fsync_file(path):
    with open(path, "rb+") as file:
        os.fsync(file.fileno())

def _token(text, limit=32):
    """One Share token: non-token characters become "_" (Share values are
    not quoted)."""

    return re.sub(r"[^A-Za-z0-9._:@/-]", "_", str(text))[:limit] or "-"

# --------------------------------------------------------------------------- #
# SegmentCodec: what is particular to one media type.  Everything else
# (names, order, atomic write, claim, commit, retention) is generic

class SegmentCodec(ABC):
    """Turn frames into segment files and segment files back into frames.

    Writer side: open() a segment at a temporary path, append() frames to
    it until append() returns True (the segment is complete), then close()
    it.  Reader side: read_header() is cheap and is called for every
    waiting segment; read() returns the header and every frame."""

    @abstractmethod
    def extension(self) -> str:
        """File name extension, for example ".csv" or ".csv.gz"."""

    def split(self, fields: dict) -> List[dict]:
        """One frame's fields as one or more frames, each small enough for
        one segment.  Default: unchanged."""

        return [fields]

    @abstractmethod
    def open(self, path: str, header: dict) -> None:
        """Start a segment at "path" with the writer's header."""

    @abstractmethod
    def append(self, fields: dict) -> bool:
        """Add one frame; True when the segment must close now."""

    @abstractmethod
    def close(self) -> None:
        """Finish the segment that open() started."""

    @abstractmethod
    def read_header(self, path: str) -> dict:
        """The writer's header (raises ValueError when it does not parse)."""

    @abstractmethod
    def read(self, path: str) -> Tuple[dict, List[dict]]:
        """(header, frames); each frame is a dict of Pipeline fields."""

# --------------------------------------------------------------------------- #
# SegmentWriter: sequence state and the temporary-file-then-rename write

class SegmentWriter:
    """Write frames as segments into an outbox, in sequence order.

    State "store_forward_write_<writer>.json" in "state_directory" keeps
    the epoch (when the state was created) and the last sequence written.
    A sequence is persisted only after its segment is visible, so a failed
    write reuses the sequence.  A lost state file starts a new epoch, so a
    reader never mistakes a restarted sequence for an old one."""

    def __init__(self, outbox, writer, codec: SegmentCodec,
                 state_directory=".", logger=None):
        if not WRITER_RE.match(str(writer)):
            raise ValueError(
                f'segment_prefix "{writer}" must be [A-Za-z0-9-], 1 to 24')
        self.outbox = outbox
        self.writer = writer
        self.codec = codec
        self.logger = logger or _LOGGER
        self.state_path = os.path.join(
            state_directory, STATE_WRITER.format(writer=writer))
        state = _read_json(self.state_path, None)
        if not state or "epoch" not in state:
            state = {"epoch": new_epoch(), "sequence": 0}
            _write_json_atomic(self.state_path, state)
        self.epoch = str(state["epoch"])
        self.sequence = int(state.get("sequence", 0))
        self.segments_written = 0
        self._open = None            # (name, temporary path) while open

    def write(self, fields: dict) -> List[str]:
        """Write one frame; the names of the segments that became visible."""

        written = []
        for part in self.codec.split(fields):
            if self._open is None:
                self._open_segment()
            if self.codec.append(part):
                written.append(self._close_segment())
        return written

    def close(self) -> Optional[str]:
        """Close an open segment (end of Stream); its name, or None."""

        return self._close_segment() if self._open else None

    def _open_segment(self):
        sequence = self.sequence + 1
        name = segment_name(self.writer, sequence, self.codec.extension())
        temporary = os.path.join(self.outbox, f".{name}")
        header = {"writer": self.writer, "epoch": self.epoch,
                  "sequence": sequence, "created_utc": utc_now()}
        self.codec.open(temporary, header)
        self._open = (name, temporary)

    def _close_segment(self) -> str:
        name, temporary = self._open
        self._open = None
        try:
            self.codec.close()
            _fsync_file(temporary)
            _replace_with_retry(temporary, os.path.join(self.outbox, name))
        except OSError:
            try:
                os.remove(temporary)
            except OSError:
                pass
            raise
        self.sequence += 1
        self.segments_written += 1
        _write_json_atomic(self.state_path,
                           {"epoch": self.epoch, "sequence": self.sequence})
        return name

# --------------------------------------------------------------------------- #
# SegmentReader: inbox scan, per-writer order, claim, commit, retention

class SegmentReader:
    """Claim segments from an inbox one at a time, in per-writer order.

    Order key: (writer, epoch).  The next segment for a key has sequence
    last + 1.  A key with no state starts at its lowest sequence.  A
    missing sequence is waited for until the oldest waiting segment of
    that key has waited "gap_timeout" seconds, then skipped with a
    warning.  A sequence at or below the last applied is a duplicate and
    goes to "done/" without being emitted.

    One segment is in flight at a time.  commit() moves it to "done/" once
    every frame of it has been committed.  A segment not committed within
    "commit_timeout" is emitted again, at most "max_attempts" times, then
    moved to "rejected/".  The poll() and commit() methods may run on
    different threads."""

    def __init__(self, inbox, work_directory, codec: SegmentCodec,
                 file_glob=None, gap_timeout=DEFAULT_GAP_TIMEOUT,
                 commit_timeout=DEFAULT_COMMIT_TIMEOUT,
                 max_attempts=DEFAULT_MAX_ATTEMPTS,
                 done_max_age=DEFAULT_DONE_MAX_AGE, logger=None):
        self.inbox = inbox
        self.codec = codec
        self.extension = codec.extension()
        self.gap_timeout = float(gap_timeout)
        self.commit_timeout = float(commit_timeout)
        self.max_attempts = int(max_attempts)
        self.done_max_age = float(done_max_age)
        self.logger = logger or _LOGGER
        self.processing = os.path.join(work_directory, "processing")
        self.done = os.path.join(work_directory, "done")
        self.rejected = os.path.join(work_directory, "rejected")
        for directory in (self.processing, self.done, self.rejected):
            os.makedirs(directory, exist_ok=True)
        self.state_path = os.path.join(work_directory, STATE_READER)
        self.applied: Dict[str, int] = {
            key: int(value) for key, value in
            _read_json(self.state_path, {}).items()}
        self.lock = threading.Lock()
        self.in_flight = None        # dict, see _claim()
        self._first_seen: Dict[str, float] = {}
        self._headers: Dict[str, Tuple[float, dict]] = {}
        self._recovery = sorted(
            name for name in os.listdir(self.processing)
            if not name.startswith("."))
        self._last_sweep = 0.0
        self.counters = {"claimed": 0, "applied": 0, "duplicates": 0,
                         "gaps": 0, "rejected": 0, "retries": 0, "waiting": 0,
                         "oldest_waiting_s": 0}

    # Poll: called by the frame generator ---------------------------------- #

    def poll(self, now=None) -> Optional[Tuple[str, List[dict]]]:
        """(segment name, frames) for the next segment, or None."""

        now = time.monotonic() if now is None else now
        with self.lock:
            self._sweep(now)
            if self.in_flight:
                return self._retry_in_flight(now)
            while self._recovery:
                name = self._recovery.pop(0)
                result = self._emit(name, now, recovered=True)
                if result:
                    return result
            name = self._select(now)
            if name is None:
                return None
            try:
                _replace_with_retry(os.path.join(self.inbox, name),
                                    os.path.join(self.processing, name))
            except OSError as error:
                self.logger.warning(f"store_forward: cannot claim {name}: "
                                    f"{error}")
                return None
            self._first_seen.pop(name, None)
            self._headers.pop(name, None)
            return self._emit(name, now)

    def _select(self, now) -> Optional[str]:
        waiting: Dict[str, List[Tuple[int, str]]] = {}
        try:
            names = sorted(os.listdir(self.inbox))
        except OSError as error:
            self.logger.warning(f"store_forward: inbox not readable: {error}")
            return None
        for name in names:
            if name.startswith(".") or not name.endswith(self.extension):
                continue
            path = os.path.join(self.inbox, name)
            parsed = parse_segment_name(name)
            if parsed is None:
                self._reject(path, name, "name does not parse")
                continue
            header = self._header(path, name)
            if header is None:
                continue
            writer, _, sequence, _ = parsed
            if header.get("writer") != writer  \
                    or int(header.get("sequence", -1)) != sequence:
                self._reject(path, name, "header does not match name")
                continue
            self._first_seen.setdefault(name, now)
            key = f"{writer} {header.get('epoch', '-')}"
            waiting.setdefault(key, []).append((sequence, name))

        self.counters["waiting"] = sum(len(items) for items in waiting.values())
        oldest = min(self._first_seen.values(), default=now)
        self.counters["oldest_waiting_s"] = int(now - oldest)

        ready = []
        for key, items in waiting.items():
            items.sort()
            last = self.applied.get(key)
            for sequence, name in list(items):
                if last is not None and sequence <= last:
                    self._duplicate(name, key, sequence)
                    items.remove((sequence, name))
            if not items:
                continue
            sequence, name = items[0]
            if last is None or sequence == last + 1:
                ready.append(name)
                continue
            waited = now - min(self._first_seen[n] for _, n in items)
            if waited >= self.gap_timeout:
                self.logger.warning(
                    f"store_forward: {key}: sequences {last + 1} to "
                    f"{sequence - 1} did not arrive in {self.gap_timeout:.0f}"
                    f" s, continuing at {sequence}")
                self.counters["gaps"] += 1
                ready.append(name)
        return min(ready) if ready else None

    def _header(self, path, name) -> Optional[dict]:
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            return None
        cached = self._headers.get(name)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            header = self.codec.read_header(path)
        except (OSError, ValueError) as error:
            self._reject(path, name, f"header: {error}")
            return None
        self._headers[name] = (mtime, header)
        return header

    def _emit(self, name, now, recovered=False):
        path = os.path.join(self.processing, name)
        try:
            header, frames = self.codec.read(path)
        except (OSError, ValueError) as error:
            self._reject(path, name, f"read: {error}")
            return None
        if not frames:
            self._reject(path, name, "no frames")
            return None
        parsed = parse_segment_name(name)
        writer = parsed[0] if parsed else header.get("writer", "-")
        self.in_flight = {
            "name": name, "key": f"{writer} {header.get('epoch', '-')}",
            "sequence": int(header.get("sequence", parsed[2] if parsed else 0)),
            "frames": frames, "remaining": len(frames), "claimed": now,
            "attempts": 1}
        self.counters["claimed"] += 1
        if recovered:
            self.logger.info(f"store_forward: {name}: emitted again "
                             f"after a restart")
        return name, [dict(frame, segment=name) for frame in frames]

    def _retry_in_flight(self, now):
        flight = self.in_flight
        if now - flight["claimed"] < self.commit_timeout:
            return None
        if flight["attempts"] >= self.max_attempts:
            name = flight["name"]
            self.in_flight = None
            self._reject(os.path.join(self.processing, name), name,
                f"not committed after {flight['attempts']} attempts")
            return None
        flight["attempts"] += 1
        flight["claimed"] = now
        flight["remaining"] = len(flight["frames"])
        self.counters["retries"] += 1
        self.logger.warning(f"store_forward: {flight['name']}: not committed "
            f"in {self.commit_timeout:.0f} s, attempt {flight['attempts']}")
        return flight["name"], [dict(frame, segment=flight["name"])
                                for frame in flight["frames"]]

    # Commit: called by CommitStoreForward ---------------------------------- #

    def commit(self, name) -> bool:
        """Record one committed frame of "name"; True when the whole
        segment is committed and has moved to "done/"."""

        with self.lock:
            flight = self.in_flight
            if not flight or flight["name"] != name:
                self.logger.warning(
                    f"store_forward: commit of {name}, which is not in flight")
                return False
            flight["remaining"] -= 1
            if flight["remaining"] > 0:
                return False
            self.in_flight = None
            self._move_done(os.path.join(self.processing, name), name)
            self.applied[flight["key"]] = max(
                flight["sequence"], self.applied.get(flight["key"], 0))
            _write_json_atomic(self.state_path, self.applied)
            self.counters["applied"] += 1
            return True

    # Disposal and retention ------------------------------------------------ #

    def _move_done(self, path, name):
        target = os.path.join(self.done, name)
        try:
            _replace_with_retry(path, target)
            os.utime(target)         # age in "done/" counts from now
        except OSError as error:
            self.logger.warning(f"store_forward: {name}: not moved to done/: "
                                f"{error}")

    def _duplicate(self, name, key, sequence):
        self.counters["duplicates"] += 1
        self.logger.info(f"store_forward: {name}: {key} sequence {sequence} "
                         f"already applied, moved to done/")
        self._first_seen.pop(name, None)
        self._headers.pop(name, None)
        self._move_done(os.path.join(self.inbox, name), name)

    def _reject(self, path, name, reason):
        self.counters["rejected"] += 1
        self.logger.error(f"store_forward: {name}: rejected: {reason}")
        self._first_seen.pop(name, None)
        self._headers.pop(name, None)
        try:
            _replace_with_retry(path, os.path.join(self.rejected, name))
        except OSError as error:
            self.logger.error(f"store_forward: {name}: not moved to "
                              f"rejected/: {error}")

    def _sweep(self, now):
        if self.done_max_age <= 0 or now - self._last_sweep < SWEEP_PERIOD:
            return
        self._last_sweep = now
        cutoff = time.time() - self.done_max_age
        removed = 0
        for entry in os.scandir(self.done):
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    os.remove(entry.path)
                    removed += 1
            except OSError:
                pass
        if removed:
            self.logger.info(f"store_forward: done/: removed {removed} "
                             f"older than {self.done_max_age:.0f} s")

# --------------------------------------------------------------------------- #
# Readers shared between ReadStoreForward and CommitStoreForward, which run
# in the same Pipeline process: key (id(pipeline), stream_id)

_READERS: Dict[Tuple[int, str], SegmentReader] = {}
_READERS_LOCK = threading.Lock()

def _reader_key(element, stream):
    return (id(element.pipeline), str(stream.stream_id))

def _parameter_float(element, name, default):
    value, _ = element.get_parameter(name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f'parameter "{name}" must be a number: {value!r}')

# --------------------------------------------------------------------------- #
# WriteStoreForward is a DataTarget: each frame's fields go through the
# codec into segments in the outbox that a SegmentStoreForward Actor sends.
#
# parameter: "data_targets"     "(store_forward://OUTBOX_DIRECTORY)"
# parameter: "segment_prefix"   writer id, [A-Za-z0-9-] 1 to 24, required
# parameter: "state_directory"  sequence state ("."), keep it with the host
#
# Shared state: "outbox", "writer", "epoch", "sequence",
#               "segments_written", "last_segment_utc"
#
# A subclass sets CODEC to a callable that takes the element and returns a
# SegmentCodec.  A write failure returns StreamEvent.ERROR: the Stream
# stops rather than drop data, and the host's supervisor restarts it.

class WriteStoreForward(aiko.DataTarget):  # PipelineElement
    CODEC = None

    def __init__(self, context: aiko.ContextPipelineElement):
        context.call_init(self, "PipelineElement", context)
        self.share.update({"outbox": "-", "writer": "-", "epoch": "-",
            "sequence": "0", "segments_written": "0", "last_segment_utc": "-"})

    def start_stream(self, stream, stream_id):
        stream_event, diagnostic = super().start_stream(stream, stream_id)
        if stream_event != aiko.StreamEvent.OKAY:
            return stream_event, diagnostic
        writer_id, _ = self.get_parameter("segment_prefix", "")
        state_directory, _ = self.get_parameter("state_directory", ".")
        try:
            codec = type(self).CODEC(self)
            state_directory = os.path.expanduser(str(state_directory))
            os.makedirs(state_directory, exist_ok=True)
            writer = SegmentWriter(stream.variables["target_outbox"],
                str(writer_id), codec, state_directory, self.logger)
        except (OSError, TypeError, ValueError) as error:
            return aiko.StreamEvent.ERROR, {"diagnostic": str(error)}
        stream.variables["segment_writer"] = writer
        self.ec_producer.update("writer", writer.writer)
        self.ec_producer.update("epoch", writer.epoch)
        self.ec_producer.update("sequence", str(writer.sequence))
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, **fields) -> Tuple[aiko.StreamEvent, dict]:
        writer = stream.variables.get("segment_writer")
        if writer is None:
            return aiko.StreamEvent.ERROR,  \
                {"diagnostic": "WriteStoreForward: no segment writer"}
        try:
            names = writer.write(fields)
        except (OSError, TypeError, ValueError) as error:
            diagnostic = f"WriteStoreForward: segment not written: {error}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        self._published(writer, names)
        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        writer = stream.variables.pop("segment_writer", None)
        if writer is not None:
            try:
                name = writer.close()
                self._published(writer, [name] if name else [])
            except OSError as error:
                self.logger.error(f"WriteStoreForward: last segment: {error}")
        if stream.variables.get("data_scheme"):
            return super().stop_stream(stream, stream_id)
        return aiko.StreamEvent.OKAY, {}

    def _published(self, writer, names):
        if not names:
            return
        self.ec_producer.update("sequence", str(writer.sequence))
        self.ec_producer.update(
            "segments_written", str(writer.segments_written))
        self.ec_producer.update("last_segment_utc", utc_now())
        for name in names:
            self.logger.debug(f"{self.my_id()}: segment {name}")

# --------------------------------------------------------------------------- #
# ReadStoreForward is a DataSource: it polls the inbox that a
# SegmentStoreForward Actor fills and emits the frames of one segment at a
# time, in per-writer sequence order.  Each frame carries "segment" (the
# file name) for CommitStoreForward.
#
# parameter: "data_sources"    "(store_forward://INBOX_DIRECTORY)"
# parameter: "work_directory"  holds processing/, done/, rejected/ and the
#                              reader state; outside the inbox, required
# parameter: "rate"            inbox polls per second (1.0)
# parameter: "gap_timeout"     seconds to wait for a missing sequence (900)
# parameter: "commit_timeout"  seconds before an uncommitted segment is
#                              emitted again (600)
# parameter: "max_attempts"    emissions before "rejected/" (3)
# parameter: "done_max_age"    seconds a segment stays in "done/"
#                              (2592000, 30 days; 0 keeps every one)
#
# Shared state: "inbox", "claimed", "applied", "waiting",
#               "oldest_waiting_s", "gaps", "duplicates", "rejected",
#               "retries"
#
# The PipelineDefinition lists the codec's frame fields and "segment" as
# this element's inputs and outputs.

class ReadStoreForward(aiko.DataSource):  # PipelineElement
    CODEC = None

    def __init__(self, context: aiko.ContextPipelineElement):
        context.call_init(self, "PipelineElement", context)
        self.share.update({"inbox": "-", "claimed": "0", "applied": "0",
            "waiting": "0", "oldest_waiting_s": "0", "gaps": "0",
            "duplicates": "0", "rejected": "0", "retries": "0"})

    def start_stream(self, stream, stream_id):
        stream.variables["store_forward_reader_factory"] = self._make_reader
        return super().start_stream(stream, stream_id,
            frame_generator=self._frame_generator, use_create_frame=False)

    def _make_reader(self, stream, inbox, work_directory):
        """Called by DataSchemeStoreForward.create_sources()."""

        reader = SegmentReader(inbox, work_directory, type(self).CODEC(self),
            gap_timeout=_parameter_float(
                self, "gap_timeout", DEFAULT_GAP_TIMEOUT),
            commit_timeout=_parameter_float(
                self, "commit_timeout", DEFAULT_COMMIT_TIMEOUT),
            max_attempts=int(_parameter_float(
                self, "max_attempts", DEFAULT_MAX_ATTEMPTS)),
            done_max_age=_parameter_float(
                self, "done_max_age", DEFAULT_DONE_MAX_AGE),
            logger=self.logger)
        with _READERS_LOCK:
            _READERS[_reader_key(self, stream)] = reader
        return reader

    def _frame_generator(self, stream, frame_id):
        reader = stream.variables.get("store_forward_reader")
        if reader is None:
            return aiko.StreamEvent.ERROR,  \
                {"diagnostic": "ReadStoreForward: no segment reader"}
        result = reader.poll()
        if result is None:
            return aiko.StreamEvent.NO_FRAME, {}
        _, frames = result
        return aiko.StreamEvent.OKAY, frames

    def process_frame(self, stream, **fields) -> Tuple[aiko.StreamEvent, dict]:
        reader = stream.variables.get("store_forward_reader")
        if reader is not None:
            publish_counters(self, reader)
        return aiko.StreamEvent.OKAY, fields

    def stop_stream(self, stream, stream_id):
        with _READERS_LOCK:
            _READERS.pop(_reader_key(self, stream), None)
        stream.variables.pop("store_forward_reader", None)
        return super().stop_stream(stream, stream_id)

def publish_counters(element, reader):
    """Publish a SegmentReader's counters in "element"'s shared state."""

    for name, value in reader.counters.items():
        if element.share.get(name) != str(value):
            element.ec_producer.update(name, str(value))

# --------------------------------------------------------------------------- #
# CommitStoreForward is the last element after a ReadStoreForward: it runs
# only when every element before it returned StreamEvent.OKAY, and then
# moves the segment from "processing/" to "done/".
#
# input: "segment", the file name that ReadStoreForward put in the frame

class CommitStoreForward(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("commit_store_forward:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, segment) -> Tuple[aiko.StreamEvent, dict]:
        with _READERS_LOCK:
            reader = _READERS.get(_reader_key(self, stream))
        if reader is None:
            diagnostic = "CommitStoreForward needs a ReadStoreForward "  \
                         "earlier in the same Pipeline and Stream"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        if reader.commit(str(segment)):
            self.logger.debug(f"{self.my_id()}: segment {segment} done")
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
