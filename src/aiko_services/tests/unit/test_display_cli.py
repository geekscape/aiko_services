# Unit tests for the "aiko_oled" command line: argument validation, the
# discovery filter, and the wire commands each subcommand sends (the
# framework's discovery and event loop are replaced by fakes).
#
# Usage: pytest src/aiko_services/tests/unit/test_oled_cli.py

import pytest
from click.testing import CliRunner

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname

from aiko_services.examples.oled import PROTOCOL, SETTINGS, WIRE_COMMANDS
from aiko_services.examples.oled import oled as oled_module
from aiko_services.examples.oled.display import fake_output
from aiko_services.examples.oled.oled import _service_filter, main

SUBCOMMANDS = ("run", "exit", "list", "clear", "log", "text", "pixels", "line",
               "set", "applet", "stop", "key", "keys", "mirror")

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
    result = invoke("--help")
    assert result.exit_code == 0
    for heading in ("Applets", "Settings", "Shared state", "Wire commands", "Keys  ("):
        assert heading in result.output, heading
    flat = " ".join(result.output.split())                 # wrapped lines joined
    for text in ("forklift_game", "blank_after", "log_pending", "(oled:text",
                 "pong | asteroids | invaders | forklift", "font 10 text Hello!"):
        assert text in flat, text
    assert all(len(line) <= 80 for line in result.output.splitlines())  # click wraps at 80
    for name in SUBCOMMANDS:
        result = invoke(name, "--help")
        assert result.exit_code == 0, name
        assert name in result.output
        assert all(len(line) <= 80 for line in result.output.splitlines()), name
    assert "forklift_game" in invoke("applet", "--help").output
    assert "arrows" in invoke("keys", "--help").output
    assert "hardware test" in invoke("set", "--help").output
    assert "foreground" in invoke("set", "--help").output
    assert "c clear" in invoke("keys", "--help").output
    assert "Braille" in invoke("run", "--help").output

