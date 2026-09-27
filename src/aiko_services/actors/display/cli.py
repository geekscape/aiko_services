#!/usr/bin/env python3
#
# Aiko Services: display Actor command line
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The "aiko_display" command: "run" starts the display Actor (display.py)
# in this process; every other subcommand discovers the Actor named with
# -n (default: this host's name) and sends it one command, giving up after
# -t seconds.  "keys" is the interactive console (console.py).
#
# Usage: aiko_display --help
#
# Not part of the Interface composition pattern (ADR-022 category
# Presentation and CLI shells) — see e_10 §2.16: a CLI shell over the
# display Actor's Interfaces.

import os
import signal
import textwrap

import click

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname

from aiko_services.actors.display.applets import APPLETS
from aiko_services.actors.display.display import (
    DEFAULT_APPLET, KEY_STATES, PIXEL_PAIRS_MAXIMUM, PROTOCOL, SETTINGS,
    SETTINGS_SPEC, Canvas, Display, DisplayImpl, Interaction, Screen,
    service_filter, service_tags,
)
from aiko_services.actors.display.graphics import parse_font_size
from aiko_services.actors.display import keys as keymap
from aiko_services.actors.display.outputs import (
    ADDRESSES, OUTPUTS, DisplayNotFound, choose_output, parse_colors, scan_i2c,
)

TIMEOUT = 5.0  # seconds to wait for the display Actor before giving up

def _start_timeout(seconds, what):
    """The framework's do_command() and do_discovery() wait for ever: give up
    with exit status 1 after the timeout (P3: every request has a deadline)"""

    def timed_out():
        aiko.event.remove_timer_handler(timed_out)
        click.echo(f"Timeout after {seconds:g} s: {what}", err=True)
        aiko.process.terminate(1)

    aiko.event.add_timer_handler(timed_out, seconds)

def _remote(interface, options, command_handler):
    """Discover the display Actor named in the group options (-n, -t) and
    invoke one command on it"""

    name, timeout = options["name"], options["timeout"]
    _start_timeout(timeout, f"no display Actor named {name or get_hostname()}")
    aiko.do_command(interface, service_filter(name), command_handler,
        terminate=True)
    aiko.process.run()

def _parse_address(ctx, param, value):
    try:
        return int(value, 0)
    except ValueError:
        raise click.BadParameter(f"{value!r} is not a number, e.g. 0x3D")

def _parse_colors(ctx, param, value):
    """-c 'FOREGROUND [BACKGROUND]': the color names (or #rrggbb), checked"""

    if value is None:
        return None
    try:
        parse_colors(value)
    except ValueError as error:
        raise click.BadParameter(
            f"{value!r}: {error}, e.g. -c yellow or -c 'yellow navy'")
    return str(value).replace(",", " ").split()

def _validate_font_size(ctx, param, value):
    try:
        parse_font_size(value)
    except ValueError as error:
        raise click.BadParameter(str(error))
    return value

def _display_hint(bus):
    found = scan_i2c(bus)
    if found:
        return ("An SSD1306 answers at "
            + " and ".join(f"0x{address:02X}" for address in found) + ": use -a")
    return ("No SSD1306 answers at "
        + " or ".join(f"0x{address:02X}" for address in ADDRESSES)
        + ": check the wiring and that I2C is enabled")

@click.group()
@click.option("--name", "-n", type=str, default=None,
    help="The display Actor: the one to run, or the one to command  "
         "[default: the local hostname]")
@click.option("--timeout", "-t", type=float, default=TIMEOUT, show_default=True,
    help="Seconds to wait for the display Actor (for list: to collect them)")
@click.pass_context

