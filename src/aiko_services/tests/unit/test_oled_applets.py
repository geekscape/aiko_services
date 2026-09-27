# Unit tests for the OLED applets: the status display (the main
# goal), help, and the proof that a 30 fps applet with a slow display
# never blocks the Actor's event loop.  No MQTT broker, no hardware:
# psutil is replaced by constants.
#
# Usage: pytest src/aiko_services/tests/unit/test_oled_applets.py

import itertools
import threading
import time
from types import SimpleNamespace

import pytest

import aiko_services as aiko

from aiko_services.examples.oled import OLEDImpl, PROTOCOL
from aiko_services.examples.oled import applets
from aiko_services.examples.oled.applets import (
    APPLETS, Applet, HelpApplet, Host,
    per_second,
)
from aiko_services.examples.oled.display import FakeDisplay
from aiko_services.examples.oled.graphics import HEIGHT, WIDTH, Font
from aiko_services.examples.oled import status as status_module
from aiko_services.examples.oled.status import (
    HISTORY, StatusApplet, parse_nmcli, parse_wireless,
)

_counter = itertools.count()

class FakePsutil:
    """Constant readings"""

    def cpu_percent(self, interval=None):
        return 12.0

    def net_io_counters(self, pernic=False):
        return {"lo0": SimpleNamespace(bytes_recv=1, bytes_sent=1),
                "eth0": SimpleNamespace(bytes_recv=1000, bytes_sent=2000),
                "wlan0": SimpleNamespace(bytes_recv=500, bytes_sent=300)}

    def cpu_freq(self):
        return SimpleNamespace(current=1500.0)

    def sensors_temperatures(self):
        return {"cpu_thermal": [SimpleNamespace(current=45.1)]}

    def boot_time(self):
        return time.time() - 3 * 86400 - 4 * 3600 - 1800

    def virtual_memory(self):
        return SimpleNamespace(percent=34.0)

    def disk_usage(self, path):
        return SimpleNamespace(percent=61.0)

class StubHost(Host):
    def __init__(self, title_rows=8, lines=None):
        super().__init__(Font("5x7"))
        self._title_rows = title_rows
        self._lines = lines or []
        self.seen = 0

    def title_rows(self):
        return self._title_rows

    def connection(self):
        return "REGISTRAR"

    def log_lines(self):
        return list(self._lines)

    def log_seen(self):
        self.seen += 1

def lit_rows(image):
    return sorted({y for y in range(image.height)
        for x in range(image.width) if image.getpixel((x, y))})

WIRELESS = """Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE
 face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
 wlan0: 0000   70.  -37.  -256        0      0      0      0      4        0
"""
NMCLI = ("yes:wlan0:geekscape_n:A6\\:91\\:B1\\:75\\:16\\:82:132:5660 MHz:540 Mbit/s:84:80 MHz\n"
         "yes:wlan1:hotspot:DC\\:A6\\:32\\:0B\\:AB\\:23:1:2412 MHz:0 Mbit/s:0:0 MHz\n"
         "no:wlan0:other:00\\:11\\:22\\:33\\:44\\:55:6:2437 MHz:65 Mbit/s:40:20 MHz\n")

def make_status(monkeypatch, options=None, wifi=True, **kwargs):
    monkeypatch.setattr(status_module, "ip_address", lambda: "192.168.0.137")
    monkeypatch.setattr(status_module.os, "getloadavg", lambda: (0.42, 0.31, 0.25))
    monkeypatch.setattr(status_module, "fan_state", lambda: "1")
    monkeypatch.setattr(status_module, "wifi_signal",
                        lambda: ("wlan0", 70, -37) if wifi else None)
    monkeypatch.setattr(status_module, "wifi_details",
                        lambda interface: parse_nmcli(NMCLI, interface))
    for values in HISTORY.values():
        values.clear()
    host = StubHost(**kwargs)
    status = StatusApplet(host, options=options)
    status.psutil = FakePsutil()
    status._before = (time.monotonic(), status._network_bytes())  # the fake's baseline
    return status, host

# --------------------------------------------------------------------------- #

