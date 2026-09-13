# Aiko Services: StoreForward HTTP message layer (Flask, requests)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# One Flask web server runs on the server host (role "server").  The edge
# host (role "edge") is always the HTTP client, so only the edge host needs
# to reach the server host across the unreliable link (no inbound ports on
# the edge host) ...
#
#   POST /in                   "(command arg ...)" from the edge host
#   GET  /out?after=SEQ        outstanding "(command ...)" for the Edge
#                              Computer, polled; items are retained until a
#                              later poll carries after >= seq
#   POST /data/<id>            create an upload {name, size, sha256}
#                              -> 201 Upload-Offset (resume point)
#   HEAD /data/<id>            Upload-Offset of an upload, or Content-Length
#                              and X-Sha256 of an offered download
#   PATCH /data/<id>           append one chunk at header Upload-Offset
#                              -> 204 Upload-Offset, or 409 Upload-Offset
#   POST /data/<id>/complete   verify sha256, move into the inbox
#   GET  /data/<id>            download an offered segment (Range supported)
#   GET  /health               {"version": ..., "role": "server"}
#
# Upload follows a minimal subset of the tus resumable upload protocol
# (offset based), download uses HTTP Range: established mechanisms rather
# than a bespoke scheme (P10).  Uploads land in <inbox>/.partial/<id>.part
# with a same-stem .meta JSON sidecar, then move atomically into the inbox.
#
# Threads (P2): the Flask server thread (werkzeug per-request threads),
# one server worker (hashing offered segments, evicting idle uploads); on
# the client a poller, a job thread and a command thread.  None of them
# touch Actor state: they call on_command() / on_event() only.
#
# Flask is not an Aiko Services dependency: "pip install flask" on the
# server host.  The client needs only "requests" (a core dependency).
#
# To Do
# ~~~~~
# - TLS and authentication (LAN only until then)
# - Replace the werkzeug development server before production use

from collections import deque
import json
import logging
import os
import re
import socket
import threading
import time
from typing import Dict, Optional

import requests

_FLASK_IMPORTED = False
try:
    from flask import Flask, jsonify, request, send_file
    from werkzeug.serving import make_server
    _FLASK_IMPORTED = True
except ModuleNotFoundError:  # server role only: "pip install flask"
    pass

from aiko_services import __version__
from aiko_services.main.store_forward.store_forward_message import (
    CHUNK_SIZE, COMMAND_QUEUE_SIZE, CONNECT_DEADLINE, IDLE_TIMEOUT,
    JOB_QUEUE_SIZE, LINK_ID, MAX_INCOMING, MAX_SEGMENT_SIZE, OUT_QUEUE_SIZE,
    NAME_EVENT, PARTIAL_DIRECTORY, PROGRESS_EVENT, PROGRESS_EVERY_CHUNKS,
    RESUME_EVENT,
    FetchJob, StoreForwardMessage, SendJob, utc_now,
    resolve_within, sha256_file, store_forward_deadline, try_put,
    valid_segment_name, valid_sha256, valid_segment_id
)

import queue

__all__ = ["StoreForwardMessageHTTPClient", "StoreForwardMessageHTTPServer"]

_LOGGER = logging.getLogger(__name__)

_ID_ROUTE = "<regex('[a-f0-9]{8,32}'):segment_id>"
_MAX_OFFERS = 32                  # offered downloads kept: evict oldest
_IN_RATE_LIMIT = 64               # POST /in accepted per second, else 429
_BACKOFF_MAX = 30.0               # seconds between retries after a failure
_TIMEOUTS = (5.0, 30.0)           # requests (connect, read) seconds
API_VERSION = "v0"                # HTTP route contract; changes move to /v1

# --------------------------------------------------------------------------- #

class _Cancelled(Exception):
    pass

class _Deadline(Exception):
    pass

