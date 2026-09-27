#!/usr/bin/env python3
#
# Aiko Services: OLED example, the Dashboard plug-in page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The pure parts: the renderer, the page model, the mirror widget with a
# recording canvas.  asciimatics has no screen double, so the frame itself
# is exercised by the test guide.

import time
from types import SimpleNamespace

import pytest

asciimatics = pytest.importorskip("asciimatics")
from asciimatics.screen import Screen  # noqa: E402

from aiko_services.examples.oled import dashboard_plugin as plugin  # noqa: E402
from aiko_services.examples.oled.dashboard_plugin import (  # noqa: E402
    DisplayPage, MirrorWidget, render_mirror,
)
from aiko_services.examples.oled.graphics import FrameBuffer, Font  # noqa: E402

def frame_bytes(text="hello"):
    frame = FrameBuffer(Font("5x7"))
    frame.text(0, 0, text)
    return frame.image.tobytes()

def test_render_mirror_tiers_and_emulation():
    data = frame_bytes()
    blocks = render_mirror(data, (128, 64), {}, True, 256)
    assert len(blocks) == 32 and all(len(row[0]) == 128 for row in blocks)
    assert any("▀" in row[0] or "▄" in row[0] or "█" in row[0] for row in blocks)
    braille = render_mirror(data, (128, 64), {}, False, 256)
    assert len(braille) == 16 and all(len(row[0]) == 64 for row in braille)
    assert braille[-1][0] != "⠀" * 64                # the text is on the bottom rows
    off = render_mirror(data, (128, 64), {"power": "off"}, True, 256)
    assert all(row[0] == " " * 128 for row in off)         # dark glass
    inverted = render_mirror(data, (128, 64), {"invert": "on"}, True, 256)
    assert inverted[0][0] == "█" * 128                     # the blank top row is lit
    colored = render_mirror(data, (128, 64), {"foreground": "yellow", "background": "navy"}, True, 256)
    assert colored[0][1] != blocks[0][1] and colored[0][3] != blocks[0][3]
    dim = render_mirror(data, (128, 64), {"contrast": "16"}, True, 8)
    assert dim[0][1] == Screen.COLOUR_WHITE and dim[0][2] == Screen.A_NORMAL
    bright = render_mirror(data, (128, 64), {"contrast": "255"}, True, 8)
    assert bright[0][2] == Screen.A_BOLD
    render_mirror(data, (128, 64), {"contrast": "abc", "foreground": "no_color"}, True, 256)

def test_page_actions_and_aliases():
    page = DisplayPage(blocks=True)
    now = 100.0
    assert page.action(ord("g"), now) == ("key", "g")
    assert page.action(ord("m"), now) == ("key", "D")     # the Dashboard reserves D
    assert page.action(ord("5"), now) == ("key", "5")
    assert page.action(ord("+"), now) == ("key", "+")
    for reserved in "D?xX":
        assert page.action(ord(reserved), now) is None
    assert page.action(ord("K"), now) == ("stop",)
    assert page.action(ord("H"), now) == ("help",)
    assert page.action(ord("L"), now) == ("log_level",)
    assert page.action(ord("q"), now) == ("back",)
    assert page.action(Screen.KEY_ESCAPE, now) == ("back",)
    assert page.action(Screen.KEY_BACK, now) == ("back",)
    assert page.action(10, now) == ("edit",)
    assert page.action(Screen.KEY_TAB, now) is None
    assert page.action(Screen.KEY_LEFT, now) == ("key", "left")
    assert page.action(Screen.KEY_LEFT, now + 0.05) == ("consumed",)   # a repeat, coalesced
    assert page.action(Screen.KEY_LEFT, now + 0.2) == ("key", "left")

def test_page_observes_state_and_feed():
    page = DisplayPage(blocks=False)
    now = 50.0
    page.observe({"size": "256x64", "last_error": "-"}, now)
    assert page.size == (256, 64) and not page.error_is_fresh(now)
    page.observe({"last_error": "set_contrast_not_int@x"}, now + 1)
    assert page.error_is_fresh(now + 2) and not page.error_is_fresh(now + 7)
    plugin._latest["frame"], plugin._latest["at"] = None, 0.0
    assert page.feed_status({}, now, False) == "MQTT down"
    assert page.feed_status({}, now, True).startswith("mirror: not supported")
    assert page.feed_status({"mirrors": "1"}, now, True) == "mirror: waiting for frames"
    plugin._mirror_handler(None, "t", frame_bytes())
    page.observe({"size": "128x64"}, time.monotonic())
    assert page.rows({}, 256) is not None and len(page.rows({}, 256)) == 16
    assert page.feed_status({"mirrors": "1", "mirror_rate": "5", "fps": "30"},
                            time.monotonic(), True) == "mirror 5 Hz  fps 30"
    assert page.feed_status({"mirrors": "1"}, time.monotonic() + 10, True).startswith("mirror: no frames")
    page.observe({"size": "256x64"}, time.monotonic())
    assert page.rows({}, 256) is None                     # the frame does not fit the size
    plugin._latest["frame"], plugin._latest["at"] = None, 0.0

def test_mirror_widget_prints_the_rows():
    printed = []
    canvas = SimpleNamespace(unicode_aware=True, colours=256,
                             print_at=lambda text, x, y, *rest: printed.append((text, x, y, rest)))
    frame = SimpleNamespace(canvas=canvas)
    page = DisplayPage(blocks=True)
    widget = MirrorWidget(page, 32)
    widget._frame, widget._x, widget._y, widget._w, widget._h = frame, 0, 2, 128, 32
    plugin._mirror_handler(None, "t", frame_bytes())
    widget.update(0)
    assert len(printed) == 32 and printed[0][2] == 2 and len(printed[0][0]) == 128
    assert widget.required_height(0, 128) == 32 and widget.value is None
    printed.clear()
    canvas.unicode_aware = False
    widget.update(1)
    assert len(printed) == 1 and "Unicode" in printed[0][0]
    plugin._latest["frame"], plugin._latest["at"] = None, 0.0
    canvas.unicode_aware = True
    widget.message = "mirror: waiting for frames"
    widget.update(2)
    assert printed[-1][0] == "mirror: waiting for frames"

def test_plugins_dict_and_topic():
    assert list(plugin.plugins) == ["display"]
    assert plugin.mirror_topic().endswith("/display/mirror")
