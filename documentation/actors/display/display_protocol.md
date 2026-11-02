---
title: Display protocol display:0
description: The wire protocol of the OLED example's Display Actor — the
  display:0 composite of the Canvas, Screen and Interaction aspects, the
  aspect tags and discovery, the topics, the one-way commands and their
  argument grammar, the leased frame mirror, the key map on the device,
  the shared state keys and
  their values, the rejection reasons, the conformance trace, and
  compatibility with the MicroPython aiko_engine_mp OLED
type: concept
audience: [developers, ai-coding-agents]
status: draft
ste: adapted
source:
  - src/aiko_services/actors/display/display.py
  - src/aiko_services/actors/display/keys.py
  - src/aiko_services/tests/unit/test_display.py
related: [display, display_dashboard, design, testing, actor, share, message,
  discovery, parameters, stream]
version: "0.8-dev"
last_updated: 2026-09-28
---

# Display protocol display:0

## Overview

This is the specification unit for the Display Actor: what a client may
send, what it observes, and what happens when something is wrong. The
Python Display Actor in `actors/display/` implements all of it. The
MicroPython aiko_engine_mp OLED implements the compatible subset, marked
in the tables below. The one-file example `examples/oled/oled_actor.py`
implements `clear`, `log` and `text` only. The decisions behind the
protocol are recorded in
[ADR-025](../../../constitution/adr/ADR-025_RemoteDisplayAbstraction.md).
The [display](display.md) document explains the Actor, and the
[test guide](testing.md) exercises every rule on this page.

The protocol id `oled:0` of Epic 0 is withdrawn before any release. Every
`oled:` alias and every wire form of Epic 0 keeps working.

## For application developers

### Command-line usage

`aiko_display` wraps the protocol. `aiko_display text 0 0 hello` sends
`(text 0 0 hello)` on the `in` topic. `aiko_display set contrast 64` sends
`(update contrast 64)` on the control topic. `aiko_display key g` sends
`(key g tap)`, and the Actor's key map starts pong. `aiko_display --help`
lists every wire command. Without the command line:

```bash
mosquitto_pub -t $TOPIC_PATH/in -m "(oled:text 0 0 hello)"
mosquitto_pub -t $TOPIC_PATH/control -m "(update contrast 64)"
```

### Public API

**Protocol id:** `github.com/geekscape/aiko_services/protocol/display:0`,
version 0. It is the composite of three aspect Interfaces. Within a major
version, only methods are added.

| Aspect | Contract id | Concern | Methods |
|--------|-------------|---------|---------|
| `Canvas` | `.../canvas:0` | Drawing on a canvas | `clear`, `log`, `pixel`, `pixels`, `line`, `text` |
| `Screen` | `.../screen:0` | Controlling the screen: its settings are shared state, and the leased frame mirror | `mirror` |
| `Interaction` | `.../interaction:0` | Controlling what runs on the display | `applet`, `key` |
| `Display` | `.../display:0`, registered | The composite | the framework's `stop`, `set_log_level` |

**Discovery.** A client discovers the Actor with a ServiceFilter on the
protocol and the Actor's name, which is the hostname by default. The
aspects are advertised as tags, because the Registrar matches one
protocol string per Service: `ec=true device=oled canvas=0 screen=0
interaction=0`. The device tag names the display backend in use. A client
that needs only drawing filters on the tag `canvas=0`:

```python
aiko.ServiceFilter("*", "w3029f1", PROTOCOL, "*", "*", "*")
aiko.ServiceFilter("*", "*", "*", "*", "*", ["canvas=0"])
```

**Topics.** The Actor listens on its `in` topic (`TOPIC_PATH/in`) for
commands. It listens on its control topic (`TOPIC_PATH/control`) for
`(update KEY VALUE)` and `(share ...)`. It publishes its shared state to
the consumers that hold a lease, as every ECProducer does. Nothing is
published on the `out` topic.

