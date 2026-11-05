#!/usr/bin/env python3
#
# Aiko Services tests: draw a Dashboard frame on a real terminal
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# asciimatics has no screen double, and the mistakes it invites are in the
# parts that no pure test reaches: a constructor that forgets fix(), a
# widget taller than the frame, a layout with no widget, a Scene that a
# popup needs, an attribute that _update() reads before it exists.  Each
# one raises the first time a person opens the page, and never before.
#
# So this helper opens a real curses Screen on a pseudo-terminal, builds
# the frame, registers a real Scene, calls the Service hook, draws one
# pass, and hands back the characters that reached the screen.  It follows
# probe_terminal() in "test_display_dashboard_plugin.py", which drives
# asciimatics the same way.
#
# A caller gets either the screen lines or a diagnostic, and the test
# skips where there is no pseudo-terminal to be had.
#
# To Do
# ~~~~~
# - Deliver key events, so that process_event() and the popups are covered
# - Several draw passes, for the frames that change over time

import json
import os
import select
import sys
import time

__all__ = ["draw_frame", "pty_available"]

# The child process: it must not import pytest, and it reports through a
# file, because a curses screen owns the terminal while it is open
_CHILD = r'''
import json, sys
from types import SimpleNamespace

module_name, class_name, state_pathname, out_pathname = sys.argv[1:5]
state = json.load(open(state_pathname))

from asciimatics.scene import Scene
from asciimatics.screen import Screen
from importlib import import_module

frame_class = getattr(import_module(module_name), class_name)

class _Consumer:
    def __init__(self, cache):
        self.cache = cache

class _Dashboard:
    """Just enough Dashboard for a ServiceFrame: the ECConsumer it shares,
    and the selected Service that _update() watches for a change"""

    def __init__(self, service, cache):
        self.ec_consumer = _Consumer(cache)
        self.selected_service = service
        self.subscribed_service = None

def read_screen(screen, rows, columns):
    lines = []
    for y in range(min(rows, screen.height)):
        line = ""
        for x in range(min(columns, screen.width)):
            character = screen.get_from(x, y)[0]
            line += chr(character) if character else " "
        lines.append(line.rstrip())
    return lines

def run(screen):
    service = state["service"]
    dashboard = _Dashboard(service, state["cache"])
    frame = frame_class(screen, dashboard)
    frame.register_scene(Scene([frame]))
    # Two passes, because a page sets its widgets after the base class has
    # drawn them, so the first pass shows the state of the one before it.
    # The Dashboard runs at about 20 Hz, where nobody sees the lag
    for frame_no in range(state.get("passes", 2)):
        frame.update(frame_no)
    screen.refresh()
    return {"lines": read_screen(screen, 40, 120),
            "size": [screen.width, screen.height]}

def report(found):
    """Write beside the name, then rename: the parent waits for the name to
    appear, and a half-written file would be read as empty"""

    import os
    part_pathname = out_pathname + ".part"
    with open(part_pathname, "w") as file:
        json.dump(found, file)
        file.flush()
        os.fsync(file.fileno())
    os.replace(part_pathname, out_pathname)

try:
    report({"ok": True, **Screen.wrapper(run)})
except BaseException as exception:
    import traceback
    report({"ok": False,
            "error": f"{type(exception).__name__}: {exception}",
            "traceback": traceback.format_exc()})
'''

def pty_available():
    return hasattr(os, "fork") and hasattr(os, "openpty")

