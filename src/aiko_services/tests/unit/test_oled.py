# Unit tests for the OLED example: graphics, display backends, the Actor
# (dispatch, wire commands, settings, applets, failure behavior) and
# the share-token contract.  No MQTT broker: the Actor is composed with a
# FakeDisplay and its methods are called directly; the event loop runs
# briefly with mqtt_connection_required=False where mailboxes or timers
# matter.  Every wire method has at least one negative test (ADR-014).
#
# Usage: pytest src/aiko_services/tests/unit/test_oled.py

import itertools
import sys
import threading

import pytest

import aiko_services as aiko
from aiko_services.main.utilities import parse

from aiko_services.examples.oled import (
    Canvas, Display, Interaction, OLEDImpl, PROTOCOL, SETTINGS,
    SETTINGS_SPEC, Screen, WIRE_COMMANDS, service_tags,
)
from aiko_services.examples.oled import applets
from aiko_services.examples.oled.applets import (
    Applet, AppletDone, parse_applet_args,
)
from aiko_services.examples.oled.display import (
    OUTPUTS, DisplayNotFound, FakeOutputImpl, NullOutputImpl, Output,
    OutputControls, PngOutputImpl, choose_output, fake_output, parse_colors,
    text_lines,
)
from aiko_services.examples.oled.graphics import (
    HEIGHT, WIDTH, Font, FrameBuffer, parse_font_size, title_strip,
)

_counter = itertools.count()

# --------------------------------------------------------------------------- #
# Helpers

def make_actor(**parameters):
    display = parameters.pop("output", None) or fake_output()
    parameters = {"output": display, "title": "off", "applet": "none", **parameters}
    name = f"oled_test_{next(_counter)}"
    actor = aiko.compose_instance(OLEDImpl,
        aiko.actor_args(name, parameters=parameters, protocol=PROTOCOL))
    return actor, display

@pytest.fixture
def actor_display():
    actor, display = make_actor()
    yield actor, display
    actor._shutdown()

def run_loop(seconds=0.2):
    """Run the event loop for a moment: mailboxes and timers"""

    def stop():
        aiko.event.remove_timer_handler(stop)
        aiko.process.terminate()

    aiko.event.add_timer_handler(stop, seconds)
    aiko.process.run(mqtt_connection_required=False)

def lit_rows(image):
    return sorted({y for y in range(image.height)
        for x in range(image.width) if image.getpixel((x, y))})

def lit_count(image):
    return sum(1 for y in range(image.height)
        for x in range(image.width) if image.getpixel((x, y)))

class Bouncer(Applet):
    """A test applet: one moving pixel per frame, records keys"""

    name = "bouncer"
    fps = 30
    OPTIONS = {"seed": int}
    description = "bouncing"

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.count = 0
        self.keys = []
        self.stopped = False

    def step(self):
        self.count += 1
        frame = self.frame()
        frame.putpixel((self.count % WIDTH, 10), 255)
        return frame

    def key(self, name, state):
        self.keys.append((name, state))

    def stop(self):
        self.stopped = True

class Failing(Applet):
    name = "failing"

    def step(self):
        raise RuntimeError("boom")

class Finishing(Applet):
    name = "finishing"

    def step(self):
        raise AppletDone

@pytest.fixture
def test_applets(monkeypatch):
    for applet in (Bouncer, Failing, Finishing):
        monkeypatch.setitem(applets.APPLETS, applet.name, applet)

# --------------------------------------------------------------------------- #
# Graphics

def test_font_5x7_renders_glyphs():
    font = Font("5x7")
    image = font.render("A")
    assert image.size == (5, 7)
    assert font.cell_height == 8 and font.cell_width == 6
    assert [image.getpixel((0, row)) > 0 for row in range(7)] ==  \
        [False, True, True, True, True, True, True]   # 0x7e: rows 1..6
    assert font.render("AB").size == (11, 7)

def test_parse_font_size():
    assert parse_font_size("5x7").token() == "5x7"
    font = parse_font_size("12")
    assert font.token() == "12" and font.cell_height == font.line_height + 1
    for bad in ("5", "65", "abc", "", "12.5"):
        with pytest.raises(ValueError):
            parse_font_size(bad)

