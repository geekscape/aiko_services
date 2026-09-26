# Unit tests for the "aiko_oled" command line: argument validation, the
# discovery filter, and the wire commands each subcommand sends (the
# framework's discovery and event loop are replaced by fakes).
#
# Usage: pytest src/aiko_services/tests/unit/test_oled_cli.py

import pytest
from click.testing import CliRunner

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname

from aiko_services.examples.oled import PROTOCOL, SETTINGS
from aiko_services.examples.oled import oled as oled_module
from aiko_services.examples.oled.display import FakeDisplay
from aiko_services.examples.oled.oled import _service_filter, main

SUBCOMMANDS = ("run", "exit", "list", "clear", "log", "text", "pixels", "line",
               "set", "applet", "stop", "key", "keys")

class RecordingProxy:
    """Stands in for the discovered OLED Actor's proxy"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name, args))

@pytest.fixture
def remote(monkeypatch):
    """Capture what a remote subcommand would send, without a broker"""

    proxy = RecordingProxy()
    seen = {}

    def do_command(interface, service_filter, command_handler, terminate=False):
        seen["interface"], seen["filter"] = interface, service_filter
        command_handler(proxy)

    monkeypatch.setattr(oled_module.aiko, "do_command", do_command)
    monkeypatch.setattr(oled_module, "_start_timeout", lambda *args: None)
    monkeypatch.setattr(aiko.process, "run", lambda *args, **kwargs: None)
    proxy.seen = seen
    return proxy

def invoke(*args):
    return CliRunner().invoke(main, list(args))

# --------------------------------------------------------------------------- #

def test_help_for_every_subcommand():
    assert invoke("--help").exit_code == 0
    for name in SUBCOMMANDS:
        result = invoke(name, "--help")
        assert result.exit_code == 0, name
        assert name in result.output

@pytest.mark.parametrize("args", [
    ("text", "a", "b", "hello"),
    ("text", "0", "64", "hello"),
    ("text", "0", "0"),
    ("pixels", "1"),
    ("pixels", "1", "x"),
    ("line", "0", "0", "200", "0"),
    ("set", "bogus", "1"),
    ("set", "title", "two words"),
    ("key", "up", "sideways"),
    ("run", "--address", "zz"),
    ("run", "-fs", "5"),
    ("run", "-c", "a b c"),
    ("run", "-o", "holodeck"),
    ("-n", "*", "exit"),
])
def test_bad_arguments_are_rejected(args):
    result = invoke(*args)
    assert result.exit_code == 2, result.output

def test_service_filter_defaults_to_the_hostname():
    service_filter = _service_filter(None)
    assert service_filter.name == get_hostname()
    assert service_filter.protocol == PROTOCOL
    assert _service_filter("w3029f1").name == "w3029f1"

def test_remote_commands_send_the_wire_command(remote):
    assert invoke("text", "0", "8", "hello", "world").exit_code == 0
    assert invoke("clear").exit_code == 0
    assert invoke("log", "boot", "ok").exit_code == 0
    assert invoke("pixels", "1", "2", "3", "4").exit_code == 0
    assert invoke("line", "0", "0", "127", "63").exit_code == 0
    assert invoke("applet", "pong", "seed=1").exit_code == 0
    assert invoke("stop").exit_code == 0
    assert invoke("key", "left").exit_code == 0
    assert invoke("key", "x", "down").exit_code == 0
    assert invoke("-n", "pi", "exit").exit_code == 0
    assert remote.calls == [
        ("text", (0, 8, "hello", "world")),
        ("clear", ()),
        ("log", ("boot", "ok")),
        ("pixels", (1, 2, 3, 4)),
        ("line", (0, 0, 127, 63)),
        ("applet", ("pong", "seed=1")),
        ("applet", ("none",)),
        ("key", ("left", "tap")),
        ("key", ("x", "down")),
        ("exit", ()),
    ]
    assert remote.seen["filter"].name == "pi"
    assert remote.seen["filter"].protocol == PROTOCOL

def test_set_publishes_an_update_on_the_control_topic(monkeypatch):
    published = []

    class Message:
        def publish(self, topic, payload):
            published.append((topic, payload))

    def do_discovery(interface, service_filter, add_handler=None, remove_handler=None):
        add_handler(("aiko/pi/1234/1", "pi", PROTOCOL, "mqtt", "me", []), None)

    monkeypatch.setattr(oled_module.aiko, "do_discovery", do_discovery)
    monkeypatch.setattr(oled_module, "_start_timeout", lambda *args: None)
    monkeypatch.setattr(aiko.process, "message", Message())
    monkeypatch.setattr(aiko.process, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(aiko.process, "terminate", lambda *args: None)
    assert invoke("set", "contrast", "64").exit_code == 0
    assert published == [("aiko/pi/1234/1/control", "(update contrast 64)")]
    for key in SETTINGS:
        assert invoke("set", key, "1").exit_code == 0

def test_run_composes_the_actor_and_blanks_on_exit(monkeypatch):
    display = FakeDisplay()
    monkeypatch.setattr(oled_module, "choose_display", lambda *args: display)
    monkeypatch.setattr(aiko.process, "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit(0)))
    result = invoke("-n", "oled_cli_test", "run", "-o", "none", "--standalone",
                    "--title", "off")
    assert result.exit_code == 0, result.output
    assert "oled_cli_test" in result.output
    assert display.opened and display.closed and display.blanked

def test_run_strict_reports_a_missing_display(monkeypatch):
    display = FakeDisplay(fail_open=True)
    monkeypatch.setattr(oled_module, "choose_display", lambda *args: display)
    monkeypatch.setattr(oled_module, "scan_i2c", lambda *args: [0x3D])
    result = invoke("-n", "oled_cli_strict", "run", "-o", "none", "--strict")
    assert result.exit_code == 1
    assert "fake display told to fail" in result.output
    assert "0x3D" in result.output

# --------------------------------------------------------------------------- #
# The keys console

from aiko_services.examples.oled.console import key_command  # noqa: E402

def test_keys_console_map():
    state = {"turns": {}, "current": None, "settings": {}}
    assert key_command("left", state) == ("key", ("left", "tap"))
    assert key_command("s", state) == ("applet", ("status",))
    assert key_command("s", state) == ("applet", ("status", "rate=4"))
    assert key_command("s", state) == ("applet", ("status",))
    assert key_command("p", state) == ("applet", ("pattern",))
    assert key_command("d", state) == ("applet", ("draw",))
    assert key_command("d", state) == ("applet", ("draw", "shade=off"))
    assert key_command("0", state) == ("update", "speed", "4")
    assert key_command("4", state) == ("update", "speed", "1")
    assert key_command("9", state) == ("update", "speed", "0.177")
    assert key_command("f", state) == ("update", "font", "8")
    state["settings"]["font"] = "24"
    assert key_command("f", state) == ("update", "font", "5x7")
    assert key_command("i", state) == ("update", "invert", "on")
    state["settings"]["invert"] = "on"
    assert key_command("i", state) == ("update", "invert", "off")
    assert key_command("o", state) == ("update", "power", "off")
    assert key_command("-", state) == ("update", "contrast", "239")
    assert key_command("+", state) == ("update", "contrast", "255")
    assert key_command("c", state) == ("clear", ())
    assert key_command("l", state) == ("applet", ("log",))
    assert key_command("C", state) == ("applet", ("clock",))
    assert key_command("e", state) == ("applet", ("eyes",))
    assert key_command("h", state) == ("applet", ("help", "page=1"))
    assert key_command("h", state) == ("applet", ("help", "page=2"))
    assert key_command("T", state) == ("update", "title", "off")
    state["settings"]["title"] = "off"
    assert key_command("T", state) == ("update", "title", "on")
    assert key_command("z", state) is None

def test_applet_list_needs_no_actor():
    result = invoke("applet", "--list")
    assert result.exit_code == 0
    for name in ("status", "log", "pong", "draw", "demo"):
        assert name in result.output
    assert "seed=" in result.output and "rate=" in result.output
    assert invoke("applet").exit_code == 2

def test_keys_needs_a_terminal():
    result = invoke("keys")
    assert result.exit_code == 2 and "terminal" in result.output
