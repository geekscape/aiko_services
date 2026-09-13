# Aiko Services StoreForward: SegmentStoreForward Actor tests, no MQTT server required
#
# Most tests call the Actor's methods directly (they are ordinary Python
# methods on the composed instance).  The hand-off test runs the Aiko
# Services event loop once with mqtt_connection_required=False and checks
# that Message-thread callbacks reach the Actor on the event-loop thread.
#
#   pytest [-s] unit/test_store_forward.py

import hashlib
import os
import re
import threading
import time
import uuid

import pytest

import aiko_services as aiko
from aiko_services.main.utilities import generate, parse

from aiko_services.main.store_forward import store_forward_message
from aiko_services.main.store_forward.store_forward_message import FetchJob, SendJob
from aiko_services.main.store_forward.store_forward import (
    ALLOWED_COMMANDS, PROTOCOL, SENT_DIRECTORY, STATE_LIMIT,
    SegmentStoreForwardImpl
)

GOOD_ID = "0123abcd"
UTC_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
OTHER_ID = "89abcdef"
SHA = "a" * 64

# --------------------------------------------------------------------------- #

class FakeMessage(store_forward_message.StoreForwardMessage):
    """Records what the Actor asks of the Message layer"""

    def __init__(self, role="edge", accept=True):
        self.role = role
        self.accept = accept
        self.jobs = []
        self.commands = []
        self.cancelled = []
        self.on_command = None
        self.on_event = None

    def start(self, on_command, on_event):
        self.on_command = on_command
        self.on_event = on_event
        return f"fake://{self.role}"

    def stop(self):
        pass

    def send_segment(self, job):
        self.jobs.append(job)
        return self.accept

    def fetch_segment(self, job):
        if self.role != "edge":
            return False
        self.jobs.append(job)
        return self.accept

    def send_command(self, payload):
        self.commands.append(payload)
        return True

    def cancel(self, segment_id):
        self.cancelled.append(segment_id)

_actor_count = [0]

def make_actor(tmp_path, role="edge", accept=True, outbox_period=0):
    inbox = tmp_path / "in"
    outbox = tmp_path / "out"
    inbox.mkdir(parents=True)
    outbox.mkdir(parents=True)
    message = FakeMessage(role, accept)
    parameters = {"message": message, "inbox": str(inbox),
                  "outbox": str(outbox), "outbox_period": outbox_period}
    _actor_count[0] += 1
    init_args = aiko.actor_args(f"st_test_{_actor_count[0]}",
        parameters=parameters, protocol=PROTOCOL, tags=[f"role={role}"])
    actor = aiko.compose_instance(SegmentStoreForwardImpl, init_args)
    return actor, message, inbox, outbox

