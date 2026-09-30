---
title: "ADR-025 — Remote display abstraction: the display:0 composite, aspect tags, the key map on the device, a bounded in-band mirror"
description: Splits the OLED example's protocol into three aspect Interfaces
  composed as display:0, advertises the aspects as Service tags until the
  Registrar matches several protocols, puts the key map on the device so that
  every client sends the same key, declares the settings as one
  Parameters-shaped table, and admits a bounded leased binary frame mirror as
  a documented CP-F gray area
type: adr
audience: [project-lead, architects, developers, ai-coding-agents]
status: proposal
ste: adapted
related: [ReadMe, ADR-022_CompositionBoundary, ADR-023_GuardedEvalDefaultDeny,
  ../p_00_DesignPrinciples, ../p_02_CandidatePrinciples,
  ../s_02_InterfaceComposition]
last_updated: 2026-09-27
---

# ADR-025 — Remote display abstraction: the `display:0` composite, aspect tags, the key map on the device, a bounded in-band mirror

**Proposed 2026-09-27** by the display work's Epic 1, whose plan the technical lead approved
on 2026-09-27. The number is claimed in this move. The reference implementation is
`src/aiko_services/actors/display/`, which ships in the wheel since Epic 1 phase 9
(2026-09-27). Before phase 9 it was the OLED example. The technical lead reclassified it as
a major Interface design and evaluation. An example teaches one concept. This work carries
a protocol, a plug-in pattern and a client design. A simple OLED example
follows in `examples/oled/`, as the protocol's second implementation.

## Context

The OLED example (then `src/aiko_services/examples/oled/`, now
`src/aiko_services/actors/display/`) delivered one Actor with one protocol id, `oled:0`, in
Epic 0. That Actor mixes three concerns. It draws on a canvas (`clear log pixel
pixels line text`). It controls the screen through settings in the shared state (`contrast
invert power all_on title font speed blank_after foreground background`). And it controls what
runs on the display (`applet`, `key`). The key map in `keys.py` ran on the client side, in
the keys console and in the emulator window.

Four facts shaped the abstraction. The same Actor shape fits other framebuffer devices: an
e-ink panel, a LED matrix, an HDMI framebuffer, a virtual window on a desktop, and later an
ESP32 OLED under `aiko_engine_mp`. The Registrar matches one protocol string per Service, and
"interface matching" is only on its To Do list. Candidate principle CP-F (in-band control,
out-of-band bulk) forbids media streams over MQTT and encoded bulk data inside S-expressions.
And the project intends to extract Parameters and Streams from `pipeline.py` and to compose
them with Actor. Thus a display's settings and its frame feed should already have that shape.

The Dashboard plug-in (Epic 1, SG0) needs a live view of the panel. Nothing was published on
the `out` topic, and a frame is bulk data in CP-F's terms, so the feed needed a decision.

## Decision

1. **Three aspect Interfaces, one composite protocol.** `Canvas` (drawing: six one-way
   methods), `Screen` (the screen: its settings in the shared state, and the mirror) and
   `Interaction` (what runs on the display: `applet`, `key`) are Interfaces. Their contract ids
   are `canvas:0`, `screen:0` and `interaction:0`. `Display(Actor, Canvas, Screen, Interaction)`
   has no methods of its own and registers the protocol
   `github.com/geekscape/aiko_services/protocol/display:0`. `oled:0` is withdrawn before any
   release, and every `oled:` alias and wire form stays. `exit` leaves the Interfaces: `(exit)`
   is an alias of the framework's `(stop)`. The allow-list of ADR-023 derives from the aspects'
   abstract methods only, never from the framework's Actor and Service methods.
2. **Aspects are advertised as tags.** The Actor registers with the tags `device=<backend>
   canvas=0 screen=0 interaction=0 ec=true`, derived from the aspects' contract ids. A client
   filters on a tag, for example `canvas=0`. When the Registrar matches several protocols per
   Service, the tags become protocol ids with no wire change. The plain names are chosen. A
   prefixed form (`aspect_canvas=0`) was considered and rejected as noise, because a user tag
   has no reason to take an aspect's name.
