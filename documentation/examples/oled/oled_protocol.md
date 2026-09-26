---
title: OLED protocol oled:0
description: The wire protocol of the OLED display Actor — the protocol id
  and discovery, the topics, the one-way commands and their argument
  grammar, the shared state keys and their values, the rejection reasons,
  the conformance trace, and compatibility with the MicroPython
  aiko_engine_mp OLED
type: concept
audience: [developers, ai-coding-agents]
status: draft
ste: adapted
source:
  - src/aiko_services/examples/oled/oled.py
  - src/aiko_services/tests/unit/test_oled.py
related: [oled, testing, actor, share, message, discovery]
version: "0.8-dev"
last_updated: 2026-09-26
---

# OLED protocol oled:0

## Overview

This is the specification unit for the OLED Actor: what a client may
send, what it observes, and what happens when something is wrong. The
Python Actor implements all of it. The MicroPython aiko_engine_mp OLED
implements the compatible subset, marked in the tables below. The
[oled](oled.md) document explains the Actor, and the
[test guide](testing.md) exercises every rule on this page.

## For application developers

### Command-line usage

`aiko_oled` wraps the protocol. `aiko_oled text 0 0 hello` sends
`(text 0 0 hello)` on the `in` topic. `aiko_oled set contrast 64` sends
`(update contrast 64)` on the control topic. `aiko_oled --help` lists
every wire command. Without the command line:

```bash
mosquitto_pub -t $TOPIC_PATH/in -m "(oled:text 0 0 hello)"
mosquitto_pub -t $TOPIC_PATH/control -m "(update contrast 64)"
```

### Public API

**Protocol id:** `github.com/geekscape/aiko_services/protocol/oled:0`,
version 0. Within a major version, only methods are added. A client
discovers the Actor with a ServiceFilter on this protocol and the
Actor's name, which is the hostname by default:

```python
aiko.ServiceFilter("*", "w3029f1", PROTOCOL, "*", "*", "*")
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

| Command | Arguments | Validation | aiko_engine_mp |
|---------|-----------|------------|----------------|
| `(clear)` | — | — | `(oled:clear)` |
| `(log WORDS ...)` | One or more words, 128 characters in all | Words are strings | `(oled:log ...)`, which keeps runs of spaces |
| `(pixel X Y)` | Integers | 0..127, 0..63 | `(oled:pixel X Y)` |
| `(pixels X Y X Y ...)` | 2..512 integers, an even count | Every pair in range, or nothing is lit | `(oled:pixels ...)` |
| `(line X0 Y0 X1 Y1)` | Integers | In range | — |
| `(text X Y WORDS ...)` | Integers, then words | In range, 128 characters | `(oled:text ...)`, with an 8x8 font |
| `(exit)` | — | — | — |
| `(applet NAME [WORDS ...] [key=value ...])` | A name, words, options | The name is in `applets`. The options are the ones the applet declares, 64 characters each | — |
| `(key NAME [tap\|down\|up])` | `up`, `down`, `left`, `right` or one character, then a state | The state as listed. `tap` is the default | — |
| `(stop)`, `(set_log_level LEVEL)` | The framework's | | — |

**Argument grammar.** Every argument arrives as a string, and the Actor
validates it (P12). An integer is decimal, with optional spaces around
it. A word is one token. Quoted text is one word:
`(text 0 0 "hello world")`. Text that starts with digits and a colon
must be quoted: `(text 0 0 "12:30")`. Unquoted, it is the parser's
canonical length prefix, and the whole command is rejected. An applet
option is `key=value`, and a token without `=` is a word. The `applet`
share key takes the same arguments, separated by commas:
`(update applet draw,subject=cat)`.

**Applet names**: `status`, `log`, `help`, `pattern`, `text`, `blink`,
`demo`, `clock`, `eyes`, `pong`, `asteroids`, `invaders`, `games`,
`forklift`, `forklift_game` and `draw`. The [oled](oled.md) document
lists the options of each one.

**Shared state**, observed with `(share TOPIC SECONDS *)` on the control
topic, or in the Dashboard. The Actor seeds every key at start, so a
consumer's first snapshot is complete. RW keys are settings, written
with `(update KEY VALUE)` on the control topic. Every value is one token
without spaces.

| Key | Values | RW | Published when |
|-----|--------|----|----------------|
| `backend` | `oled`, `window`, `terminal`, `png`, `none`, `fake` | R | The display is chosen |
| `device` | `ssd1306@0x3C/i2c1`, `pygame`, `tty`, `png:NAME`, `-`, `absent` | R | The display is opened, fails, or is opened again |
| `size`, `origin` | `128x64`, `bottom` | R | Start |
| `connection` | `NONE`, `NETWORK`, `TRANSPORT`, `REGISTRAR` | R | The connection state changes |
| `applets` | Comma-separated names | R | Start |
| `applet` | A name or `none`. When written, also `NAME,ARG,...` | RW | An applet starts or stops |
| `applet_detail` | A token, or `-` | R | The applet reports |
| `fps` | Integer | R | Every 2 s |
| `speed` | `0.1`..`10`, a decimal number | RW | Written |
| `font` | `5x7`, or `6`..`64` | RW | Written |
| `contrast` | `0`..`255` | RW | Written |
| `invert`, `power`, `all_on` | `on`, `off`. Also accepted: `true`, `false`, `1`, `0`, `yes`, `no` | RW | Written |
| `title` | Text of at most 32 characters, `_` for a space. Or `on`, `off` | RW | Written. `on` publishes the last text again |
| `blank_after` | `0`..`86400` seconds, `0` never | RW | Written |
| `foreground`, `background` | A color name that Pillow knows, or `#rrggbb`. When written, also `default`: the starting color | RW | Written |
| `log_pending` | `on`, `off` | R | A log line arrives, or an applet shows the lines |
| `log_count` | Integer | R | A log line is accepted |
| `heartbeat` | Integer seconds since start | R | Every second |
| `last_error` | `WHAT@YYYY-MM-DDTHH:MM:SSZ`, or `-` | R | A rejection or a failure |
| `metrics.commands`, `metrics.rejected`, `metrics.frames`, `metrics.frame_ms`, `metrics.errors` | Integers | R | Every 2 s, when changed |

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
| `set` | `applet_unknown`, `applet_args`, `applet_failed`, `contrast_not_int`, `contrast_range`, `invert_not_on_off` (also `power`, `all_on`), `title_too_long`, `font_range`, `speed_not_number`, `speed_range`, `blank_after_not_int`, `blank_after_range`, `foreground_not_color`, `background_not_color` |
| `display` | `not_found`, `failed` |
| `tick`, `key`, `heartbeat`, `metrics`, `reopen` | The class name of the exception that a guarded timer caught, for example `tick_RuntimeError` |