**Commands** on the `in` topic. All are one-way (P1): nothing is
returned, and nothing is raised across the wire. Coordinates: x 0..127
left to right, y 0..63 bottom to top. A text cell's bottom-left corner
is at (X, Y). Thus `(text 0 0 hi)` is the bottom row, and
`(text 0 8 hi)` is the row above with the 5x7 font.

| Aspect | Command | Arguments | Validation | aiko_engine_mp |
|--------|---------|-----------|------------|----------------|
| Canvas | `(clear)` | — | — | `(oled:clear)` |
| Canvas | `(log WORDS ...)` | One or more words, 128 characters in all | Words are strings | `(oled:log ...)`, which keeps runs of spaces |
| Canvas | `(pixel X Y)` | Integers | 0..127, 0..63 | `(oled:pixel X Y)` |
| Canvas | `(pixels X Y X Y ...)` | 2..512 integers, an even count | Every pair in range, or nothing is lit | `(oled:pixels ...)` |
| Canvas | `(line X0 Y0 X1 Y1)` | Integers | In range | — |
| Canvas | `(text X Y WORDS ...)` | Integers, then words | In range, 128 characters | `(oled:text ...)`, with an 8x8 font |
| Screen | `(mirror TOPIC SECONDS)` | A topic, then seconds | The topic is one token of at most 128 characters without `+` or `#`. Seconds 0..300. At most 4 holders | — |
| Interaction | `(applet NAME [WORDS ...] [key=value ...])` | A name, words, options | The name is in `applets`. The options are the ones the applet declares, 64 characters each | — |
| Interaction | `(key NAME [tap\|down\|up])` | `up`, `down`, `left`, `right` or one character, then a state | The state as listed. `tap` is the default. `down` holds the key for 2 s at most | — |
| Display | `(stop)`, `(exit)` | — | `exit` is an alias of `stop` | — |
| Display | `(set_log_level LEVEL)` | The framework's | | — |

**The key map on the device.** `(key NAME STATE)` has two outcomes. A
key in the display's key map runs its preset, or changes its setting, on
`tap` or `down` and does nothing on `up`. Any other key goes to the
running applet. The map is published as the share keys `keys.*`, for
example `keys.g` = `pong|asteroids|invaders|forklift` and `keys.digits` =
`speed`. Thus every client sends the same `(key K tap)`. The arrow keys
are never mapped.

**How long a key is held.** A `tap` holds a key for 0.15 s. A `down`
holds it until the `up`, but for 2 s at most (`KEY_DOWN_MAXIMUM`). Thus
a lost `up` cannot hold a key for ever (P9). A client that holds a key
for longer sends `down` again, at least once each 2 s. The Dashboard
page and the emulator window send it each second. This limit is new on
2026-09-28, and it changes the meaning of `down` for a client that sent
one `down` and waited.

**The frame mirror.** `(mirror TOPIC SECONDS)` creates or extends a leased
feed, in the vocabulary of a Stream: TOPIC names the holder and is the
destination, SECONDS is the lease, a repeat extends it, and 0 destroys
it. While a lease holds, the Actor publishes the frame to TOPIC as raw
bytes: PIL mode `1`, `size` pixels, row major, the most significant bit
first, 1024 bytes at 128x64. It publishes only when the frame changed,
at most `mirror_rate` times a second, and never while the transport is
down. A frame that arrives too soon waits as the one pending frame, so
the last frame of a burst always arrives. The holder count is `mirrors`.
The Dashboard page uses this feed for its live mirror, on its own topic.

**Argument grammar.** Every argument arrives as a string, and the Actor
validates it (P12). A client does not range-check. An integer is decimal,
with optional spaces around it. A word is one token. Quoted text is one
word: `(text 0 0 "hello world")`. Text that starts with digits and a
colon must be quoted: `(text 0 0 "12:30")`. Unquoted, it is the parser's
canonical length prefix, and the whole command is rejected. An applet
option is `key=value`, and a token without `=` is a word. The `applet`
share key takes the same arguments, separated by commas:
`(update applet draw,subject=cat)`.

