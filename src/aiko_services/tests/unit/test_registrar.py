# Usage
# ~~~~~
# pytest [-s] unit/test_registrar.py
#
# Unit tests for the Registrar Interface contract (e_10 §2.2, 2026-07-13):
# the wire commands add/remove/history/share are real Interface methods
# (service_add / service_remove / services_history / services_share — the
# "service(s)_" prefix avoids colliding with universal Service state
# "share" and "history"), with _topic_in_handler() reduced to
# parse-and-delegate.  The primary election's liveness probe (a found
# primary is probed before this Registrar yields) is tested here with a
# recording message stub and the timer handlers called directly, plus one
# run of the real event loop; the election over a real MQTT server is in
# tests/integration/test_registrar_election.py.
#
# To Do
# ~~~~~
# - None, yet !

import pytest

import aiko_services as aiko
from aiko_services.main import aiko as process_data
from aiko_services.main import event
import aiko_services.main.registrar as registrar_module
from aiko_services.main.registrar import (
    Registrar, RegistrarImpl, service_duration, _seconds_terse,
)
from aiko_services.main.utilities import parse, utc_iso_since_epoch


class _StubMessage:
    def __init__(self):
        self.published = []
        self.retained = []
        self.will = None

    def publish(self, topic, payload=None, retain=False):
        self.published.append((topic, payload))
        if retain:
            self.retained.append((topic, payload))

    def set_last_will_and_testament(self, topic, payload, retain):
        self.will = (topic, payload, retain)

    def subscribe(self, topic):
        pass

    def unsubscribe(self, topic):
        pass


def test_registrar_interface_declares_contract():
    assert {"service_add", "service_remove",
            "services_history", "services_share"
           } <= set(Registrar.__abstractmethods__)

def test_registrar_add_remove_share():
    saved_message = process_data.message
    stub = _StubMessage()
    process_data.message = stub
    try:
        registrar = aiko.compose_instance(
            RegistrarImpl, aiko.service_args("t_registrar"))

        registrar.service_add(
            "aiko/host/9999/9", "t_svc", "t_proto:0", "mqtt", "o", ["x=1"])
        assert registrar.services.count == 1
        assert registrar.share["service_count"] == 1
        topic, payload = stub.published[-1]
        assert topic == registrar.topic_out
    # registrar:3 appends time_add and time_remove, and a Service that is
    # still running has no time_remove.  registrar:2 published six fields
        command, parameters = parse(payload)
        assert command == "add" and len(parameters) == 8
        assert parameters[:6] == [
            "aiko/host/9999/9", "t_svc", "t_proto:0", "mqtt", "o", ["x=1"]]
        assert parameters[7] == "-"
        time_add = parameters[6]
        assert utc_iso_since_epoch(time_add) > 0      # a real UTC stamp

        registrar.services_share(
            "t/response", "t_svc", "*", "*", "*", "*")
        payloads = [payload for _, payload in stub.published]
        assert "(item_count 1)" in payloads
        assert payloads[-1] == "(sync t/response)"
        assert any(payload.startswith("(add aiko/host/9999/9 t_svc")
            for payload in payloads)

        registrar.service_remove("aiko/host/9999/9")
        assert registrar.services.count == 0
        assert len(registrar.history) == 1
        assert stub.published[-1][1] == "(remove aiko/host/9999/9)"

        registrar.services_history("t/response", 16)
        history = [payload for _, payload in stub.published[-2:]
            if payload.startswith("(add aiko/host/9999/9")]
        assert history, "the history reply holds the terminated Service"
        parameters = parse(history[-1])[1]
        assert len(parameters) == 8
        assert parameters[6] == time_add               # the same stamp
        assert utc_iso_since_epoch(parameters[7]) >=  \
            utc_iso_since_epoch(time_add)              # removed after added

        # The wire handler is parse-and-delegate onto the same methods
        registrar._topic_in_handler(None, registrar.topic_in,
            "(add aiko/host/8888/8 t_svc2 p:0 mqtt o (y=2))")
        assert registrar.services.count == 1
    finally:
        model = registrar.state_machine.model
        for handler in list(model._timers):              # the search timer
            model._timer_remove(handler)
        process_data.message = saved_message


