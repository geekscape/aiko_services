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