**Applet names**: `status`, `log`, `help`, `pattern`, `text`, `blink`,
`demo`, `clock`, `eyes`, `pong`, `asteroids`, `invaders`, `games`,
`forklift`, `forklift_game` and `draw`. The [display](display.md) document
lists the options of each one.

**Shared state**, observed with `(share TOPIC SECONDS *)` on the control
topic, or in the Dashboard. The Actor seeds every key at start, so a
consumer's first snapshot is complete. RW keys are settings, written
with `(update KEY VALUE)` on the control topic. The settings are declared
once, in `SETTINGS_SPEC`, and the `settings` key lists them. Every value
is one token without spaces.

| Aspect | Key | Values | RW | Published when |
|--------|-----|--------|----|----------------|
| Canvas | `size`, `origin`, `depth` | `128x64`, `bottom`, `1` (bits per pixel) | R | Start |
| Canvas | `font` | `5x7`, or `6`..`64` | RW | Written |
| Canvas | `title` | Text of at most 32 characters, `_` for a space. Or `on`, `off` | RW | Written. `on` publishes the last text again |
| Canvas | `log_pending` | `on`, `off` | R | A log line arrives, or an applet shows the lines |
| Canvas | `log_count` | Integer | R | A log line is accepted |
| Screen | `backend` | `oled`, `window`, `terminal`, `png`, `none`, `fake` | R | The display is chosen |
| Screen | `device`, `panels` | `ssd1306@0x3C/i2c1`, `pygame`, `tty`, `png:NAME`, `-`, `absent` | R | The display is opened, fails, or is opened again. `panels` lists every panel from Epic 1 phase 4 |
| Screen | `contrast` | `0`..`255` | RW | Written |
| Screen | `invert`, `power`, `all_on` | `on`, `off`. Also accepted: `true`, `false`, `1`, `0`, `yes`, `no` | RW | Written |
| Screen | `blank_after` | `0`..`86400` seconds, `0` never | RW | Written |
| Screen | `foreground`, `background` | A color name that Pillow knows, or `#rrggbb`. When written, also `default`: the starting color | RW | Written |
| Screen | `fps` | Integer | R | Every 2 s |
| Screen | `mirror_rate` | `1`..`10`, frames a second to each holder at most | RW | Written |
| Screen | `mirrors` | Integer, the feed's holders (at most 4) | R | A feed is created, destroyed or expires |
| Interaction | `applets` | Comma-separated names of the applets that fit the canvas | R | Start |
| Interaction | `applet` | A name or `none`. When written, also `NAME,ARG,...` | RW | An applet starts or stops |
| Interaction | `applet_detail` | A token, or `-` | R | The applet reports |
| Interaction | `speed` | `0.1`..`10`, a decimal number | RW | Written |
| Interaction | `keys.KEY` | The applets a key steps through, joined by `\|`, or the setting it changes | R | Start |
| Display | `settings` | The RW keys, comma-separated | R | Start |
| Display | `connection` | `NONE`, `NETWORK`, `TRANSPORT`, `REGISTRAR` | R | The connection state changes |
| Display | `heartbeat` | Integer seconds since start | R | Every second |
| Display | `last_error` | `WHAT@YYYY-MM-DDTHH:MM:SSZ`, or `-` | R | A rejection or a failure |
| Display | `metrics.commands`, `metrics.rejected`, `metrics.frames`, `metrics.frame_ms`, `metrics.errors`, `metrics.mirrored` | Integers | R | Every 2 s, when changed |

### Failure behavior

- A rejected command changes nothing but `metrics.rejected` (+1) and
  `last_error`. `pixels` is all or nothing.
- A rejected setting also publishes the value still in force, so the
  shared state converges. Thus a bad Dashboard edit corrects itself.
- Delivery is at most once (P1). A client that needs to know that a
  command was applied observes the shared state.
- A display that cannot be opened, or that fails: `device` is `absent`,
  and `last_error` is `display_not_found@...` or `display_failed@...`.
  The Actor retries every 10 s, and it accepts commands meanwhile.
