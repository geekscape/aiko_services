# Unit tests for the OLED applications: the status display (the main
# goal), help, and the proof that a 30 fps application with a slow display
# never blocks the Actor's event loop.  No MQTT broker, no hardware:
# psutil is replaced by constants.
#
# Usage: pytest src/aiko_services/tests/unit/test_oled_applications.py

import itertools
import threading
import time
from types import SimpleNamespace

import pytest

import aiko_services as aiko

from aiko_services.examples.oled import OLEDImpl, PROTOCOL
from aiko_services.examples.oled import applications
from aiko_services.examples.oled.applications import (
    APPLICATIONS, Application, HelpApplication, Host, StatusApplication,
    per_second,
)
from aiko_services.examples.oled.display import FakeDisplay
from aiko_services.examples.oled.graphics import HEIGHT, WIDTH, Font

_counter = itertools.count()

class FakePsutil:
    """Constant readings"""

    def cpu_percent(self, interval=None):
        return 12.0

    def net_io_counters(self, pernic=False):
        return {"lo0": SimpleNamespace(bytes_recv=1, bytes_sent=1),
                "eth0": SimpleNamespace(bytes_recv=1000, bytes_sent=2000)}

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

def make_status(monkeypatch, **kwargs):
    monkeypatch.setattr(applications, "ip_address", lambda: "192.168.0.137")
    host = StubHost(**kwargs)
    status = StatusApplication(host)
    status.psutil = FakePsutil()
    return status, host

# --------------------------------------------------------------------------- #

def test_status_lines_with_a_title_row(monkeypatch):
    status, host = make_status(monkeypatch, lines=["boot ok", "hello"])
    lines = status.lines()
    assert lines[0] == "IP 192.168.0.137"
    assert lines[2].endswith(" up 3d04h")
    assert lines[3] == "CPU 12% Mem 34%"
    assert lines[4].startswith("Disk 61% Rx") and "Tx" in lines[4]
    assert lines[5] == "Temp 45.1C 1500MHz"
    assert lines[6:] == ["boot ok", "hello"]
    frame = status.step()
    assert frame.size == (WIDTH, HEIGHT)
    assert min(lit_rows(frame)) == 8                     # below the title row
    assert host.seen == 1                                # "L" annunciator cleared

def test_status_lines_without_a_title_row(monkeypatch):
    status, host = make_status(monkeypatch, title_rows=0)
    lines = status.lines()
    assert lines[0] == "oled REGISTRAR"
    assert lines[1] == "IP 192.168.0.137"
    assert min(lit_rows(status.step())) == 0

def test_status_falls_back_to_load_and_rate_option(monkeypatch):
    status, host = make_status(monkeypatch)
    status.psutil.sensors_temperatures = lambda: {}
    assert status.lines()[5].startswith("Load ")
    assert StatusApplication(host, options={"rate": 4}).fps == 4
    assert StatusApplication(host, options={"rate": 99}).fps == 10

def test_per_second():
    assert [per_second(n) for n in (0, 950, 1200, 12000, 3.4e6, 2e12)]  \
        == ["0", "950", "1.2k", "12k", "3.4M", "2T"]

def test_help_application_writes_lines():
    host = StubHost()
    help_application = HelpApplication(host)
    frame = help_application.step()
    assert lit_rows(frame)[0] >= 8 and len(lit_rows(frame)) > 20
    assert set(APPLICATIONS) >= {"status", "help"}

def test_write_lines_drops_what_does_not_fit():
    host = StubHost(title_rows=0)
    frame = Application(host).write_lines(["x"] * 20)
    assert max(lit_rows(frame)) <= HEIGHT - 1
    assert len(lit_rows(frame)) <= 8 * 7

# --------------------------------------------------------------------------- #
# The Actor with the status application, and the no-blocking proof

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

def test_status_is_the_default_application(monkeypatch):
    monkeypatch.setattr(applications, "ip_address", lambda: "10.0.0.2")
    actor, display = make_actor()
    try:
        assert actor.share["application"] == "status"
        assert set(actor.share["applications"].split(",")) == set(APPLICATIONS)
        assert actor.share["title"] == actor.name
        actor.log("boot", "ok")                           # log keeps status running
        assert actor.share["application"] == "status"
        run_loop(0.3)
        assert len(display.frames) >= 2 and actor._application is not None
        frame = display.frames[-1]
        assert max(lit_rows(frame)) > 40                  # status rows under the title
        remote = actor._ec_producer_change_handler
        actor.share["application"] = "help"
        remote("update", "application", "help")
        assert actor.share["application"] == "help"
    finally:
        actor._shutdown()

class Bouncer(Application):
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
    """A 30 fps application on a display that takes 25 ms per frame (an
    I2C SSD1306 at 400 kHz): the heartbeat keeps ticking and a command
    posted from another thread is applied within 100 ms"""

    monkeypatch.setitem(applications.APPLICATIONS, "bouncer", Bouncer)
    display = FakeDisplay(show_delay=0.025)
    actor, _ = make_actor(display=display, application="bouncer", title="off")
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
        assert actor.share["application"] == "none"       # text stopped it
    finally:
        actor._shutdown()

