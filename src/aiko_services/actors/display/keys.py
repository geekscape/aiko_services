#!/usr/bin/env python3
#
# Aiko Services: display key map
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# What each key does.  The map lives on the device: the Actor's key()
# runs a mapped key's preset, or changes its setting, and passes any other
# key to the running applet.  Thus every client, the "aiko_display keys"
# console, the emulator window, the Dashboard plug-in and "aiko_display key",
# sends the same "(key K tap)" and gets the same result.  Letters switch
# applets, and the same letter again steps to the next preset (as the
# original oled_test.py stepped through each subcommand's options); digits
# set the speed; other keys change settings.  legend() publishes the map
# as the share keys "keys.*".  Pure: no I/O, so tests can check every key.
#
# Not part of the Interface composition pattern (ADR-022 category
# Value and data types) — see e_10 §2.16: a data table owned by the Actor.
#
# Keys
# ~~~~
#   s status screens: host, wifi   S the next view of that screen: text, charts
#   l log  p pattern  t text  d draw  D demo  P blink  C clock  e eyes
#   g games: pong, asteroids, invaders, forklift   G forklift game
#   h ? help (again: the next page)
#   arrows: (key left|right|up|down)   0-9 speed (0 fastest, 4 normal, 9 slowest)
#   f F next / previous font   T title on/off   i invert   o power
#   a all pixels on   + - contrast
#   b B next foreground / background color (emulated displays)   c clear
#   R reset the settings and the colors, show status
#   x q quit (the console; in the window: exit the Actor)   X exit the Actor

from aiko_services.actors.display.drawings import SUBJECTS
from aiko_services.actors.display.graphics import FONT_SIZES
from aiko_services.actors.display.status import STATUS_VIEWS

__all__ = ["ACTION_KEYS", "ARROWS", "BACKGROUNDS", "FOREGROUNDS", "KEY_APPLETS",
           "MAPPED_KEYS", "PRESETS", "RESET", "applet", "key_command", "legend",
           "reset_commands", "update"]

ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}  # the terminal's codes

# What "b" and "B" step through (the original oled_test.py's lists)
FOREGROUNDS = ("white", "deepskyblue", "yellow", "lime", "orange", "hotpink")
BACKGROUNDS = ("black", "midnightblue", "darkslategray", "maroon", "dimgray", "white")

def applet(name, *arguments):
    return ("applet", (name, *arguments))

def update(key, value):
    return ("update", key, value)

# What each applet key sends; the same key again: the next preset.  A
# preset without its own font goes back to the base font (see key_command)
PRESETS = {
    "s": [[applet("status")], [applet("status", "screen=wifi")]],
    "l": [[applet("log")]],
    "h": [[applet("help", f"page={page}")] for page in range(1, 7)],
    "p": [[applet("pattern")], [update("font", "5x7"), applet("pattern")],
          [update("font", "10"), applet("pattern")],
          [update("font", "16"), applet("pattern")]],
    "t": [[applet("text")], [update("font", "5x7"), applet("text")],
          [update("font", "10"), applet("text")],
          [update("font", "16"), applet("text")],
          [update("font", "10"), applet("text", "Hello!")],
          [update("font", "24"), applet("text", "OLED")],
          [update("font", "16"), applet("text", "128x64")]],
    "d": [[applet("draw")], [applet("draw", "shade=off")],
          [applet("draw", "style=hatch")], [applet("draw", "style=stipple")]]
         + [[applet("draw", f"subject={subject}")] for subject in sorted(SUBJECTS)],
    "g": [[applet("pong")], [applet("asteroids")], [applet("invaders")], [applet("forklift")]],
    "G": [[applet("forklift_game")]],
    "P": [[applet("blink")], [applet("blink", "rate=8")]],
    "D": [[applet("demo")], [applet("demo", "random=off")]],
    "C": [[applet("clock")], [applet("clock", "title=on")], [applet("clock", "seconds=off")],
          [applet("clock", "face=digital")]],
    "e": [[applet("eyes")]] + [[applet("eyes", f"emotion={emotion}")]
                               for emotion in ("happy", "sad", "angry", "surprised",
                                               "sleepy", "suspicious", "curious", "loving")],
}
KEY_APPLETS = {key: presets[0][-1][1][0] for key, presets in PRESETS.items()}