def main(ctx, name, timeout):
    """display Actor: run it, or send commands to the running one

    An SSD1306 128x64 OLED as an Aiko Services Actor (protocol oled:0): a
    status display for a headless host, a canvas any client draws on with
    the same S-expressions as the aiko_engine_mp OLED, settings the Aiko
    Dashboard reads and writes, and applets (games, drawings, a clock, eyes,
    a demo) that run on the display.  Without the panel, a desktop window,
    the terminal or a PNG file emulates it.

    \b
    export AIKO_MQTT_HOST=localhost       # the broker; aiko_registrar must run
    aiko_display run -a 0x3C                 # the OLED, or emulated on a desktop
    aiko_display text 0 0 hello            # from another terminal: the bottom row
    aiko_display log Hello from nomad        # scrolls; the status applet shows it
    aiko_display set contrast 64           # a setting: the Dashboard edits it too
    aiko_display applet pong                 # an applet; applet -l lists them
    aiko_display keys                        # an interactive console
    aiko_display -n w3029f1 -t 3 applet eyes  # another host, 3 s to find it
    aiko_display exit
    """

    ctx.obj = {"name": name, "timeout": timeout}

@main.command(name="run")
@click.option("--output", "-o", type=click.Choice(OUTPUTS), default="auto",
    show_default=True,
    help="oled: the SSD1306 over I2C; window (pygame), terminal, png: "
         "emulations; auto: the OLED if there is an I2C bus, else a window "
         "on a desktop with pygame, else the terminal")
@click.option("--address", "-a", default="0x3C", callback=_parse_address,
    help="I2C address of the OLED  [default: 0x3C]")
@click.option("--bus", "-b", type=int, default=1, show_default=True,
    help="I2C bus number")
@click.option("--applet", default=DEFAULT_APPLET, show_default=True,
    help="Applet to run at start; none: show the canvas")
@click.option("--font_size", "-fs", default="5x7", show_default=True,
    callback=_validate_font_size,
    help="5x7 bitmap font, or a TrueType font size in pixels, 6 to 64")
@click.option("--title", default=None,
    help="Title row text (use _ for spaces) or off  [default: the Actor name]")
@click.option("--color", "-c", default=None, callback=_parse_colors,
    metavar="'FOREGROUND [BACKGROUND]'",
    help="Colors of an emulated display, e.g. 'yellow navy': the settings "
         "foreground and background, which the keys b and B step through")
@click.option("--png", type=click.Path(dir_okay=False), default=None,
    help="File for -o png  [default: oled.png]")
@click.option("--standalone", is_flag=True,
    help="Run without an MQTT broker (status display only)")
@click.option("--strict", is_flag=True,
    help="Exit when the display can't be opened, instead of retrying")

@click.pass_obj

def run_command(options, output, address, bus, applet, font_size, title,
    color, png, standalone, strict):
    """Run the display Actor in the foreground (append & for the background, or
    start it with "aiko_process create")

    \b
    The display (-o):
      oled      the SSD1306 over I2C: -a address (0x3C, or 0x3D with SA0
                high), -b bus; needs "pip install luma.oled"
      window    an emulated OLED in a pygame window, 5x with pixel gaps;
                the keys work as in "aiko_display keys"; Esc, x or q exits
      terminal  half-block characters, 128x34 (Braille dots when smaller)
      png       the latest frame in a PNG file (--png, at most once a second)
      none      no display: the Actor still runs (shared state, applets)
      auto      oled when /dev/i2c-N exists, else window on a desktop with
                pygame, else terminal

    \b
    At start the Actor shows --applet (status: IP address, CPU and memory,
    disk and network, load, temperature and fan, uptime, the newest log line;
    status,screen=wifi: the Wi-Fi link; view=cpu_mem: a chart) under
    the title row: the Actor's name (-n, default the hostname; --title TEXT
    with _ for spaces, or off), the annunciators L (log lines not yet
    shown), M (connected to the broker) and R (registered), and the clock.
    -fs is the text font (5x7, or a TrueType size 6..64).  -c colors an
    emulated display, e.g. -c 'yellow navy': the settings "foreground" and
    "background", which the keys b and B step through while it runs.

    \b
    --standalone runs without an MQTT broker: the status display still
    works.  --strict exits when the display can't be opened, instead of
    reporting "device absent" and retrying every 10 s.  Ctrl-C, SIGTERM,
    "(exit)" and "aiko_display exit" all blank the display on the way out.
    """

    name = options["name"] or get_hostname()
    if output == "terminal":  # console logging would scribble on the picture
        os.environ.setdefault("AIKO_LOG_MQTT", "true")
    backend = choose_output(output, address, bus, png)
    parameters = {
        "output": backend, "applet": applet, "font": font_size,
        "title": title, "strict": strict, "colors": color,
    }
    init_args = aiko.actor_args(
        name, parameters=parameters, protocol=PROTOCOL,
        tags=service_tags(backend.name))
    signal.signal(signal.SIGTERM, lambda *_: aiko.process.terminate())
    actor = None
    try:
        actor = aiko.compose_instance(DisplayImpl, init_args)
        backend.message(f"{name}: {actor.topic_in}")
        if backend.name != "terminal":
            click.echo(f"display Actor {name}: {actor.topic_in}")
        aiko.process.run(mqtt_connection_required=not standalone)
    except DisplayNotFound as error:
        raise click.ClickException(f"{error}\n{_display_hint(bus)}")
    finally:
        if actor:
            actor._shutdown()