# --------------------------------------------------------------------------- #
# The primary election's liveness probe

BOOT = process_data.TOPIC_REGISTRAR_BOOT
DEAD = "aiko/deadhost/4242/1"

@pytest.fixture
def election(monkeypatch):
    """A Registrar in primary_search with a recording message stub; every
    timer it leaves pending is removed afterwards"""

    stub = _StubMessage()
    monkeypatch.setattr(process_data, "message", stub)   # the class: undone cleanly
    registrar = aiko.compose_instance(RegistrarImpl, aiko.service_args("t_election"))
    model = registrar.state_machine.model
    yield registrar, model, stub
    for handler in list(model._timers):
        model._timer_remove(handler)

def state(registrar):
    return registrar.state_machine.get_state()

def found(registrar, topic_path=DEAD):
    registrar._registrar_handler("found", {"topic_path": topic_path,
                                           "version": "2", "timestamp": "0"})

def test_found_primary_is_probed(election):
    registrar, model, stub = election
    assert state(registrar) == "primary_search"
    assert model.primary_search_timer in model._timers
    found(registrar)
    assert state(registrar) == "primary_probe"
    assert registrar.share["lifecycle"] == "primary_probe"
    assert stub.published[-1] == (f"{DEAD}/in", f"(history {registrar.topic_probe} 0)")
    assert model._timers == {model.primary_probe_timer}  # the search timer cancelled

def test_probe_reply_makes_a_secondary(election):
    registrar, model, stub = election
    found(registrar)
    registrar._probe_handler(None, registrar.topic_probe, "(item_count 0)")
    assert state(registrar) == "secondary" and model._timers == set()
    assert stub.retained == []                           # nothing published

def test_probe_timeout_publishes_absent_then_the_echo_promotes(election):
    registrar, model, stub = election
    found(registrar)
    model.primary_probe_timer()                          # no reply
    assert stub.retained == [(BOOT, "(primary absent)")]
    assert state(registrar) == "primary_search"
    registrar._registrar_handler("absent", None)         # the echo
    assert state(registrar) == "primary"
    assert stub.will == (BOOT, "(primary absent)", True)
    assert stub.retained[-1][1].startswith(f"(primary found {registrar.topic_path} ")
    assert model._timers == set()

def test_probe_timeout_without_echo_the_search_timer_promotes(election):
    registrar, model, stub = election
    found(registrar)
    model.primary_probe_timer()
    assert model._timers == {model.primary_search_timer}
    model.primary_search_timer()                         # the echo was lost
    assert state(registrar) == "primary" and model._timers == set()

def test_own_topic_path_never_announced_is_stale(election):
    registrar, model, stub = election
    found(registrar, registrar.topic_path)               # a reused PID
    assert state(registrar) == "primary_search"
    assert stub.retained == [(BOOT, "(primary absent)")]
    assert not any(payload.startswith("(history") for _, payload in stub.published)

def test_own_topic_path_once_announced_is_this_registrar(election):
    registrar, model, stub = election
    registrar.announced = True
    found(registrar, registrar.topic_path)
    assert state(registrar) == "primary"

def test_absent_while_probing_searches_without_publishing(election):
    registrar, model, stub = election
    found(registrar)
    registrar._registrar_handler("absent", None)
    assert state(registrar) == "primary_search"
    assert stub.retained == [] and model._timers == {model.primary_search_timer}

def test_newer_primary_is_probed_again(election):
    registrar, model, stub = election
    found(registrar)
    found(registrar, "aiko/newhost/77/1")
    assert state(registrar) == "primary_probe" and model.probe_target == "aiko/newhost/77/1"
    assert stub.published[-1][0] == "aiko/newhost/77/1/in"
    probes = len(stub.published)
    found(registrar, "aiko/newhost/77/1")                # the same one: no new probe
    assert len(stub.published) == probes
    assert model._timers == {model.primary_probe_timer}