# The keys the map acts on: the device runs their presets or changes their
# settings.  Any other key, the arrows above all, goes to the running applet
ACTION_KEYS = frozenset("0123456789fFTioa+-bBcSR?")
MAPPED_KEYS = frozenset(PRESETS) | ACTION_KEYS

# What the action keys mean, as share tokens ("keys.KEY")
_ACTIONS = {"S": "status_view", "digits": "speed", "f": "font_next",
            "F": "font_previous", "T": "title", "i": "invert", "o": "power",
            "a": "all_on", "plus": "contrast_up", "minus": "contrast_down",
            "b": "foreground", "B": "background", "c": "clear", "R": "reset",
            "arrows": "applet"}

def legend():
    """The key map as shared state: "keys.KEY" is the applets a key steps
    through, joined by "|", or the setting it changes.  Single tokens, so
    that a client of any display builds its legend from the share"""

    entries = {}
    for key, presets in PRESETS.items():
        names = []
        for preset in presets:
            for command in preset:
                if command[0] == "applet" and command[1][0] not in names:
                    names.append(command[1][0])
        entries[key] = "|".join(names)
    entries.update(_ACTIONS)
    return entries

# "R": every setting back to its default; "default" for a color is the
# color the Actor started with (-c), as the original oled_test.py reset to
# the starting colors
RESET = {"contrast": "255", "invert": "off", "power": "on", "all_on": "off",
         "font": "5x7", "speed": "1", "foreground": "default", "background": "default"}

def _next_color(names, current):
    """The color after the current one in the list, or the first"""

    return names[(names.index(current) + 1) % len(names)] if current in names else names[0]

def key_command(key, state):
    """The commands a key sends: a list of ("applet", arguments),
    ("key", arguments), ("clear", ()) or ("update", key, value); [] for a
    key that means nothing.  "state" holds the preset turns, the current
    key, the Actor's settings and the base font"""

    settings = state["settings"]
    if key == "?":
        key = "h"                    # help, wherever the key is typed
    if key in ARROWS.values():
        return [("key", (key, "tap"))]
    if key in PRESETS:
        presets = PRESETS[key]
        turn = state["turns"].get(key, -1) + 1 if state.get("current") == key else 0
        turn %= len(presets)
        state["turns"][key] = turn
        state["current"] = key
        commands = list(presets[turn])
        base = state.get("base_font")
        if base and not any(command[:2] == ("update", "font") for command in commands)  \
                and settings.get("font", base) != base:
            commands.insert(0, update("font", base))     # back to the base font
        return commands
    if key == "S":                   # the next view of the status screen shown
        detail = str(settings.get("applet_detail", ""))
        screen, _, view = detail.partition("_")
        if settings.get("applet") != "status" or screen not in STATUS_VIEWS:
            return [applet("status")]
        views = STATUS_VIEWS[screen]
        turn = (views.index(view) + 1) % len(views) if view in views else 0
        return [applet("status", f"screen={screen}", f"view={views[turn]}")]
    if key.isdigit():
        return [update("speed", f"{2 ** ((4 - int(key)) / 2):.3g}")]
    if key == "T":
        current = settings.get("title", "on")
        return [update("title", "on" if current == "off" else "off")]
    if key in ("f", "F"):
        sizes = [str(size) for size in FONT_SIZES]
        current = settings.get("font", "5x7")
        step = 1 if key == "f" else -1
        turn = (sizes.index(current) + step) % len(sizes) if current in sizes else 0
        state["base_font"] = sizes[turn]
        return [update("font", sizes[turn])]
    if key in ("i", "o", "a"):
        name = {"i": "invert", "o": "power", "a": "all_on"}[key]
        current = settings.get(name, "on" if name == "power" else "off")
        return [update(name, "off" if current == "on" else "on")]
    if key in ("+", "-"):
        try:
            contrast = int(settings.get("contrast", "255"))
        except ValueError:
            contrast = 255
        contrast = max(0, min(255, contrast + (16 if key == "+" else -16)))
        return [update("contrast", str(contrast))]
    if key in ("b", "B"):
        name = "foreground" if key == "b" else "background"
        names = FOREGROUNDS if key == "b" else BACKGROUNDS
        return [update(name, _next_color(names, settings.get(name)))]
    if key == "c":
        return [("clear", ())]
    return []

def reset_commands(state):
    """"R": every setting in RESET back to its default, then the status
    applet in the base font"""

    state["current"], state["base_font"] = "s", RESET["font"]
    return [update(name, value) for name, value in RESET.items()] + [applet("status")]