@main.command(name="exit")
@click.option("--all", "every", is_flag=True,
    help="Allow -n '*': exit every display Actor")
@click.pass_obj

def exit_command(options, every):
    """Blank the display and terminate the display Actor

    The Actor named with -n (default: the local hostname).  -n '*' with
    --all exits every display Actor on the broker.  Exit status 1 after -t
    seconds when no Actor answers.  The same as "(exit)", the framework's
    "(stop)", on the in topic: the display blanks on the way out.
    """

    if options["name"] == "*" and not every:
        raise click.BadParameter("-n '*' would exit every display Actor: add --all")
    _remote(Display, options, lambda display: display.stop())

@main.command(name="list")
@click.pass_obj

def list_command(options):
    """List the running display Actors: name, topic path, tags

    Every display:0 Actor on the broker (or the one named with -n), collected
    for -t seconds through the Registrar.  Exit status 1 when none is found:
    check AIKO_MQTT_HOST, that aiko_registrar runs, and for a stale retained
    Registrar announcement (see the test guide).
    """

    name, timeout = options["name"] or "*", options["timeout"]
    found = []

    def add_handler(service_details, service):
        found.append(service_details)

    def done():
        aiko.event.remove_timer_handler(done)
        for details in found:
            click.echo(f"{details[1]}  {details[0]}  {' '.join(details[5])}")
        if not found:
            click.echo("No display Actors found", err=True)
        aiko.process.terminate(0 if found else 1)

    aiko.do_discovery(Display,
        aiko.ServiceFilter("*", name, PROTOCOL, "*", "*", "*"), add_handler)
    aiko.event.add_timer_handler(done, timeout)
    aiko.process.run()

@main.command(name="clear")

@click.pass_obj

def clear_command(options):
    """Erase the canvas (the title row stays)

    Drawing commands (clear, text, pixels, line) stop a running applet so
    that the canvas shows; "aiko_display applet status" brings the status
    display back.  The same as "(clear)" or aiko_engine_mp's "(oled:clear)".
    """

    _remote(Canvas, options, lambda oled: oled.clear())

@main.command(name="log", no_args_is_help=True)
@click.argument("words", nargs=-1, required=True)

@click.pass_obj

def log_command(options, words):
    """Scroll the canvas up one text row and write WORDS on the bottom row

    The line is also kept (the last eight) for the status applet, which
    shows the newest, and the log applet, which shows them all; until one
    of them shows it, the title row's L annunciator is on (shared state
    log_pending).  A running applet keeps running.  At most 128 characters.
    The same as "(log WORDS ...)" or aiko_engine_mp's "(oled:log ...)".
    """

    _remote(Canvas, options, lambda oled: oled.log(*words))

@main.command(name="text", no_args_is_help=True)
@click.argument("x", type=int)
@click.argument("y", type=int)
@click.argument("words", nargs=-1, required=True)

@click.pass_obj

