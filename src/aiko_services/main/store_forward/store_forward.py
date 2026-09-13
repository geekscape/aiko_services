#!/usr/bin/env python3
#
# Aiko Services: SegmentStoreForward Actor, one per host
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Bi-directional store / forward of segments (files: video segments, images,
# tensors) between two hosts across an unreliable link.  The Actor takes
# custody of a segment dropped in its outbox and delivers it to the peer's
# inbox, verified by sha256, resuming after any interruption.  The Actor
# owns all shared state and the one-way command surface; a
# StoreForwardMessage implementation (store_forward_http.py) moves the bytes
# and the "(command ...)" S-expressions between the hosts.
#
# Roles: the "server" host runs the HTTP routes; the "edge" host is always
# the client, polls the server and needs no inbound ports.  No Aiko Services
# (MQTT) traffic crosses the link: each host runs its own mosquitto and
# aiko_registrar, so its Actor appears on its own Dashboard.
#
# Sending is triggered by dropping a segment into the outbox (watched every
# --outbox_period seconds), or by publishing to the Actor's topic ...
#
#   mosquitto_pub -t $TOPIC_IN -m "(send_segment 0123abcd notes.txt)"
#
# Usage
# ~~~~~
#   Each host: mosquitto and aiko_registrar with AIKO_MQTT_HOST=localhost
#   Server host: pip install flask
#
#   aiko_store_forward server --inbox ~/st/in --outbox ~/st/out  \
#       [--http_port_range 8080-8089] [--advertise_host HOST]
#   aiko_store_forward edge --inbox ~/st/in --outbox ~/st/out  \
#       --server_url http://HOST:8080
#
#   cp segment.mp4 ~/st/out     # either host: arrives in the peer's inbox
#
# Wire commands (one-way, no return values) ...
#   (send_segment SEGMENT_ID NAME)
#   (fetch_segment SEGMENT_ID NAME SIZE SHA256)     edge host only
#   (acknowledge SEGMENT_ID SHA256 STATUS)
#   (cancel SEGMENT_ID)
#   (forget SEGMENT_ID)
#
# Shared state (observe via aiko_dashboard) ...
#   role, inbox, outbox, http_endpoint | server_url
#   link            up@TIME | down@TIME | unknown
#                   edge host: from the /out poll
#                   server host: from edge host activity, down after
#                   --link_timeout seconds without a poll
#   peer.last_poll  server host: time of the last /out poll
#   store_forwards.<id>  queued|hashing|offered|connecting|sending|fetching|
#                   verifying|done|acked|cancelled|failed_*|rejected_*
#   received.<id>   receiving|verifying|ok|failed_sha256|failed_timeout
#   progress.<id>   <bytes>/<size>
#                   (each table keeps the last STATE_LIMIT segments)
#   metrics.*       sent_bytes received_bytes resumes failures
#                   rejected_commands out_dropped
#
# Protocol: store_forward:0
#
# To Do
# ~~~~~
# - Actor discovery by name, protocol and tags replacing --server_url
# - Heart-beat with QoS statistics on the poll
# - MQTT push and store / forward StoreForwardMessage implementations
# - SQLite3 for the store / forward state-of-play

from abc import abstractmethod
import os
import sys
import threading
import time
import uuid

import click

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname, parse

from aiko_services import __version__
from aiko_services.main.store_forward.store_forward_message import (
    CHUNK_SIZE, LINK_EVENTS, LINK_ID, MAX_SEGMENT_SIZE, NAME_EVENT,
    PROGRESS_EVENT, RECEIVED_EVENTS, RESUME_EVENT, STORE_FORWARD_EVENTS,
    FetchJob, SendJob,
    resolve_within, valid_segment_name, valid_sha256, valid_segment_id
)

__all__ = [
    "ALLOWED_COMMANDS", "PROTOCOL", "PROTOCOL_TYPE",
    "SegmentStoreForward", "SegmentStoreForwardImpl"
]

_VERSION = 0

PROTOCOL_TYPE = "store_forward"
ACTOR_TYPE = "segment_store_forward"
PROTOCOL = f"{aiko.SERVICE_PROTOCOL_AIKO}/{PROTOCOL_TYPE}:{_VERSION}"

STATE_LIMIT = 3                # last segments kept per store_forwards / received /
                               # progress table: oldest evicted
BOOKKEEPING_LIMIT = 64         # ids remembered for sizes, names, sha256
SENT_NAMES_LIMIT = 1024        # outbox names already sent: drop oldest
SENT_DIRECTORY = ".sent"       # under the outbox: acknowledged segments
LINK_TIMEOUT = 10.0            # server: seconds without an Edge poll -> down

_FAILED_PREFIXES = ("failed_", "rejected_")
_LOG_INFO_STATES = {"queued", "offered", "done", "acked", "cancelled"}

_RECEIVED_STATES = {           # Message event -> received.<id>
    "receiving": "receiving",
    "received_verifying": "verifying",
    "received_ok": "ok",
    "received_failed_sha256": "failed_sha256",
    "received_failed_timeout": "failed_timeout"
}

def _stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def _remember(table, key, value, limit=BOOKKEEPING_LIMIT):
    table[key] = value
    while len(table) > limit:
        del table[next(iter(table))]

# --------------------------------------------------------------------------- #

class SegmentStoreForward(aiko.Actor):
    """
    Takes custody of segments (files) for a peer host across an unreliable
    link and delivers them, verified by sha256, resuming after interruption
    (concepts/store_forward.md).  One Actor per host, role "server" or
    "edge".  Every method is one-way; outcomes are observed in share
    ("store_forwards.<id>", "received.<id>", "progress.<id>", "link",
    "metrics.*"), never returned.  Segment ids are hexadecimal, 8 to 32
    characters, chosen by the sender
    """
    aiko.Interface.default("SegmentStoreForward",
        "aiko_services.main.store_forward.store_forward.SegmentStoreForwardImpl")

    @abstractmethod
    def send_segment(self, segment_id, name):
        """Get the outbox segment "name" to the peer.  Arguments: segment_id
        (hex token), name (file name inside the outbox, no path).
        Wire form: "(send_segment SEGMENT_ID NAME)" on topic_in.  Outcome:
        share "store_forwards.<id>" queued ... done, acked.
        Projection: command"""

    @abstractmethod
    def fetch_segment(self, segment_id, name, size, sha256):
        """Download a segment the peer offered (edge role only).  Arguments:
        segment_id, name, size (bytes), sha256 (hex).  Wire form:
        "(fetch_segment SEGMENT_ID NAME SIZE SHA256)", sent by the server
        role through its message layer.  Outcome: share "received.<id>" ok,
        then "(acknowledge ...)" back to the peer.  Projection: command"""

    @abstractmethod
    def acknowledge(self, segment_id, sha256, status):
        """Peer confirms a segment arrived intact.  Arguments: segment_id,
        sha256 (must match the segment sent), status ("ok").  Wire form:
        "(acknowledge SEGMENT_ID SHA256 STATUS)".  Outcome: share
        "store_forwards.<id>" acked and the outbox copy moves to .sent/.
        Idempotent.  Projection: command"""

    @abstractmethod
    def cancel(self, segment_id):
        """Stop a segment in progress.  Wire form: "(cancel SEGMENT_ID)".
        Outcome: share "store_forwards.<id>" cancelled when the worker
        notices.  Projection: command"""

    @abstractmethod
    def forget(self, segment_id):
        """Remove a segment from the shared state tables.  Wire form:
        "(forget SEGMENT_ID)".  Outcome: "store_forwards.<id>",
        "received.<id>" and "progress.<id>" are removed.
        Projection: command"""

# The HTTP "(command ...)" allow-list is seeded from the Interface (P12):
# only these public declarations may be dispatched from the peer.

ALLOWED_COMMANDS = frozenset(name
    for name, member in vars(SegmentStoreForward).items()
    if getattr(member, "__isabstractmethod__", False)
    and not name.startswith("_"))

# --------------------------------------------------------------------------- #

class SegmentStoreForwardImpl(SegmentStoreForward):
    def __init__(self, context):
        context.call_init(self, "Actor", context)
        parameters = context.get_parameters()
        self.message = parameters["message"]           # StoreForwardMessage
        self.inbox = os.path.realpath(parameters["inbox"])
        self.outbox = os.path.realpath(parameters["outbox"])
        self.outbox_period = float(parameters.get("outbox_period", 2.0))
        self.link_timeout = float(parameters.get("link_timeout", LINK_TIMEOUT))
        self.loop_thread = threading.get_ident()      # asserted by tests
        self.last_event_thread = None                  # asserted by tests

        self._jobs = {}            # segment_id -> SendJob | FetchJob
        self._names = {}           # segment_id -> segment name (bounded)
        self._sizes = {}           # segment_id -> size in bytes (bounded)
        self._sha256 = {}          # segment_id -> sha256 sent (bounded)
        self._sent_names = {}      # outbox name -> segment_id (bounded)
        self._pending_outbox = {}  # outbox name -> (size, mtime) seen once
        self._warned_names = set() # outbox names already reported as bad
        self._link = "unknown"
        self._last_poll = None     # monotonic time of the last Edge poll
        self._metrics = {
            "sent_bytes": 0, "received_bytes": 0, "resumes": 0,
            "failures": 0, "rejected_commands": 0, "out_dropped": 0
        }
        self.share.update({                            # initial snapshot
            "source_file": f"v{_VERSION}⇒ {__file__}",
            "role": self.message.role,
            "inbox": self.inbox,
            "outbox": self.outbox,
            "link": "unknown",
            "store_forwards": {}, "received": {}, "progress": {},
            "metrics": dict(self._metrics)
        })

        os.makedirs(os.path.join(self.outbox, SENT_DIRECTORY), exist_ok=True)
        endpoint = self.message.start(self._http_command, self._message_event)
        endpoint_key = "http_endpoint"  \
            if self.message.role == "server" else "server_url"
        self.ec_producer.update(endpoint_key, endpoint)

        if self.outbox_period > 0:
            aiko.event.add_timer_handler(self._outbox_scan, self.outbox_period)
        if self.message.role == "server":
            aiko.event.add_timer_handler(
                self._link_check, max(1.0, self.link_timeout / 2))

        self.logger.info(f"{self.message.role} {context.name}: {endpoint}")
        self.logger.info(f"inbox: {self.inbox}")
        self.logger.info(f"outbox: {self.outbox} (scan every "
            f"{self.outbox_period} s, sent segments move to {SENT_DIRECTORY}/)")
        print(f"MQTT topic: {self.topic_in}")

    # Wire commands (event-loop thread) ------------------------------------- #

    def send_segment(self, segment_id, name):
        if not valid_segment_id(segment_id):
            return self._reject_command(
                f"send_segment: bad id {segment_id!r} (hex, 8-32 chars)")
        if segment_id in self._jobs or segment_id in self.share["store_forwards"]:
            return                                     # idempotent
        _remember(self._names, segment_id, str(name))
        path = resolve_within(self.outbox, name)
        if not path:
            return self._reject_store_forward(segment_id, "rejected_path",
                "name must be [A-Za-z0-9_-][A-Za-z0-9._-]* and inside outbox")
        if not os.path.isfile(path):
            return self._reject_store_forward(segment_id, "rejected_missing",
                f"{path} is not a regular file")
        size = os.path.getsize(path)
        if size > MAX_SEGMENT_SIZE:
            return self._reject_store_forward(segment_id, "rejected_size",
                f"{size} B exceeds {MAX_SEGMENT_SIZE} B")
        job = SendJob(segment_id, name, path, size)
        if not self.message.send_segment(job):
            return self._reject_store_forward(segment_id, "rejected_busy",
                "send queue full")
        self._jobs[segment_id] = job
        _remember(self._sizes, segment_id, size)
        self._set_store_forward(segment_id, "queued", f"{size} B")

    def fetch_segment(self, segment_id, name, size, sha256):
        if not valid_segment_id(segment_id):
            return self._reject_command(
                f"fetch_segment: bad id {segment_id!r} (hex, 8-32 chars)")
        if segment_id in self._jobs:
            return                                     # idempotent
        _remember(self._names, segment_id, str(name))
        if self.message.role != "edge":
            return self._reject_store_forward(segment_id, "rejected_role",
                "only the edge host fetches")
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = -1
        if not valid_segment_name(name) or not valid_sha256(sha256)  \
            or size < 0 or size > MAX_SEGMENT_SIZE:
            return self._reject_store_forward(segment_id, "rejected_path",
                f"bad name, size or sha256: {name!r} {size} {sha256!r}")
        job = FetchJob(segment_id, name, size, sha256)
        if not self.message.fetch_segment(job):
            return self._reject_store_forward(segment_id, "rejected_busy",
                "fetch queue full")
        self._jobs[segment_id] = job
        _remember(self._sizes, segment_id, size)
        self._set_store_forward(segment_id, "fetching", f"{size} B")

    def acknowledge(self, segment_id, sha256, status):
        if not valid_segment_id(segment_id):
            return self._reject_command(
                f"acknowledge: bad id {segment_id!r}")
        expected = self._sha256.get(segment_id)
        if expected and expected == sha256 and status == "ok":
            self._set_store_forward(segment_id, "acked")
            self.message.cancel(segment_id)           # release any offer
            self._move_to_sent(segment_id)
        else:
            self.logger.warning(f"acknowledge {segment_id} "
                f"{self._names.get(segment_id, '?')}: ignored, status "
                f"{status!r}, sha256 {sha256[:12]!r} expected "
                f"{(expected or '?')[:12]!r}")

    def cancel(self, segment_id):
        if not valid_segment_id(segment_id):
            return self._reject_command(f"cancel: bad id {segment_id!r}")
        job = self._jobs.get(segment_id)
        if job:
            job.cancel.set()
            self.logger.info(f"cancel {segment_id} {job.name}: requested")
        self.message.cancel(segment_id)

    def forget(self, segment_id):
        if not valid_segment_id(segment_id):
            return self._reject_command(f"forget: bad id {segment_id!r}")
        for table in ("store_forwards", "received", "progress"):
            if segment_id in self.share[table]:
                self.ec_producer.remove(f"{table}.{segment_id}")
        for table in (self._jobs, self._names, self._sizes, self._sha256):
            table.pop(segment_id, None)

    # Message layer hand-off (event-loop thread) ---------------------------- #

    def _store_forward_event(self, segment_id, event, detail):
        """Posted by _message_event() from message-layer threads.  Reachable from
        the local bus too, so every argument is validated"""

        self.last_event_thread = threading.get_ident()
        if not isinstance(event, str) or not isinstance(detail, str):
            return self._reject_command("_store_forward_event: bad arguments")
        if segment_id == LINK_ID:
            if event in LINK_EVENTS:
                self._link_event(event, detail)
            return
        if not valid_segment_id(segment_id):
            return self._reject_command(
                f"_store_forward_event: bad id {segment_id!r}")
        name = self._names.get(segment_id, "?")

        if event in STORE_FORWARD_EVENTS:
            state = f"failed_http_{detail}" if event == "failed_http" else event
            self._set_store_forward(segment_id, state, detail)
            if event in ("offered", "done") and valid_sha256(detail):
                _remember(self._sha256, segment_id, detail)
            if event == "done":
                self._add_metric("sent_bytes", self._sizes.get(segment_id, 0))
                if isinstance(self._jobs.get(segment_id), SendJob):
                    self._move_to_sent(segment_id)
            if state.startswith(_FAILED_PREFIXES):
                self._add_metric("failures", 1)
            if state.startswith(_FAILED_PREFIXES)  \
                or state in ("done", "acked", "cancelled"):
                self._jobs.pop(segment_id, None)
        elif event in RECEIVED_EVENTS:
            state = _RECEIVED_STATES[event]
            self._set_state("received", segment_id, state)
            if event == "receiving" and "/" in detail:
                _remember(self._sizes, segment_id, int(detail.split("/")[1]))
            size = self._sizes.get(segment_id, 0)
            if event == "received_ok":
                self._add_metric("received_bytes", size)
                self.logger.info(
                    f"received {segment_id} {name}: ok, {size} B, "
                    f"sha256 {detail[:12]}, into {self.inbox}")
                if not self.message.send_command(
                    f"(acknowledge {segment_id} {detail} ok)"):
                    self.logger.warning(f"received {segment_id} {name}: "
                        "acknowledge not queued (command queue full)")
            elif event.startswith("received_failed"):
                self._add_metric("failures", 1)
                self.logger.warning(
                    f"received {segment_id} {name}: {state} {detail}")
            elif event == "receiving" and detail.startswith("0/"):
                self.logger.info(f"receiving {segment_id}: {size} B")
        elif event == NAME_EVENT:
            if valid_segment_name(detail):
                _remember(self._names, segment_id, detail)
        elif event == PROGRESS_EVENT:
            self._set_state("progress", segment_id, detail)
        elif event == RESUME_EVENT:
            self._add_metric("resumes", 1)
            self.logger.info(f"store_forward {segment_id} {name}: "
                f"resumed at byte {detail}")
        else:
            self._reject_command(
                f"_store_forward_event {segment_id}: unknown event {event!r}")

    def _link_event(self, event, detail):
        if event == "link_up":
            self._set_link("up", detail or "server host reachable")
        elif event == "link_down":
            self._set_link("down", detail or "server host unreachable")
        elif event == "peer_poll":
            self._last_poll = time.monotonic()
            self.ec_producer.update("peer.last_poll", detail)
            if hasattr(self.message, "out_queue_depth"):
                self.ec_producer.update("out_queue_depth",
                    str(self.message.out_queue_depth()))
            if self._link != "up":
                self._set_link("up", "edge host polling /out")
        elif event == "out_dropped":
            self._metrics["out_dropped"] = int(detail)
            self.ec_producer.update("metrics.out_dropped", detail)
            self.logger.warning(f"/out queue full: {detail} commands dropped")
        elif event == "rejected_command":
            self._add_metric("rejected_commands", 1)
            if not detail.startswith("local:"):  # local ones are logged already
                self.logger.warning(
                    f"peer rejected or dropped a command: {detail}")

    def _link_check(self):
        """Server role timer: no edge poll for link_timeout -> link down"""

        if self._link != "up" or self._last_poll is None:
            return
        idle = time.monotonic() - self._last_poll
        if idle > self.link_timeout:
            self._set_link("down",
                f"no poll from the edge host for {int(idle)} s")

    def _set_link(self, state, reason):
        if state == self._link:
            return
        self._link = state
        self.ec_producer.update("link", f"{state}@{_stamp()}")
        if state == "up":
            self.logger.info(f"link up: {reason}")
        else:
            self.logger.warning(f"link down: {reason}")

    # Callbacks invoked on Message threads: post, never touch state -------- #

    def _http_command(self, payload) -> str:
        result = "accepted"
        try:
            command, arguments = parse(payload)
        except Exception:                  # the parser raises on odd tokens
            result = "rejected_parse"
        else:
            if command not in ALLOWED_COMMANDS:
                result = "rejected_command"
            elif not isinstance(arguments, list) or not all(
                isinstance(argument, str) for argument in arguments):
                result = "rejected_parse"
        if result != "accepted":
            self.logger.warning(f"{result} from peer: {payload[:80]!r}")
            self._post_message(aiko.ActorTopic.IN, "_store_forward_event",
                [LINK_ID, "rejected_command", f"local:{result}"])
            return result
        self._post_message(aiko.ActorTopic.IN, command, arguments)
        return result

    def _message_event(self, segment_id, event, detail):
        self._post_message(aiko.ActorTopic.IN, "_store_forward_event",
            [str(segment_id), str(event), str(detail)])

    # Outbox watcher (event-loop timer): list only, no hashing or IO ------- #

    def _outbox_scan(self):
        try:
            entries = list(os.scandir(self.outbox))
        except OSError as os_error:
            self.logger.warning(f"outbox scan failed: {os_error}")
            return
        seen = set()
        for entry in entries:
            name = entry.name
            if name.startswith(".") or not entry.is_file(follow_symlinks=False):
                continue
            if name in self._sent_names:
                continue
            if not valid_segment_name(name):
                if name not in self._warned_names:
                    self._warned_names.add(name)
                    self.logger.warning(f"outbox: ignoring {name!r}, names "
                        "must match [A-Za-z0-9_-][A-Za-z0-9._-]{0,127}")
                continue
            stat = entry.stat(follow_symlinks=False)
            signature = (stat.st_size, stat.st_mtime_ns)
            seen.add(name)
            if self._pending_outbox.get(name) == signature:  # stable: send
                del self._pending_outbox[name]
                segment_id = uuid.uuid4().hex[:12]
                self._remember_sent(name, segment_id)
                self.send_segment(segment_id, name)
            else:
                self._pending_outbox[name] = signature   # still being written
        for name in list(self._pending_outbox):
            if name not in seen:
                del self._pending_outbox[name]

    def _remember_sent(self, name, segment_id):
        _remember(self._sent_names, name, segment_id, SENT_NAMES_LIMIT)

    def _move_to_sent(self, segment_id):
        job = self._jobs.get(segment_id)
        name = job.name if isinstance(job, SendJob) else None
        if not name:
            for sent_name, sent_id in self._sent_names.items():
                if sent_id == segment_id:
                    name = sent_name
        if not name:
            return
        source = os.path.join(self.outbox, name)
        target = os.path.join(self.outbox, SENT_DIRECTORY, name)
        try:
            if os.path.isfile(source):
                os.replace(source, target)
        except OSError as os_error:
            self.logger.warning(
                f"store_forward {segment_id} {name}: move to {SENT_DIRECTORY}/ "
                f"failed: {os_error}")
        self._sent_names.pop(name, None)

    # Shared state: bounded tables and counters ---------------------------- #

    def _set_store_forward(self, segment_id, state, detail=""):
        self._set_state("store_forwards", segment_id, state)
        name = self._names.get(segment_id, "?")
        if valid_sha256(detail):
            detail = f"sha256 {detail[:12]}"
        if state.startswith(_FAILED_PREFIXES):
            self.logger.warning(
                f"store_forward {segment_id} {name}: {state} {detail}".rstrip())
        elif state in _LOG_INFO_STATES:
            self.logger.info(
                f"store_forward {segment_id} {name}: {state} {detail}".rstrip())
        else:
            self.logger.debug(f"store_forward {segment_id} {name}: {state}")

    def _reject_store_forward(self, segment_id, state, diagnostic):
        self._set_store_forward(segment_id, state, f"({diagnostic})")

    def _set_state(self, table, segment_id, state):
        """Keep each table to the last STATE_LIMIT segments: oldest first"""

        current = self.share.get(table, {})
        while segment_id not in current and len(current) >= STATE_LIMIT:
            self.ec_producer.remove(f"{table}.{next(iter(current))}")
        self.ec_producer.update(f"{table}.{segment_id}", state)

    def _add_metric(self, name, increment):
        self._metrics[name] += int(increment)
        self.ec_producer.update(f"metrics.{name}", str(self._metrics[name]))

    def _reject_command(self, diagnostic):
        self.logger.warning(diagnostic)
        self._add_metric("rejected_commands", 1)

# --------------------------------------------------------------------------- #

def _port_range(text):
    tokens = text.split("-")
    if len(tokens) == 1:
        tokens = [tokens[0], tokens[0]]
    try:
        first, last = int(tokens[0]), int(tokens[1])
    except ValueError:
        raise click.BadParameter(f'"{text}" must be PORT or FIRST-LAST')
    if first < 1 or last < first:
        raise click.BadParameter(f'"{text}" must be PORT or FIRST-LAST')
    return first, last

def _run(name, role, message, inbox, outbox, outbox_period, link_timeout):
    parameters = {
        "message": message, "inbox": inbox, "outbox": outbox,
        "outbox_period": outbox_period, "link_timeout": link_timeout
    }
    init_args = aiko.actor_args(name,
        parameters=parameters, protocol=PROTOCOL, tags=[f"role={role}"])
    try:
        aiko.compose_instance(SegmentStoreForwardImpl, init_args)
    except OSError as os_error:
        click.echo(f"store_forward {role}: cannot start: {os_error}", err=True)
        sys.exit(1)
    aiko.process.run()

def _common_options(function):
    options = [
        click.option("--name", "-n", default=None,
            help="Actor name (default: store_forward_<hostname>_<role>)"),
        click.option("--inbox", "-i", required=True,
            type=click.Path(exists=True, file_okay=False),
            help="Directory that receives segments from the peer"),
        click.option("--outbox", "-o", required=True,
            type=click.Path(exists=True, file_okay=False),
            help="Directory watched for segments to send"),
        click.option("--outbox_period", "-op", default=2.0, show_default=True,
            help="Seconds between outbox scans (0 disables)"),
        click.option("--chunk_size", "-cs", default=CHUNK_SIZE,
            show_default=True, help="Bytes per HTTP chunk")
    ]
    for option in reversed(options):
        function = option(function)
    return function

def _default_name(name, role):
    return name or f"store_forward_{get_hostname()}_{role}"

@click.group(help="Aiko Services: segment store / forward between two hosts")

def main():
    pass

@main.command(help="Run the server host Actor and its HTTP routes")
@_common_options
@click.option("--http_port_range", "-pr", default="8080-8089", show_default=True,
    help="TCP port or FIRST-LAST range to bind (Aiko Services ZMQ uses 6502)")
@click.option("--bind", "-b", default="0.0.0.0", show_default=True,
    help="Interface address to bind")
@click.option("--advertise_host", "-ah", default=None,
    help="Host name in the advertised endpoint (default: this host name)")
@click.option("--link_timeout", "-lt", default=LINK_TIMEOUT, show_default=True,
    help="Seconds without an edge host poll before link is down")

def server(name, inbox, outbox, outbox_period, chunk_size,
    http_port_range, bind, advertise_host, link_timeout):

    from aiko_services.main.store_forward.store_forward_http import (
        StoreForwardMessageHTTPServer
    )
    message = StoreForwardMessageHTTPServer(inbox, outbox, bind=bind,
        port_range=_port_range(http_port_range),
        advertise_host=advertise_host, chunk_size=chunk_size)
    _run(_default_name(name, "server"), "server", message,
        inbox, outbox, outbox_period, link_timeout)

@main.command(help="Run the edge host Actor, polling the server host")
@_common_options
@click.option("--server_url", "-su", required=True,
    help="server host endpoint, e.g http://HOST:8080")
@click.option("--poll_period", "-pp", default=2.0, show_default=True,
    help="Seconds between /out polls")

def edge(name, inbox, outbox, outbox_period, chunk_size,
    server_url, poll_period):

    from aiko_services.main.store_forward.store_forward_http import (
        StoreForwardMessageHTTPClient
    )
    message = StoreForwardMessageHTTPClient(server_url, inbox, outbox,
        poll_period=poll_period, chunk_size=chunk_size)
    _run(_default_name(name, "edge"), "edge", message,
        inbox, outbox, outbox_period, LINK_TIMEOUT)

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
