---
title: Dashboard plug-in
description: How to extend the Aiko Services Dashboard with a custom page
  (ServiceFrame) shown for Services of a given name or protocol
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/dashboard_plugins.py
  - src/aiko_services/main/dashboard.py
related: [design_overview, dashboard, service, share, registrar]
version: "0.6"
last_updated: 2026-07-05
---

# Dashboard plug-in

## Overview

A **Dashboard plug-in** adds a custom page to the Aiko Services
[Dashboard](dashboard.md) for a particular kind of
[Service](service.md). When the user selects a Service and presses `S`
("Show Service page"), the Dashboard looks up the Service's *name* and
*protocol* in its plug-in registry and switches to the matching page; if
neither matches, a "Does not have a custom page" pop-up appears.

A plug-in is simply a Python module with a `plugins` dictionary mapping a
Service name or protocol to a subclass of `aiko.ServiceFrame`. The
built-in module `aiko_services.main.dashboard_plugins` provides one
example — `RegistrarFrame`, a page for the
[Registrar](registrar.md) that lists all discovered Service topic paths
above a live log tail.

**Why you'd use it**: your Actor has domain state that deserves a richer
view than the generic variables table — for example a Pipeline's frame
metrics, an MQTT broker's statistics, or a REPL. Ship a page with your
application and load it at start-up:

```bash
aiko_dashboard --plugin my_application.dashboard_pages
# select your Service, press "S" --> your custom page
# press "D" --> back to the Dashboard
```

## For application developers

### Command-line usage

Plug-ins have no CLI of their own; they are loaded by `aiko_dashboard`:

```bash
aiko_dashboard [--plugin MODULE]...   # -p MODULE, may be repeated
```

- The default is the single module `aiko_services.main.dashboard_plugins`
  (which registers the `registrar` page). Supplying any `--plugin` option
  *replaces* that default — list the built-in module explicitly if you
  want to keep the Registrar page alongside your own.
- A module name that cannot be imported is silently ignored
  (`ModuleNotFoundError` is caught and no plug-ins are added).
- Modules are loaded with `load_module()`, so a Python module path
  (`package.module`) is expected.

### Public API

A plug-in module provides two things — one or more `ServiceFrame`
subclasses, and a module-level `plugins` dictionary:

```python
# plugin key can be either the Service "name" or "protocol"

plugins = {
    "registrar": RegistrarFrame
}
```

The key is matched (in `DashboardFrame._raise_next_scene()`) against the
selected Service's name first, then against its protocol *short name* —
the last path component with the version stripped, so protocol
`…/registrar:0` matches the key `registrar`. The key also becomes the
`asciimatics` scene name, so the keys `Dashboard` and `Log` are reserved
by the built-in pages (a plug-in using them would replace those pages).

The frame contract, from the exported base class:

```python
class ServiceFrame(FrameCommon, asciimatics_Frame):
    def __init__(self, screen, dashboard, name="service_frame"): ...
    def _service_frame_start(self, service, service_ec_consumer): ...
    def _service_frame_stop(self, service): ...
```

| Member | Responsibility |
|--------|----------------|
| `__init__(screen, dashboard)` | Build widgets and layouts; **must end with `self.fix()`** to prepare the `asciimatics` Frame |
| `_service_frame_start(service, service_ec_consumer)` | Called when the page becomes active for a newly selected Service; `service` is the record tuple `(topic_path, name, protocol, transport, owner, tags)` and `service_ec_consumer` is the Dashboard's live `ECConsumer` (or `None` if the Service does not share state) |
| `_service_frame_stop(service)` | Called when the user presses `D` to return to the Dashboard — release everything acquired in start |
| `_update(frame_no)` | Optional override to re-render at the frame rate (call `super()._update(frame_no)` first) |
| `process_event(event)` | Optional override for extra keyboard commands |

Two rules from the source worth quoting:

- "Plugins that add handlers to the ec_consumer must also remove them !"
  — anything registered in `_service_frame_start()` must be unregistered
  in `_service_frame_stop()`.
- The base class draws a title bar and a Service bar
  (`Service: TOPIC_PATH: NAME`) for you, and already handles `?` (help),
  `D` (back to Dashboard) and `x` (exit).

The reusable `LogUI` class provides a ready-made log-tail section
(subscribe to the Service's log topic, 128-record ring buffer,
follow-latest scrolling) — embed it as `RegistrarFrame` does:

