#!/usr/bin/env python3
#
# Aiko Services: the Display Actor's Dashboard plug-in page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The pure parts: the renderer, the page model, the mirror widget with a
# recording canvas.  asciimatics has no screen double, so the frame itself
# is exercised by the test guide.

import time
from types import SimpleNamespace

import pytest

asciimatics = pytest.importorskip("asciimatics")
from asciimatics.screen import Screen  # noqa: E402

from aiko_services.actors.display import dashboard_plugin as plugin  # noqa: E402
from aiko_services.actors.display.dashboard_plugin import (  # noqa: E402
    DisplayPage, MirrorWidget, render_mirror,
)
from aiko_services.actors.display.graphics import FrameBuffer, Font  # noqa: E402
from aiko_services.actors.display.outputs import (  # noqa: E402
    KEY_DOWN_RENEW, ascii_lines, text_lines,
)

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
    assert page.action(ord("g"), now) == ("key", "g", "tap")
    assert page.action(ord("m"), now) == ("key", "D", "tap")   # the Dashboard reserves D
    assert page.action(ord("5"), now) == ("key", "5", "tap")
    assert page.action(ord("+"), now) == ("key", "+", "tap")
    assert page.action(ord("M"), now) == ("mirror",)
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

def test_arrow_hold_renew_and_release():
    page = DisplayPage(blocks=True)
    now = 100.0
    assert page.action(Screen.KEY_LEFT, now) == ("key", "left", "down")
    assert page.released(now + 0.1) == []
    repeat = now
    while repeat < now + KEY_DOWN_RENEW - 0.05:              # auto-repeats: consumed
        repeat += 0.05
        assert page.action(Screen.KEY_LEFT, repeat) == ("consumed",)
    repeat += 0.05                                           # held a while: renewed
    assert page.action(Screen.KEY_LEFT, repeat) == ("key", "left", "down")
    assert page.released(repeat + plugin.ARROW_RELEASE - 0.01) == []
    assert page.released(repeat + plugin.ARROW_RELEASE) == ["left"]   # let go
    assert page.action(Screen.KEY_LEFT, repeat + 1) == ("key", "left", "down")
    assert page.action(Screen.KEY_UP, repeat + 1) == ("key", "up", "down")
    assert sorted(page.release_all()) == ["left", "up"] and page.arrows_held == {}

def test_latency_measure():
    page = DisplayPage(blocks=True)
    plugin._latest["frame"], plugin._latest["at"] = None, 0.0
    page.action(ord("g"), 10.0)
    page.measure(10.5)
    assert page.latency_ms is None and page.sent_at == 10.0   # no frame yet
    plugin._latest["at"] = 10.25
    page.measure(10.5)
    assert page.latency_ms == 250 and page.sent_at is None
    page.action(ord("g"), 20.0)
    page.measure(20.0 + plugin.LATENCY_WINDOW + 0.1)         # nothing visible changed
    assert page.sent_at is None and page.latency_ms == 250
    plugin._mirror_handler(None, "t", frame_bytes())
    assert page.feed_status({"mirrors": "1", "fps": "30"}, time.monotonic(), True)  \
        .endswith("key 250 ms")
    plugin._latest["frame"], plugin._latest["at"] = None, 0.0

def test_ascii_lines_both_tiers():
    image = FrameBuffer(Font("5x7")).image
    image.putpixel((0, 0), 1)                                # top of a pair
    image.putpixel((1, 1), 1)                                # bottom of a pair
    image.putpixel((2, 0), 1)
    image.putpixel((2, 1), 1)                                # both
    pairs = ascii_lines(image, True)
    assert len(pairs) == 32 and pairs[0][:4] == "'.: "
    for x in range(2):                                       # a full 2x4 cell
        for y in range(4):
            image.putpixel((4 + x, y), 1)
    for y in range(3):
        image.putpixel((8, y), 1)                            # 3 in a cell
    cells = ascii_lines(image, False)
    assert len(cells) == 16 and len(cells[0]) == 64
    assert cells[0][:5] == "..# :"                           # 2, 2, 8, 0 and 3 lit
    assert all(ord(c) < 128 for row in pairs + cells for c in row)
    assert [len(row) for row in text_lines(image, True)] == [len(row) for row in pairs]

def test_render_mirror_ascii_and_mode():
    data = frame_bytes()
    ascii_rows = render_mirror(data, (128, 64), {}, True, 256, unicode=False)
    assert len(ascii_rows) == 32 and all(ord(c) < 128 for row in ascii_rows for c in row[0])
    assert any(row[0].strip() for row in ascii_rows)
    inverted = render_mirror(data, (128, 64), {"invert": "on"}, False, 0, unicode=False)
    assert inverted[0][0] == "#" * 64                        # emulation applies too
    plugin._mirror_handler(None, "t", frame_bytes())
    page = DisplayPage(blocks=True, mode="ascii")            # AIKO_DISPLAY_MIRROR=ascii
    rows = page.rows({}, 256, unicode=True)
    assert all(ord(c) < 128 for row in rows for c in row[0])
    unicode_page = DisplayPage(blocks=True, mode="on")
    assert unicode_page.rows({}, 256, unicode=False)[0][0] == rows[0][0]   # the terminal decides
    assert unicode_page.rows({}, 256, unicode=True) != rows
    plugin._latest["frame"], plugin._latest["at"] = None, 0.0

