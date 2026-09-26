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
        assert actor.share["applications"] == "help,status"
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