def test_canvas_origin_is_bottom_left():
    canvas = FrameBuffer(Font("5x7"))
    canvas.pixel(0, 0)
    assert canvas.image.getpixel((0, HEIGHT - 1))
    canvas.pixel(WIDTH - 1, HEIGHT - 1)
    assert canvas.image.getpixel((WIDTH - 1, 0))
    canvas.clear()
    canvas.text(0, 0, "A")
    assert lit_rows(canvas.image) == list(range(56, 63))
    canvas.clear()
    canvas.text(0, 8, "A")
    assert lit_rows(canvas.image) == list(range(48, 55))
    canvas.clear()
    canvas.line(0, 0, 0, 63)
    assert lit_count(canvas.image) == HEIGHT

def test_canvas_log_scrolls_below_the_title_row():
    canvas = FrameBuffer(Font("5x7"))
    canvas.title_rows = 8
    canvas.log("ONE")
    assert lit_rows(canvas.image) == list(range(56, 63))
    canvas.log("TWO")
    rows = lit_rows(canvas.image)
    assert rows[0] == 48 and rows[-1] == 62         # "ONE" moved up a row
    canvas.clear()
    assert lit_count(canvas.image) == 0
    canvas.title_rows = 8
    for _ in range(9):
        canvas.log("x")
    assert min(lit_rows(canvas.image)) >= 8           # never into the title

def test_title_strip_is_inverse_video():
    strip = title_strip(Font("5x7"), "nomad", "LMR", "12:30:45")
    assert strip.size == (WIDTH, 8)
    lit = lit_count(strip)
    assert WIDTH * 8 * 0.6 < lit < WIDTH * 8          # mostly lit, text unlit

# --------------------------------------------------------------------------- #
# Display backends

def test_fake_output_emulates_the_panel():
    output = fake_output()
    output.open()
    canvas = FrameBuffer(Font("5x7"))
    canvas.pixel(0, 0)
    output.show(canvas.image)
    assert len(output.frames) == 1

    def shown():
        return output.appearance.apply(output.frame)

    assert shown().getpixel((0, HEIGHT - 1))
    output.invert(True)
    assert not shown().getpixel((0, HEIGHT - 1))
    output.invert(False)
    output.power(False)
    assert lit_count(shown()) == 0
    output.power(True)
    output.all_on(True)
    assert lit_count(shown()) == WIDTH * HEIGHT
    assert output.controls[-1] == ("all_on", True)
    output.close()
    assert output.closed and output.blanked

def test_text_lines():
    canvas = FrameBuffer(Font("5x7"))
    canvas.pixel(0, HEIGHT - 1)                          # top-left pixel
    lines = text_lines(canvas.image, blocks=True)
    assert len(lines) == HEIGHT // 2 and all(len(line) == WIDTH for line in lines)
    assert lines[0][0] == "▀"
    lines = text_lines(canvas.image, blocks=False)
    assert len(lines) == HEIGHT // 4 and len(lines[0]) == WIDTH // 2
    assert lines[0][0] == chr(0x2801)

def test_png_output_writes_a_file(tmp_path):
    path = tmp_path / "oled.png"
    output = choose_output("png", png_path=path)
    output.open()
    output.show(FrameBuffer(Font("5x7")).image)
    output.close()
    from PIL import Image
    assert Image.open(path).size == (WIDTH * 4, HEIGHT * 4)

def test_choose_output_composes_every_backend(tmp_path):
    """Every -o choice composes to an instance with the full Output and
    OutputControls method set (the default Impl fills what a backend lacks)"""

    methods = [name for interface in (Output, OutputControls)
               for name, member in vars(interface).items()
               if getattr(member, "__isabstractmethod__", False)]
    assert sorted(methods) == sorted([
        "add_handler", "all_on", "close", "contrast", "invert", "message",
        "open", "power", "pump", "set_colors", "show"])
    for name in [*OUTPUTS, "fake"]:
        if name == "auto":
            continue
        output = choose_output(name, png_path=tmp_path / "x.png")
        assert output.name == name, name
        assert all(callable(getattr(output, method)) for method in methods), name
        output.add_handler(lambda event: None)   # the no-ops work unopened,
        output.pump()                            # whatever __init__ ran
        output.message("hello")
        output.set_colors((1, 2, 3), None)
    assert isinstance(choose_output("fake"), FakeOutputImpl)
    assert isinstance(choose_output("none"), NullOutputImpl)
    assert isinstance(choose_output("png", png_path=tmp_path / "x.png"), PngOutputImpl)
    with pytest.raises(ValueError):
        choose_output("holodeck")

