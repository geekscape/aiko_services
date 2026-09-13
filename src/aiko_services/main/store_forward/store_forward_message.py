# Aiko Services: StoreForward "StoreForwardMessage" layer seam
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# A StoreForwardMessage moves S-expression "(command ...)" function calls
# and segment bytes between two hosts across an unreliable link.  It sits
# above the framework's publish / subscribe "aiko.Message" (message/): an
# HTTP implementation is built on Flask and requests, a later MQTT push
# implementation on aiko.message.publish() and Actor "/in" topics.  It is
# named "StoreForwardMessage" (MQTT, HTTP, ZMQ, ...) rather than "Transport", which is
# the OSI name for the TCP / UDP layer.
#
# This module has no other Aiko Services import, so implementations can be
# tested without an event loop or an MQTT server.  The SegmentStoreForward
# Actor (store_forward.py) owns all shared state; implementations report
# through two callbacks, invoked on the implementation's own threads ...
#
#   on_command(payload) -> "accepted" | "rejected_parse" | "rejected_command"
#       An S-expression "(command arg ...)" received from the peer
#
#   on_event(segment_id, event, detail)
#       Progress of a segment, or "-" as segment_id for link-level events
#
# Every queue in an implementation is bounded (P9) and the overflow policy
# is drop-newest, reported to the caller as False.
#
# Not part of the Interface composition pattern yet (see ADR-022): this seam
# is a plain ABC, as main/message/message.py is.  TODO: compose it as an
# Interface with Interface.default() and "...Impl" classes.
#
# To Do
# ~~~~~
# - MQTT push implementation (store_forward_mqtt.py) on aiko.message
# - ZMQ implementation (store_forward_zmq.py): Aiko Services ZMQ uses 6502
# - Compose per ADR-022 (above)

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
import os
import queue
import re
import threading
from typing import Callable, Optional

__all__ = [
    "CHUNK_SIZE", "COMMAND_QUEUE_SIZE", "CONNECT_DEADLINE", "IDLE_TIMEOUT",
    "JOB_QUEUE_SIZE", "MAX_INCOMING", "MAX_SEGMENT_SIZE", "OUT_QUEUE_SIZE",
    "PARTIAL_DIRECTORY", "PROGRESS_EVERY_CHUNKS",
    "LINK_ID", "NAME_EVENT", "PROGRESS_EVENT", "RESUME_EVENT",
    "STORE_FORWARD_EVENTS", "RECEIVED_EVENTS", "LINK_EVENTS",
    "FetchJob", "StoreForwardMessage", "SendJob",
    "resolve_within", "sha256_file", "store_forward_deadline", "try_put",
    "valid_sha256", "valid_segment_name", "valid_segment_id"
]

# --------------------------------------------------------------------------- #
# Limits: every buffer has a bound and a stated overflow policy (P9)

CHUNK_SIZE = 64 * 1024                # bytes per HTTP PATCH / Range read
MAX_SEGMENT_SIZE = 64 * 1024 * 1024   # reject larger segments
MAX_INCOMING = 4                      # concurrent uploads accepted by a server
JOB_QUEUE_SIZE = 16                   # send / fetch jobs: drop-newest
COMMAND_QUEUE_SIZE = 64               # outgoing "(command ...)": drop-newest
OUT_QUEUE_SIZE = 256                  # server "/out" items: drop-newest
CONNECT_DEADLINE = 60.0               # seconds to first successful request
IDLE_TIMEOUT = 120.0                  # seconds before an idle upload is evicted
PROGRESS_EVERY_CHUNKS = 8             # rate limit for progress events
PARTIAL_DIRECTORY = ".partial"        # under the inbox: resumable parts
MIN_RATE_BYTES_PER_SECOND = 50 * 1024 # sizes the overall transfer deadline

LINK_ID = "-"                         # segment_id for link-level events

# Event names, grouped by the shared state item that the Actor updates.
# Detail is a single token: sha256, "bytes/size", an HTTP status or a reason.