def text_command(options, x, y, words):
    """Write WORDS on the canvas with the text cell's bottom-left at X Y

    X is 0..127 left to right and Y 0..63 bottom to top, as on the
    aiko_engine_mp OLED: "text 0 0 hello" is the bottom row, "text 0 8 ..."
    the row above with the 5x7 font (8 pixel rows, 21 characters across).
    The font is the "font" setting.  Quote a word that starts with digits
    and a colon ("12:30").  Stops a running applet so the canvas shows.
    The same as "(text X Y WORDS ...)" or "(oled:text ...)".
    """

    _remote(Canvas, options, lambda oled: oled.text(x, y, *words))

@main.command(name="pixels", no_args_is_help=True)
@click.argument("coordinates", nargs=-1, type=int, required=True)

@click.pass_obj

def pixels_command(options, coordinates):
    """Light pixels at X Y pairs, origin bottom-left

    X 0..127, Y 0..63; at most 256 pairs; all or nothing when a coordinate
    is out of range.  The same as "(pixels X Y X Y ...)" or "(oled:pixels
    ...)"; one pixel is "(pixel X Y)".
    """

    if len(coordinates) % 2 or len(coordinates) > 2 * PIXEL_PAIRS_MAXIMUM:
        raise click.BadParameter(
            f"give X Y pairs, at most {PIXEL_PAIRS_MAXIMUM} of them")
    _remote(Canvas, options, lambda oled: oled.pixels(*coordinates))

@main.command(name="line", no_args_is_help=True)
@click.argument("x0", type=int)
@click.argument("y0", type=int)
@click.argument("x1", type=int)
@click.argument("y1", type=int)

@click.pass_obj

def line_command(options, x0, y0, x1, y1):
    """Draw a line from X0 Y0 to X1 Y1, origin bottom-left

    The same as "(line X0 Y0 X1 Y1)" (not in aiko_engine_mp).
    """

    _remote(Canvas, options, lambda oled: oled.line(x0, y0, x1, y1))

@main.command(name="set", no_args_is_help=True)
@click.argument("key", type=click.Choice(SETTINGS))
@click.argument("value")

@click.pass_obj

def set_command(options, key, value):
    """Change a setting: shared state that the Aiko Dashboard also edits

    Sends "(update KEY VALUE)" on the Actor's control topic, exactly what
    the Dashboard does when a variable is edited.  A bad value is rejected
    (last_error tells why) and the value in force is published again.
    Values are single tokens: _ stands for a space in a title.
    """

    if any(character.isspace() for character in value):
        raise click.BadParameter("no spaces in a value: use _ instead")
    name, timeout = options["name"], options["timeout"]
    what = f"no display Actor named {name or get_hostname()}"

    def add_handler(service_details, service):
        topic_path = service_details[0]
        aiko.process.message.publish(
            f"{topic_path}/control", f"(update {key} {value})")
        aiko.process.terminate()

    _start_timeout(timeout, what)
    aiko.do_discovery(Display, service_filter(name), add_handler)
    aiko.process.run()

@main.command(name="applet")
@click.option("--list", "-l", "list_applets", is_flag=True,
    help="List the applets and their options, without an Actor")
@click.argument("applet_name", required=False)
@click.argument("arguments", nargs=-1)

@click.pass_obj

def applet_command(options, list_applets, applet_name, arguments):
    """Run an applet, e.g. status, pong seed=1; none shows the canvas"""

    if list_applets:
        width = max(len(applet_name) for applet_name in APPLETS)
        for applet_name, applet_class in sorted(APPLETS.items()):
            options = " ".join(f"{option}=" for option in applet_class.OPTIONS)
            summary = applet_class.summary or " ".join((applet_class.__doc__ or "").split())
            click.echo(f"{applet_name:{width}}  {summary}"
                       + (f"  [{options}]" if options else ""))
        return
    if not applet_name:
        raise click.UsageError("give an applet name, or --list")
    _remote(Interaction, options,
        lambda oled: oled.applet(applet_name, *arguments))

@main.command(name="stop")

@click.pass_obj

