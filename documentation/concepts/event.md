---
title: Event
description: The cooperative event loop at the heart of every Aiko Services
  process — timer, mailbox, queue and flat-out handlers all executed by a
  single event-loop thread
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/event.py
related: [design_overview, process, actor, lease, message, service,
  connection]
version: "0.6"
last_updated: 2026-07-05
---

# Event

## Overview

The **Event** module (historically titled the *Aiko Engine*) provides the
cooperative event loop that drives every Aiko Services process. All work in
a process — incoming [messages](message.md) for an [Actor](actor.md), timer
callbacks, [Lease](lease.md) expiry, stream frame processing — is delivered
as a *handler invocation* made by one event-loop thread. This is the
concurrency model of the whole framework: instead of application code
managing threads and locks, handlers are registered with the event loop and
executed serially by it.

Four kinds of handler are supported:

| Handler kind | Registered via | Invoked when |
|--------------|----------------|--------------|
| Timer | `add_timer_handler(handler, time_period)` | Every `time_period` seconds |
| Mailbox | `add_mailbox_handler(handler, name)` | An item is posted with `mailbox_put(name, item)` |
| Queue | `add_queue_handler(handler, item_types)` | An item of a matching type is posted with `queue_put(item, item_type)` |
| Flat-out | `add_flatout_handler(handler)` | Every pass of the event loop, as fast as possible |