def test_status_lines_with_a_title_row(monkeypatch):
    status, host = make_status(monkeypatch, lines=["boot ok", "hello"])
    assert status.description == "host_text"
    lines = status.host_lines(status.sample())
    assert lines[0] == "IP 192.168.0.137"
    assert lines[1] == "CPU 12% Mem 34%"                   # fixed widths
    assert lines[2] == "Dsk 61% R   0  T   0 "
    assert lines[3] == "Load 0.42 0.31 0.25"               # 1, 5 and 15 minutes
    assert lines[4] == "Temp 45C F 1 1500MHz"              # the fan on GPIO14
    assert lines[5] == "hello"                             # the newest line only
    assert lines[6] == "Up 3d04h"                          # uptime last
    assert all(len(line) <= 21 for line in lines)
    status.options["date"] = True
    lines = status.host_lines(status.sample())
    assert lines[1].endswith(str(time.localtime().tm_year))  # the date row
    assert "hello" not in lines and lines[-1] == "Up 3d04h"  # the log line went first
    frame = status.step()
    assert frame.size == (WIDTH, HEIGHT)
    assert min(lit_rows(frame)) == 8                     # below the title row
    assert host.seen == 1                                # "L" annunciator cleared

def test_status_lines_without_a_title_row(monkeypatch):
    status, host = make_status(monkeypatch, title_rows=0)
    lines = status.host_lines(status.sample())
    assert lines[0] == "oled REGISTRAR"
    assert lines[1] == "IP 192.168.0.137"
    assert lines[-1].endswith(" up 3d04h") and lines[-1][2] == ":"   # hh:mm:ss up ...
    assert min(lit_rows(status.step())) == 0

def test_status_falls_back_without_sensor_fan_and_rate_option(monkeypatch):
    status, host = make_status(monkeypatch)
    status.psutil.sensors_temperatures = lambda: {}
    assert not any(line.startswith("Temp") for line in status.host_lines(status.sample()))
    status.psutil.sensors_temperatures = FakePsutil().sensors_temperatures
    monkeypatch.setattr(status_module, "fan_state", lambda: "-")
    status._fan = (0.0, "-")
    assert "Temp 45C F - 1500MHz" in status.host_lines(status.sample())
    assert StatusApplet(host, options={"rate": 4}).fps == 4
    assert StatusApplet(host, options={"rate": 99}).fps == 10

def test_status_wifi_screen(monkeypatch):
    status, host = make_status(monkeypatch, options={"screen": "wifi"})
    assert status.description == "wifi_text"
    lines = status.wifi_lines(status.sample())
    assert lines == ["SSID geekscape_n", "Ch 132 5GHz BW 80MHz", "RSSI -37dBm Q 70/70",
                     "Rate 540Mb/s Sig 84%", "AP a6:91:b1:75:16:82", "R   0  T   0 ",
                     "IF wlan0"]
    assert all(len(line) <= 21 for line in lines)
    assert min(lit_rows(status.step())) == 8
    none, _ = make_status(monkeypatch, options={"screen": "wifi"}, wifi=False)
    assert none.wifi_lines(none.sample())[0] == "Wi-Fi: none"

def test_status_charts(monkeypatch):
    status, host = make_status(monkeypatch, options={"view": "cpu_mem"})
    assert status.description == "host_cpu_mem"
    for _ in range(5):
        frame = status.step()
    assert len(HISTORY["cpu"]) == 5 and HISTORY["cpu"][-1] == 12.0
    rows = lit_rows(frame)
    assert 8 in rows and 63 in rows                      # the heading and the baseline
    assert sum(frame.getpixel((x, 63)) > 0 for x in range(WIDTH)) == WIDTH
    plotted = [y for y in rows if 16 <= y < 63]
    assert plotted                                       # traces in the plot area
    for view, screen in (("rx_tx", "host"), ("rssi", "wifi"), ("rx_tx", "wifi")):
        chart, _ = make_status(monkeypatch, options={"screen": screen, "view": view})
        assert chart.description == f"{screen}_{view}"
        assert chart.step().size == (WIDTH, HEIGHT)
    with pytest.raises(ValueError):
        StatusApplet(host, options={"screen": "wifi", "view": "cpu_mem"})
    with pytest.raises(ValueError):
        parse_applet_args(["screen=moon"], StatusApplet.OPTIONS)
    for _ in range(130):
        HISTORY["cpu"].append(1.0)
    assert len(HISTORY["cpu"]) == 128                    # bounded