3. **The key map lives on the device.** `Interaction.key()` is defined as: a key in the
   display's key map runs its preset, or changes its setting, on `tap` or `down`. Any other
   key goes to the running applet. The map is published as the share keys `keys.*`. Thus
   every client sends the same `(key K tap)`: the console, the emulator window, the Dashboard
   plug-in and `aiko_display key`. A mapped letter cannot reach a running applet, which was the
   emulator window's rule already. A foreign device ships its own map and legend, and the
   same clients drive it.
4. **Capabilities are traits in the share (P3).** `size`, `origin`, `depth`, `panels`,
   `backend`, `applets`, `settings` and `keys.*` tell a client what the display is, so a
   client adapts without code. The Actor validates every value (P12), and a client does not
   range-check locally.
5. **The settings are one declaration.** `SETTINGS_SPEC` declares each setting once: name,
   kind, default, range and description. The `settings` share key, the setters, the
   rejection reasons, the help texts and the tests derive from it. This is the shape of a
   Pipeline Parameters declaration, and it fills the gap that the Parameters roadmap names: no
   declaration of accepted names and no validation. When Parameters compose with Actor,
   `SETTINGS_SPEC` becomes a Parameters declaration and `(update KEY VALUE)` stays the wire.
6. **A bounded in-band mirror is admitted for the example.** `(mirror TOPIC SECONDS)` on the
   `Screen` aspect creates or extends a leased frame feed, in the vocabulary of a Stream.
   While a lease holds, the Actor publishes the frame as raw bytes to the holder's topic. It
   publishes only when the frame changed, at most `mirror_rate` times a second (1 to 10,
   default 5), and to at most four holders. `(mirror TOPIC 0)` destroys the feed, and an
   expired lease stops it. A frame is
   fixed and small: 1024 bytes at 128x64, 2048 at 256x64. The worst case is 40 KB/s for four
   holders of a game. Nothing is encoded inside an S-expression. This is a gray area under
   CP-F, admitted because the feed is bounded, opt-in, leased and the panel's own state, not
   media. A media stream, or a larger display, must go out-of-band. If CP-F is adopted with a
   ruling against this feed, the plug-in runs without the mirror region.

## Consequences

- One shipped package shows the framework's composition rule at Interface level (P7): a
  capability is an aspect, and a device is a composite.
- Names: the protocol id is lower case (`display:0`) and the Interface is a Python class,
  upper case (`Display`). The Actor is "the Display Actor" (project-lead direction,
  2026-09-27). The `Output` seam of the example composes in
  the same Epic (ADR-022 decision 1: a test double and alternative backends must compose).
- The compatibility of four clients rests on one wire vocabulary and one key map, and parity
  tests keep them equal. A Dashboard page of a foreign display needs no code change.
- The applet Host contract is shaped for a later step: applets, and other UI/UX, defined
  purely in S-expressions and run by the sandboxed evaluator of ADR-023. Every Host call takes
  S-expression-representable arguments, and no Host method returns a Python object.
- Events on the `out` topic (`(applet NAME started)`, `(rejected METHOD REASON)`) are a
  recorded candidate for a later Epic. State stays in the share (P3). The frame feed is not
  an `out` event, because `out` is a text topic.
- Evidence trail:
  - Principles P1, P3, P5, P7, P9, P10 and P12. Candidates CP-F, CP-G and CP-I.
  - ADR-022 decision 1 and ADR-023 decision 2. s_02 §4, additive evolution.
  - The extraction intent in the Parameters and Stream concept documents.
  - The Epic 1 plan of 2026-09-27 and the technical lead's decisions of the same day.

## Alternatives rejected

- **Keep `oled:0` and add the aspect tags.** Less change, but the discovery id would name a
  device family, and every family would need its own client filter and plug-in key.
- **Base64 frames inside S-expressions on `out`.** One publish would serve every watcher, but
  CP-F forbids the encoding, and a text topic is the wrong plane for bulk bytes.
- **No mirror.** The page would show state and keys only. Kept as the fallback if CP-F rules
  against the feed.
- **The key map on every client.** The console and the window already ran it twice, and a
  third client would make three copies to keep equal.