def stop_command(options):
    """Stop the running applet: the canvas is shown again

    The same as "aiko_display applet none" or "(applet none)".
    """

    _remote(Interaction, options, lambda oled: oled.applet("none"))

@main.command(name="mirror")
@click.argument("topic")
@click.argument("seconds", type=int, default=30)
@click.pass_obj

def mirror_command(options, topic, seconds):
    """Ask the Actor to publish its frames to TOPIC: a leased feed

    Raw frames (1024 bytes at 128x64: PIL mode "1", row major, MSB first) go
    to TOPIC whenever the panel changes, at most "mirror_rate" a second, for
    SECONDS (default 30, at most 300; repeat to extend); 0 stops.  At most
    4 holders.  The same as "(mirror TOPIC SECONDS)".  The Dashboard plug-in
    uses this for its live mirror; "mosquitto_sub -t TOPIC" shows the bytes.
    """

    _remote(Screen, options, lambda screen: screen.mirror(topic, seconds))

@main.command(name="keys")

@click.pass_obj

def keys_command(options):
    """Interactive console: keys switch applets and settings, arrows play

    \b
    s status screens (host, wifi)  S the next view of that screen (charts)
    l log  p pattern  t text  d draw  D demo  P blink  C clock  e eyes
    g games (pong, asteroids, invaders, forklift)  G forklift game
    h or ? help (the same applet key again: its next options)
    arrows: keys for the applet   0-9 speed (4 normal)   f F next/previous font
    T title  i invert  o power  a all pixels on  +/- contrast  b B color
    c clear  R reset   x or q quit the console   X exit the display Actor
    """

    from aiko_services.actors.display.console import KeysConsole  # (imports this module)
    KeysConsole(options["name"], options["timeout"]).run()

@main.command(name="key", no_args_is_help=True)
@click.argument("key_name")
@click.argument("state", type=click.Choice(KEY_STATES), default="tap")

@click.pass_obj

def key_command(options, key_name, state):
    """Send a key to the running display Actor

    KEY_NAME is up, down, left, right or one character; STATE is tap (held
    briefly, the default), down or up.  A key in the Actor's key map runs its
    preset or changes its setting ("key g" starts pong, "key 5" halves the
    speed, "key R" resets); any other key goes to the running applet:
    forklift_game: left and right drive, up and down lift; help: right and
    left turn the pages.  The same as "(key NAME [STATE])"; "aiko_display keys"
    sends every key this way.
    """

    _remote(Interaction, options,
        lambda oled: oled.key(key_name, state))

# --------------------------------------------------------------------------- #
# Reference text for --help, made from the same tables the code uses

def _block(lines):
    return "\b\n" + "\n".join(lines)

def _applets_reference():
    width = max(len(name) for name in APPLETS)
    lines = ["Applets  (aiko_display applet NAME [WORDS ...] [key=value ...]; -l lists them)"]
    for name, applet_class in sorted(APPLETS.items()):
        options = " ".join(f"{option}=" for option in applet_class.OPTIONS)
        text = applet_class.summary + (f"  [{options}]" if options else "")
        lines += textwrap.wrap(text, width=75, initial_indent=f"  {name:{width}}  ",
                               subsequent_indent=" " * (width + 4))
    return _block(lines)

def _settings_reference():
    lines = ["Settings  (aiko_display set KEY VALUE, or (update KEY VALUE) on the control",
             "           topic; the Aiko Dashboard edits them; a bad value converges back)"]
    cells = [f"{setting.name:12} {setting.values}" for setting in SETTINGS_SPEC]
    for left, right in zip(cells[0::2], cells[1::2] + [""]):
        lines.append(f"  {left:37}{right}".rstrip())
    return _block(lines)

