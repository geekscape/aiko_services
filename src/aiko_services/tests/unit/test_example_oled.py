# Unit tests for the simple OLED example (examples/oled/oled_actor.py): the
# Actor draws clear, log and text on a recording panel, with the origin at
# the bottom-left as in the display:0 protocol.  The wheel excludes
# examples/, so the test skips there.
#
# Usage: pytest src/aiko_services/tests/unit/test_example_oled.py

import pytest

import aiko_services as aiko

example = pytest.importorskip("aiko_services.examples.oled.oled_actor")

class RecordingPanel(example.Panel):
    def __init__(self):
        self.opened = self.closed = False
        self.shown = []

    def open(self):
        self.opened = True

    def show(self, image):
        self.shown.append(image.copy())

    def close(self):
        self.closed = True

def lit_rows(image):
    return sorted({y for y in range(image.height) for x in range(image.width)
                   if image.getpixel((x, y))})

@pytest.fixture
def actor():
    panel = RecordingPanel()
    actor = aiko.compose_instance(example.OLEDActor, aiko.actor_args(
        "oled_example_test", parameters={"panel": panel},
        protocol=example.PROTOCOL, tags=["ec=true", "device=test", "canvas=0"]))
    return actor, panel

def test_protocol_matches_the_display_actor():
    display = pytest.importorskip("aiko_services.actors.display")
    assert example.PROTOCOL == display.PROTOCOL

def test_text_log_and_clear(actor):
    actor, panel = actor
    assert panel.opened and len(panel.shown) == 1 and lit_rows(panel.shown[0]) == []
    actor.text("0", "0", "hello")                        # wire arguments are text
    rows = lit_rows(panel.shown[-1])
    assert rows and min(rows) >= example.HEIGHT - example.ROW   # the bottom row
    actor.text(0, example.HEIGHT - example.ROW, "top")
    assert min(lit_rows(panel.shown[-1])) < example.ROW         # the top row
    actor.clear()
    assert lit_rows(panel.shown[-1]) == []
    actor.log("one")
    first = lit_rows(panel.shown[-1])
    actor.log("two")
    second = lit_rows(panel.shown[-1])
    assert min(second) < min(first)                      # "one" scrolled up a row
    assert max(second) >= example.HEIGHT - example.ROW   # "two" on the bottom row

def test_open_panel_falls_back_to_the_terminal(monkeypatch):
    monkeypatch.setattr(example.os.path, "exists", lambda path: False)
    assert isinstance(example.open_panel(0x3C), example.TerminalPanel)
    assert isinstance(example.open_panel(None), example.TerminalPanel)
    monkeypatch.setattr(example.os.path, "exists", lambda path: True)
    assert isinstance(example.open_panel(0x3C), example.Ssd1306Panel)

def test_terminal_panel_draws_half_blocks(capsys):
    image = example.Image.new("1", (example.WIDTH, example.HEIGHT))
    image.putpixel((0, 0), 1)
    example.TerminalPanel().show(image)
    lines = capsys.readouterr().out.split("\n")
    assert lines[0].endswith("▀" + " " * (example.WIDTH - 1))