@pytest.mark.parametrize("args", [
    ("text", "a", "b", "hello"),                    # (ranges: the Actor checks them)
    ("text", "0", "0"),
    ("pixels", "1"),
    ("pixels", "1", "x"),
    ("line", "0", "0", "x", "0"),
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
    assert invoke("mirror", "aiko/probe/mirror", "60").exit_code == 0
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
        ("mirror", ("aiko/probe/mirror", 60)),
        ("stop", ()),
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
    display = fake_output()
    monkeypatch.setattr(oled_module, "choose_output", lambda *args: display)
    monkeypatch.setattr(aiko.process, "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit(0)))
    result = invoke("-n", "oled_cli_test", "run", "-o", "none", "--standalone",
                    "--title", "off")
    assert result.exit_code == 0, result.output
    assert "oled_cli_test" in result.output
    assert display.opened and display.closed and display.blanked

def test_run_strict_reports_a_missing_display(monkeypatch):
    display = fake_output(fail_open=True)
    monkeypatch.setattr(oled_module, "choose_output", lambda *args: display)
    monkeypatch.setattr(oled_module, "scan_i2c", lambda *args: [0x3D])
    result = invoke("-n", "oled_cli_strict", "run", "-o", "none", "--strict")
    assert result.exit_code == 1
    assert "fake output told to fail" in result.output
    assert "0x3D" in result.output

# --------------------------------------------------------------------------- #
# The keys console

from aiko_services.examples.oled.keys import (  # noqa: E402
    MAPPED_KEYS, RESET, key_command, legend, reset_commands,
)

def test_key_map_parity():
    """Every command the key map emits is a declared wire method or a
    declared setting, and the legend names every mapped key"""

    state = {"turns": {}, "current": None, "settings": {}, "base_font": "5x7"}
    for key in sorted(MAPPED_KEYS):
        for _ in range(12):                                # every preset turn
            for command in key_command(key, state):
                if command[0] == "update":
                    assert command[1] in SETTINGS, (key, command)
                elif command[0] == "clear":
                    assert "clear" in WIRE_COMMANDS
                else:
                    assert command[0] in ("applet", "key") and command[0] in WIRE_COMMANDS
    for command in reset_commands(state):
        assert command[0] == "applet" or command[1] in SETTINGS
    legend_keys = set(legend()) - {"digits", "plus", "minus", "arrows"}
    assert legend_keys == MAPPED_KEYS - set("0123456789+-?")
    assert all(" " not in value for value in legend().values())

def test_cli_covers_every_wire_command():
    subcommands = set(main.commands)
    covered = {"clear", "log", "pixels", "line", "text", "applet", "key", "mirror"}
    assert covered <= subcommands
    assert WIRE_COMMANDS - {"pixel", "stop", "set_log_level"} == covered   # pixel: pixels
    assert {"exit", "stop", "set", "list", "run", "keys"} <= subcommands   # stop: exit
    help_text = invoke("set", "--help").output
    for name in SETTINGS:
        assert name in help_text, name

def test_keys_console_map():
    state = {"turns": {}, "current": None, "settings": {}, "base_font": "5x7"}
    assert key_command("left", state) == [("key", ("left", "tap"))]
    assert key_command("s", state) == [("applet", ("status",))]
    assert key_command("s", state) == [("applet", ("status", "screen=wifi"))]
    assert key_command("s", state) == [("applet", ("status",))]
    assert key_command("S", state) == [("applet", ("status",))]            # not running
    state["settings"].update({"applet": "status", "applet_detail": "host_text"})
    assert key_command("S", state) == [("applet", ("status", "screen=host", "view=cpu_mem"))]
    state["settings"]["applet_detail"] = "host_cpu_mem"
    assert key_command("S", state) == [("applet", ("status", "screen=host", "view=rx_tx"))]
    state["settings"]["applet_detail"] = "host_rx_tx"
    assert key_command("S", state) == [("applet", ("status", "screen=host", "view=text"))]
    state["settings"]["applet_detail"] = "wifi_text"
    assert key_command("S", state) == [("applet", ("status", "screen=wifi", "view=rssi"))]
    state["settings"]["applet"] = "pong"
    assert key_command("S", state) == [("applet", ("status",))]
    assert key_command("g", state) == [("applet", ("pong",))]
    assert key_command("g", state) == [("applet", ("asteroids",))]
    assert key_command("g", state) == [("applet", ("invaders",))]
    assert key_command("g", state) == [("applet", ("forklift",))]
    assert key_command("g", state) == [("applet", ("pong",))]
    assert key_command("G", state) == [("applet", ("forklift_game",))]
    assert key_command("P", state) == [("applet", ("blink",))]
    assert key_command("d", state) == [("applet", ("draw",))]
    assert key_command("d", state) == [("applet", ("draw", "shade=off"))]
    assert key_command("t", state)[0] == ("applet", ("text",))
    assert key_command("t", state) == [("update", "font", "5x7"), ("applet", ("text",))]
    assert key_command("t", state) == [("update", "font", "10"), ("applet", ("text",))]
    state["settings"]["font"] = "10"                     # the Actor applied it
    assert key_command("p", state) == [("update", "font", "5x7"), ("applet", ("pattern",))]
    state["settings"]["font"] = "5x7"
    assert key_command("0", state) == [("update", "speed", "4")]
    assert key_command("4", state) == [("update", "speed", "1")]
    assert key_command("9", state) == [("update", "speed", "0.177")]
    assert key_command("f", state) == [("update", "font", "8")] and state["base_font"] == "8"
    state["settings"]["font"] = "24"
    assert key_command("f", state) == [("update", "font", "5x7")]
    state["settings"]["font"] = "5x7"
    assert key_command("F", state) == [("update", "font", "24")]   # the previous font
    state["settings"]["font"] = "10"
    assert key_command("F", state) == [("update", "font", "8")]
    state["base_font"] = "5x7"                               # (as after "R")
    assert key_command("i", state) == [("update", "invert", "on")]
    state["settings"]["invert"] = "on"
    assert key_command("i", state) == [("update", "invert", "off")]
    assert key_command("o", state) == [("update", "power", "off")]
    assert key_command("-", state) == [("update", "contrast", "239")]
    assert key_command("+", state) == [("update", "contrast", "255")]
    assert key_command("c", state) == [("clear", ())]
    assert key_command("b", state) == [("update", "foreground", "white")]
    state["settings"]["foreground"] = "white"                # the Actor applied it
    assert key_command("b", state) == [("update", "foreground", "deepskyblue")]
    state["settings"]["foreground"] = "#123456"              # not in the list
    assert key_command("b", state) == [("update", "foreground", "white")]
    state["settings"]["background"] = "black"
    assert key_command("B", state) == [("update", "background", "midnightblue")]
    assert key_command("l", state) == [("update", "font", "5x7"), ("applet", ("log",))]
    state["settings"]["font"] = "5x7"
    assert key_command("C", state) == [("applet", ("clock",))]
    assert key_command("C", state) == [("applet", ("clock", "title=on"))]
    assert key_command("C", state) == [("applet", ("clock", "seconds=off"))]
    assert key_command("C", state) == [("applet", ("clock", "face=digital"))]
    assert key_command("e", state) == [("applet", ("eyes",))]
    assert key_command("e", state) == [("applet", ("eyes", "emotion=happy"))]
    assert key_command("h", state) == [("applet", ("help", "page=1"))]
    assert key_command("?", state) == [("applet", ("help", "page=2"))]   # ? is h
    assert key_command("T", state) == [("update", "title", "off")]
    state["settings"]["title"] = "off"
    assert key_command("T", state) == [("update", "title", "on")]
    for key in ("w", "A", "z", "k"):
        assert key_command(key, state) == []
    commands = reset_commands(state)
    assert commands[-1] == ("applet", ("status",))
    assert ("update", "foreground", "default") in commands
    assert len(commands) == len(RESET) + 1
    assert state["current"] == "s" and state["base_font"] == "5x7"

def test_keys_needs_a_terminal():
    result = invoke("keys")
    assert result.exit_code == 2 and "terminal" in result.output