def test_colors_and_pumped_events():
    output = fake_output()
    output.set_colors(*parse_colors("yellow navy"))
    assert output.foreground == (255, 255, 0) and output.background == (0, 0, 128)
    with pytest.raises(ValueError):
        parse_colors("a b c")
    seen = []
    output.add_handler(seen.append)
    output.events = [("tap", "g"), "quit"]
    output.pump()
    assert seen == [("tap", "g"), "quit"] and output.events == []

# --------------------------------------------------------------------------- #
# The Actor: composition and dispatch

def test_composition_and_wire_commands(actor_display):
    actor, display = actor_display
    for aspect in (Display, Canvas, Screen, Interaction):
        assert isinstance(actor, aspect)
    assert WIRE_COMMANDS == {"clear", "log", "pixel", "pixels", "line", "text",
        "applet", "key", "mirror", "set_log_level", "stop"}
    assert PROTOCOL.endswith("/display:0")
    assert service_tags("fake") == ["ec=true", "device=fake", "canvas=0", "screen=0",
                                    "interaction=0"]
    assert actor.share["settings"] == ",".join(SETTINGS)
    assert actor.share["depth"] == "1" and actor.share["panels"] == "fake"
    assert actor.share["keys"]["g"] == "pong|asteroids|invaders|forklift"
    assert [setting.name for setting in SETTINGS_SPEC] == list(SETTINGS)
    for name in ("run", "add_tags", "_tick", "_shutdown", "ec_producer_change_handler"):
        assert name not in WIRE_COMMANDS
    assert "oled_test" not in sys.modules                 # R0: never imported
    assert actor.share["backend"] == "fake" and actor.share["device"] == "fake"
    assert actor.share["size"] == "128x64" and actor.share["origin"] == "bottom"
    assert actor.share["applet"] == "none"
    assert display.opened and len(display.frames) == 1   # the blank canvas

def test_dispatch_aliases_allow_list_and_parse_guard(actor_display):
    actor, display = actor_display
    for payload in ("(oled:text 0 0 hello)", "(run)", "(bogus 1)",
                    "(log 12:30 lunch)", "(text x: 1 y: 2)", "(add_tags t)"):
        actor._topic_in_handler(None, actor.topic_in, payload)
    run_loop()
    assert lit_rows(display.frames[-1]) == list(range(56, 63))
    assert actor._metrics["rejected"] == 5
    assert actor.share["last_error"].startswith("dispatch_")
    assert actor._metrics["commands"] == 1

# --------------------------------------------------------------------------- #
# The Actor: wire commands

def test_pixel(actor_display):
    actor, display = actor_display
    actor.pixel("0", "0")
    assert display.frames[-1].getpixel((0, HEIGHT - 1))
    actor.pixel(127, 63)
    assert display.frames[-1].getpixel((WIDTH - 1, 0))
    frames = len(display.frames)
    actor.pixel("128", "0")
    actor.pixel("a", "0")
    actor.pixel("0", "-1")
    assert len(display.frames) == frames and actor._metrics["rejected"] == 3
    assert actor.share["last_error"].startswith("pixel_y_range@")

def test_pixels_is_atomic(actor_display):
    actor, display = actor_display
    actor.pixels("0", "0", "127", "63")
    assert display.frames[-1].getpixel((0, 63)) and display.frames[-1].getpixel((127, 0))
    frames = len(display.frames)
    actor.pixels("1", "1", "200")             # odd count
    actor.pixels("1", "1", "5", "64")         # one out of range: nothing lit
    actor.pixels()
    assert len(display.frames) == frames and actor._metrics["rejected"] == 3
    assert not display.frames[-1].getpixel((1, 62))