def test_late_reply_or_timer_is_ignored(election):
    registrar, model, stub = election
    registrar._probe_handler(None, registrar.topic_probe, "(item_count 0)")
    assert state(registrar) == "primary_search"          # not probing: ignored
    model.primary_probe_timer()
    assert stub.retained == []

def test_history_zero_costs_one_message(election):
    registrar, model, stub = election
    registrar.service_add("aiko/h/1/1", "s", "p:0", "mqtt", "o", [])
    registrar.service_remove("aiko/h/1/1")
    before = len(stub.published)
    registrar.services_history("t/probe", 0)
    assert stub.published[before:] == [("t/probe", "(item_count 0)")]

def test_probe_timeout_on_the_real_event_loop(election, monkeypatch):
    registrar, model, stub = election
    monkeypatch.setattr(registrar_module, "_PRIMARY_PROBE_TIMEOUT", 0.05)
    monkeypatch.setattr(registrar_module, "_PRIMARY_PROBE_JITTER", 0.0)
    monkeypatch.setattr(registrar_module, "_PRIMARY_SEARCH_TIMEOUT", 0.05)
    model._timer_remove(model.primary_search_timer)      # armed at 2 s: re-arm
    registrar.state_machine.transition("primary_found", {"topic_path": DEAD})

    def stop():
        event.remove_timer_handler(stop)
        event.terminate()

    event.add_timer_handler(stop, 0.5)
    event.loop()
    assert stub.retained[0] == (BOOT, "(primary absent)")
    assert state(registrar) == "primary"                 # the search timer promoted
    assert model._timers == set()

# registrar:3 — the timestamps, and what a client makes of them ---------- #
#
# "time_add" and "time_remove" used to be time.monotonic(): no other
# process could read them, and a restart began the clock again.  They are
# UTC ISO 8601 now, as s_03_SelfAwarenessTelemetry REQ-9 has every other
# timestamp, so the Registrar's version is 3 and not 2.

from aiko_services.main import REGISTRAR_PROTOCOL, REGISTRAR_VERSION
from aiko_services.main.utilities import datetime_now_utc_iso

RUNNING = ["aiko/h/1/1", "svc", "p:0", "mqtt", "owner", [],
           "2026-10-23T08:00:00.000000+00:00", "-"]
GONE = ["aiko/h/1/1", "svc", "p:0", "mqtt", "owner", [],
        "2026-10-23T08:00:00.000000+00:00",
        "2026-10-23T09:30:00.000000+00:00"]
OLD = ["aiko/h/1/1", "svc", "p:0", "mqtt", "owner", []]   # registrar:2

def test_the_version_says_the_wire_form_changed():
    assert REGISTRAR_VERSION == 3
    assert REGISTRAR_PROTOCOL.endswith("/registrar:3")

def test_a_running_service_has_an_uptime_and_no_duration():
    start, uptime, duration = service_duration(
        RUNNING, now_utc_iso="2026-10-23T08:45:30.000000+00:00")

    assert uptime == "45m30s"
    assert duration == "-"
    assert start.startswith("2026-10-23")      # local time, for a person

def test_a_terminated_service_has_a_duration_and_no_uptime():
    start, uptime, duration = service_duration(GONE)

    assert duration == "1h30m"
    assert uptime == "-"

def test_a_service_from_an_older_registrar_has_neither():
    """registrar:2 sent six fields, and a client of registrar:3 must show
    that rather than fail"""

    assert service_duration(OLD) == ("-", "-", "-")

# A registrar:2 Registrar's history reply, which is where this first went
# wrong.  Its "(share ...)" reply carries six fields, so the test above
# covered it, and its "(history ...)" reply carries eight -- with both
# times as time.monotonic() floats.  So the guard that tested only for an
# absent field let a number through to the ISO 8601 parser, and
# "aiko_registrar list --history" raised ValueError.