class _HttpStatus(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code

def _describe(exception, limit=160):
    """Short, diagnosable text for a requests exception: the innermost
    OS error where there is one, e.g "ConnectionError: Connection refused" """

    cause = exception
    while getattr(cause, "__cause__", None)  \
        or getattr(cause, "__context__", None):
        cause = cause.__cause__ or cause.__context__
    text = str(cause) or str(exception)
    text = re.sub(r"<[^>]*>", "", text).strip(" :")   # drop object reprs
    return f"{type(exception).__name__}: {text}"[:limit]

def _partial_paths(inbox, segment_id):
    directory = os.path.join(inbox, PARTIAL_DIRECTORY)
    os.makedirs(directory, exist_ok=True)
    stem = os.path.join(directory, segment_id)
    return f"{stem}.part", f"{stem}.meta"

def _finish_download(inbox, name, part_path, meta_path):
    """Atomic move of a verified part into the inbox; returns the path"""

    path = os.path.join(os.path.realpath(inbox), name)
    os.replace(part_path, path)
    if os.path.exists(meta_path):
        os.remove(meta_path)
    return path

def _discard(*paths):
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

# --------------------------------------------------------------------------- #

class _Incoming:
    """One upload in progress on the server"""

    def __init__(self, name, size, sha256, part_path, meta_path, offset):
        self.name = name
        self.size = size
        self.sha256 = sha256
        self.part_path = part_path
        self.meta_path = meta_path
        self.offset = offset
        self.chunks = 0
        self.last_activity = time.monotonic()
        self.lock = threading.Lock()

class _Offer:
    """One segment offered for download by the server"""

    def __init__(self, name, path, size, sha256):
        self.name = name
        self.path = path
        self.size = size
        self.sha256 = sha256

# --------------------------------------------------------------------------- #

class StoreForwardMessageHTTPServer(StoreForwardMessage):
    role = "server"

    def __init__(self, inbox, outbox, bind="0.0.0.0", port_range=(8080, 8089),
        advertise_host=None, chunk_size=CHUNK_SIZE):

        self.inbox = os.path.realpath(inbox)
        self.outbox = os.path.realpath(outbox)
        self.bind = bind
        self.port_range = port_range
        self.advertise_host = advertise_host or socket.gethostname()
        self.chunk_size = int(chunk_size)

        self._on_command = None
        self._on_event = None
        self._server = None
        self._server_thread = None
        self._worker_thread = None
        self._stop = threading.Event()

        self._lock = threading.Lock()          # guards the three tables below
        self._out_items = deque()              # (seq, payload), bounded
        self._out_seq = 0
        self._out_dropped = 0
        self._offers: Dict[str, _Offer] = {}
        self._incoming: Dict[str, _Incoming] = {}
        self._in_times = deque()               # POST /in times (rate limit)

        self._jobs = queue.Queue(maxsize=JOB_QUEUE_SIZE)
        self.port = None
        self.endpoint = None

    # StoreForwardMessage interface ---------------------------------------- #

    def start(self, on_command, on_event):
        if not _FLASK_IMPORTED:
            raise OSError('flask not installed: "pip install flask"')
        self._on_command = on_command
        self._on_event = on_event
        os.makedirs(os.path.join(self.inbox, PARTIAL_DIRECTORY), exist_ok=True)

        app = self._create_app()
        first, last = self.port_range
        error = None
        for port in range(first, last + 1):
            # werkzeug prints a hint and calls sys.exit(1) when the port is
            # in use, so SystemExit must be caught as well as OSError to
            # try the next port in the range
            try:
                self._server = make_server(self.bind, port, app, threaded=True)
                self.port = self._server.server_port  # port 0: ephemeral
                break
            except (OSError, SystemExit) as exception:
                error = f"port {port} in use or not permitted ({exception})"
        if not self._server:
            raise OSError(
                f"no free HTTP port in {first}-{last} on {self.bind}: {error}")

        self._server_thread = threading.Thread(
            target=self._server.serve_forever, daemon=True,
            name="store_forward_http_server")
        self._server_thread.start()
        self._worker_thread = threading.Thread(
            target=self._worker, daemon=True, name="store_forward_http_worker")
        self._worker_thread.start()

        self.endpoint = f"http://{self.advertise_host}:{self.port}"
        return self.endpoint

    def stop(self):
        self._stop.set()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        for thread in (self._server_thread, self._worker_thread):
            if thread:
                thread.join(timeout=2.0)

    def send_segment(self, job: SendJob) -> bool:
        return try_put(self._jobs, job)

    def fetch_segment(self, job: FetchJob) -> bool:
        return False                           # the server never fetches

    def send_command(self, payload: str) -> bool:
        with self._lock:
            if len(self._out_items) >= OUT_QUEUE_SIZE:
                self._out_dropped += 1
                dropped = self._out_dropped
            else:
                self._out_seq += 1
                self._out_items.append((self._out_seq, payload))
                dropped = None
        if dropped is not None:
            self._event(LINK_ID, "out_dropped", str(dropped))
            return False
        return True

    def cancel(self, segment_id):
        with self._lock:
            self._offers.pop(segment_id, None)
            incoming = self._incoming.pop(segment_id, None)
        if incoming:
            _discard(incoming.part_path, incoming.meta_path)

    # Introspection for tests and the Actor -------------------------------- #

    def out_queue_depth(self) -> int:
        with self._lock:
            return len(self._out_items)

    # Worker: hash offered segments, evict idle uploads --------------------- #

    def _event(self, segment_id, event, detail=""):
        if self._on_event:
            self._on_event(segment_id, event, str(detail))

    def _worker(self):
        while not self._stop.is_set():
            try:
                job = self._jobs.get(timeout=1.0)
            except queue.Empty:
                self._evict_idle()
                continue
            try:
                self._offer(job)
            except Exception as exception:  # never kill the worker thread
                _LOGGER.error(f"offer {job.segment_id}: {exception}")
                self._event(job.segment_id, "failed_http", "offer")

    def _offer(self, job: SendJob):
        if job.cancel.is_set():
            self._event(job.segment_id, "cancelled")
            return
        self._event(job.segment_id, "hashing")
        sha256 = sha256_file(job.path)
        with self._lock:
            while len(self._offers) >= _MAX_OFFERS:
                oldest = next(iter(self._offers))
                del self._offers[oldest]
            self._offers[job.segment_id] =  \
                _Offer(job.name, job.path, job.size, sha256)
        payload = f"(fetch_segment {job.segment_id} {job.name} "  \
                  f"{job.size} {sha256})"
        if self.send_command(payload):
            self._event(job.segment_id, "offered", sha256)
        else:
            self._event(job.segment_id, "rejected_busy", "out_queue")

    def _evict_idle(self):
        now = time.monotonic()
        expired = []
        with self._lock:
            for segment_id, incoming in list(self._incoming.items()):
                if now - incoming.last_activity > IDLE_TIMEOUT:
                    expired.append(segment_id)
                    del self._incoming[segment_id]  # the .part stays on disk
        for segment_id in expired:
            self._event(segment_id, "received_failed_timeout", "idle")

    # Flask application ----------------------------------------------------- #

    def _create_app(self):
        from werkzeug.routing import BaseConverter

        class RegexConverter(BaseConverter):
            def __init__(self, url_map, *items):
                super().__init__(url_map)
                self.regex = items[0]

        app = Flask("store_forward")
        app.url_map.converters["regex"] = RegexConverter
        app.config["MAX_CONTENT_LENGTH"] = self.chunk_size
        logging.getLogger("werkzeug").setLevel(logging.WARNING)

        app.add_url_rule("/health", view_func=self._health, methods=["GET"])
        app.add_url_rule("/in", view_func=self._in, methods=["POST"])
        app.add_url_rule("/out", view_func=self._out, methods=["GET"])
        app.add_url_rule(f"/data/{_ID_ROUTE}", view_func=self._data_create,
            methods=["POST"])
        app.add_url_rule(f"/data/{_ID_ROUTE}", view_func=self._data_patch,
            methods=["PATCH"])
        app.add_url_rule(f"/data/{_ID_ROUTE}", view_func=self._data_get_head,
            methods=["GET", "HEAD"])
        app.add_url_rule(f"/data/{_ID_ROUTE}/complete",
            view_func=self._data_complete, methods=["POST"])
        return app

    def _health(self):
        return jsonify({"role": self.role, "version": API_VERSION,
            "package": __version__})

    def _in(self):
        now = time.monotonic()
        with self._lock:
            while self._in_times and now - self._in_times[0] > 1.0:
                self._in_times.popleft()
            if len(self._in_times) >= _IN_RATE_LIMIT:
                return jsonify({"status": "rejected_busy"}), 429
            self._in_times.append(now)

        payload = request.get_data(as_text=True).strip()
        result = self._on_command(payload) if self._on_command else "accepted"
        if result == "accepted":
            return jsonify({"status": "accepted"}), 202
        if result == "rejected_parse":
            return jsonify({"status": "rejected_parse"}), 400
        return jsonify({"status": "rejected_command"}), 403

    def _out(self):
        try:
            after = int(request.args.get("after", "0"))
        except ValueError:
            return jsonify({"status": "rejected_parse"}), 400
        with self._lock:
            while self._out_items and self._out_items[0][0] <= after:
                self._out_items.popleft()
            items = [{"seq": seq, "payload": payload}
                     for seq, payload in self._out_items]
        self._event(LINK_ID, "peer_poll", utc_now())
        return jsonify({"items": items})

    def _data_create(self, segment_id):
        meta = request.get_json(silent=True) or {}
        name = meta.get("name")
        size = meta.get("size")
        sha256 = meta.get("sha256")
        if not valid_segment_name(name) or not valid_sha256(sha256)  \
            or not isinstance(size, int) or size < 0:
            return jsonify({"status": "rejected_parse"}), 400
        if size > MAX_SEGMENT_SIZE:
            return jsonify({"status": "rejected_size"}), 413

        with self._lock:
            incoming = self._incoming.get(segment_id)
            if incoming:                      # re-creation: report the offset
                return self._offset_response(incoming.offset, 200)
            if len(self._incoming) >= MAX_INCOMING:
                return jsonify({"status": "rejected_busy"}), 409

            part_path, meta_path = _partial_paths(self.inbox, segment_id)
            offset = 0
            if os.path.exists(part_path):
                previous = {}
                try:
                    with open(meta_path) as file:
                        previous = json.load(file)
                except (OSError, ValueError):
                    pass
                if previous.get("sha256") == sha256:
                    offset = min(os.path.getsize(part_path), size)
                    if offset < os.path.getsize(part_path):
                        with open(part_path, "r+b") as file:
                            file.truncate(offset)
                else:
                    _discard(part_path, meta_path)
            if not os.path.exists(part_path):
                open(part_path, "wb").close()
            with open(meta_path, "w") as file:
                json.dump({"name": name, "size": size, "sha256": sha256}, file)
            self._incoming[segment_id] =  \
                _Incoming(name, size, sha256, part_path, meta_path, offset)
        self._event(segment_id, NAME_EVENT, name)
        self._event(segment_id, "receiving", f"{offset}/{size}")
        return self._offset_response(offset, 201)

    def _offset_response(self, offset, status):
        response = jsonify({"status": "ok"})
        response.status_code = status
        response.headers["Upload-Offset"] = str(offset)
        return response

    def _data_get_head(self, segment_id):
        if request.method == "HEAD":
            return self._data_head(segment_id)
        return self._data_get(segment_id)

    def _data_head(self, segment_id):
        with self._lock:
            incoming = self._incoming.get(segment_id)
            offer = self._offers.get(segment_id)
        if incoming:
            response = jsonify({})
            response.headers["Upload-Offset"] = str(incoming.offset)
            return response
        if offer:
            response = jsonify({})
            response.headers["Content-Length"] = str(offer.size)
            response.headers["X-Sha256"] = offer.sha256
            return response
        return jsonify({"status": "unknown"}), 404

    def _data_patch(self, segment_id):
        try:
            offset = int(request.headers.get("Upload-Offset", ""))
        except ValueError:
            return jsonify({"status": "rejected_parse"}), 400
        with self._lock:
            incoming = self._incoming.get(segment_id)
        if not incoming:
            return jsonify({"status": "unknown"}), 404

        chunk = request.get_data()
        with incoming.lock:
            if offset != incoming.offset:
                return self._offset_response(incoming.offset, 409)
            if incoming.offset + len(chunk) > incoming.size:
                return jsonify({"status": "rejected_size"}), 400
            with open(incoming.part_path, "ab") as file:
                file.write(chunk)
            incoming.offset += len(chunk)
            incoming.chunks += 1
            incoming.last_activity = time.monotonic()
            offset = incoming.offset
            report = incoming.chunks % PROGRESS_EVERY_CHUNKS == 0  \
                or offset == incoming.size
        if report:
            self._event(
                segment_id, PROGRESS_EVENT, f"{offset}/{incoming.size}")
        return self._offset_response(offset, 204)

    def _data_complete(self, segment_id):
        with self._lock:
            incoming = self._incoming.get(segment_id)
        if not incoming:
            return jsonify({"status": "unknown"}), 404
        with incoming.lock:
            if incoming.offset != incoming.size:
                return self._offset_response(incoming.offset, 409)
            self._event(segment_id, "received_verifying")
            sha256 = sha256_file(incoming.part_path)
            with self._lock:
                self._incoming.pop(segment_id, None)
            if sha256 != incoming.sha256:
                _discard(incoming.part_path, incoming.meta_path)
                self._event(segment_id, "received_failed_sha256", sha256)
                return jsonify({"status": "failed_sha256"}), 422
            _finish_download(self.inbox, incoming.name,
                incoming.part_path, incoming.meta_path)
        self._event(segment_id, "received_ok", sha256)
        return jsonify({"status": "ok"}), 200

    def _data_get(self, segment_id):
        with self._lock:
            offer = self._offers.get(segment_id)
        if not offer:
            return jsonify({"status": "unknown"}), 404
        response = send_file(offer.path, mimetype="application/octet-stream",
            conditional=True)
        response.headers["X-Sha256"] = offer.sha256
        return response

# --------------------------------------------------------------------------- #

class StoreForwardMessageHTTPClient(StoreForwardMessage):
    role = "edge"

    def __init__(self, server_url, inbox, outbox, poll_period=2.0,
        chunk_size=CHUNK_SIZE, connect_deadline=CONNECT_DEADLINE):

        self.server_url = server_url.rstrip("/")
        self.inbox = os.path.realpath(inbox)
        self.outbox = os.path.realpath(outbox)
        self.poll_period = float(poll_period)
        self.chunk_size = int(chunk_size)
        self.connect_deadline = float(connect_deadline)

        self._on_command = None
        self._on_event = None
        self._stop = threading.Event()
        self._session = requests.Session()
        self._threads = []
        self._jobs = queue.Queue(maxsize=JOB_QUEUE_SIZE)
        self._commands = queue.Queue(maxsize=COMMAND_QUEUE_SIZE)
        self._after = 0                        # /out cursor
        self._link_up = None                   # unknown until the first poll

    # StoreForwardMessage interface ---------------------------------------- #

    def start(self, on_command, on_event):
        self._on_command = on_command
        self._on_event = on_event
        os.makedirs(os.path.join(self.inbox, PARTIAL_DIRECTORY), exist_ok=True)
        for name, target in (
            ("store_forward_http_poller", self._poller),
            ("store_forward_http_jobs", self._job_worker),
            ("store_forward_http_commands", self._command_worker)):
            thread = threading.Thread(target=target, daemon=True, name=name)
            thread.start()
            self._threads.append(thread)
        return self.server_url

    def stop(self):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._session.close()

    def send_segment(self, job: SendJob) -> bool:
        return try_put(self._jobs, job)

    def fetch_segment(self, job: FetchJob) -> bool:
        return try_put(self._jobs, job)

    def send_command(self, payload: str) -> bool:
        return try_put(self._commands, payload)

    def cancel(self, segment_id):
        pass                                   # the Actor sets job.cancel

    # Helpers --------------------------------------------------------------- #

    def _event(self, segment_id, event, detail=""):
        if self._on_event:
            self._on_event(segment_id, event, str(detail))

    def _url(self, path):
        return f"{self.server_url}{path}"

    def _set_link(self, up, cause="", text=""):
        """Report a link change once: "cause" is a single token for share
        (e.g ConnectionError), "text" the diagnosable detail for the log"""

        if self._link_up != up:
            self._link_up = up
            detail = f"{cause} {text}".strip()
            self._event(LINK_ID, "link_up" if up else "link_down", detail)

    def _retry(self, deadline, cancel, function):
        """Call function() until it returns without a connection or read
        error; exponential back-off, bounded by the deadline and cancel"""

        backoff = 1.0
        while True:
            if cancel and cancel.is_set():
                raise _Cancelled()
            if self._stop.is_set():
                raise _Cancelled()
            try:
                return function()
            except (requests.ConnectionError, requests.Timeout) as exception:
                self._set_link(False, type(exception).__name__,
                    _describe(exception))
                if time.monotonic() + backoff > deadline:
                    raise _Deadline()
                self._stop.wait(backoff)
                backoff = min(backoff * 2.0, _BACKOFF_MAX)

    # Poller: GET /out ------------------------------------------------------ #

    def _poller(self):
        backoff = self.poll_period
        while not self._stop.is_set():
            try:
                response = self._session.get(self._url("/out"),
                    params={"after": self._after}, timeout=_TIMEOUTS)
                if response.status_code != 200:
                    raise requests.ConnectionError(
                        f"/out HTTP {response.status_code}")
                items = response.json().get("items", [])
                self._set_link(True, "server_reachable")
                backoff = self.poll_period
                for item in items:
                    seq = int(item.get("seq", 0))
                    payload = str(item.get("payload", ""))
                    if seq > self._after:
                        self._after = seq
                        if self._on_command:
                            result = self._on_command(payload)
                            if result != "accepted":
                                self._event(
                                    LINK_ID, "rejected_command", result)
            except (requests.RequestException, ValueError) as exception:
                self._set_link(False, type(exception).__name__,
                    f"GET {self._url('/out')}: {_describe(exception)}")
                backoff = min(backoff * 2.0, _BACKOFF_MAX)
            self._stop.wait(backoff)

    # Command worker: POST /in ---------------------------------------------- #

    def _command_worker(self):
        while not self._stop.is_set():
            try:
                payload = self._commands.get(timeout=1.0)
            except queue.Empty:
                continue
            deadline = time.monotonic() + self.connect_deadline * 5
            try:
                response = self._retry(deadline, None,
                    lambda: self._session.post(self._url("/in"), data=payload,
                        headers={"Content-Type": "text/plain"},
                        timeout=_TIMEOUTS))
                if response.status_code != 202:
                    self._event(LINK_ID, "rejected_command",
                        str(response.status_code))
                else:
                    self._set_link(True, "server_reachable")
            except (_Deadline, _Cancelled):
                self._event(LINK_ID, "rejected_command", "deadline")

    # Job worker: uploads and downloads ------------------------------------- #

    def _job_worker(self):
        while not self._stop.is_set():
            try:
                job = self._jobs.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                if isinstance(job, SendJob):
                    self._upload(job)
                else:
                    self._download(job)
            except _Cancelled:
                self._event(job.segment_id, "cancelled")
            except _Deadline:
                self._event(job.segment_id, "failed_timeout")
            except _HttpStatus as http_status:
                self._event(job.segment_id, "failed_http",
                    str(http_status.status_code))
            except Exception as exception:  # never kill the worker thread
                _LOGGER.error(f"job {job.segment_id}: {exception}")
                self._event(job.segment_id, "failed_http", "exception")

    def _upload(self, job: SendJob):
        segment_id = job.segment_id
        self._event(segment_id, "hashing")
        sha256 = sha256_file(job.path)
        self._event(segment_id, "connecting")
        url = self._url(f"/data/{segment_id}")
        meta = {"name": job.name, "size": job.size, "sha256": sha256}

        response = self._retry(time.monotonic() + self.connect_deadline,
            job.cancel, lambda: self._session.post(url, json=meta,
                timeout=_TIMEOUTS))
        if response.status_code not in (200, 201):
            raise _HttpStatus(response.status_code)
        self._set_link(True, "server_reachable")
        offset = int(response.headers.get("Upload-Offset", "0"))
        if offset:
            self._event(segment_id, RESUME_EVENT, str(offset))

        deadline = time.monotonic() + store_forward_deadline(job.size)
        self._event(segment_id, "sending", f"{offset}/{job.size}")
        chunks = 0
        with open(job.path, "rb") as file:
            while offset < job.size:
                file.seek(offset)
                chunk = file.read(self.chunk_size)
                if not chunk:
                    break
                headers = {"Upload-Offset": str(offset),
                    "Content-Type": "application/offset+octet-stream"}
                try:
                    response = self._retry(deadline, job.cancel,
                        lambda: self._session.patch(url, data=chunk,
                            headers=headers, timeout=_TIMEOUTS))
                except _Deadline:
                    raise
                if response.status_code == 204:
                    offset = int(response.headers["Upload-Offset"])
                elif response.status_code == 409:
                    offset = int(response.headers.get("Upload-Offset", "0"))
                    self._event(segment_id, RESUME_EVENT, str(offset))
                    continue
                elif response.status_code == 404:
                    # server lost the upload (restart): re-create and resume
                    response = self._retry(deadline, job.cancel,
                        lambda: self._session.post(url, json=meta,
                            timeout=_TIMEOUTS))
                    if response.status_code not in (200, 201):
                        raise _HttpStatus(response.status_code)
                    offset = int(response.headers.get("Upload-Offset", "0"))
                    self._event(segment_id, RESUME_EVENT, str(offset))
                    continue
                else:
                    raise _HttpStatus(response.status_code)
                chunks += 1
                if chunks % PROGRESS_EVERY_CHUNKS == 0 or offset == job.size:
                    self._event(segment_id, PROGRESS_EVENT,
                        f"{offset}/{job.size}")

        self._event(segment_id, "verifying", sha256)
        response = self._retry(deadline, job.cancel,
            lambda: self._session.post(f"{url}/complete", timeout=_TIMEOUTS))
        if response.status_code == 200:
            self._event(segment_id, "done", sha256)
        elif response.status_code == 422:
            self._event(segment_id, "failed_sha256", sha256)
        else:
            raise _HttpStatus(response.status_code)

    def _download(self, job: FetchJob):
        segment_id = job.segment_id
        url = self._url(f"/data/{segment_id}")
        part_path, meta_path = _partial_paths(self.inbox, segment_id)
        with open(meta_path, "w") as file:
            json.dump({"name": job.name, "size": job.size,
                       "sha256": job.sha256}, file)
        # Create the part now, so a zero-byte segment (no GET at all) still
        # has a part to hash and move; drop a stale part larger than size
        offset = os.path.getsize(part_path) if os.path.exists(part_path) else 0
        if offset > job.size:
            offset = 0
        with open(part_path, "ab") as file:
            file.truncate(offset)
        self._event(segment_id, NAME_EVENT, job.name)
        self._event(segment_id, "fetching", f"{offset}/{job.size}")
        if offset:
            self._event(segment_id, RESUME_EVENT, str(offset))

        deadline = time.monotonic() + store_forward_deadline(job.size)
        chunks = 0
        while offset < job.size:
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            response = self._retry(deadline, job.cancel,
                lambda: self._session.get(url, headers=headers, stream=True,
                    timeout=_TIMEOUTS))
            if response.status_code == 200:
                offset = 0                     # server ignored Range: restart
                mode = "wb"
            elif response.status_code == 206:
                mode = "ab"
            else:
                raise _HttpStatus(response.status_code)
            self._set_link(True, "server_reachable")
            try:
                with open(part_path, mode) as file:
                    for chunk in response.iter_content(self.chunk_size):
                        if job.cancel.is_set():
                            raise _Cancelled()
                        file.write(chunk)
                        offset += len(chunk)
                        chunks += 1
                        if chunks % PROGRESS_EVERY_CHUNKS == 0:
                            self._event(segment_id, PROGRESS_EVENT,
                                f"{offset}/{job.size}")
            except (requests.ConnectionError, requests.Timeout) as exception:
                self._set_link(False, type(exception).__name__,
                    _describe(exception))
                self._event(segment_id, RESUME_EVENT, str(offset))
                if time.monotonic() > deadline:
                    raise _Deadline()
                self._stop.wait(1.0)
            finally:
                response.close()

        self._event(segment_id, PROGRESS_EVENT, f"{offset}/{job.size}")
        self._event(segment_id, "received_verifying")
        sha256 = sha256_file(part_path)
        if sha256 != job.sha256:
            _discard(part_path, meta_path)
            self._event(segment_id, "received_failed_sha256", sha256)
            return
        _finish_download(self.inbox, job.name, part_path, meta_path)
        self._event(segment_id, "received_ok", sha256)
        self._event(segment_id, "done", sha256)

# --------------------------------------------------------------------------- #