def test_line(actor_display):
    actor, display = actor_display
    actor.line("0", "0", "0", "63")
    assert lit_count(display.frames[-1]) == HEIGHT
    frames = len(display.frames)
    actor.line("0", "0", "128", "0")
    assert len(display.frames) == frames and actor._metrics["rejected"] == 1

def test_text(actor_display):
    actor, display = actor_display
    actor.text("0", "8", "hello", "world")
    assert lit_rows(display.frames[-1]) == list(range(48, 55))
    frames = len(display.frames)
    actor.text("a", "0", "x")
    actor.text("0", "0")                      # no words
    actor.text("0", "0", ["nested"])
    actor.text("0", "0", "x" * 129)
    assert len(display.frames) == frames and actor._metrics["rejected"] == 4
    assert actor.share["last_error"].startswith("text_too_long@")

def test_clear(actor_display):
    actor, display = actor_display
    actor.text(0, 0, "hello")
    actor.clear()
    assert lit_count(display.frames[-1]) == 0

def test_log_scrolls_and_keeps_eight_lines(actor_display):
    actor, display = actor_display
    assert actor.share["log_pending"] == "off"
    for n in range(10):
        actor.log(f"line{n}", "x")
    assert list(actor._log)[0] == "line2 x" and len(actor._log) == 8
    assert actor.share["log_count"] == "10"
    assert actor.share["log_pending"] == "on" and actor._log_pending
    actor._host.log_seen()
    assert actor.share["log_pending"] == "off"
    frame = display.frames[-1]
    assert min(lit_rows(frame)) < 8                       # scrolled to the top
    frames = len(display.frames)
    actor.log()
    actor.log(["nested"])
    assert len(display.frames) == frames and actor._metrics["rejected"] == 2

def test_exit_is_stop_and_terminates(actor_display, monkeypatch):
    actor, _ = actor_display
    calls, posted = [], []
    monkeypatch.setattr(aiko.process, "terminate", lambda *args: calls.append(args))
    monkeypatch.setattr(actor, "_post_message", lambda *args: posted.append(args))
    actor._topic_in_handler(None, actor.topic_in, "(exit)")
    assert posted[-1][1:] == ("stop", [])                # the alias
    actor.stop()
    assert calls == [()]

# --------------------------------------------------------------------------- #
# The Actor: applets

def test_applet_lifecycle(actor_display, test_applets):
    actor, display = actor_display
    actor.applet("bouncer", "seed=3")
    assert actor.share["applet"] == "bouncer"
    assert actor.share["applet_detail"] == "bouncing"
    assert actor._applet.options == {"seed": 3}
    run_loop(0.3)
    assert actor._applet.count >= 3 and len(display.frames) >= 4
    bouncer = actor._applet
    actor.log("still", "running")                          # log doesn't stop it
    assert actor._applet is bouncer
    actor.text(0, 0, "canvas")                            # drawing does
    assert actor._applet is None and bouncer.stopped
    assert actor.share["applet"] == "none"
    assert actor.share["applet_detail"] == "-"
    actor.applet("bouncer")
    actor.applet("none")
    assert actor._applet is None

def test_applet_rejections(actor_display, test_applets):
    actor, _ = actor_display
    actor.applet("nosuch")
    assert actor.share["applet"] == "none"
    assert actor.share["last_error"].startswith("set_applet_unknown@")
    actor.applet("bouncer", "seed=abc")
    actor.applet("bouncer", "colour=red")
    actor.applet("bouncer", "x" * 65)
    assert actor._metrics["rejected"] == 4 and actor._applet is None

def test_finished_applet_returns_to_default(actor_display, test_applets):
    actor, _ = actor_display
    actor._default_applet = "bouncer"
    actor.applet("finishing")
    run_loop(0.2)
    assert actor.share["applet"] == "bouncer"
    actor.applet("finishing")
    actor._default_applet = "none"
    run_loop(0.2)
    assert actor.share["applet"] == "none"

def test_failing_applet_is_stopped_not_the_process(actor_display, test_applets):
    actor, _ = actor_display
    actor.applet("failing")
    run_loop(0.2)                                          # the loop survives
    assert actor.share["applet"] == "none"
    assert actor._metrics["errors"] >= 1
    assert actor.share["last_error"].startswith("tick_RuntimeError@")