def draw_frame(module_name, class_name, cache, tmp_path,
    service=None, size=(100, 30), term="xterm-256color", timeout=30.0,
    passes=2):
    """Build the frame on a pseudo-terminal and draw it once.

    Returns the result dictionary: "ok" with "lines" and "size", or "ok"
    False with "error" and "traceback".  A frame that raises anywhere in
    its constructor, its layout or its first draw reports it here
    """

    import fcntl
    import pty
    import struct
    import termios

    service = service or [
        "aiko/host/1234/1", class_name, "protocol:0", "mqtt", "owner", []]
    state_pathname = str(tmp_path / "state.json")
    out_pathname = str(tmp_path / "drawn.json")
    with open(state_pathname, "w") as file:
        json.dump({"cache": cache, "service": service, "passes": passes}, file)

    environment = {name: value for name, value in os.environ.items()
        if name not in ("TERM",)}
    environment["TERM"] = term
    environment.setdefault("LANG", "en_AU.UTF-8")

    pid, fd = pty.fork()
    if pid == 0:                           # the child: its size, then exec
        try:
            fcntl.ioctl(0, termios.TIOCSWINSZ,
                struct.pack("HHHH", size[1], size[0], 0, 0))
            os.execve(sys.executable, [sys.executable, "-c", _CHILD,
                module_name, class_name, state_pathname, out_pathname],
                environment)
        finally:
            os._exit(127)

    output, deadline = b"", time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:            # the child closed the terminal
                    break
                if not chunk:
                    break
                output += chunk
            if os.path.exists(out_pathname):
                break
        else:
            os.kill(pid, 9)
    finally:
        os.close(fd)
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass

    if not os.path.exists(out_pathname):
        return {"ok": False, "error": "the child wrote nothing",
                "traceback": output.decode("utf-8", "replace")[-400:]}
    with open(out_pathname) as file:
        return json.load(file)

# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# A FormFrame the fixture above can build, because draw_frame() calls a
# class with the screen and a Dashboard, and a form takes its fields

class FormProbe:
    """Every kind of field, so that one draw shows each widget"""

    def __new__(cls, screen, dashboard):
        from aiko_services.ide.tui.dashboard import (
            FormFrame, choice_field, radio_field, text_field,
        )
        cls.accepted = {}
        return FormFrame(screen, "Probe the form", [
            text_field("name", "Name", "a name"),
            radio_field("kind", "Entry",
                [("Dependency", "dependency"), ("Category", "category")]),
            choice_field("field", "Field",
                [("name", "name"), ("owner", "owner")]),
            text_field("tags", "Tags"),
        ], "Accept", cls.accepted.update, note="A note, above the fields")

# --------------------------------------------------------------------------- #
# A page that has more than one view needs one probe for each, because
# draw_frame() delivers no key events and a view is reached with a key

class PowerManagerProbe:
    """A PowerManagerFrame already showing one view"""

    view = None

    def __new__(cls, screen, dashboard):
        from aiko_services.actors.power_manager.dashboard_plugin import (
            PowerManagerFrame,
        )
        frame = PowerManagerFrame(screen, dashboard)
        if cls.view:
            frame.page.view = cls.view
        return frame

class PowerManagerSummary(PowerManagerProbe):
    view = "summary"

class PowerManagerDetail(PowerManagerProbe):
    view = "detail"

class PowerManagerInformation(PowerManagerProbe):
    view = "information"

class PowerManagerChart:
    """The chart is a Frame of its own, so it has a probe of its own"""

    def __new__(cls, screen, dashboard):
        from aiko_services.actors.power_manager.dashboard_plugin import (
            PowerManagerChartFrame,
        )
        return PowerManagerChartFrame(screen, dashboard)

class PowerManagerChartFilled:
    """The chart with a window of samples already in it.

    draw_frame() draws once, and a page that has seen one reading has
    nothing to plot.  This fills the window first, so the drawn test
    covers the lines and not only the frame around them"""

    def __new__(cls, screen, dashboard):
        import math
        from aiko_services.actors.power_manager.dashboard_plugin import (
            PowerManagerChartFrame, page_singleton,
        )
        page = page_singleton()
        page.samples.clear()
        now = 1_762_000_000.0
        for step in range(120):
            wave = math.sin(step / 9.0)
            page.samples.append((now + step * 15.0,
                11.4 + wave * 0.1, 0.7 + wave * 0.2, 8.0 + wave * 2.0,
                11.1 + wave * 0.1, 0.7 + wave * 0.2, 7.8 + wave * 2.0,
                32.0 + wave, 52.0 + wave * 4))
        page.end = now + 119 * 15.0
        return PowerManagerChartFrame(screen, dashboard)

# --------------------------------------------------------------------------- #
