---
title: OLED protocol oled:0
description: The wire protocol of the OLED display Actor — protocol id,
  one-way commands, shared state keys, failure behavior, the conformance
  trace, and compatibility with the MicroPython aiko_engine_mp OLED
type: concept
audience: [developers, ai-coding-agents]
status: draft
ste: false
source:
  - src/aiko_services/examples/oled/oled.py
  - src/aiko_services/tests/unit/test_oled.py
related: [oled, actor, share, message]
version: "0.8-dev"
last_updated: 2026-09-26
---

# OLED protocol oled:0

## Overview

This is the specification unit for the OLED Actor: what a client may send,
what it observes, and what happens when something is wrong.  The Python
Actor implements it; the MicroPython aiko_engine_mp OLED implements the
compatible subset marked below.

## For application developers

### Command-line usage

See [oled](oled.md).  `aiko_oled text 0 0 hello` sends `(text 0 0 hello)`;
`aiko_oled set contrast 64` sends `(update contrast 64)` on the control
topic.

### Public API

**Protocol id:** `github.com/geekscape/aiko_services/protocol/oled:0`.
Version 0.  Within a major version only methods are added.

**Commands** on the Actor's `in` topic.  All are one-way (P1): nothing is
returned and nothing is raised across the wire.  Coordinates: x 0..127
left to right, y 0..63 bottom to top; a text cell's bottom-left is at
(X, Y), so `(text 0 0 hi)` is the bottom row and `(text 0 8 hi)` the row
above with the 5x7 font.

| Command | Arguments | Validation | aiko_engine_mp |
|---------|-----------|------------|----------------|
| `(clear)` | — | — | `(oled:clear)` |
| `(log WORDS ...)` | one or more words, 128 characters | words are strings | `(oled:log ...)`, keeps runs of spaces |
| `(pixel X Y)` | integers | 0..127, 0..63 | `(oled:pixel X Y)` |
| `(pixels X Y X Y ...)` | 2..512 integers, even count | every pair in range, or nothing is lit | `(oled:pixels ...)` |
| `(line X0 Y0 X1 Y1)` | integers | in range | — |
| `(text X Y WORDS ...)` | integers, words | in range; 128 characters | `(oled:text ...)`, 8x8 font |
| `(exit)` | — | — | — |
| `(applet NAME [WORDS ...] [key=value ...])` | name, words, options | name in `applets` (status, help, pattern, text, blink, demo, pong, asteroids, invaders, games, forklift, forklift_game, draw); options as the applet declares; 64 characters each | — |
| `(key NAME [tap\|down\|up])` | `up`, `down`, `left`, `right` or one character | state as listed | — |
| `(stop)`, `(set_log_level LEVEL)` | framework | | — |

Quoted text is one word: `(text 0 0 "hello world")`.  Text starting with
digits and a colon must be quoted: `(text 0 0 "12:30")`; unquoted it is
the parser's canonical form and the command is rejected.

**Shared state** (observed with `(share ...)` on the control topic, or in
the Dashboard): the keys and values listed in [oled](oled.md).  Settings
are written with `(update KEY VALUE)` on the control topic: `applet`,
`contrast`, `invert`, `power`, `all_on`, `title`, `font`, `speed`,
`blank_after`.  Values are single tokens.

### Failure behavior

- A rejected command changes nothing but `metrics.rejected` (+1) and
  `last_error` (`METHOD_REASON@UTC`, e.g. `pixel_x_range@...`,
  `text_too_long@...`, `dispatch_unknown_command@...`,
  `dispatch_parse_error@...`).  `pixels` is all or nothing.
- A rejected setting also publishes the value still in force
  (`last_error` `set_contrast_not_int@...`), so the shared state converges.
- Delivery is at most once (P1): a client that needs to know a command
  was applied observes the shared state.
- A display that can't be opened or that fails: `device` is `absent`,
  `last_error` is `display_not_found@...` or `display_failed@...`, the
  Actor retries every 10 s and keeps accepting commands meanwhile.
- An exception in an applet or a timer: `metrics.errors` +1,
  `last_error` `tick_RuntimeError@...`, the applet is stopped
  (`applet` `none`); the process continues.

## For framework developers (internals)

### Design

See [oled](oled.md).  The `oled:` names are aliases of the same methods,
resolved in the Actor's dispatch handler; the y flip happens in one place.

### Implementation notes

**Conformance trace** (`test_oled.py`,
`test_dispatch_aliases_allow_list_and_parse_guard` and the wire command
tests).  Given a fresh Actor with a fake display and no title:

| Payload on `in` | Outcome |
|-----------------|---------|
| `(oled:text 0 0 hello)` | the frame's lit rows are 56..62; `metrics.commands` 1 |
| `(run)` | rejected: `dispatch_unknown_command@...` |
| `(bogus 1)` | rejected |
| `(log 12:30 lunch)` | rejected: `dispatch_parse_error@...` |
| `(text x: 1 y: 2)` | rejected (dictionary arguments) |
| `(add_tags t)` | rejected; `metrics.rejected` 5 |
| `(pixel 0 0)` | device pixel (0, 63) lit |
| `(pixel 128 0)` | rejected: `pixel_x_range@...`, frame unchanged |
| `(pixels 1 1 5 64)` | rejected: no pixel lit |
| `(update contrast 64)` on `control` | `contrast` `64`, the display's contrast set |
| `(update contrast abc)` on `control` | `contrast` back to `64`, `last_error` `set_contrast_not_int@...` |

### CRC card

See [oled](oled.md).

## Current limitations and roadmap

- aiko_engine_mp differences: its font is 8x8 (16 characters per row, here
  21 with the 5x7 font); it keeps runs of spaces in `oled:log`; it spreads
  text across two panels; it has no `line`, `exit`, `applet` or `key`,
  and no shared state.  Its planned `(oled:traits)` reply is not needed
  here: `size`, `backend` and `applets` in the shared state are the
  traits.
- Convergence: aiko_engine_mp could register protocol `oled:0`, accept
  both `text` and `oled:text`, and expose `contrast`, `invert` and `power`
  as shared state, so that the same clients and Dashboard page drive
  both.

## Related concepts

- [oled](oled.md): the Actor
- [Actor](../../concepts/actor.md), [Share](../../concepts/share.md),
  [Message](../../concepts/message.md)