def test_keys(actor_display, test_applets):
    actor, _ = actor_display
    actor.applet("bouncer")
    actor.key("up")
    actor.key("x", "down")
    assert actor._keys_held() == {"up", "x"}
    assert actor._applet.keys == [("up", "tap"), ("x", "down")]
    actor.key("x", "up")
    assert actor._keys_held() == {"up"}
    actor.key("select")
    actor.key("up", "sideways")
    assert actor._metrics["rejected"] == 2
    for name in "jkmnuvw":                                 # keys the map ignores
        actor.key(name, "down")
    assert len(actor._held) == 5                           # bounded

def test_wire_key_runs_the_map(actor_display, test_applets):
    actor, _ = actor_display
    actor.key("g")                                         # a mapped key: its preset
    assert actor.share["applet"] == "pong"
    actor.key("g", "down")
    assert actor.share["applet"] == "asteroids"
    actor.key("5")
    assert actor.share["speed"] == "0.707"
    actor.key("b")
    assert actor.share["foreground"] == "deepskyblue"
    actor.key("R")
    assert actor.share["applet"] == "status" and actor.share["speed"] == "1"
    actor.applet("bouncer")
    actor.key("w")                                         # not mapped: the applet's
    actor.key("g", "up")                                   # a release does nothing
    assert actor._applet.keys == [("w", "tap")]

# --------------------------------------------------------------------------- #
# The Actor: settings through the shared state

def remote_update(actor, key, value):
    """What ECProducer does for "(update KEY VALUE)" on the control topic:
    the share is written first, then the change handlers run"""

    actor.share[key] = value
    actor._ec_producer_change_handler("update", key, value)

def test_settings_apply_and_bad_values_converge(actor_display):
    actor, display = actor_display
    remote_update(actor, "contrast", "64")
    assert actor.share["contrast"] == "64" and display.controls[-1] == ("contrast", 64)
    remote_update(actor, "contrast", "abc")
    assert actor.share["contrast"] == "64"
    assert actor.share["last_error"].startswith("set_contrast_not_int@")
    remote_update(actor, "invert", "on")
    assert actor.share["invert"] == "on" and display.appearance.inverted
    remote_update(actor, "invert", "maybe")
    assert actor.share["invert"] == "on"
    remote_update(actor, "power", "off")
    assert not display.appearance.powered
    remote_update(actor, "all_on", "1")
    assert actor.share["all_on"] == "on" and display.appearance.all_lit
    remote_update(actor, "speed", "2.5")
    assert actor.share["speed"] == "2.5" and actor._speed == 2.5
    remote_update(actor, "speed", "0")
    assert actor.share["speed"] == "2.5"
    remote_update(actor, "font", "12")
    assert actor.share["font"] == "12" and actor._font.token() == "12"
    remote_update(actor, "font", "5")
    assert actor.share["font"] == "12"
    remote_update(actor, "blank_after", "30")
    assert actor._blank_after == 30
    remote_update(actor, "blank_after", "-1")
    assert actor.share["blank_after"] == "30"
    assert actor._metrics["rejected"] == 5
    for key in SETTINGS:
        assert actor.share[key] == actor._applied[key]

def test_color_settings_apply_and_reset(actor_display, monkeypatch):
    actor, display = actor_display
    assert actor.share["foreground"] == "white" and actor.share["background"] == "black"
    remote_update(actor, "foreground", "yellow")
    assert actor.share["foreground"] == "yellow"
    assert display.foreground == (255, 255, 0) and display.controls[-1][0] == "colors"
    remote_update(actor, "background", "#000080")
    assert display.background == (0, 0, 128) and actor.share["background"] == "#000080"
    remote_update(actor, "foreground", "not_a_color")
    assert actor.share["foreground"] == "yellow"            # converged back
    assert actor.share["last_error"].startswith("set_foreground_not_color@")
    remote_update(actor, "foreground", "default")
    assert actor.share["foreground"] == "white" and display.foreground == (255, 255, 255)
    started, _ = make_actor(colors=["lime", "navy"])       # -c 'lime navy'
    try:
        assert started.share["foreground"] == "lime"
        assert started._output.foreground == (0, 255, 0)
        assert started._output.background == (0, 0, 128)
        remote_update(started, "background", "white")
        remote_update(started, "background", "default")
        assert started.share["background"] == "navy"
    finally:
        started._shutdown()