def write_segment(directory, name, size=100):
    data = (b"segment-" * (size // 8 + 1))[:size]
    path = os.path.join(directory, name)
    with open(path, "wb") as file:
        file.write(data)
    return path, hashlib.sha256(data).hexdigest()

# --------------------------------------------------------------------------- #

def test_initial_share(tmp_path):
    actor, message, inbox, outbox = make_actor(tmp_path, role="server")
    assert actor.share["role"] == "server"
    assert actor.share["http_endpoint"] == "fake://server"
    assert actor.share["inbox"] == os.path.realpath(str(inbox))
    assert actor.share["link"] == "unknown"
    assert message.on_command and message.on_event
    assert os.path.isdir(os.path.join(str(outbox), SENT_DIRECTORY))

def test_send_segment_boundary(tmp_path):
    actor, message, inbox, outbox = make_actor(tmp_path)
    store_forwards = actor.share["store_forwards"]

    actor.send_segment(GOOD_ID, "../x")
    assert store_forwards[GOOD_ID] == "rejected_path"
    actor.forget(GOOD_ID)

    outside, _ = write_segment(str(tmp_path), "secret.txt")
    os.symlink(outside, os.path.join(str(outbox), "link.txt"))
    actor.send_segment(GOOD_ID, "link.txt")
    assert store_forwards[GOOD_ID] == "rejected_path"        # escapes the outbox
    actor.forget(GOOD_ID)

    actor.send_segment(GOOD_ID, "missing.txt")
    assert store_forwards[GOOD_ID] == "rejected_missing"
    actor.forget(GOOD_ID)

    actor.send_segment("a.b", "notes.txt")               # bad id: no state
    assert "a.b" not in store_forwards
    assert actor.share["metrics"]["rejected_commands"] == "1"

    path, _ = write_segment(str(outbox), "notes.txt")
    actor.send_segment(GOOD_ID, "notes.txt")
    assert store_forwards[GOOD_ID] == "queued"
    assert len(message.jobs) == 1
    job = message.jobs[0]
    assert isinstance(job, SendJob)
    assert (job.segment_id, job.name, job.path, job.size) ==  \
        (GOOD_ID, "notes.txt", os.path.realpath(path), 100)

    actor.send_segment(GOOD_ID, "notes.txt")             # idempotent
    assert len(message.jobs) == 1

def test_fetch_segment_boundary(tmp_path):
    actor, message, _, _ = make_actor(tmp_path, role="server")
    actor.fetch_segment(GOOD_ID, "a.txt", "10", SHA)
    assert actor.share["store_forwards"][GOOD_ID] == "rejected_role"
    assert message.jobs == []

    actor, message, _, _ = make_actor(tmp_path / "edge")
    actor.fetch_segment(GOOD_ID, "a.txt", "abc", SHA)
    assert actor.share["store_forwards"][GOOD_ID] == "rejected_path"
    actor.forget(GOOD_ID)
    actor.fetch_segment(GOOD_ID, "a.txt", "10", "not-a-sha")
    assert actor.share["store_forwards"][GOOD_ID] == "rejected_path"
    actor.forget(GOOD_ID)

    actor.fetch_segment(GOOD_ID, "a.txt", "10", SHA)
    assert actor.share["store_forwards"][GOOD_ID] == "fetching"
    job = message.jobs[0]
    assert isinstance(job, FetchJob)
    assert (job.name, job.size, job.sha256) == ("a.txt", 10, SHA)

def test_queue_full_is_rejected_busy(tmp_path):
    actor, message, _, outbox = make_actor(tmp_path, accept=False)
    write_segment(str(outbox), "notes.txt")
    actor.send_segment(GOOD_ID, "notes.txt")
    assert actor.share["store_forwards"][GOOD_ID] == "rejected_busy"

def test_state_tables_are_bounded(tmp_path):
    actor, _, _, _ = make_actor(tmp_path)
    for index in range(STATE_LIMIT + 5):
        actor.send_segment(f"{index:08x}", "missing.txt")
    store_forwards = actor.share["store_forwards"]
    assert len(store_forwards) == STATE_LIMIT
    assert "00000000" not in store_forwards                    # oldest evicted
    assert f"{STATE_LIMIT + 4:08x}" in store_forwards

def test_store_forward_events_acknowledge_forget(tmp_path):
    actor, message, inbox, outbox = make_actor(tmp_path)
    path, sha256 = write_segment(str(outbox), "notes.txt", 100)
    actor.send_segment(GOOD_ID, "notes.txt")

    actor._store_forward_event(GOOD_ID, "sending", "0/100")
    assert actor.share["store_forwards"][GOOD_ID] == "sending"
    actor._store_forward_event(GOOD_ID, "progress", "50/100")
    assert actor.share["progress"][GOOD_ID] == "50/100"
    actor._store_forward_event(GOOD_ID, "resume", "50")
    assert actor.share["metrics"]["resumes"] == "1"
    actor._store_forward_event(GOOD_ID, "done", sha256)
    assert actor.share["store_forwards"][GOOD_ID] == "done"
    assert actor.share["metrics"]["sent_bytes"] == "100"
    assert not os.path.exists(path)                       # moved to .sent
    assert os.path.exists(os.path.join(str(outbox), SENT_DIRECTORY, "notes.txt"))

    actor.acknowledge(GOOD_ID, "b" * 64, "ok")            # wrong sha: ignored
    assert actor.share["store_forwards"][GOOD_ID] == "done"
    actor.acknowledge(GOOD_ID, sha256, "ok")
    assert actor.share["store_forwards"][GOOD_ID] == "acked"
    assert message.cancelled == [GOOD_ID]                 # offer released
    actor.acknowledge(GOOD_ID, sha256, "ok")              # idempotent
    assert actor.share["store_forwards"][GOOD_ID] == "acked"

    actor._store_forward_event(OTHER_ID, "failed_http", "503")
    assert actor.share["store_forwards"][OTHER_ID] == "failed_http_503"
    assert actor.share["metrics"]["failures"] == "1"

    actor.forget(GOOD_ID)
    assert GOOD_ID not in actor.share["store_forwards"]
    assert GOOD_ID not in actor.share["progress"]

def test_received_events_send_acknowledge(tmp_path):
    actor, message, _, _ = make_actor(tmp_path, role="server")
    actor._store_forward_event(GOOD_ID, "name", "up.txt")
    actor._store_forward_event(GOOD_ID, "name", "../evil")       # ignored
    assert actor._names[GOOD_ID] == "up.txt"
    actor._store_forward_event(GOOD_ID, "receiving", "0/300")
    assert actor.share["received"][GOOD_ID] == "receiving"
    actor._store_forward_event(GOOD_ID, "received_verifying", "")
    assert actor.share["received"][GOOD_ID] == "verifying"
    actor._store_forward_event(GOOD_ID, "received_ok", SHA)
    assert actor.share["received"][GOOD_ID] == "ok"
    assert actor.share["metrics"]["received_bytes"] == "300"
    assert message.commands == [f"(acknowledge {GOOD_ID} {SHA} ok)"]

    actor._store_forward_event(OTHER_ID, "received_failed_sha256", SHA)
    assert actor.share["received"][OTHER_ID] == "failed_sha256"
    assert actor.share["metrics"]["failures"] == "1"

def test_link_events_and_bad_events(tmp_path):
    actor, _, _, _ = make_actor(tmp_path)
    actor._store_forward_event("-", "link_up", "")
    assert re.match(r"^up@\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", actor.share["link"])
    assert actor.share["link_cause"] == "server_reachable"
    assert UTC_RE.match(actor.share["link_changed_utc"])
    actor._store_forward_event("-", "link_down",
        "ConnectionError GET http://h:1/out: [Errno 61] refused")
    assert actor.share["link"].startswith("down@20")
    assert actor.share["link_cause"] == "ConnectionError"   # first token
    assert actor.share["metrics"]["link_downs"] == "1"
    actor._store_forward_event("-", "peer_poll", "2026-09-13T01:02:03Z")
    assert actor.share["peer"]["last_poll"] == "2026-09-13T01:02:03Z"
    assert actor.share["link"].startswith("up@")            # poll -> up
    assert actor.share["link_cause"] == "edge_polling"
    actor._store_forward_event("-", "rejected_command", "403")
    assert actor.share["metrics"]["rejected_commands"] == "1"
    assert actor.last_event_thread == threading.get_ident()

    actor._store_forward_event("not hex", "done", "x")
    assert actor.share["metrics"]["rejected_commands"] == "2"
    actor._store_forward_event(GOOD_ID, "made_up_event", "x")
    assert actor.share["metrics"]["rejected_commands"] == "3"
    assert GOOD_ID not in actor.share["store_forwards"]

def test_server_link_from_edge_polls_and_timeout(tmp_path):
    """The server host's link follows edge host activity: up on a poll,
    down when no poll arrives for link_timeout seconds"""

    actor, _, _, _ = make_actor(tmp_path, role="server")
    actor.link_timeout = 5.0
    assert actor.share["link"] == "unknown"
    actor._link_check()                                   # nothing yet
    assert actor.share["link"] == "unknown"

    actor._store_forward_event("-", "peer_poll", "1725400000")
    assert actor.share["link"].startswith("up@")
    actor._link_check()                                   # fresh poll: stays
    assert actor.share["link"].startswith("up@")

    actor._last_poll = time.monotonic() - 100
    actor._link_check()
    assert actor.share["link"].startswith("down@")
    assert actor.share["link_cause"] == "no_poll_100s"
    actor._store_forward_event("-", "peer_poll", "1725400100") # poll again: up
    assert actor.share["link"].startswith("up@")

def test_state_tables_keep_last_three(tmp_path):
    actor, _, _, _ = make_actor(tmp_path)
    assert STATE_LIMIT == 3
    for index in range(5):
        actor._store_forward_event(f"{index:08x}", "progress", f"{index}/9")
    assert list(actor.share["progress"]) == ["00000002", "00000003", "00000004"]
    actor._store_forward_event("00000002", "progress", "9/9")   # existing: no evict
    assert list(actor.share["progress"]) == ["00000002", "00000003", "00000004"]

def test_last_error_token(tmp_path):
    actor, _, _, outbox = make_actor(tmp_path)
    assert actor.share["last_error"] == "-"
    actor.send_segment(GOOD_ID, "missing.txt")
    assert re.match(r"^rejected_missing/0123abcd@\d{4}-.*Z$",
        actor.share["last_error"])
    actor._store_forward_event(OTHER_ID, "received_failed_sha256", SHA)
    assert actor.share["last_error"].startswith("failed_sha256/89abcdef@")
    actor._store_forward_event("bad id", "done", "x")
    assert actor.share["last_error"].startswith("rejected_command/-@")

def test_queue_and_sampled(tmp_path):
    actor, message, _, outbox = make_actor(tmp_path)
    assert actor.share["queue"] == {"depth": "0", "oldest_s": "0", "bytes": "0"}
    for name, size in (("a.txt", 100), ("b.txt", 200), ("c.txt", 300)):
        write_segment(str(outbox), name, size)
    old = os.path.join(str(outbox), "a.txt")
    os.utime(old, (time.time() - 90, time.time() - 90))
    write_segment(str(outbox), ".hidden", 999)              # ignored
    actor._outbox_scan()                                    # first sighting
    assert actor.share["queue"]["depth"] == "3"
    assert actor.share["queue"]["bytes"] == "600"
    assert 89 <= int(actor.share["queue"]["oldest_s"]) <= 92
    assert UTC_RE.match(actor.share["sampled_utc"])
    actor._outbox_scan()                                    # stable: queued
    assert len(message.jobs) == 3
    assert actor.share["queue"]["depth"] == "3"             # still in outbox
    actor._store_forward_event(message.jobs[0].segment_id, "done", SHA)
    actor._outbox_scan()                                    # moved to .sent
    assert actor.share["queue"]["depth"] == "2"

def test_network_ladder_raise_only(tmp_path):
    """Link up raises the process Connection from NONE to NETWORK and link
    down lowers it back; at or above TRANSPORT the sensor never touches it"""

    actor, _, _, _ = make_actor(tmp_path)
    connection = aiko.process.connection
    # The Connection is process-global and other tests may leave it at
    # any rung; position it directly rather than through update_state(),
    # whose handlers (MQTT logging) need a broker this test does not have
    initial_state = connection.get_state()
    connection.connection_state = aiko.ConnectionState.NONE
    try:
        actor._store_forward_event("-", "link_up", "")
        assert connection.get_state() == aiko.ConnectionState.NETWORK
        actor._store_forward_event("-", "link_down", "ConnectionError x")
        assert connection.get_state() == aiko.ConnectionState.NONE

        connection.connection_state = aiko.ConnectionState.TRANSPORT
        actor._store_forward_event("-", "link_up", "")
        assert connection.get_state() == aiko.ConnectionState.TRANSPORT
        actor._store_forward_event("-", "link_down", "ReadTimeout x")
        assert connection.get_state() == aiko.ConnectionState.TRANSPORT
        assert actor.share["link"].startswith("down@")     # share still moves
    finally:
        connection.connection_state = initial_state

def _queue_via_scan(actor):
    actor._outbox_scan()                                    # first sighting
    actor._outbox_scan()                                    # stable: send

def test_retry_after_failed_send(tmp_path):
    """A failed send is not stuck: after a back-off the watcher re-sends
    the same outbox file with a fresh id and counts the retry"""

    actor, message, _, outbox = make_actor(tmp_path)
    write_segment(str(outbox), "seg.txt")
    _queue_via_scan(actor)
    first_id = message.jobs[0].segment_id
    actor._store_forward_event(first_id, "failed_timeout", "")
    assert "seg.txt" not in actor._sent_names
    assert actor._retry_after["seg.txt"] > time.monotonic()
    _queue_via_scan(actor)                                  # backing off
    assert len(message.jobs) == 1

    actor._retry_after["seg.txt"] = 0                       # back-off over
    _queue_via_scan(actor)
    assert len(message.jobs) == 2
    assert message.jobs[1].segment_id != first_id
    assert actor.share["metrics"]["retries"] == "1"
    assert actor._retry_backoff["seg.txt"] == 60.0          # doubles next time
    actor._store_forward_event(message.jobs[1].segment_id, "failed_http", "503")
    assert actor._retry_backoff["seg.txt"] == 120.0

    actor._retry_after["seg.txt"] = 0
    _queue_via_scan(actor)
    actor._store_forward_event(message.jobs[2].segment_id, "done", SHA)
    assert "seg.txt" not in actor._retry_backoff            # delivered: reset
    assert os.path.exists(os.path.join(str(outbox), SENT_DIRECTORY, "seg.txt"))

def test_rejected_busy_retries(tmp_path):
    actor, message, _, outbox = make_actor(tmp_path, accept=False)
    write_segment(str(outbox), "seg.txt")
    _queue_via_scan(actor)
    assert list(actor.share["store_forwards"].values()) == ["rejected_busy"]
    assert "seg.txt" in actor._retry_after
    message.accept = True
    actor._retry_after["seg.txt"] = 0
    _queue_via_scan(actor)
    assert message.jobs[-1].name == "seg.txt"
    assert actor.share["metrics"]["retries"] == "1"

def test_offer_not_acked_is_reoffered(tmp_path):
    """Server role: an offer the edge never acknowledged is withdrawn
    after RETRY_AFTER_S and re-offered with a fresh id"""

    from aiko_services.main.store_forward.store_forward import RETRY_AFTER_S
    actor, message, _, outbox = make_actor(tmp_path, role="server")
    write_segment(str(outbox), "seg.txt")
    _queue_via_scan(actor)
    first_id = message.jobs[0].segment_id
    actor._store_forward_event(first_id, "offered", SHA)
    actor._offered_at[first_id] -= RETRY_AFTER_S + 1
    actor._outbox_scan()
    assert message.cancelled == [first_id]                  # withdrawn
    assert "seg.txt" in actor._retry_after
    actor._retry_after["seg.txt"] = 0
    _queue_via_scan(actor)
    assert len(message.jobs) == 2 and message.jobs[1].segment_id != first_id
    assert actor.share["metrics"]["retries"] == "1"

def test_stale_partial_sweep(tmp_path):
    from aiko_services.main.store_forward.store_forward_message import (
        PARTIAL_DIRECTORY
    )
    actor, _, inbox, _ = make_actor(tmp_path)
    partial = inbox / PARTIAL_DIRECTORY
    partial.mkdir()
    for stem, age in (("aaaa1111", 100), ("bbbb2222", 5)):
        for suffix in (".part", ".meta"):
            path = partial / f"{stem}{suffix}"
            path.write_text("x")
            os.utime(path, (time.time() - age, time.time() - age))
    actor.partial_max_age = 10
    actor._sweep_partial(time.monotonic(), force=True)
    assert sorted(p.name for p in partial.iterdir()) ==  \
        ["bbbb2222.meta", "bbbb2222.part"]

def test_cancel_sets_job_event(tmp_path):
    actor, message, _, outbox = make_actor(tmp_path)
    write_segment(str(outbox), "notes.txt")
    actor.send_segment(GOOD_ID, "notes.txt")
    assert not message.jobs[0].cancel.is_set()
    actor.cancel(GOOD_ID)
    assert message.jobs[0].cancel.is_set()
    assert message.cancelled == [GOOD_ID]

def test_http_command_guard(tmp_path):
    actor, _, _, _ = make_actor(tmp_path)
    assert actor._http_command("bogus") == "rejected_command"
    assert actor._http_command("(_store_forward_event 0123abcd done x)")  \
        == "rejected_command"
    assert actor._http_command("(run)") == "rejected_command"
    assert actor._http_command("(cancel 12:34)") == "rejected_parse"
    assert actor._http_command("(cancel 0123abcd)") == "accepted"

def test_outbox_scan_sends_once_when_stable(tmp_path):
    actor, message, _, outbox = make_actor(tmp_path)
    write_segment(str(outbox), ".hidden", 10)
    path, _ = write_segment(str(outbox), "notes.txt", 100)

    actor._outbox_scan()                                  # first sighting
    assert message.jobs == []
    with open(path, "ab") as file:                        # still growing
        file.write(b"more")
    actor._outbox_scan()
    assert message.jobs == []
    actor._outbox_scan()                                  # stable: send
    assert len(message.jobs) == 1
    assert message.jobs[0].name == "notes.txt"
    assert len(message.jobs[0].segment_id) == 12
    actor._outbox_scan()                                  # not again
    assert len(message.jobs) == 1
    assert actor.share["store_forwards"][message.jobs[0].segment_id] == "queued"

def test_mailbox_handoff_runs_on_event_loop_thread(tmp_path):
    """Message-thread callbacks post to the mailbox; the Actor's state
    changes happen on the event-loop thread (Aiko Services P2)"""

    actor, message, _, outbox = make_actor(tmp_path)
    write_segment(str(outbox), "notes.txt")
    actor.send_segment(GOOD_ID, "notes.txt")
    poster_thread = {}

    def poster():
        poster_thread["id"] = threading.get_ident()
        message.on_event(GOOD_ID, "sending", "0/100")
        assert message.on_command(f"(cancel {GOOD_ID})") == "accepted"

    def check():
        aiko.event.remove_timer_handler(check)
        try:
            assert actor.share["store_forwards"][GOOD_ID] == "sending"
            assert actor.last_event_thread == threading.get_ident()
            assert actor.last_event_thread != poster_thread["id"]
            assert message.jobs[0].cancel.is_set()
            results["ok"] = True
        finally:
            aiko.process.terminate()

    results = {}
    threading.Thread(target=poster).start()
    aiko.event.add_timer_handler(check, 0.5)
    aiko.process.run(mqtt_connection_required=False)
    assert results.get("ok")

# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Wire encoding guards: shared state values are single S-expression tokens
# and the parser reads a leading "<digits>:" as a canonical symbol

STATE_TOKENS = [
    "queued", "hashing", "offered", "connecting", "sending", "fetching",
    "verifying", "done", "acked", "cancelled", "failed_timeout",
    "failed_sha256", "failed_http_404", "rejected_path", "rejected_missing",
    "rejected_size", "rejected_role", "rejected_busy",
    "receiving", "ok", "up", "down", "unknown", "2048/5000", "1725400000",
    "http://server.local:8080", "/Users/someone/store_forward/in",
    "up@2026-09-13T01:02:03Z", "2026-09-13T01:02:03Z",
    "failed_timeout/0123abcd@2026-09-13T01:02:03Z", "rejected_command/-@2026-09-13T01:02:03Z",
    "no_poll_4s", "ConnectionError", "edge_polling", "startup"
]

def test_state_tokens_round_trip():
    for value in STATE_TOKENS:
        command, arguments = parse(f"(update store_forwards.0123abcd {value})")
        assert command == "update"
        assert arguments == ["store_forwards.0123abcd", value], value

def test_hex_segment_ids_are_plain_tokens():
    for _ in range(50):
        segment_id = uuid.uuid4().hex[:12]
        command, arguments = parse(f"(cancel {segment_id})")
        assert (command, arguments) == ("cancel", [segment_id])

def test_canonical_symbol_hazard_documented():
    """A value such as 12:34 is not a plain token: the parser reads it as a
    canonical symbol length prefix.  Never publish such values"""

    with pytest.raises(Exception):
        parse("(update store_forwards.0123abcd 12:34)")

def test_role_tag_survives_generate():
    payload = generate("add",
        ["aiko/host/1/1", "store_forward_host", "p:0", "mqtt", "owner",
         ["role=edge", "ec=true"]])
    command, arguments = parse(payload)
    assert command == "add"
    assert arguments[5] == ["role=edge", "ec=true"]

def test_allowed_commands_seeded_from_interface():
    assert ALLOWED_COMMANDS == frozenset(
        {"send_segment", "fetch_segment", "acknowledge", "cancel", "forget"})
    assert "_store_forward_event" not in ALLOWED_COMMANDS