**Why you'd use it**: run periodic work without spawning threads — for
example, a heartbeat printed once a second while a busy-loop counter runs
flat-out (this is the module's own usage example):

```python
import time
import aiko_services.main.event as event

counter = 1
def flatout_test():
    global counter
    counter += 1

def timer_test():
    print(f"timer_test(): {time.monotonic()}: {counter}")

event.add_flatout_handler(flatout_test)
event.add_timer_handler(timer_test, 1.0)
event.loop()  # blocking; returns when handlers are removed or terminate()
```

Most applications never call `event.loop()` directly —
`aiko.process.run()` calls it for you after connecting to MQTT.

## For application developers

### Command-line usage

The Event module has no CLI of its own; it is a library that every Aiko
Services process embeds. It is exercised indirectly by every tool and
example — e.g. `aiko_registrar`, `aiko_dashboard`, or
`src/aiko_services/examples/aloha_honua/aloha_honua_0.py` — all of which
end up blocked inside `event.loop()` via `aiko.process.run()`.

### Public API

The Event module is functional, not an Interface class — its public
contract is the set of module functions re-exported by
`aiko_services.main`:

```python
__all__ = [
    "add_flatout_handler", "add_mailbox_handler",
    "add_queue_handler", "add_timer_handler",
    "loop", "mailbox_put", "queue_put",
    "remove_flatout_handler", "remove_mailbox_handler",
    "remove_queue_handler", "remove_timer_handler",
    "terminate"
]
```

**Timer handlers.**

```python
event.add_timer_handler(handler, time_period, immediate=False)
event.remove_timer_handler(handler)
```

`handler()` takes no arguments and is called every `time_period` seconds
(monotonic clock). `immediate=True` is intended to fire the first
invocation straight away (see roadmap — currently suspect). A periodic
handler that should fire once simply removes itself:

```python
def once():
    event.remove_timer_handler(once)
    ...
event.add_timer_handler(once, 5.0)
```

**Mailbox handlers.** A mailbox is a named FIFO queue whose items are
consumed on the event-loop thread:

```python
event.add_mailbox_handler(mailbox_handler, mailbox_name)
event.mailbox_put(mailbox_name, item)

def mailbox_handler(mailbox_name, item, time_posted):
    ...   # time_posted is time.monotonic() at mailbox_put()
```

Adding a mailbox name that already exists raises `RuntimeError`, as does
posting to a mailbox that does not exist. The *first* mailbox added to the
process gets **priority handling**: whenever it has items pending, draining
of other mailboxes is interrupted so the priority mailbox is served first.
[Actors](actor.md) rely on this — each Actor registers one mailbox per
topic, and every incoming MQTT message is `mailbox_put()` for serial
processing on the event-loop thread.

**Queue handlers.** A single shared queue dispatches items by
`item_type` string to any handlers registered for that type:

```python
event.add_queue_handler(queue_handler, item_types=["default"])
event.queue_put(item, item_type="default")

def queue_handler(item, item_type):
    ...
```

The framework itself uses one queue handler (item type `"message"`) to
move raw MQTT messages from the transport thread onto the event loop
(see [Process](process.md)). The queue handler mechanism is slated for
removal in favour of mailboxes (see roadmap).

**Flat-out handlers.** `add_flatout_handler(handler)` registers a
zero-argument function called on every loop pass — for polling-style work
such as reading frames from a device.

**Running and stopping the loop.**

```python
event.loop(loop_when_no_handlers=False)  # blocking
event.terminate()                        # stop the loop from any thread
```

`loop()` returns when `terminate()` is called or — unless
`loop_when_no_handlers=True` — when the count of registered handlers drops
to zero. Calling `loop()` while a loop is already running returns
immediately (a lock-guarded `event_loop_running` flag ensures a single
loop per process). `KeyboardInterrupt` raises
`SystemExit("KeyboardInterrupt: abort !")`.

## For framework developers (internals)

### Design

```
   other threads (MQTT transport, application)
        │ mailbox_put() / queue_put() / add_*_handler()
        ▼
   ┌───────────────────────────────────────────────┐
   │ event loop (single thread)                    │
   │                                               │
   │  EventList (sorted linked list of timers)     │
   │      head ─► Event(t+0.8) ─► Event(t+1.0) …   │
   │  mailboxes (OrderedDict; first = priority)    │
   │  event_queue + queue_handlers (by item_type)  │
   │  flatout_handlers (list)                      │
   │                                               │
   │  while enabled and handlers exist:            │
   │    fire due timer  ─► handle one queue item   │
   │    ─► drain mailboxes (priority first)        │
   │    ─► run flat-out handlers ─► sleep ≤ 10 ms  │
   └───────────────────────────────────────────────┘
```

Key design points:

- **Single-threaded execution of handlers** is the framework's core
  concurrency rule: shared state is safe to mutate inside handlers because
  only the event-loop thread runs them. Producers on other threads hand
  work over via thread-safe `queue.Queue` instances inside `mailbox_put()`
  and `queue_put()`.
- **Timers** live in `EventList`, a singly linked list kept sorted by
  `time_next`; only the head is ever due. After firing, `update()`
  re-schedules the head by adding its period and re-inserts it in order.
  `_timer_counter` caches the time until the head is due, so idle passes
  avoid re-reading the list.
- **Loop cadence**: each pass sleeps up to 10 ms (`sleep_time = 0.01`),
  minus time consumed by flat-out handlers — so timers have roughly 10 ms
  resolution and flat-out handlers run at up to ~100 Hz. (A stale source
  comment mentions 1 ms / 1,000 Hz.)
- **One queue item per pass** is processed, while mailboxes are drained
  completely (subject to priority-mailbox pre-emption) — mailboxes are the
  favoured mechanism.
- **Mailbox monitoring**: each `Mailbox` tracks `size` and
  `high_water_mark`, and computes a warning each time the backlog grows by
  `increment_warning` (default 4) — the warning `print()` is currently
  commented out.

### Implementation notes

- `loop()` calls `event_list.reset()` on entry, rebasing every timer's
  `time_next` to *now + period* — timers added before the loop starts do
  not fire "in the past".
- `_handler_count` is a plain module-level integer incremented and
  decremented by every add/remove function; the loop exits when it reaches
  zero. It is **not** thread-safe (acknowledged bug).
- `EventList.remove(handler)` matches by handler identity — two timers
  registered with the *same* function are indistinguishable, and removal
  may take the wrong one (acknowledged bug). Use distinct bound methods
  (as `Lease` does) to stay safe.
- `terminate()` merely clears `event_enabled`; the loop notices on its
  next pass. Calling `terminate()` *before* `loop()` starts is lost,
  because `loop()` sets `event_enabled = True` on entry (acknowledged
  bug).
- The module's own usage header shows `import aiko_services.event` — the
  current import path is `aiko_services.main.event` (re-exported through
  `aiko_services.main`).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Event` | One scheduled timer: handler, period, next fire time; linked-list node | `EventList` |
| `EventList` | Keep timers sorted by due time; add, remove, reset, re-schedule head | `Event`; module `loop()` |
| `Mailbox` | Named FIFO with size / high-water-mark tracking and backlog warning | `queue.Queue`; module `loop()` |
| module functions (`loop`, `add_*` / `remove_*`, `*_put`, `terminate`) | Registry of all handler kinds; run the single event-loop thread; dispatch timers, queue items, mailboxes and flat-out handlers in order | [Actor](actor.md) (mailboxes), [Lease](lease.md) (timers), Process (`run()` / queue `"message"`), `Lock` (loop-running guard) |

## Current limitations and roadmap

From the source `To Do` list — highlights:

- Remove the queue handler mechanism, replacing usage with mailboxes; more
  generally, allow any object to be queued with a specified handler
- Ensure *all* shared-data updates occur via events executed solely by the
  event-loop thread (a rule the rest of the framework is converging on)
- Known bugs: `remove_timer_handler()` may remove the wrong timer when one
  function backs several timers (needs per-timer identifiers);
  `terminate()` before `loop()` is silently lost; `_handler_count` is not
  thread-safe; `immediate=True` timers do not fire immediately
- `add_timer_handler(..., count=N)` auto-expiry and
  `add_mailbox_handler(..., max_size=N)` bounded mailboxes
- Refactor remaining module functions into an `EventEngine` class; move
  `_timer_counter` into `EventList`; coalesce the `remove_*_handler()`
  variants; possibly rename `event.py` to `handler.py`
- Check timers between every mailbox delivery; make the flat-out cadence
  configurable; wall-clock monitoring of handler invocation time
- New event types: GStreamer appsink / appsrc, serial
- No unit tests yet for the add/remove of the various handler types

## Related concepts

- [Design overview](design_overview.md)
- [Process](process.md) — calls `event.loop()` in `run()` and feeds the
  `"message"` queue from the MQTT thread
- [Actor](actor.md) — delivers every incoming message through an event
  mailbox
- [Lease](lease.md) — time-limited claims built on timer handlers
- [Message](message.md) / [Transport](transport.md) — the MQTT thread that
  feeds the event loop from outside
- [Connection](connection.md) — shares the "updates via events only"
  roadmap direction