def test_window_keys_use_the_console_map(actor_display, test_applets, monkeypatch):
    actor, display = actor_display
    exits = []
    monkeypatch.setattr(aiko.process, "terminate", lambda *args: exits.append(args))

    def typed(*keys):
        display.events = [("tap", key) for key in keys]
        actor._step()

    typed("g")
    assert actor.share["applet"] == "pong"
    typed("g")
    assert actor.share["applet"] == "asteroids"              # the next preset
    typed("5", "b", "b", "B", "-")
    assert actor.share["speed"] == "0.707"
    assert actor.share["foreground"] == "yellow"             # white, deepskyblue, yellow
    assert display.foreground == (255, 255, 0)
    assert actor.share["background"] == "midnightblue"
    assert actor.share["contrast"] == "239"
    typed("c")
    assert actor.share["applet"] == "none"                   # clear: a drawing command
    typed("?")
    assert actor.share["applet"] == "help"                   # ? is help, as h
    typed("R")
    assert actor.share["applet"] == "status"
    assert actor.share["foreground"] == "white" and actor.share["contrast"] == "255"
    assert actor.share["speed"] == "1"
    actor.applet("bouncer")
    typed("w")                                               # not a console key
    assert actor._applet.keys[-1] == ("w", "tap")
    display.events = [("down", "left"), ("up", "left")]     # arrows: the applet's
    actor._step()
    assert actor._applet.keys[-2:] == [("left", "down"), ("left", "up")]
    typed("x")
    assert exits                                             # as Esc: the Actor exits

def mirror_setup(actor, monkeypatch, connected=True):
    published = []
    monkeypatch.setattr(aiko.process.message, "publish",
                        lambda topic, payload, **kwargs: published.append((topic, payload)))
    monkeypatch.setattr(aiko.process.connection, "is_connected", lambda state: connected)
    return published

def test_mirror_publishes_on_change_and_caps_rate(actor_display, monkeypatch):
    actor, display = actor_display
    published = mirror_setup(actor, monkeypatch)
    actor.mirror("aiko/probe/mirror", "30")
    assert actor.share["mirrors"] == "1" and actor._metrics["rejected"] == 0
    actor._step()                                          # the holder sees the panel now
    assert published[-1][0] == "aiko/probe/mirror" and len(published[-1][1]) == 1024
    assert published[-1][1] == display.frames[-1].tobytes()
    count = len(published)
    actor.text("0", "0", "hi")                             # within the rate: pending
    assert len(published) == count and actor._mirror_pending == display.frames[-1].tobytes()
    actor._mirror_due = 0.0
    actor._step()                                          # the end of the burst
    assert len(published) == count + 1 and actor._mirror_pending is None
    actor.text("0", "0", "hi")                             # unchanged: nothing
    actor._mirror_due = 0.0
    actor._step()
    assert len(published) == count + 1
    remote_update(actor, "mirror_rate", "10")
    assert actor._mirror_rate == 10 and actor.share["mirror_rate"] == "10"
    actor._flush_metrics()
    assert actor.share["metrics"]["mirrored"] == "2"

def test_mirror_leases_extend_expire_and_destroy(actor_display, monkeypatch):
    actor, _ = actor_display
    mirror_setup(actor, monkeypatch)
    actor.mirror("aiko/probe/a", "1")
    actor.mirror("aiko/probe/a", "1")                      # extend, not a second holder
    assert actor.share["mirrors"] == "1"
    run_loop(1.4)
    assert actor.share["mirrors"] == "0" and not actor._mirrors   # expired
    actor.mirror("aiko/probe/b", "30")
    actor.mirror("aiko/probe/b", "0")                      # destroy
    assert actor.share["mirrors"] == "0"