## For framework developers (internals)

### Design

The dispatch handler replaces the framework's, in four steps. It parses
the payload inside a guard. It maps an `oled:` name to the method name.
It checks the name against the allow-list. Then it posts the message to
the mailbox.
The allow-list is the set of abstract methods of the two Interfaces plus
`stop` and `set_log_level`. Thus an inherited public method such as
`run` is not callable from the wire. The y flip from the bottom-left
wire origin to PIL's top-left rows happens in one place,
`Canvas._device_y()`. The [oled](oled.md) document gives the full
design.

### Implementation notes

**Conformance trace** (`test_oled.py`). Given a fresh Actor with a fake
display and no title row:

| Test | Payload on `in` | Outcome |
|------|-----------------|---------|
| `test_dispatch_aliases_allow_list_and_parse_guard` | `(oled:text 0 0 hello)` | The frame's lit rows are 56..62. `metrics.commands` 1 |
| | `(run)` | Rejected: `dispatch_unknown_command@...` |
| | `(bogus 1)` | Rejected |
| | `(log 12:30 lunch)` | Rejected: `dispatch_parse_error@...` |
| | `(text x: 1 y: 2)` | Rejected (dictionary arguments) |
| | `(add_tags t)` | Rejected. `metrics.rejected` 5 |
| `test_pixel` | `(pixel 0 0)` | Device pixel (0, 63) lit |
| | `(pixel 128 0)` | Rejected: `pixel_x_range@...`, the frame unchanged |
| `test_pixels_is_atomic` | `(pixels 1 1 5 64)` | Rejected: no pixel lit |
| `test_text` | `(text 0 0 xxx...)`, 129 characters | Rejected: `text_too_long@...` |
| `test_settings_apply_and_bad_values_converge` | `(update contrast 64)` on `control` | `contrast` `64`, and the display's contrast set |
| | `(update contrast abc)` on `control` | `contrast` back to `64`, `last_error` `set_contrast_not_int@...` |
| `test_display_not_found_degrades_and_reopens` | A display that fails to open | `device` `absent`, `last_error` `display_not_found@...`, then the reopen succeeds |
| `test_show_failure_marks_the_display_absent` | A display that fails on `show()` | `last_error` `display_failed@...`, the Actor lives on |
| `test_failing_applet_is_stopped_not_the_process` | An applet that raises | `metrics.errors` 1, `last_error` `tick_RuntimeError@...`, `applet` `none`, the loop alive |

### CRC card

See [oled](oled.md).

## Current limitations and roadmap

**Compatibility with aiko_engine_mp:**

| Feature | This Actor | aiko_engine_mp |
|---------|------------|----------------|
| Commands | `clear`, `log`, `pixel`, `pixels`, `line`, `text`, `exit`, `applet`, `key` | `oled:clear`, `oled:log`, `oled:pixel`, `oled:pixels`, `oled:text` |
| Name prefix | Both `text` and `oled:text` | `oled:text` only |
| Origin | Bottom-left | Bottom-left |
| Font | 5x7 (21 characters per row), or TrueType | 8x8 (16 characters per row) |
| Runs of spaces in `log` | Collapsed by the parser | Kept |
| Panels | One per Actor | Two, with the text spread across them |
| Shared state | Every setting and observation above | None |
| Traits | `size`, `backend` and `applets` in the shared state | A planned `(oled:traits)` reply |

**Planned convergence** (Epic 1): aiko_engine_mp could register protocol
`oled:0`, accept both `text` and `oled:text`, and expose `contrast`,
`invert` and `power` as shared state. Then the same clients, the same
console and the same Dashboard page drive both.

## Related concepts

- [oled](oled.md) — the Actor
- [testing](testing.md) — the step-by-step test guide
- [Actor](../../concepts/actor.md), [Share](../../concepts/share.md),
  [Message](../../concepts/message.md),
  [Discovery](../../concepts/discovery.md)
- [S-expression parser](../../concepts/utilities/parser.md) — the wire
  format, quoting and the canonical length prefix