```python
from asciimatics.widgets import Layout, MultiColumnListBox

import aiko_services as aiko  # designed to be external to the main framework

class RegistrarFrame(aiko.ServiceFrame):
    def __init__(self, screen, dashboard):
        super(RegistrarFrame, self).__init__(
            screen, dashboard, name="registrar_frame")

        self.services_cache = aiko.services_cache_create_singleton(
            aiko.process, True, history_limit=screen.height)

        self._registrar_widget = MultiColumnListBox(
            screen.height * 1 // 2, ["<0"], options=[],
            titles=["Registrar: Discovered Services topic paths"]
        )
        layout_0 = Layout([1])
        self.add_layout(layout_0)
        layout_0.add_widget(self._registrar_widget)
        self.log_ui = aiko.LogUI(self)
        self.fix()  # Prepare asciimatics_Frame for use

    def _service_frame_start(self, service, service_ec_consumer):
        self.log_ui._service_frame_start(service, service_ec_consumer)

    def _service_frame_stop(self, service):
        self.log_ui._service_frame_stop(service)
```

(`RegistrarFrame._update()` then repopulates the widget from the
`ServicesCache` and calls `self.log_ui._update(frame_no)`.)

There is no wire protocol specific to plug-ins — pages speak the same
[Share](share.md) and log-topic protocols as the Dashboard itself.

## For framework developers (internals)

### Design

```
aiko_dashboard --plugin my_module
        │
        ▼ main(): load_module() per --plugin
update_plugins(module.plugins)
        │
        ▼         _PLUGINS (ordered dict)
   ┌─────────────────────────────────────────┐
   │ "Dashboard" ─► DashboardFrame (built-in)│
   │ "Log"       ─► LogFrame       (built-in)│
   │ "registrar" ─► RegistrarFrame (plug-in) │
   └─────────────────────────────────────────┘
        │ run_dashboard(): one Scene per entry
        ▼
   "S" key: _raise_next_scene(service)
     match service name, then protocol short
     name, against _PLUGINS keys ─► NextScene
```

Key design points:

- `update_plugins()` seeds `_PLUGINS` with the two built-in pages on
  first call, then merges each plug-in module's `plugins` dict —
  later modules can override earlier keys.
- `run_dashboard()` constructs one Scene per `_PLUGINS` entry, in
  insertion order. The `Dashboard` entry is first, and after its Scene is
  created the `DashboardFrame` singleton exists — every subsequent
  (plug-in) frame receives it as the `dashboard` constructor argument.
- Selection state stays in the singleton: a `ServiceFrame` notices a new
  selection by comparing `dashboard.selected_service` with
  `dashboard.subscribed_service` inside `_update()`, then fires
  `_service_frame_start()`. Pressing `D` clears `subscribed_service` and
  fires `_service_frame_stop()`.

### Implementation notes

- Plug-in frames are constructed once at start-up (and again after a
  terminal resize), not per selection — treat `__init__()` as widget
  layout only and do per-Service work in `_service_frame_start()`.
- `LogUI` derives the log topic from the Service topic path by replacing
  the service id with `0` (`NAMESPACE/HOST/PID/0/log`) — one log page per
  *process*, with "use correct Service Id" a recorded To Do.
- `services_cache_create_singleton()` is shared with the main Dashboard —
  calling it again in a plug-in returns the same cache (the
  `history_limit` argument only takes effect for whoever creates it
  first).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ServiceFrame` (base) | Per-Service page lifecycle: service title bar, detect selection change, `_service_frame_start()` / `_service_frame_stop()` hooks, `D` navigation | `DashboardFrame` singleton ([Dashboard](dashboard.md)), `FrameCommon` |
| `LogUI` | Embeddable log tail: subscribe / unsubscribe to the Service's log topic, ring buffer, scrolling | `aiko.process` message handlers, host frame |
| `RegistrarFrame` (example plug-in) | Show all discovered Service topic paths plus the Registrar's log | `ServicesCache`, `LogUI`, [Registrar](registrar.md) |
| `update_plugins()` / `_PLUGINS` | Registry mapping scene names (Service name or protocol) to frame classes | `run_dashboard()`, `DashboardFrame._raise_next_scene()` |

## Current limitations and roadmap

- Plug-in loading failures are silent — a mistyped `--plugin` module name
  simply yields no page.
- One page per Service *type*; there is no per-instance page state beyond
  the currently selected Service.
- The Dashboard To Do list envisages plug-ins as the main growth path
  ("Dashboard plug-ins: Metrics for all Services/Actors/Agents/
  Pipelines"), including: a LISP REPL / composable GUI workspace
  integrating `do_command()` / `do_request()`; a mosquitto (MQTT) metrics
  and administration page; a Registrar tree viewer; ProcessManager and
  HyperSpace pages driving their APIs.
- Writing a custom plug-in is also the recommended fourth debugging
  approach for a Service or Actor (see the `dashboard.py` header notes).

## Related concepts

- [Design overview](design_overview.md)
- [Dashboard](dashboard.md) — the host application and its singleton
  frame
- [Service](service.md) — what a page is shown for; name and protocol
  drive plug-in matching
- [Share](share.md) — the `ECConsumer` handed to
  `_service_frame_start()`
- [Registrar](registrar.md) — subject of the built-in example plug-in