def test_mirror_rejections_and_bounds(actor_display, monkeypatch):
    actor, _ = actor_display
    mirror_setup(actor, monkeypatch)
    actor.mirror("aiko/+/mirror", "30")
    assert actor.share["last_error"].startswith("mirror_topic@")
    actor.mirror("aiko/probe", "999")
    assert actor.share["last_error"].startswith("mirror_seconds_range@")
    actor.mirror("aiko/probe", "soon")
    assert actor.share["last_error"].startswith("mirror_seconds_not_int@")
    for holder in range(5):
        actor.mirror(f"aiko/probe/{holder}", "30")
    assert actor.share["mirrors"] == "4"                   # bounded
    assert actor.share["last_error"].startswith("mirror_full@")
    assert actor._metrics["rejected"] == 4
    actor._shutdown()
    assert not actor._mirrors                              # leases terminated

def test_mirror_drops_frames_while_disconnected(actor_display, monkeypatch):
    actor, _ = actor_display
    published = mirror_setup(actor, monkeypatch, connected=False)
    actor.mirror("aiko/probe/mirror", "30")
    actor._step()
    actor.text("0", "0", "hi")
    actor._mirror_due = 0.0
    actor._step()
    assert published == [] and actor._metrics["mirrored"] == 0   # no block, no send

def test_title_setting(actor_display):
    actor, display = actor_display
    assert actor.share["title"] == "off" and actor._canvas.title_rows == 0
    remote_update(actor, "title", "Aiko_v0.8")
    assert actor._title_text == "Aiko v0.8" and actor._canvas.title_rows == 8
    assert lit_count(display.frames[-1]) > 200                # the strip
    remote_update(actor, "title", "off")
    assert actor.share["title"] == "off" and lit_count(display.frames[-1]) == 0
    remote_update(actor, "title", "on")                      # the last text again
    assert actor.share["title"] == "Aiko_v0.8" and actor._title_text == "Aiko v0.8"
    remote_update(actor, "title", "off")
    remote_update(actor, "title", "x" * 33)
    assert actor.share["title"] == "off" and actor._metrics["rejected"] == 1

def test_own_updates_do_not_loop_and_replay_is_ignored(actor_display, monkeypatch):
    actor, display = actor_display
    calls = []
    original = actor._setters["contrast"]
    monkeypatch.setitem(actor._setters, "contrast",
        lambda value: (calls.append(value), original(value)))
    remote_update(actor, "contrast", "100")
    assert calls == ["100"]                                # once, not re-entered
    actor._ec_producer_change_handler("add", "contrast", "100")
    actor._ec_producer_change_handler("update", "metrics.frames", "3")
    assert calls == ["100"]

def test_applet_setting_starts_an_applet(actor_display, test_applets):
    actor, _ = actor_display
    remote_update(actor, "applet", "bouncer,seed=7")
    assert actor.share["applet"] == "bouncer"
    assert actor._applet.options == {"seed": 7}
    remote_update(actor, "applet", "nosuch")
    assert actor.share["applet"] == "bouncer"

# --------------------------------------------------------------------------- #
# The Actor: display failure, blanking, threads, shutdown

def test_display_not_found_degrades_and_reopens():
    display = fake_output(fail_open=True)
    actor, _ = make_actor(output=display)
    try:
        assert actor.share["device"] == "absent"
        assert actor.share["last_error"].startswith("display_not_found@")
        assert not actor._output_ok and actor._reopening
        actor.text(0, 0, "unseen")
        assert display.frames == []
        display.fail_open = False
        actor._reopen()
        assert actor._output_ok and actor.share["device"] == "fake"
        assert len(display.frames) == 1 and not actor._reopening
    finally:
        actor._shutdown()

def test_strict_display_not_found_raises():
    display = fake_output(fail_open=True)
    with pytest.raises(DisplayNotFound):
        make_actor(output=display, strict=True)

def test_show_failure_marks_the_display_absent(actor_display, monkeypatch):
    actor, display = actor_display

    def broken(image):
        raise OSError("I2C unplugged")

    monkeypatch.setattr(display, "show", broken)
    actor.text(0, 0, "x")
    assert actor.share["device"] == "absent" and not actor._output_ok
    assert actor.share["last_error"].startswith("display_failed@")
    actor.text(0, 8, "y")                                  # no exception

def test_blank_after_powers_down_until_activity(actor_display):
    actor, display = actor_display
    remote_update(actor, "blank_after", "1")
    actor._last_change -= 2
    actor._step()
    assert actor._blanked and display.controls[-1] == ("power", False)
    actor.text(0, 0, "wake")
    assert not actor._blanked and ("power", True) in display.controls