STORE_FORWARD_EVENTS = {                   # -> store_forwards.<id>
    "queued", "hashing", "offered", "connecting", "sending", "fetching",
    "verifying", "done", "cancelled", "failed_timeout", "failed_sha256",
    "failed_http", "rejected_busy"
}
RECEIVED_EVENTS = {                   # -> received.<id>
    "receiving", "received_verifying", "received_ok",
    "received_failed_sha256", "received_failed_timeout"
}
LINK_EVENTS = {                       # segment_id == LINK_ID
    "link_up", "link_down", "peer_poll", "out_dropped", "rejected_command"
}
PROGRESS_EVENT = "progress"           # -> progress.<id> = "bytes/size"
RESUME_EVENT = "resume"               # -> metrics.resumes += 1
NAME_EVENT = "name"                   # detail = segment name (receiver side)

# --------------------------------------------------------------------------- #
# Validation at the boundary (P12): identifiers, names and paths

_SEGMENT_ID_RE = re.compile(r"^[a-f0-9]{8,32}$")
_SEGMENT_NAME_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

def valid_segment_id(segment_id) -> bool:
    return isinstance(segment_id, str)  \
        and bool(_SEGMENT_ID_RE.match(segment_id))

def valid_segment_name(name) -> bool:
    return isinstance(name, str) and bool(_SEGMENT_NAME_RE.match(name))

def valid_sha256(sha256) -> bool:
    return isinstance(sha256, str) and bool(_SHA256_RE.match(sha256))

def resolve_within(directory, name) -> Optional[str]:
    """Return the real path of "directory/name" when it stays inside the
    real "directory" (symbolic links resolved), else None"""

    if not valid_segment_name(name):
        return None
    directory = os.path.realpath(directory)
    path = os.path.realpath(os.path.join(directory, name))
    try:
        if os.path.commonpath([directory, path]) != directory:
            return None
    except ValueError:  # different drives (Windows) or mixed absolute paths
        return None
    return path

def sha256_file(path, chunk_size=1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()

def store_forward_deadline(size) -> float:
    """Seconds allowed for a whole transfer: at least two minutes, and
    never faster than MIN_RATE_BYTES_PER_SECOND"""

    return max(120.0, float(size) / MIN_RATE_BYTES_PER_SECOND)

def try_put(bounded_queue, item) -> bool:
    """Drop-newest put: False when the bounded queue is full"""

    try:
        bounded_queue.put_nowait(item)
        return True
    except queue.Full:
        return False

# --------------------------------------------------------------------------- #
# Jobs: immutable descriptions handed from the Actor to Message threads.
# The Actor owns the cancel Event and sets it; threads only read it.

@dataclass(frozen=True)
class SendJob:
    segment_id: str
    name: str
    path: str                 # real path inside the outbox
    size: int
    cancel: threading.Event = field(default_factory=threading.Event)

@dataclass(frozen=True)
class FetchJob:
    segment_id: str
    name: str
    size: int
    sha256: str
    cancel: threading.Event = field(default_factory=threading.Event)

# --------------------------------------------------------------------------- #

class StoreForwardMessage(ABC):
    """Moves "(command ...)" S-expressions and segment bytes to a peer.
    Implementations never touch the Actor's shared state: they call
    on_command() and on_event() from their own threads and the Actor posts
    the result onto its own mailbox"""

    role: str = "?"           # "server" or "edge"

    @abstractmethod
    def start(self,
        on_command: Callable[[str], str],
        on_event: Callable[[str, str, str], None]) -> str:
        """Start threads; return the endpoint description, e.g a URL"""

    @abstractmethod
    def stop(self) -> None:
        """Stop threads and release sockets, bounded wait"""

    @abstractmethod
    def send_segment(self, job: SendJob) -> bool:
        """Queue a segment for the peer: False when the job queue is full"""

    @abstractmethod
    def fetch_segment(self, job: FetchJob) -> bool:
        """Queue a download offered by the peer: False when full or when
        the role cannot fetch"""

    @abstractmethod
    def send_command(self, payload: str) -> bool:
        """Queue one "(command arg ...)" for the peer: False when full"""

    @abstractmethod
    def cancel(self, segment_id: str) -> None:
        """Release any server-side resources for a transfer"""

# --------------------------------------------------------------------------- #