def test_status_parsers():
    assert parse_wireless(WIRELESS) == ("wlan0", 70, -37)
    assert parse_wireless("") is None
    details = parse_nmcli(NMCLI, "wlan0")
    assert details["ssid"] == "geekscape_n" and details["bssid"] == "a6:91:b1:75:16:82"
    assert details["channel"] == "132" and details["mhz"] == 5660 and details["band"] == "5GHz"
    assert details["rate"] == "540Mb/s" and details["bandwidth"] == "80MHz"
    assert parse_nmcli(NMCLI, "wlan1")["band"] == "2.4GHz"
    assert parse_nmcli(NMCLI, "wlan9") == {}

def test_per_second():
    assert [per_second(n) for n in (0, 950, 1200, 12000, 111000, 3.4e6, 2e12)]  \
        == ["  0 ", "950 ", "1.2k", " 12k", "111k", "3.4M", "  2T"]
    assert all(len(per_second(n)) == 4 for n in (0, 999, 1000, 99999, 1e9))

def test_log_applet_shows_the_lines_and_clears_the_annunciator():
    from aiko_services.examples.oled.applets import LogApplet
    host = StubHost(lines=[f"line {n}" for n in range(9)])
    log = LogApplet(host)
    frame = log.step()
    assert host.seen == 1 and len(lit_rows(frame)) > 40
    assert min(lit_rows(frame)) == 8                     # below the title row
    assert log.step() is None                            # nothing new
    host._lines.append("newest")
    assert log.step() is not None and host.seen == 2

def test_help_applet_writes_lines():
    host = StubHost()
    help_applet = HelpApplet(host)
    frame = help_applet.step()
    assert lit_rows(frame)[0] >= 8 and len(lit_rows(frame)) > 20
    assert set(APPLETS) >= {"status", "help"}

def test_write_lines_drops_what_does_not_fit():
    host = StubHost(title_rows=0)
    frame = Applet(host).write_lines(["x"] * 20)
    assert max(lit_rows(frame)) <= HEIGHT - 1
    assert len(lit_rows(frame)) <= 8 * 7

# --------------------------------------------------------------------------- #
# The Actor with the status applet, and the no-blocking proof

def make_actor(**parameters):
    display = parameters.pop("display", None) or FakeDisplay()
    parameters = {"display": display, **parameters}
    name = f"oled_status_{next(_counter)}"
    actor = aiko.compose_instance(OLEDImpl,
        aiko.actor_args(name, parameters=parameters, protocol=PROTOCOL))
    return actor, display

def run_loop(seconds):
    def stop():
        aiko.event.remove_timer_handler(stop)
        aiko.process.terminate()

    aiko.event.add_timer_handler(stop, seconds)
    aiko.process.run(mqtt_connection_required=False)

def test_status_is_the_default_applet(monkeypatch):
    monkeypatch.setattr(applets, "ip_address", lambda: "10.0.0.2")
    actor, display = make_actor()
    try:
        assert actor.share["applet"] == "status"
        assert set(actor.share["applets"].split(",")) == set(APPLETS)
        assert actor.share["title"] == actor.name
        actor.log("boot", "ok")                           # log keeps status running
        assert actor.share["applet"] == "status"
        run_loop(0.3)
        assert len(display.frames) >= 2 and actor._applet is not None
        frame = display.frames[-1]
        assert max(lit_rows(frame)) > 40                  # status rows under the title
        remote = actor._ec_producer_change_handler
        actor.share["applet"] = "help"
        remote("update", "applet", "help")
        assert actor.share["applet"] == "help"
    finally:
        actor._shutdown()

class Bouncer(Applet):
    name = "bouncer"
    fps = 30

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.count = 0

    def step(self):
        self.count += 1
        frame = self.frame()
        frame.putpixel((self.count % WIDTH, 20), 255)
        return frame

def test_slow_display_does_not_block_the_event_loop(monkeypatch):
    """A 30 fps applet on a display that takes 25 ms per frame (an
    I2C SSD1306 at 400 kHz): the heartbeat keeps ticking and a command
    posted from another thread is applied within 100 ms"""

    monkeypatch.setitem(applets.APPLETS, "bouncer", Bouncer)
    display = FakeDisplay(show_delay=0.025)
    actor, _ = make_actor(display=display, applet="bouncer", title="off")
    results = {}

    def poster():
        time.sleep(0.6)
        results["posted"] = time.monotonic()
        actor._post_message(aiko.ActorTopic.IN, "text", ["0", "0", "posted"])

    original_text = actor.text

    def timed_text(*args):
        results["applied"] = time.monotonic()
        original_text(*args)

    monkeypatch.setattr(actor, "text", timed_text)
    threading.Thread(target=poster).start()
    try:
        run_loop(1.5)
        assert int(actor.share["heartbeat"]) >= 1
        assert actor._metrics["frames"] >= 15
        assert actor._metrics["errors"] == 0
        assert results["applied"] - results["posted"] < 0.1
        assert actor.share["applet"] == "none"       # text stopped it
    finally:
        actor._shutdown()