def test_callbacks_from_other_threads_reach_the_event_loop(actor_display):
    actor, _ = actor_display
    poster = {}

    def post():
        poster["thread"] = threading.get_ident()
        actor._connection_handler(None, "TRANSPORT")

    thread = threading.Thread(target=post)
    thread.start()
    thread.join()
    run_loop(0.2)
    assert actor.share["connection"] == "TRANSPORT"
    assert actor.last_event_thread == threading.get_ident() != poster["thread"]

def test_heartbeat_and_metrics_flush(actor_display):
    actor, display = actor_display
    actor.text(0, 0, "a")
    actor.pixel(999, 0)
    actor._flush_metrics()
    assert actor.share["metrics"]["commands"] == "1"
    assert actor.share["metrics"]["rejected"] == "1"
    assert actor.share["metrics"]["frames"] == "2"
    published = []
    actor.ec_producer.add_handler(lambda *args: published.append(args))
    published.clear()
    actor._flush_metrics()                                 # nothing changed
    assert all(item[1] == "fps" for item in published)   # (fps is time based)
    run_loop(1.2)
    assert int(actor.share["heartbeat"]) >= 1

def test_shutdown_blanks_and_is_idempotent(actor_display):
    actor, display = actor_display
    actor._shutdown()
    assert display.closed and display.blanked
    actor._shutdown()

# --------------------------------------------------------------------------- #
# Share tokens: every value must survive the unencoded "(update K V)" publish

def test_share_values_are_single_tokens(actor_display, test_applets):
    actor, _ = actor_display
    remote_update(actor, "title", "12:30 lunch")           # would break the parser
    actor.pixel("x", 0)
    actor.applet("bouncer")
    remote_update(actor, "font", "16")
    actor._flush_metrics()
    values = {key: value for key, value in actor.share.items()
              if key not in ("source_file", "metrics", "keys")}
    for group in ("metrics", "keys"):                     # the two-level keys
        values.update({f"{group}.{key}": value
                       for key, value in actor.share[group].items()})
    for key, value in values.items():
        assert parse(f"(update {key} {value})") == ("update", [key, str(value)]), key

def test_parse_applet_args():
    words, options = parse_applet_args(["hello", "seed=3"], {"seed": int})
    assert words == ["hello"] and options == {"seed": 3}
    for bad in (["seed=x"], ["colour=1"], [["nested"]], ["x" * 65]):
        with pytest.raises(ValueError):
            parse_applet_args(bad, {"seed": int})

# --------------------------------------------------------------------------- #
# The Actor: the output's events, the canvas size and applet portability

def test_output_events_drive_the_display(monkeypatch):
    actor, output = make_actor()
    try:
        output.events = [("tap", "g")]                    # the window's g key
        actor._step()
        assert actor.share["applet"] == "pong"
        stopped = []
        monkeypatch.setattr(aiko.process, "terminate", lambda: stopped.append(True))
        output.events = ["quit"]
        actor._step()
        assert stopped
    finally:
        actor._shutdown()

def test_applet_too_small_is_rejected_and_hidden():
    actor, output = make_actor(size=(128, 32))
    try:
        assert actor.share["size"] == "128x32"
        listed = set(actor.share["applets"].split(","))
        assert {"status", "clock", "text"} <= listed and "pong" not in listed
        actor.applet("pong")
        assert actor.share["applet"] == "none"
        assert actor.share["last_error"].startswith("set_applet_too_small@")
        actor.text(0, 0, "fits")
        assert output.frames[-1].size == (128, 32)
    finally:
        actor._shutdown()

def test_a_fixed_field_is_centered_on_a_wide_canvas():
    actor, output = make_actor(size=(256, 64))
    try:
        assert "pong" in actor.share["applets"].split(",")
        actor.applet("pong", "seed=1")
        actor._step()
        frame = output.frames[-1]
        assert frame.size == (256, 64)
        left, _, right, _ = frame.getbbox()
        assert 64 <= left and right <= 192               # the 128-wide field, centered
    finally:
        actor._shutdown()