def test_mirror_switch():
    assert plugin._mirror_mode("OFF") == "off" and plugin._mirror_mode("bogus") == "on"
    assert plugin._mirror_mode(None) == "on" and plugin._mirror_mode(" ascii ") == "ascii"
    page = DisplayPage(blocks=True, mode="off")
    assert not page.mirror_on
    plugin._mirror_handler(None, "t", frame_bytes())
    assert page.rows({}, 256) is None
    assert page.feed_status({"mirrors": "1"}, time.monotonic(), True) == "mirror: off (M)"
    assert page.toggle_mirror() and page.rows({}, 256) is not None
    assert not page.toggle_mirror()
    plugin._latest["frame"], plugin._latest["at"] = None, 0.0

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
    canvas.unicode_aware = False                             # the ASCII tier
    widget.update(1)
    assert len(printed) == 32 and all(ord(c) < 128 for row in printed for c in row[0])
    plugin._latest["frame"], plugin._latest["at"] = None, 0.0
    canvas.unicode_aware = True
    widget.message = "mirror: waiting for frames"
    widget.update(2)
    assert printed[-1][0] == "mirror: waiting for frames"

def test_plugins_dict_and_topic():
    assert list(plugin.plugins) == ["display"]
    assert plugin.mirror_topic().endswith("/display/mirror")

# --------------------------------------------------------------------------- #
# The terminal matrix: what asciimatics decides for each terminal type,
# locale and size, found in a real pseudo-terminal, then the page drawn
# with those capabilities.  asciimatics decides Unicode from the locale
# encoding only (Python coerces LANG=C to UTF-8, but not LC_ALL=C) and the
# colours from terminfo.  The Linux console's font has no Braille glyphs:
# that and the real terminals are on the manual checklist (testing.md)

import json      # noqa: E402
import os        # noqa: E402
import select    # noqa: E402
import sys       # noqa: E402

PROBE = """
import json, sys
from asciimatics.screen import Screen
screen = Screen.open()
found = {"unicode": screen.unicode_aware, "colours": screen.colours,
         "width": screen.width, "height": screen.height}
screen.close()
with open(sys.argv[1], "w") as file:
    json.dump(found, file)
"""

TERMS = ("xterm-256color", "xterm", "linux", "vt100")
LOCALES = {"LANG=en_AU.UTF-8": {"LANG": "en_AU.UTF-8"},
           "LANG=C": {"LANG": "C"}, "LC_ALL=C": {"LC_ALL": "C", "LANG": "C"}}
SIZES = ((132, 48), (80, 24))

def probe_terminal(term, locale_env, size, path, timeout=20.0):
    """Run the probe on a pseudo-terminal of SIZE (columns, rows)"""

    import fcntl
    import pty
    import struct
    import termios

    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith("LC_") and name not in ("LANG", "TERM")}
    environment.update(locale_env, TERM=term)
    pid, fd = pty.fork()
    if pid == 0:                                  # the child: set the size first
        try:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", size[1], size[0], 0, 0))
            os.execve(sys.executable, [sys.executable, "-c", PROBE, str(path)], environment)
        finally:
            os._exit(127)
    output, deadline = b"", time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:                   # the child closed the terminal
                    break
                if not chunk:
                    break
                output += chunk
        else:
            os.kill(pid, 9)
    finally:
        os.close(fd)
        os.waitpid(pid, 0)
    if not path.exists():
        return None, output
    return json.loads(path.read_text()), output

@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs a POSIX pseudo-terminal")
@pytest.mark.parametrize("size", SIZES, ids=lambda size: f"{size[0]}x{size[1]}")
@pytest.mark.parametrize("locale_name", LOCALES)
@pytest.mark.parametrize("term", TERMS)
def test_terminal_matrix(term, locale_name, size, tmp_path):
    found, output = probe_terminal(term, LOCALES[locale_name], size, tmp_path / "found.json")
    if found is None and b"curs_set" in output:
        pytest.xfail(f"asciimatics needs cursor control, which TERM={term} lacks:"
                     " no Dashboard at all")
    if found is None:
        pytest.skip(f"no curses screen for TERM={term}: {output[-200:]!r}")
    assert (found["width"], found["height"]) == size
    if locale_name == "LC_ALL=C":
        assert found["unicode"] is False
    elif locale_name == "LANG=C":
        assert found["unicode"] is True          # coerced to C.UTF-8
    if term == "xterm-256color":
        assert found["colours"] >= 256

    plugin._mirror_handler(None, "t", frame_bytes())
    width, height = size
    wide = width >= plugin.WIDE[0] and height >= plugin.WIDE[1]
    for colours in (found["colours"], 8, 0):     # what it found, 8 colours, none
        printed = []
        canvas = SimpleNamespace(unicode_aware=found["unicode"], colours=colours,
            print_at=lambda text, x, y, *rest: printed.append((text, x, y, rest)))
        page = DisplayPage(blocks=wide)
        page.observe({"size": "128x64"}, time.monotonic())
        widget = MirrorWidget(page, 32 if wide else 16)
        widget._frame, widget._x, widget._y = SimpleNamespace(canvas=canvas), 0, 0
        widget._w, widget._h = (128, 32) if wide else (64, 16)
        widget.update(0)
        assert len(printed) == widget._h and all(len(text) <= width for text, *_ in printed)
        if not found["unicode"]:
            assert all(ord(c) < 128 for text, *_ in printed for c in text)
    plugin._latest["frame"], plugin._latest["at"] = None, 0.0