# --------------------------------------------------------------------------- #
# Phase 2: pattern, text, blink, demo, games, forklift, drawings

from aiko_services.examples.oled.applications import (  # noqa: E402
    TOUR, BlinkApplication, DemoApplication, PatternApplication, TextApplication,
    parse_application_args, random_steps,
)
from aiko_services.examples.oled.drawings import (  # noqa: E402
    DrawApplication, erase_frames, scene, scene_strokes, sketch_frames,
)
from aiko_services.examples.oled.games import (  # noqa: E402
    FORKS_CARRY, GROUND, ForkliftApplication, ForkliftGameApplication,
    GamesApplication,
)
from aiko_services.examples.oled.applications import ApplicationDone  # noqa: E402
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

def frames_of(application, count):
    return [application.step() for _ in range(count)]

def test_registry_has_every_application():
    assert set(APPLICATIONS) == {"status", "help", "pattern", "text", "blink", "demo",
        "pong", "asteroids", "invaders", "games", "forklift", "forklift_game", "draw"}

@pytest.mark.parametrize("name", ["pong", "asteroids", "invaders", "forklift", "forklift_game"])
def test_games_are_deterministic_with_a_seed(name):
    host = RecordingHost()
    first = [frame.tobytes() for frame in frames_of(APPLICATIONS[name](host, [], {"seed": 1}), 100)]
    again = [frame.tobytes() for frame in frames_of(APPLICATIONS[name](host, [], {"seed": 1}), 100)]
    other = [frame.tobytes() for frame in frames_of(APPLICATIONS[name](host, [], {"seed": 2}), 100)]
    assert first == again and first != other
    assert all(len(frame) == WIDTH * HEIGHT // 8 for frame in first)

def test_games_take_turns():
    host = RecordingHost()
    games = GamesApplication(host, [], {"seed": 1, "duration": 1})
    assert games.description == "pong"
    frames_of(games, 31)
    assert games.description == "asteroids"
    frames_of(games, 30)
    assert games.description == "invaders"

def test_forklift_duration_ends_the_application():
    host = RecordingHost()
    forklift = ForkliftApplication(host, [], {"seed": 1, "duration": 0.1})
    frames_of(forklift, 3)
    with pytest.raises(ApplicationDone):
        forklift.step()
    assert host.statuses[0].startswith(("ground_to_bay_", "bay_"))

def test_forklift_game_keys_move_the_forklift():
    host = RecordingHost()
    game = ForkliftGameApplication(host, [], {"seed": 1}).game
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
    game = ForkliftGameApplication(host, [], {"seed": 1}).game
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

def test_draw_application_sequence_and_options():
    host = RecordingHost()
    draw = DrawApplication(host, [], {"seed": 3, "count": 1, "speed": 1, "hold": 0.5})
    frames = []
    with pytest.raises(ApplicationDone):
        while True:
            frames.append(draw.step())
    images = [frame for frame in frames if frame is not None]
    assert 18 <= len(images) <= 24 and frames.count(None) == 10
    assert host.statuses and host.statuses[0].endswith(("_outline", "_hatch", "_stipple"))
    for bad in (["subject=nosuch"], ["style=bold"], ["shade=maybe"]):
        with pytest.raises(ValueError):
            parse_application_args(bad, DrawApplication.OPTIONS)

def test_pattern_and_text_redraw_only_when_the_font_changes():
    host = RecordingHost()
    pattern = PatternApplication(host)
    assert pattern.step() is not None and pattern.step() is None
    host.font = Font(10)
    assert pattern.step() is not None
    text = TextApplication(host, ["Hi"])
    frame = text.step()
    assert text.description == "message" and 0 < len(lit_rows(frame)) < 20
    digits = TextApplication(host)
    assert digits.description == "digits" and len(lit_rows(digits.step())) > 40

def test_blink_toggles_the_power_and_restores_it():
    host = RecordingHost()
    blink = BlinkApplication(host, [], {"rate": 4})
    assert blink.fps == 4
    assert blink.step() is not None and host.controls[-1] == ("power", "off")
    assert blink.step() is None and host.controls[-1] == ("power", "on")
    blink.stop()
    assert host.controls[-1] == ("power", "on")

def test_demo_tour_runs_steps_and_restores_settings():
    host = RecordingHost()
    _, options = parse_application_args(["random=off", "count=3"], DemoApplication.OPTIONS)
    assert options == {"random": False, "count": 3}
    demo = DemoApplication(host, [], options)
    seen, subs = [], []
    with pytest.raises(ApplicationDone):
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

def test_random_steps_are_valid_applications():
    steps = list(__import__("itertools").islice(random_steps(random.Random(1)), 40))
    for seconds, name, args, settings in steps:
        assert seconds > 0 and name in APPLICATIONS
        parse_application_args(args, APPLICATIONS[name].OPTIONS)
        assert set(settings) <= {"font", "invert", "contrast"}
    assert len({name for _, name, _, _ in steps}) >= 5
    assert all(name in APPLICATIONS for _, name, _, _ in TOUR)