_SETTINGS_REFERENCE = _settings_reference()
_STATE_REFERENCE = _block([
    "Shared state  (aiko_dashboard, or (share TOPIC SECONDS *) on control)",
    "  backend device panels size origin depth settings keys.* connection",
    "  mirrors applets applet applet_detail fps",
    "  speed font contrast invert power all_on title blank_after foreground",
    "  background heartbeat last_error log_count log_pending metrics.commands",
    "  metrics.rejected metrics.frames metrics.frame_ms metrics.errors",
    "  metrics.mirrored",
])
_WIRE_REFERENCE = _block([
    "Wire commands on the in topic  (mosquitto_pub -t TOPIC/in -m '...')",
    "  origin bottom-left; the aiko_engine_mp names in brackets",
    "  (clear)                  [(oled:clear)]    erase the canvas",
    "  (log WORDS ...)          [(oled:log ..)]   scroll up, write the bottom row",
    "  (pixel X Y)              [(oled:pixel ..)] light a pixel",
    "  (pixels X Y X Y ...)     [(oled:pixels .)] at most 256 pairs",
    "  (line X0 Y0 X1 Y1)                         draw a line",
    "  (text X Y WORDS ...)     [(oled:text ..)]  text with its bottom-left at X Y",
    "  (exit)                   = (stop)          blank the display and terminate",
    "  (applet NAME [ARGS ...])                   run an applet; none: the canvas",
    "  (key NAME [tap|down|up])                   a mapped key runs its preset,",
    "                                             any other goes to the applet",
    "  (mirror TOPIC SECONDS)                     a leased feed of raw frames to",
    "                                             TOPIC (the Dashboard plug-in)",
    "  Anything else is rejected (last_error, metrics.rejected).",
])

def _preset_text(commands):
    words = []
    for command in commands:
        if command[0] == "update":
            words.append(f"{command[1]} {command[2]}")
        else:
            words.append(" ".join(command[1]))
    return " ".join(words)

def _keys_reference():
    lines = ["Keys  (the map lives on the Actor: \"(key K)\" from the console, the",
             "       emulator window, the plug-in or \"aiko_display key\"; the same key",
             "       again: the next preset)"]
    for key, presets in keymap.PRESETS.items():
        text = " | ".join(_preset_text(preset) for preset in presets)
        lines += textwrap.wrap(text, width=75, initial_indent=f"  {key}  ",
                               subsequent_indent="     ")
    lines += [
        "  S  the next view of the status screen shown: text, then its charts",
        "  arrows  (key left|right|up|down) for the applet: the forklift game, help",
        "  0-9  speed: 0 fastest (x4), 4 normal, 9 slowest   f F  next/previous font",
        "  T title on/off   i invert   o power   a all pixels on   + - contrast by 16",
        "  b B  the next foreground / background color (emulated displays)  c clear",
        "  R  reset the settings and the colors, show status   ? the same as h",
        "  x q  quit the console   X  exit the display Actor (then y to confirm)",
        "  The same keys work in the emulator window (-o window); x q X exit there",
    ]
    return _block(lines)

def _reference():
    return "\n\n".join([_applets_reference(), _SETTINGS_REFERENCE, _STATE_REFERENCE,
                        _WIRE_REFERENCE, _keys_reference()])

main.epilog = _reference()
main.commands["applet"].help = (
    "Run an applet on the display, replacing the running one; ARGS are words and\n"
    "key=value options.  \"none\" shows the canvas; --list lists the applets without\n"
    "an Actor.  Every applet is deterministic for a seed= (no clocks, only frame\n"
    "counts); \"set speed\" changes their pace.\n\n" + _applets_reference())
def _set_help():
    rows = [f"{'KEY':12} {'VALUE':22} MEANING"]
    for setting in SETTINGS_SPEC:
        rows += textwrap.wrap(setting.description, width=76,
            initial_indent=f"{setting.name:12} {setting.values:22} ",
            subsequent_indent=" " * 36)
    return main.commands["set"].help.rstrip() + "\n\n\b\n" + "\n".join(rows)

main.commands["set"].help = _set_help()
main.commands["keys"].help = (
    "Interactive console for the running display Actor: keys typed here become wire\n"
    "commands and settings, and a status line follows the Actor's shared state.\n"
    "Needs a terminal.  x or q quits the console; the Actor keeps running.\n\n"
    + _keys_reference())

if __name__ == "__main__":
    main()
