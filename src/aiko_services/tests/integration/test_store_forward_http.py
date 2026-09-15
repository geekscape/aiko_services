# Aiko Services StoreForward: HTTP "StoreForwardMessage" layer tests, server and client on 127.0.0.1
#
# No Aiko Services, event loop or MQTT server required.
#
#   pytest [-s] integration/test_store_forward_http.py

import errno
import hashlib
import os
import socket
import threading
import time

import pytest
import requests

pytest.importorskip("flask",
    reason="StoreForward HTTP server needs flask: pip install flask")

from aiko_services.main.store_forward.store_forward_message import (
    MAX_INCOMING, MAX_SEGMENT_SIZE, OUT_QUEUE_SIZE, PARTIAL_DIRECTORY,
    FetchJob, SendJob
)
from aiko_services.main.store_forward import store_forward_http
from aiko_services.main.store_forward.store_forward_http import StoreForwardMessageHTTPClient, StoreForwardMessageHTTPServer

CHUNK = 1024
TIMEOUT = 15.0

# --------------------------------------------------------------------------- #

class Recorder:
    """Collects on_command() / on_event() calls from Message threads"""

    def __init__(self, command_result="accepted"):
        self.command_result = command_result
        self.commands = []
        self.events = []
        self.lock = threading.Lock()
        self.threads = set()

    def on_command(self, payload):
        with self.lock:
            self.commands.append(payload)
            self.threads.add(threading.get_ident())
        return self.command_result

    def on_event(self, segment_id, event, detail):
        with self.lock:
            self.events.append((segment_id, event, detail))
            self.threads.add(threading.get_ident())

    def wait_event(self, segment_id, event, timeout=TIMEOUT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                for record in self.events:
                    if record[0] == segment_id and record[1] == event:
                        return record
            time.sleep(0.02)
        raise AssertionError(
            f"No event {event} for {segment_id}: {self.events}")

    def wait_command(self, prefix, timeout=TIMEOUT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                for payload in self.commands:
                    if payload.startswith(prefix):
                        return payload
            time.sleep(0.02)
        raise AssertionError(f"No command {prefix}: {self.commands}")

    def count(self, segment_id, event):
        with self.lock:
            return sum(1 for record in self.events
                if record[0] == segment_id and record[1] == event)

def write_segment(directory, name, size, seed=b"cos-edge-"):
    data = (seed * (size // len(seed) + 1))[:size]
    path = os.path.join(directory, name)
    with open(path, "wb") as file:
        file.write(data)
    return path, data, hashlib.sha256(data).hexdigest()

def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

def make_dirs(tmp_path, prefix):
    inbox = tmp_path / f"{prefix}_in"
    outbox = tmp_path / f"{prefix}_out"
    inbox.mkdir()
    outbox.mkdir()
    return str(inbox), str(outbox)

# --------------------------------------------------------------------------- #

@pytest.fixture
def pair(tmp_path):
    """A server and a client, each with its own inbox and outbox"""

    server_in, server_out = make_dirs(tmp_path, "server")
    client_in, client_out = make_dirs(tmp_path, "client")
    server = StoreForwardMessageHTTPServer(server_in, server_out, bind="127.0.0.1",
        port_range=(0, 0), advertise_host="127.0.0.1", chunk_size=CHUNK)
    server_recorder = Recorder()
    endpoint = server.start(server_recorder.on_command, server_recorder.on_event)

    client = StoreForwardMessageHTTPClient(endpoint, client_in, client_out,
        poll_period=0.1, chunk_size=CHUNK, connect_deadline=5.0)
    client_recorder = Recorder()
    client.start(client_recorder.on_command, client_recorder.on_event)

    yield server, server_recorder, client, client_recorder
    client.stop()
    server.stop()

# --------------------------------------------------------------------------- #

def test_health_and_link(pair):
    server, _, client, client_recorder = pair
    response = requests.get(f"{server.endpoint}/health", timeout=5)
    assert response.status_code == 200
    assert response.json()["role"] == "server"
    assert response.json()["version"] == "v0"
    client_recorder.wait_event("-", "link_up")

def test_upload_roundtrip(pair):
    server, server_recorder, client, client_recorder = pair
    path, data, sha256 = write_segment(client.outbox, "notes.txt", 2500)
    job = SendJob("0123abcd", "notes.txt", path, len(data))
    assert client.send_segment(job)

    assert client_recorder.wait_event("0123abcd", "done")[2] == sha256
    assert server_recorder.wait_event("0123abcd", "received_ok")[2] == sha256
    with open(os.path.join(server.inbox, "notes.txt"), "rb") as file:
        assert file.read() == data
    assert not os.listdir(server.partial_directory)
    # progress reported as bytes/size on both sides
    assert client_recorder.wait_event("0123abcd", "progress")[2].endswith(
        "/2500")

def test_commands_both_ways(pair):
    server, server_recorder, client, client_recorder = pair
    assert server.send_command("(acknowledge 0123abcd ab ok)")
    assert client_recorder.wait_command("(acknowledge 0123abcd")
    assert client.send_command("(acknowledge 89abcdef cd ok)")
    assert server_recorder.wait_command("(acknowledge 89abcdef")

def test_download_roundtrip(pair):
    server, server_recorder, client, client_recorder = pair
    path, data, sha256 = write_segment(server.outbox, "reply.txt", 3000)
    job = SendJob("89abcdef", "reply.txt", path, len(data))
    assert server.send_segment(job)
    assert server_recorder.wait_event("89abcdef", "offered")[2] == sha256

    payload = client_recorder.wait_command("(fetch_segment 89abcdef")
    tokens = payload.strip("()").split()
    assert tokens == ["fetch_segment", "89abcdef", "reply.txt", "3000", sha256]

    assert client.fetch_segment(FetchJob("89abcdef", "reply.txt", 3000, sha256))
    assert client_recorder.wait_event("89abcdef", "received_ok")[2] == sha256
    client_recorder.wait_event("89abcdef", "done")
    with open(os.path.join(client.inbox, "reply.txt"), "rb") as file:
        assert file.read() == data
    assert not os.listdir(client.partial_directory)

def test_upload_resume_from_partial(pair):
    """A .part with the same sha256 already on the server: the upload
    resumes from its size instead of starting again"""

    server, server_recorder, client, client_recorder = pair
    path, data, sha256 = write_segment(client.outbox, "big.txt", 5000)
    partial = server.partial_directory
    with open(os.path.join(partial, "abcd1234.part"), "wb") as file:
        file.write(data[:2048])
    with open(os.path.join(partial, "abcd1234.meta"), "w") as file:
        file.write('{"name": "big.txt", "size": 5000, "sha256": "%s"}' % sha256)

    assert client.send_segment(SendJob("abcd1234", "big.txt", path, 5000))
    assert client_recorder.wait_event("abcd1234", "resume")[2] == "2048"
    client_recorder.wait_event("abcd1234", "done")
    with open(os.path.join(server.inbox, "big.txt"), "rb") as file:
        assert file.read() == data

def test_upload_resume_after_server_restart(tmp_path):
    """The server dies after two chunks and comes back on the same port
    and inbox: the client re-creates the upload and resumes"""

    server_in, server_out = make_dirs(tmp_path, "server")
    client_in, client_out = make_dirs(tmp_path, "client")
    port = free_port()
    crashes = {"count": 0}

    class CrashingServer(StoreForwardMessageHTTPServer):
        def _data_patch(self, segment_id):
            response = super()._data_patch(segment_id)
            with self._lock:
                incoming = self._incoming.get(segment_id)
            if incoming and incoming.chunks == 2 and not crashes["count"]:
                crashes["count"] += 1
                threading.Thread(target=self.stop, daemon=True).start()
            return response

    recorder_1 = Recorder()
    server_1 = CrashingServer(server_in, server_out, bind="127.0.0.1",
        port_range=(port, port), advertise_host="127.0.0.1", chunk_size=CHUNK)
    endpoint = server_1.start(recorder_1.on_command, recorder_1.on_event)

    client_recorder = Recorder()
    client = StoreForwardMessageHTTPClient(endpoint, client_in, client_out,
        poll_period=0.1, chunk_size=CHUNK, connect_deadline=10.0)
    client.start(client_recorder.on_command, client_recorder.on_event)
    try:
        path, data, sha256 = write_segment(client_out, "big.txt", 6000)
        assert client.send_segment(SendJob("feedbeef", "big.txt", path, 6000))
        deadline = time.monotonic() + TIMEOUT
        while not crashes["count"] and time.monotonic() < deadline:
            time.sleep(0.02)
        assert crashes["count"] == 1
        time.sleep(0.5)                       # let the client hit the failure

        recorder_2 = Recorder()
        server_2 = StoreForwardMessageHTTPServer(server_in, server_out, bind="127.0.0.1",
            port_range=(port, port), advertise_host="127.0.0.1",
            chunk_size=CHUNK)
        server_2.start(recorder_2.on_command, recorder_2.on_event)
        try:
            resume = client_recorder.wait_event("feedbeef", "resume")
            assert int(resume[2]) >= 2048
            client_recorder.wait_event("feedbeef", "done")
            recorder_2.wait_event("feedbeef", "received_ok")
            with open(os.path.join(server_in, "big.txt"), "rb") as file:
                assert file.read() == data
        finally:
            server_2.stop()
    finally:
        client.stop()

def test_download_resume_from_partial(pair):
    server, server_recorder, client, client_recorder = pair
    path, data, sha256 = write_segment(server.outbox, "reply.txt", 5000)
    assert server.send_segment(SendJob("0000aaaa", "reply.txt", path, 5000))
    server_recorder.wait_event("0000aaaa", "offered")
    partial = client.partial_directory
    with open(os.path.join(partial, "0000aaaa.part"), "wb") as file:
        file.write(data[:3000])

    assert client.fetch_segment(FetchJob("0000aaaa", "reply.txt", 5000, sha256))
    assert client_recorder.wait_event("0000aaaa", "resume")[2] == "3000"
    client_recorder.wait_event("0000aaaa", "received_ok")
    with open(os.path.join(client.inbox, "reply.txt"), "rb") as file:
        assert file.read() == data

def test_zero_byte_segment_both_ways(pair):
    """A zero-byte segment needs no PATCH and no GET, yet must still be
    verified and delivered in both directions"""

    server, server_recorder, client, client_recorder = pair
    empty_sha = hashlib.sha256(b"").hexdigest()

    path, _, sha256 = write_segment(client.outbox, "empty_up.txt", 0)
    assert sha256 == empty_sha
    assert client.send_segment(SendJob("0000000a", "empty_up.txt", path, 0))
    assert client_recorder.wait_event("0000000a", "done")[2] == empty_sha
    server_recorder.wait_event("0000000a", "received_ok")
    assert os.path.getsize(os.path.join(server.inbox, "empty_up.txt")) == 0

    path, _, _ = write_segment(server.outbox, "empty_down.txt", 0)
    assert server.send_segment(SendJob("0000000b", "empty_down.txt", path, 0))
    server_recorder.wait_event("0000000b", "offered")
    assert client.fetch_segment(
        FetchJob("0000000b", "empty_down.txt", 0, empty_sha))
    assert client_recorder.wait_event("0000000b", "received_ok")[2] == empty_sha
    client_recorder.wait_event("0000000b", "done")
    assert os.path.getsize(os.path.join(client.inbox, "empty_down.txt")) == 0
    assert not os.listdir(client.partial_directory)
    assert client_recorder.count("0000000b", "failed_http") == 0

def test_download_stale_oversized_part_is_discarded(pair):
    """A leftover .part longer than the offered size restarts from zero
    instead of producing a sha256 failure"""

    server, server_recorder, client, client_recorder = pair
    path, data, sha256 = write_segment(server.outbox, "reply.txt", 2000)
    assert server.send_segment(SendJob("0000000c", "reply.txt", path, 2000))
    server_recorder.wait_event("0000000c", "offered")
    partial = client.partial_directory
    with open(os.path.join(partial, "0000000c.part"), "wb") as file:
        file.write(b"stale" * 1000)                 # 5000 bytes, wrong data

    assert client.fetch_segment(FetchJob("0000000c", "reply.txt", 2000, sha256))
    assert client_recorder.wait_event("0000000c", "received_ok")[2] == sha256
    assert client_recorder.count("0000000c", "resume") == 0
    with open(os.path.join(client.inbox, "reply.txt"), "rb") as file:
        assert file.read() == data

def test_port_range_fallback_and_exhaustion(tmp_path):
    """A busy first port is skipped (werkzeug exits instead of raising);
    an exhausted range raises OSError with a diagnosable message"""

    server_in, server_out = make_dirs(tmp_path, "server")
    port = free_port()
    first = StoreForwardMessageHTTPServer(server_in, server_out, bind="127.0.0.1",
        port_range=(port, port), advertise_host="127.0.0.1")
    first.start(Recorder().on_command, Recorder().on_event)
    try:
        second_in, second_out = make_dirs(tmp_path, "second")
        second = StoreForwardMessageHTTPServer(second_in, second_out, bind="127.0.0.1",
            port_range=(port, port + 1), advertise_host="127.0.0.1")
        try:
            endpoint = second.start(Recorder().on_command, Recorder().on_event)
            assert endpoint == f"http://127.0.0.1:{port + 1}"
        finally:
            second.stop()

        third = StoreForwardMessageHTTPServer(second_in, second_out, bind="127.0.0.1",
            port_range=(port, port), advertise_host="127.0.0.1")
        with pytest.raises(OSError) as raised:
            third.start(Recorder().on_command, Recorder().on_event)
        assert f"no free HTTP port in {port}-{port}" in str(raised.value)
    finally:
        first.stop()

def test_out_cursor(pair):
    server, _, client, _ = pair
    client.stop()                              # poll by hand instead
    for index in range(3):
        assert server.send_command(f"(cancel {index:08x})")
    items = requests.get(f"{server.endpoint}/out", timeout=5).json()["items"]
    assert [item["seq"] for item in items] == [1, 2, 3]
    items = requests.get(f"{server.endpoint}/out", params={"after": 2},
        timeout=5).json()["items"]
    assert [item["seq"] for item in items] == [3]
    assert server.out_queue_depth() == 1
    for index in range(OUT_QUEUE_SIZE - 1):
        assert server.send_command(f"(cancel {index:08x})")
    assert not server.send_command("(cancel ffffffff)")     # drop-newest
    assert server.out_queue_depth() == OUT_QUEUE_SIZE

def test_in_guard(pair):
    server, server_recorder, _, _ = pair
    url = f"{server.endpoint}/in"
    assert requests.post(url, data="(cancel 01234567)", timeout=5)  \
        .status_code == 202
    server_recorder.command_result = "rejected_parse"
    assert requests.post(url, data="bogus", timeout=5).status_code == 400
    server_recorder.command_result = "rejected_command"
    assert requests.post(url, data="(_store_forward_event 01234567 done x)",
        timeout=5).status_code == 403
    assert server_recorder.commands[0] == "(cancel 01234567)"

def test_timeout_fires(tmp_path):
    client_in, client_out = make_dirs(tmp_path, "client")
    recorder = Recorder()
    client = StoreForwardMessageHTTPClient(f"http://127.0.0.1:{free_port()}", client_in,
        client_out, poll_period=0.1, chunk_size=CHUNK, connect_deadline=1.0)
    client.start(recorder.on_command, recorder.on_event)
    try:
        path, data, _ = write_segment(client_out, "x.txt", 100)
        started = time.monotonic()
        assert client.send_segment(SendJob("0badf00d", "x.txt", path, 100))
        recorder.wait_event("0badf00d", "failed_timeout", timeout=6.0)
        assert time.monotonic() - started < 6.0
        recorder.wait_event("-", "link_down")
    finally:
        client.stop()
    assert not any(thread.is_alive() for thread in client._threads)

def test_bad_input(pair):
    server, server_recorder, _, _ = pair
    base = f"{server.endpoint}/data"
    good = {"name": "a.txt", "size": 2048, "sha256": "0" * 64}

    assert requests.post(f"{base}/not-hex!", json=good, timeout=5)  \
        .status_code == 404
    assert requests.post(f"{base}/0123abcd", json={**good, "name": "../x"},
        timeout=5).status_code == 400
    assert requests.post(f"{base}/0123abcd", json={**good, "size": "2048"},
        timeout=5).status_code == 400
    assert requests.post(f"{base}/0123abcd",
        json={**good, "size": MAX_SEGMENT_SIZE + 1}, timeout=5)  \
        .status_code == 413

    response = requests.post(f"{base}/0123abcd", json=good, timeout=5)
    assert response.status_code == 201
    assert response.headers["Upload-Offset"] == "0"

    response = requests.patch(f"{base}/0123abcd", data=b"x" * CHUNK,
        headers={"Upload-Offset": "512"}, timeout=5)
    assert response.status_code == 409
    assert response.headers["Upload-Offset"] == "0"
    assert requests.patch(f"{base}/0123abcd", data=b"x" * (CHUNK + 1),
        headers={"Upload-Offset": "0"}, timeout=5).status_code == 413
    assert requests.patch(f"{base}/0123abcd", data=b"x" * CHUNK,
        headers={"Upload-Offset": "0"}, timeout=5).status_code == 204
    assert requests.post(f"{base}/0123abcd/complete", timeout=5)  \
        .status_code == 409                    # incomplete
    assert requests.patch(f"{base}/0123abcd", data=b"x" * CHUNK,
        headers={"Upload-Offset": str(CHUNK)}, timeout=5).status_code == 204
    assert requests.post(f"{base}/0123abcd/complete", timeout=5)  \
        .status_code == 422                    # sha256 of zeros is wrong
    server_recorder.wait_event("0123abcd", "received_failed_sha256")
    assert not os.listdir(server.partial_directory)
    assert os.listdir(server.inbox) == [PARTIAL_DIRECTORY]

    for index in range(MAX_INCOMING):
        assert requests.post(f"{base}/{index:08x}", json=good, timeout=5)  \
            .status_code == 201
    assert requests.post(f"{base}/deadbeef", json=good, timeout=5)  \
        .status_code == 409

    assert requests.get(f"{base}/deadbeef", timeout=5).status_code == 404
    assert requests.head(f"{base}/00000000", timeout=5)  \
        .headers["Upload-Offset"] == "0"

# --------------------------------------------------------------------------- #

def test_partial_directory_outside_inbox(tmp_path):
    """Both roles keep their parts away from the inbox: only final files
    ever appear there, and a seeded part still gives a resume"""

    server_in, server_out = make_dirs(tmp_path, "server")
    client_in, client_out = make_dirs(tmp_path, "client")
    server_parts = tmp_path / "server_state" / "parts"
    client_parts = tmp_path / "client_state" / "parts"
    server = StoreForwardMessageHTTPServer(server_in, server_out,
        bind="127.0.0.1", port_range=(0, 0), advertise_host="127.0.0.1",
        chunk_size=CHUNK, partial_directory=str(server_parts))
    server_recorder = Recorder()
    endpoint = server.start(server_recorder.on_command, server_recorder.on_event)
    client = StoreForwardMessageHTTPClient(endpoint, client_in, client_out,
        poll_period=0.1, chunk_size=CHUNK, connect_deadline=5.0,
        partial_directory=str(client_parts))
    client_recorder = Recorder()
    client.start(client_recorder.on_command, client_recorder.on_event)
    try:
        assert server_parts.is_dir() and client_parts.is_dir()
        assert server.partial_directory == os.path.realpath(server_parts)

        path, data, sha256 = write_segment(client.outbox, "up.txt", 5000)
        (server_parts / "abcd1234.part").write_bytes(data[:2048])
        (server_parts / "abcd1234.meta").write_text(
            '{"name": "up.txt", "size": 5000, "sha256": "%s"}' % sha256)
        assert client.send_segment(SendJob("abcd1234", "up.txt", path, 5000))
        assert client_recorder.wait_event("abcd1234", "resume")[2] == "2048"
        server_recorder.wait_event("abcd1234", "received_ok")

        path, data, sha256 = write_segment(server.outbox, "down.txt", 3000)
        assert server.send_segment(SendJob("dcba4321", "down.txt", path, 3000))
        client_recorder.wait_command("(fetch_segment dcba4321")  # no Actor:
        assert client.fetch_segment(                             # fetch here
            FetchJob("dcba4321", "down.txt", 3000, sha256))
        client_recorder.wait_event("dcba4321", "done")

        assert os.listdir(server.inbox) == ["up.txt"]
        assert os.listdir(client.inbox) == ["down.txt"]
        assert os.listdir(server_parts) == []
        assert os.listdir(client_parts) == []
    finally:
        client.stop()
        server.stop()

def test_upload_store_failure_is_reported(pair, monkeypatch):
    """The inbox refuses the final move: the server discards the part and
    reports received_failed_store with the errno; the client sees 507"""

    server, server_recorder, client, client_recorder = pair

    def refuse(inbox, name, part_path, meta_path):
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC), inbox)

    monkeypatch.setattr(store_forward_http, "_finish_download", refuse)
    path, data, sha256 = write_segment(client.outbox, "full.txt", 2500)
    assert client.send_segment(SendJob("0123abcd", "full.txt", path, 2500))
    assert server_recorder.wait_event("0123abcd", "received_failed_store")[2]  \
        == "ENOSPC"
    assert client_recorder.wait_event("0123abcd", "failed_http")[2] == "507"
    assert os.listdir(server.partial_directory) == []
    assert not os.path.exists(os.path.join(server.inbox, "full.txt"))