- An exception in an applet or a timer: `metrics.errors` +1,
  `last_error` `tick_RuntimeError@...`, and the applet stops (`applet`
  `none`). The process continues.

`last_error` is `METHOD_REASON@UTC`. The Actor also logs each rejection
as a WARNING: `NAME: METHOD rejected: REASON (DETAIL)`. The reasons:

| Method | Reasons |
|--------|---------|
| `dispatch` | `parse_error` (the payload does not parse), `unknown_command` (not a wire command, or dictionary arguments) |
| `log` | `empty`, `not_text`, `too_long` |
| `text` | `x_not_int`, `x_range`, `y_not_int`, `y_range`, then `empty`, `not_text`, `too_long` |
| `pixel`, `line` | `x_not_int`, `x_range`, `y_not_int`, `y_range` |
| `pixels` | `count` (no values, an odd count, or more than 512), `xy_not_int`, `xy_range`, `range` (a pair out of range) |
| `key` | `name`, `state` |
| `mirror` | `topic`, `seconds_not_int`, `seconds_range`, `full` (a fifth holder) |
| `set` | `applet_unknown`, `applet_too_small` (the canvas is smaller than the applet's `MIN_SIZE`), `applet_args`, `applet_failed`, `contrast_not_int`, `contrast_range`, `invert_not_on_off` (also `power`, `all_on`), `title_too_long`, `font_range`, `speed_not_number`, `speed_range`, `blank_after_not_int`, `blank_after_range`, `foreground_not_color`, `background_not_color`, `mirror_rate_not_int`, `mirror_rate_range` |
| `display` | `not_found`, `failed` |
| `tick`, `key`, `heartbeat`, `metrics`, `reopen` | The class name of the exception that a guarded timer caught, for example `tick_RuntimeError` |

## For framework developers (internals)

### Design

The dispatch handler replaces the framework's, in four steps. It parses
the payload inside a guard. It maps an `oled:` name, or `exit`, to the
method name. It checks the name against the allow-list, which is derived
from the abstract methods of the three aspects, plus `stop` and
`set_log_level`. Then it posts the message to the mailbox. Thus an
inherited public method such as `run` is not callable from the wire. The
y flip from the bottom-left wire origin to PIL's top-left rows happens in
one place, `FrameBuffer._device_y()`. The settings are one declaration,
`SETTINGS_SPEC`, in the shape of a Pipeline
[Parameters](../../concepts/parameters.md) declaration. The
[display](display.md) document gives the full design.

### Implementation notes

**Conformance trace** (`test_display.py`). Given a fresh Actor with a fake
display and no title row:

| Test | Payload on `in` | Outcome |
|------|-----------------|---------|
| `test_dispatch_aliases_allow_list_and_parse_guard` | `(oled:text 0 0 hello)` | The frame's lit rows are 56..62. `metrics.commands` 1 |
| | `(run)` | Rejected: `dispatch_unknown_command@...` |
| | `(bogus 1)` | Rejected |
| | `(log 12:30 lunch)` | Rejected: `dispatch_parse_error@...` |
| | `(text x: 1 y: 2)` | Rejected (dictionary arguments) |
| | `(add_tags t)` | Rejected. `metrics.rejected` 5 |
| `test_exit_is_stop_and_terminates` | `(exit)` | Posted as `stop`, which terminates the process |
| `test_pixel` | `(pixel 0 0)` | Device pixel (0, 63) lit |
| | `(pixel 128 0)` | Rejected: `pixel_x_range@...`, the frame unchanged |
| `test_pixels_is_atomic` | `(pixels 1 1 5 64)` | Rejected: no pixel lit |
| `test_text` | `(text 0 0 xxx...)`, 129 characters | Rejected: `text_too_long@...` |
| `test_wire_key_runs_the_map` | `(key g tap)` | `applet` `pong`: the key map ran the preset |
| | `(key g down)` | `applet` `asteroids`: the next preset |
| | `(key w tap)` with an applet running | The applet received `w` |
| `test_mirror_publishes_on_change_and_caps_rate` | `(mirror aiko/probe/mirror 30)` | `mirrors` `1`. The current frame, 1024 bytes, is published to the topic on the next tick. A changed frame within the rate waits, and the end of the burst arrives. An unchanged frame is not sent |
| `test_mirror_leases_extend_expire_and_destroy` | `(mirror T 1)` twice, then 1.4 s | `mirrors` `1`, then `0` when the lease expires. `(mirror T 0)` destroys at once |
| `test_mirror_rejections_and_bounds` | `(mirror aiko/+/mirror 30)`, `(mirror T 999)`, `(mirror T soon)`, a fifth holder | `mirror_topic@...`, `mirror_seconds_range@...`, `mirror_seconds_not_int@...`, `mirror_full@...`; `mirrors` stays `4` |
| `test_mirror_drops_frames_while_disconnected` | A feed while the transport is down | Nothing is published, nothing blocks |
| `test_settings_apply_and_bad_values_converge` | `(update contrast 64)` on `control` | `contrast` `64`, and the display's contrast set |
| | `(update contrast abc)` on `control` | `contrast` back to `64`, `last_error` `set_contrast_not_int@...` |
| `test_display_not_found_degrades_and_reopens` | A display that fails to open | `device` `absent`, `last_error` `display_not_found@...`, then the reopen succeeds |
| `test_show_failure_marks_the_display_absent` | A display that fails on `show()` | `last_error` `display_failed@...`, the Actor lives on |
| `test_failing_applet_is_stopped_not_the_process` | An applet that raises | `metrics.errors` 1, `last_error` `tick_RuntimeError@...`, `applet` `none`, the loop alive |

The Canvas rows are the conformance fixture (e_06 methodology M4) that
aiko_engine_mp must pass in Epic 2.

### CRC card

See [display](display.md).

## Current limitations and roadmap

**Compatibility with aiko_engine_mp:**

| Feature | This Actor | aiko_engine_mp |
|---------|------------|----------------|
| Protocol id | `display:0`, aspects as tags | None registered yet (Epic 2: `display:0` with `device=esp32`) |
| Commands | `clear`, `log`, `pixel`, `pixels`, `line`, `text`, `applet`, `key`, `stop` | `oled:clear`, `oled:log`, `oled:pixel`, `oled:pixels`, `oled:text` |
| Name prefix | Both `text` and `oled:text` | `oled:text` only |
| Origin | Bottom-left | Bottom-left |
| Font | 5x7 (21 characters per row), or TrueType | 8x8 (16 characters per row) |
| Runs of spaces in `log` | Collapsed by the parser | Kept |
| Panels | One per Actor (both panels as one display: Epic 1 phase 4, only on the lead's "Do it") | Two, with the text spread across them |
| Shared state | Every setting and observation above | None |
| Traits | `size`, `depth`, `backend`, `applets`, `settings`, `keys.*` in the shared state | A planned `(oled:traits)` reply |

**Only on the lead's "Do it"**: the `panels` list for two panels as one
display (phase 4). **Deferred**: the 8x8 font. **Planned convergence** (Epic 2): aiko_engine_mp registers
`display:0`, accepts both `text` and `oled:text`, and exposes `contrast`,
`invert` and `power` as shared state. Then the same clients, the same
console and the same Dashboard page drive both.

## Related concepts

- [display](display.md) — the Actor
- [testing](testing.md) — the step-by-step test guide
- [ADR-025](../../../constitution/adr/ADR-025_RemoteDisplayAbstraction.md)
  — the decisions behind the protocol
- [design](design.md) — the design record and the future directions
- [Actor](../../concepts/actor.md), [Share](../../concepts/share.md),
  [Message](../../concepts/message.md),
  [Discovery](../../concepts/discovery.md)
- [Parameters](../../concepts/parameters.md), [Stream](../../concepts/stream.md)
  — the shapes the settings and the mirror follow
- [S-expression parser](../../concepts/utilities/parser.md) — the wire
  format, quoting and the canonical length prefix