OLD_HISTORY = ["aiko/h/1/1", "svc", "p:0", "mqtt", "owner", [],
               "4672447.229599291", "4672450.100000000"]

def test_a_monotonic_time_from_an_older_registrar_is_not_a_time():
    """There is no origin another process can know, so there is no
    wall-clock time to show"""

    assert service_duration(OLD_HISTORY) == ("-", "-", "-")

def test_a_monotonic_time_that_is_still_running():
    details = OLD_HISTORY[:7] + ["-"]

    assert service_duration(details) == ("-", "-", "-")

@pytest.mark.parametrize("value", [
    "4672447.229599291", "0", "-1", "", "not a time", "2026-10-23",
    "2026-10-23T08:00:00", "08:17:40", None, 4672447.2, 0,
])
def test_anything_that_is_not_a_utc_iso_string_reads_as_absent(value):
    """Absence and unreadability are the same thing to a person reading a
    column, and neither may raise"""

    details = ["aiko/h/1/1", "svc", "p:0", "mqtt", "owner", [], value, "-"]

    assert service_duration(details) == ("-", "-", "-")

def test_a_readable_time_with_an_unreadable_remove():
    """Half of registrar:3 and half of something else: the start is still
    worth showing, and the duration is not"""

    details = ["aiko/h/1/1", "svc", "p:0", "mqtt", "owner", [],
               "2026-10-23T08:00:00.000000+00:00", "4672450.1"]

    start, uptime, duration = service_duration(
        details, now_utc_iso="2026-10-23T08:00:10.000000+00:00")
    assert start.startswith("2026-10-23")
    assert uptime == "10s" and duration == "-"    # read as still running

def test_the_uptime_of_a_service_that_just_started():
    now = datetime_now_utc_iso()
    details = RUNNING[:6] + [now, "-"]

    _, uptime, _ = service_duration(details, now_utc_iso=now)

    assert uptime == "0s"

@pytest.mark.parametrize("seconds,expected", [
    (0, "0s"), (3, "3s"), (59, "59s"), (60, "1m00s"), (124, "2m04s"),
    (3599, "59m59s"), (3600, "1h00m"), (3720, "1h02m"), (86399, "23h59m"),
    (86400, "1d00h"), (273600, "3d04h"),
])
def test_a_duration_a_person_reads_at_a_glance(seconds, expected):
    assert _seconds_terse(seconds) == expected

def test_a_negative_duration_is_not_shown_as_negative():
    """Two hosts' clocks disagree, so a remove can look earlier than its
    add.  s_03 says never to compare clocks across hosts, and this is what
    that looks like when it happens anyway"""

    assert _seconds_terse(-5) == "0s"

# The live stream accepts a Registrar that knows more than this client --- #

def cache_accepts(payload, topic_path):
    """Feed one "(add ...)" to a ServicesCache and say whether it landed.

    The cache is a per-process singleton that every composed Service
    registers into, so the count is whatever the tests before this one
    left behind.  Asserting a count made this test pass alone and fail in
    the suite.  What matters is that this topic path arrived"""

    cache = aiko.services_cache_create_singleton(aiko.process)
    try:
        before = cache.get_services().get_service(topic_path)
        cache.registrar_out_handler(None, "t/out", payload)
        after = cache.get_services().get_service(topic_path)
        return before is None and after is not None
    finally:
        aiko.services_cache_delete()

def test_the_services_cache_accepts_eight_fields():
    """share.py used to demand exactly six, so a newer Registrar's every
    registration was dropped with one debug line and nothing else"""

    assert cache_accepts(
        "(add aiko/h/1/1 svc p:0 mqtt owner ()"
        " 2026-10-23T08:00:00.000000+00:00 -)", "aiko/h/1/1")