# --------------------------------------------------------------------------- #
# Phase 2: pattern, text, blink, demo, games, forklift, drawings

from aiko_services.examples.oled.applets import (  # noqa: E402
    TOUR, BlinkApplet, DemoApplet, PatternApplet, TextApplet,
    parse_applet_args, random_steps,
)
from aiko_services.examples.oled.drawings import (  # noqa: E402
    DrawApplet, erase_frames, scene, scene_strokes, sketch_frames,
)
from aiko_services.examples.oled.games import (  # noqa: E402
    FORKS_CARRY, GROUND, ForkliftApplet, ForkliftGameApplet,
    GamesApplet,
)
from aiko_services.examples.oled.applets import AppletDone  # noqa: E402
import random  # noqa: E402

class RecordingHost(StubHost):
    """A host that records settings changes and answers setting()"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings = {"invert": "off", "contrast": "255", "font": "5x7", "power": "on"}
        self.controls = []
        self.statuses = []
        self.held = set()

    def setting(self, name):
        return self.settings.get(name)

    def control(self, name, value):
        self.controls.append((name, value))
        self.settings[name] = value

    def status(self, token):
        self.statuses.append(token)

    def keys_held(self):
        return self.held

def frames_of(applet, count):
    return [applet.step() for _ in range(count)]

def test_registry_has_every_applet():
    assert set(APPLETS) == {"status", "log", "help", "pattern", "text", "blink", "demo",
        "clock", "eyes", "pong", "asteroids", "invaders", "games", "forklift",
        "forklift_game", "draw"}

@pytest.mark.parametrize("name", ["pong", "asteroids", "invaders", "forklift", "forklift_game"])
def test_games_are_deterministic_with_a_seed(name):
    host = RecordingHost()
    first = [frame.tobytes() for frame in frames_of(APPLETS[name](host, [], {"seed": 1}), 100)]
    again = [frame.tobytes() for frame in frames_of(APPLETS[name](host, [], {"seed": 1}), 100)]
    other = [frame.tobytes() for frame in frames_of(APPLETS[name](host, [], {"seed": 2}), 100)]
    assert first == again and first != other
    assert all(len(frame) == WIDTH * HEIGHT // 8 for frame in first)

def test_games_take_turns():
    host = RecordingHost()
    games = GamesApplet(host, [], {"seed": 1, "duration": 1})
    assert games.description == "pong"
    frames_of(games, 31)
    assert games.description == "asteroids"
    frames_of(games, 30)
    assert games.description == "invaders"

def test_forklift_duration_ends_the_applet():
    host = RecordingHost()
    forklift = ForkliftApplet(host, [], {"seed": 1, "duration": 0.1})
    frames_of(forklift, 3)
    with pytest.raises(AppletDone):
        forklift.step()
    assert host.statuses[0].startswith(("ground_to_bay_", "bay_"))

def test_forklift_game_keys_move_the_forklift():
    host = RecordingHost()
    game = ForkliftGameApplet(host, [], {"seed": 1}).game
    x, forks = game.x, game.forks
    host.held = {"right"}
    for _ in range(5):
        game.step(host.keys_held())
    assert round(game.x - x, 1) == 7.0 and game.forks == forks
    host.held = {"up"}
    for _ in range(5):
        game.step(host.keys_held())
    assert game.forks == forks - 5
    assert host.statuses[0].startswith("to_")

def test_forklift_game_places_a_pallet_on_bay_1():
    host = RecordingHost()
    game = ForkliftGameApplet(host, [], {"seed": 1}).game
    game.pallet, game.x, game.forks, game.target = [50.0, GROUND - 1], 0.0, FORKS_CARRY, "bay 1"
    for keys, count in (({"down"}, 10), ({"right"}, 30), ({"up"}, 20), ({"right"}, 60),
                        ({"down"}, 30), ({"left"}, 20)):
        for _ in range(count):
            game.step(keys)
    assert game.placed == 1 and game.broken == 0
    assert any(status.startswith("placed_1") for status in host.statuses)
    assert game.frame().size == (WIDTH, HEIGHT)

def test_sketch_frames_count_and_the_finished_drawing():
    rng = random.Random(1)
    names, shapes = scene(rng, ["house"], "outline")
    strokes = scene_strokes(shapes, "outline", rng)
    frames = list(sketch_frames(strokes, 40))
    assert 36 <= len(frames) <= 44
    finished = frames[-1]
    assert lit_rows(finished) and len(lit_rows(finished)) > 30
    erased = list(erase_frames(finished))
    assert lit_rows(erased[-1]) == []

def test_draw_applet_sequence_and_options():
    host = RecordingHost()
    draw = DrawApplet(host, [], {"seed": 3, "count": 1, "speed": 1, "hold": 0.5})
    frames = []
    with pytest.raises(AppletDone):
        while True:
            frames.append(draw.step())
    images = [frame for frame in frames if frame is not None]
    assert 18 <= len(images) <= 24 and frames.count(None) == 10
    assert host.statuses and host.statuses[0].endswith(("_outline", "_hatch", "_stipple"))
    for bad in (["subject=nosuch"], ["style=bold"], ["shade=maybe"]):
        with pytest.raises(ValueError):
            parse_applet_args(bad, DrawApplet.OPTIONS)

def test_pattern_and_text_redraw_only_when_the_font_changes():
    host = RecordingHost()
    pattern = PatternApplet(host)
    assert pattern.step() is not None and pattern.step() is None
    host.font = Font(10)
    assert pattern.step() is not None
    text = TextApplet(host, ["Hi"])
    frame = text.step()
    assert text.description == "message" and 0 < len(lit_rows(frame)) < 20
    digits = TextApplet(host)
    assert digits.description == "digits" and len(lit_rows(digits.step())) > 40

def test_blink_toggles_the_power_and_restores_it():
    host = RecordingHost()
    blink = BlinkApplet(host, [], {"rate": 4})
    assert blink.fps == 4
    assert blink.step() is not None and host.controls[-1] == ("power", "off")
    assert blink.step() is None and host.controls[-1] == ("power", "on")
    blink.stop()
    assert host.controls[-1] == ("power", "on")

def test_demo_tour_runs_steps_and_restores_settings():
    host = RecordingHost()
    _, options = parse_applet_args(["random=off", "count=3"], DemoApplet.OPTIONS)
    assert options == {"random": False, "count": 3}
    demo = DemoApplet(host, [], options)
    seen, subs = [], []
    with pytest.raises(AppletDone):
        for _ in range(400):
            demo.step()
            if not subs or subs[-1] is not demo._sub:
                subs.append(demo._sub)
                seen.append(demo.description)
    assert seen == ["demo_blink", "demo_pattern", "demo_pattern"]
    assert type(subs[0]).name == "blink" and type(subs[2]).name == "pattern"
    assert ("invert", "on") in host.controls               # the third step's setting
    assert host.controls[-1] == ("invert", "off")          # put back at the end
    assert host.settings["power"] == "on"                  # blink stopped cleanly

def test_random_steps_are_valid_applets():
    steps = list(__import__("itertools").islice(random_steps(random.Random(1)), 40))
    for seconds, name, args, settings in steps:
        assert seconds > 0 and name in APPLETS
        parse_applet_args(args, APPLETS[name].OPTIONS)
        assert set(settings) <= {"font", "invert", "contrast"}
    assert len({name for _, name, _, _ in steps}) >= 5
    assert all(name in APPLETS for _, name, _, _ in TOUR)

# --------------------------------------------------------------------------- #
# Help pages, the clock face, the eyes

from datetime import datetime  # noqa: E402
from aiko_services.examples.oled.faces import EMOTIONS, ClockApplet, EyesApplet  # noqa: E402

def test_help_pages_fit_the_display_and_turn():
    assert len(HelpApplet.PAGES) == 6
    for heading, lines in HelpApplet.PAGES:
        assert len(heading) <= 16 and 1 <= len(lines) <= 6
        assert all(len(line) <= 21 for line in lines), heading
    host = RecordingHost()
    fixed = HelpApplet(host, [], {"page": 3})
    assert fixed.description == "help_3_of_6"
    assert fixed.step() is not None and fixed.step() is None
    fixed.key("right", "tap")
    assert fixed.description == "help_4_of_6" and fixed.step() is not None
    fixed.key("left", "tap")
    assert fixed.description == "help_3_of_6"
    auto = HelpApplet(host, [], {"hold": 1})
    assert auto.description == "help_1_of_6"
    frames = [auto.step() for _ in range(3)]
    assert auto.description == "help_2_of_6"
    assert frames[1] is not None and frames[2] is None      # turned on step 2
    assert min(lit_rows(frames[0])) == 8                  # below the title row

def test_clock_face():
    host = RecordingHost()
    clock = ClockApplet(host)
    assert not clock.wants_title
    face = clock.face(datetime(2026, 9, 26, 10, 10, 30))
    rows = lit_rows(face)
    assert face.size == (WIDTH, HEIGHT) and rows[0] <= 1 and rows[-1] >= 62
    assert face.tobytes() != clock.face(datetime(2026, 9, 26, 10, 10, 31)).tobytes()
    still = ClockApplet(host, [], {"seconds": False})
    assert still.face(datetime(2026, 9, 26, 10, 10, 30)).tobytes()  \
        == still.face(datetime(2026, 9, 26, 10, 10, 31)).tobytes()
    titled = ClockApplet(host, [], {"title": True})
    assert titled.wants_title and min(lit_rows(titled.face(datetime(2026, 1, 1)))) >= 8
    assert clock.step() is not None and clock.step() is None   # once a second

def lit_bands(image):
    """The runs of consecutive lit rows: (first, last) of each"""

    bands, rows = [], lit_rows(image)
    for row in rows:
        if bands and row == bands[-1][1] + 1:
            bands[-1][1] = row
        else:
            bands.append([row, row])
    return bands

def test_clock_digital_face():
    host = RecordingHost()
    digital = ClockApplet(host, [], {"face": "digital"})
    assert digital.wants_title and digital.description == "digital"
    face = digital.face(datetime(2026, 9, 27, 8, 5, 9))
    bands = lit_bands(face)
    assert len(bands) == 3 and bands[0][0] >= 8 + 2            # below the title, spaced
    assert all(b[0] - a[1] > 2 for a, b in zip(bands, bands[1:]))   # whitespace between
    assert bands[-1][1] <= HEIGHT - 1 - 2
    size = digital._digital_font[1].size
    assert 12 <= size <= 20                                    # the largest that fits
    assert face.tobytes() != digital.face(datetime(2026, 9, 27, 8, 5, 10)).tobytes()
    full = ClockApplet(host, [], {"face": "digital", "title": False})
    assert not full.wants_title
    assert full._fit_font(["Wednesday", "2026-09-27", "00:00:00"], WIDTH, HEIGHT).size > size
    minutes = ClockApplet(host, [], {"face": "digital", "seconds": False})
    assert minutes.face(datetime(2026, 9, 27, 8, 5, 9)).tobytes()  \
        == minutes.face(datetime(2026, 9, 27, 8, 5, 10)).tobytes()
    with pytest.raises(ValueError):
        parse_applet_args(["face=round"], ClockApplet.OPTIONS)

def test_eyes_are_deterministic_and_emotional():
    host = RecordingHost()
    first = [frame.tobytes() for frame in frames_of(EyesApplet(host, [], {"seed": 1}), 100)]
    again = [frame.tobytes() for frame in frames_of(EyesApplet(host, [], {"seed": 1}), 100)]
    assert first == again
    host = RecordingHost()
    eyes = EyesApplet(host, [], {"seed": 4})
    frames = frames_of(eyes, 400)
    assert len(set(host.statuses)) >= 3 and set(host.statuses) <= set(EMOTIONS)
    lit = [lit_count(frame) for frame in frames]
    assert min(lit) < 0.6 * max(lit)                       # a blink or a squint
    fixed_host = RecordingHost()
    angry = EyesApplet(fixed_host, [], {"seed": 4, "emotion": "angry", "blink": False})
    frames_of(angry, 200)
    assert fixed_host.statuses == ["angry"] and angry.description == "angry"
    with pytest.raises(ValueError):
        parse_applet_args(["emotion=grumpy"], EyesApplet.OPTIONS)
    assert {"clock", "eyes", "help"} <= set(APPLETS)

def lit_count(image):
    return sum(1 for y in range(image.height) for x in range(image.width) if image.getpixel((x, y)))