def test_the_services_cache_still_accepts_six_fields():
    """A client of registrar:3 reading an older Registrar"""

    assert cache_accepts(
        "(add aiko/h/2/1 svc p:0 mqtt owner ())", "aiko/h/2/1")

# The command line ------------------------------------------------------- #

def test_the_bare_command_still_runs_the_registrar(monkeypatch):
    """"aiko_registrar" with no sub-command is what the ReadMe, four
    documents and every ProcessManager definition file say to type"""

    from click.testing import CliRunner

    ran = []
    monkeypatch.setattr(registrar_module, "compose_instance",
        lambda *args, **kwargs: ran.append("composed"))
    monkeypatch.setattr(aiko.process, "run", lambda *args, **kwargs: None)

    result = CliRunner().invoke(registrar_module.main, [])

    assert result.exit_code == 0, result.output
    assert ran == ["composed"]

def test_the_run_subcommand_does_the_same(monkeypatch):
    from click.testing import CliRunner

    ran = []
    monkeypatch.setattr(registrar_module, "compose_instance",
        lambda *args, **kwargs: ran.append("composed"))
    monkeypatch.setattr(aiko.process, "run", lambda *args, **kwargs: None)

    result = CliRunner().invoke(registrar_module.main, ["run"])

    assert result.exit_code == 0, result.output
    assert ran == ["composed"]

def test_the_list_subcommand_exists():
    from click.testing import CliRunner

    result = CliRunner().invoke(registrar_module.main, ["list", "--help"])

    assert result.exit_code == 0
    assert "--history" in result.output

# --------------------------------------------------------------------------- #

# The UTC utility the timestamps rest on --------------------------------- #
#
# It had no tests, and utc_iso_since_epoch() raised TypeError on every
# call: it subtracted a naive epoch from an aware datetime.  Nothing
# called it, so nothing reported it.

from aiko_services.main.utilities import (
    epoch_to_utc_iso, local_iso_now, utc_iso_to_datetime, utc_iso_to_local,
)

def test_a_stamp_converts_to_seconds_and_back():
    stamp = datetime_now_utc_iso()
    seconds = utc_iso_since_epoch(stamp)

    assert utc_iso_since_epoch(epoch_to_utc_iso(seconds)) ==  \
        pytest.approx(seconds, abs=0.001)

def test_the_epoch_itself():
    assert utc_iso_since_epoch("1970-01-01T00:00:00.000000+00:00") == 0.0

def test_a_stamp_with_no_microseconds():
    """utc_iso_to_datetime() branches on the length of the string"""

    assert utc_iso_since_epoch("2026-10-23T08:00:00+00:00") > 0

def test_a_stamp_is_a_single_wire_token():
    """It holds a "+" and colons, and no space or parenthesis, so the
    generator needs no length prefix and a reader gets it back exactly"""

    from aiko_services.main.utilities import generate

    stamp = datetime_now_utc_iso()
    payload = generate("update", ["time_add", stamp])

    assert " " not in stamp
    assert parse(payload)[1][1] == stamp

def test_the_local_form_is_for_a_person():
    local = utc_iso_to_local("2026-10-23T08:00:00.000000+00:00")

    assert len(local) == 19 and "T" not in local       # "YYYY-MM-DD HH:MM:SS"

def test_the_utilities_still_work_for_their_one_caller():
    """local_iso_now() is what pipeline.py stamps a frame with"""

    assert len(local_iso_now()) == 19
    assert utc_iso_to_datetime(datetime_now_utc_iso()).tzinfo is not None

# --------------------------------------------------------------------------- #

# The sentinel, as a decision rather than an accident ------------------- #
#
# The Go port asked whether "-" was deliberate, because the codec's own
# None is "0:".  It is: "0:" says None in Python, and each other language
# must then choose what None is, where "-" is a value every language reads
# the same way.  documentation/concepts/utilities/parser.md records the
# three sentinels.

def test_a_running_service_uses_the_dash_and_not_the_codecs_none():
    from aiko_services.main.registrar import _TIME_ABSENT
    from aiko_services.main.utilities import generate

    assert _TIME_ABSENT == "-"
    assert generate("add", ["t", _TIME_ABSENT]) == "(add t -)"
    assert generate("add", ["t", None]) == "(add t 0:)"   # the codec's None
    assert parse("(add t 0:)")[1][1] is None
    assert parse("(add t -)")[1][1] == "-"

def test_a_full_date_time_needs_no_length_prefix():
    """A bare clock time begins with "digits:", which the generator reads
    as a canonical symbol and prefixes.  The full form does not"""

    from aiko_services.main.utilities import generate

    full = "2026-10-23T08:17:40.845965+00:00"
    assert generate("add", ["t", full]) == f"(add t {full})"
    assert generate("add", ["t", "08:17:40"]) == "(add t 8:08:17:40)"

# --------------------------------------------------------------------------- #

def test_a_reader_still_reads_the_codecs_none():
    """The other half of the rule: "0:" is never written into a new wire
    form, and a reader keeps a None to read it with, because
    generate(None) still emits it and an older form still carries it"""

    from aiko_services.main.utilities import generate

    assert parse(generate("add", ["t", None]))[1][1] is None

# The client side of the version check ---------------------------------- #
#
# This branch had no test, and it shipped calling a logger that does not
# exist in process.py.  The NameError raised before "process_data.registrar" was
# set, so the enclosing "except" turned it into "Exception raised when
# adding to Registrar" and every Service failed to register against a
# registrar:2 Registrar.  The same shape as the deny-by-default guard that
# called a function that does not exist: a guard nothing executes.

import aiko_services.main.process as process_module

FOUND_V2 = "(primary found aiko/host/1/1 2 1234.5)"
FOUND_V3 = f"(primary found aiko/host/1/1 {REGISTRAR_VERSION} 1234.5)"

@pytest.fixture
def on_registrar(monkeypatch):
    """Drive ProcessImplementation.on_registrar() with no broker, and
    collect what it logged as an error"""

    errors = []
    monkeypatch.setattr(
        process_module._LOGGER_PROCESS, "error", errors.append)
    saved_message, saved_registrar = process_data.message, process_data.registrar
    process_data.message = _StubMessage()

    def drive(payload):
        aiko.process.on_registrar(None, BOOT, payload)
        return errors

    yield drive
    process_data.message = saved_message
    process_data.registrar = saved_registrar

def test_a_matching_version_is_not_reported(on_registrar):
    assert on_registrar(FOUND_V3) == []
    assert process_data.registrar["version"] == str(REGISTRAR_VERSION)

def test_an_older_registrar_is_reported_and_still_used(on_registrar):
    """Report, never refuse: the Service registers with a registrar:2
    Registrar and says so, because a reader of registrar:3 reads
    registrar:2"""

    errors = on_registrar(FOUND_V2)

    assert len(errors) == 1
    assert "version 2" in errors[0] and str(REGISTRAR_VERSION) in errors[0]
    assert process_data.registrar["version"] == "2"      # used, not refused

def test_the_report_cannot_stop_a_service_registering(on_registrar):
    """The report runs after the Service has registered, so a fault in it
    leaves the registration alone.  This is what went wrong"""

    def raise_anything(_message):
        raise RuntimeError("a fault in the report")

    process_module._LOGGER_PROCESS.error = raise_anything
    try:
        aiko.process.on_registrar(None, BOOT, FOUND_V2)
    except RuntimeError:
        pass                                     # swallowed by on_registrar
    assert process_data.registrar is not None
    assert process_data.registrar["topic_path"] == "aiko/host/1/1"

def test_an_absent_registrar_still_clears_it(on_registrar):
    on_registrar(FOUND_V3)
    assert process_data.registrar is not None

    on_registrar("(primary absent)")
    assert process_data.registrar is None

# --------------------------------------------------------------------------- #
