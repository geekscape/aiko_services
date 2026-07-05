---
title: Dashboard
description: A terminal user interface for observing and controlling every
  running Service — live shared variables, logs, history and remote updates
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/dashboard.py
related: [design_overview, dashboard_plugin, service, share, registrar,
  connection, recorder]
version: "0.6"
last_updated: 2026-07-05
---

# Dashboard

## Overview

The **Dashboard** is the Aiko Services terminal user interface (TUI) —
built on the `asciimatics` library — for watching and operating a running
distributed system. It discovers every [Service](service.md) via the
[Registrar](registrar.md), then presents three live sections in one page:
the current Services, the selected Service's shared variables (via
[Share](share.md) — ECProducer / ECConsumer), and a history of terminated
Services. From the keyboard you can update a Service variable, change a
Service's log level, tail a Service's log, filter the Service list and
kill a local Service process.

The Dashboard is deliberately written *as an application, outside the
framework core* (`import aiko_services as aiko` — "designed to be external
to the main framework"), which makes it both the reference consumer of the
public discovery / shared-state APIs and extensible through
[Dashboard plug-ins](dashboard_plugin.md) that add custom pages per
Service protocol.

**Why you'd use it**: you have a Registrar plus a handful of Services and
Pipelines running across several hosts, and want one live view of what is
up, what each Service's state is, and a way to tweak a variable or log
level without restarting anything:

```bash
aiko_registrar &          # if not already running
aiko_dashboard            # full-screen TUI appears
# select a Service, press Enter on a variable to update it,
# press "L" to tail its log, press "x" to exit
```

## For application developers

### Command-line usage

The console script is `aiko_dashboard` (defined in `pyproject.toml` as
`aiko_services.main.dashboard:main`); the module can also be run directly
(`./dashboard.py` in `src/aiko_services/main`).

```bash
aiko_dashboard [--history_limit N] [--plugin MODULE]...

# -hl, --history_limit N   History length requested from the Registrar
#                          (default: 32)
# -p,  --plugin MODULE     Dashboard plug-in module(s) to load
#                          (default: aiko_services.main.dashboard_plugins)
```

Keyboard commands on the Dashboard page (press `?` for this list):

```
Enter  Update variable value          C      Clear selection
Tab    Move to next section           D      Show Dashboard page
c      Copy topic path to clipboard   K      Kill Service (local)
f      Filter Service (toggle)        L      Show Log page
l      Log level change               S      Show Service page
s      Select Service (toggle)        x      Exit
```

- `f` opens the filter pop-up: `1` toggles hiding Services with
  service id > 1, `c` toggles Category Services, `e` toggles
  PipelineElements, `R` resets. By default `category` and
  `pipeline_element` Services are hidden.
- `l` opens the log level pop-up: `d/e/i/w` set DEBUG / ERROR / INFO /
  WARNING for the selected Service, `D/E/I/W` set `*_ALL` variants.
- On the Log page (and plug-in pages), `D` returns to the Dashboard;
  `Home` / `End` jump to the oldest / latest log record, and scrolling up
  pauses follow-latest mode.
- Clipboard copy (`c`) requires the `pyperclip` Python package and, on
  Linux, the `xclip` system package.

Because the TUI owns the terminal, debugging output is separated by file
descriptor — a technique documented in the source header:

```bash
aiko_dashboard 1>/dev/null   # show debug messages only (stderr)
aiko_dashboard 2>/dev/null   # show the TUI only (stdout)

# or publish debug messages over MQTT and watch them separately
mosquitto_sub -h $AIKO_MQTT_HOST -t $AIKO_NAMESPACE/DASHBOARD -v
```

### Public API

The Dashboard has no Aiko Services Interface of its own — it is a client
of the standard discovery and shared-state protocols. What it *does*
define is the contract a Service must meet to be fully observable:

| Service provides | Dashboard behaviour |
|------------------|---------------------|
| Registered with the [Registrar](registrar.md) | Appears in the Services section; terminated Services appear in History |
| Tag `ec=true` | Dashboard creates an `ECConsumer` on `TOPIC_PATH/control` and shows the Service's shared variables live |
| Shared variable `log_level` | The `l` pop-up updates it remotely |
| Log records published to its log topic | The Log page (`L`) tails them |

**Wire protocol.** Updating a variable (the `Enter` dialogue and the log
level pop-up) publishes a standard [Share](share.md) update command to the
Service's control topic:

```
TOPIC_PATH/control  ◄──  (update VARIABLE_NAME VALUE)
```

Log tailing subscribes to the Service process's log topic — currently
hard-coded to service id `0` of the process
(`NAMESPACE/HOST/PID/0/log`); using the correct service id is a
known To Do.

Selecting a Service is a genuine multi-party exchange:

```
Dashboard                  Registrar                 Service
    │                          │                        │
    │──(share …) / (history …)─►                        │  Services cache:
    │◄─ Service records ───────│                        │  current + history
    │                          │                        │
    │  user selects a Service with tag ec=true          │
    │                                                   │
    │──ECConsumer: (share …) to TOPIC_PATH/control ────►│
    │◄─ variable values, then incremental updates ──────│
    │                                                   │
    │──(update log_level DEBUG) to TOPIC_PATH/control ─►│
```

For building custom Dashboard pages, the module exports two classes —
`ServiceFrame` and `LogUI` — documented in
[Dashboard plug-in](dashboard_plugin.md).

## For framework developers (internals)

### Design

```
Screen.wrapper ──► run_dashboard(screen, start_scene)
                        │  one Scene per _PLUGINS entry
   ┌────────────────────┼──────────────────────┐
   │ "Dashboard"        │ "Log"                │ plug-in scenes …
   │ DashboardFrame     │ LogFrame(ServiceFrame│ e.g. "registrar"
   │ (singleton)        │   + LogUI)           │ RegistrarFrame
   └────────────────────┴──────────────────────┘
   DashboardFrame sections:
   ┌──────────────────────────────────────────┐
   │ Services   (ServicesCache ◄── Registrar) │
   │ Variables  (ECConsumer ◄── selected      │
   │             Service TOPIC_PATH/control)  │
   │ History    (ServicesCache history)       │
   └──────────────────────────────────────────┘
```

Key design points:

- **Scene-per-page.** Every page is an `asciimatics` Scene holding one
  Frame; navigation is `raise NextScene(name)`. The `_PLUGINS` dict maps
  scene names to Frame classes, seeded with `Dashboard` and `Log` and
  extended by plug-in modules.
- **Singleton DashboardFrame.** `DashboardFrame.get_singleton()` gives
  plug-in frames access to the selected Service and its `ECConsumer`, so
  selection state lives in exactly one place.
- **Pull, not push.** The frame `_update()` runs at roughly 5 Hz
  (`_FRAME_UPDATE_RATE`) and re-renders from the `ServicesCache` and the
  `ECConsumer`'s dictionary; the [Connection](connection.md) state is
  polled at roughly 1 Hz rather than via a registered handler (the
  `add_handler` call is present but commented out) and a pop-up warns when
  the MQTT server or Registrar is missing.
- **One ECConsumer at a time.** Selecting a Service tears down the
  previous `ECConsumer` (`_ec_consumer_reset()`) and creates a new one
  only when the Service carries the `ec=true` tag.

### Implementation notes

- **Frame naming clash.** `stream.py` defines a `Frame` dataclass;
  the Dashboard therefore imports
  `asciimatics.widgets.Frame as asciimatics_Frame` — keep that alias when
  extending.
- **Service records** from the `ServicesCache` are tuples:
  `(topic_path, name, protocol, transport, owner, tags)` — indices matter
  throughout (`service[2]` protocol, `service[3]` transport,
  `service[5]` tags).
- **Filtering.** `_filter()` tracks the most recent service id `1` entry
  as the "parent" so that PipelineElements (service id > 1 whose parent
  protocol is `pipeline`) can be hidden as a group; protocols are compared
  by short name with the version stripped (`protocol.split(":")[0]`).
- **Line wrapping.** `_update_field()` wraps long variable values and log
  records across multiple rows with a two-space hanging indent.
- **Kill is local only.** `K` parses the process id out of the topic path
  and runs `kill -9` (or `-2` for `transport == "ray"`) via
  `subprocess.Popen` on the local host — it does not send a terminate
  message to remote Services (known limitation, see roadmap).
- **Resize handling.** `ResizeScreenError` is caught in `main()` and the
  whole Scene set is rebuilt; event handlers registered by frames are
  currently *not* removed first (known FIX in the To Do list).
- **Exit cleanup.** `x` / `X` / `Ctrl-C` delete the Services cache
  singleton (`aiko.services_cache_delete()`) before stopping the
  application.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `FrameCommon` | Shared frame behaviour: title bar, palette, connection-state pop-up, help/exit key handling, value line-wrapping, `(update …)` publishing | `Connection`, `asciimatics` widgets |
| `DashboardFrame` | Singleton main page: render Services / variables / history; selection, filtering, clipboard, kill, scene navigation | `ServicesCache` ([Registrar](registrar.md)), `ECConsumer` ([Share](share.md)), `FilterPopupMenu`, `LogLevelPopupMenu`, plug-in frames |
| `ServiceFrame` | Base class for per-Service pages: service title bar, start/stop hooks on selection change, `D` returns to Dashboard | `DashboardFrame` (selection and ECConsumer), [Dashboard plug-ins](dashboard_plugin.md) |
| `LogUI` | Reusable log-tail widget: subscribe to a Service's log topic, ring buffer (128 records), follow-latest scrolling | `aiko.process` message handlers, host Frame |
| `LogFrame` | The `Log` scene: a `ServiceFrame` embedding a `LogUI` | `ServiceFrame`, `LogUI` |
| `FilterPopupMenu` | Toggle Service-list filters (sid>1, category, pipeline_element), reset | `DashboardFrame.filter_out` |
| `LogLevelPopupMenu` | Set the selected Service's `log_level` shared variable (per-Service or `*_ALL`) | `DashboardFrame`, [Share](share.md) |

## Current limitations and roadmap

Known bugs recorded in the source To Do list:

- Variables containing whitespace are not displayed at all
- The ECConsumer is not un-shared on exit, and its lease-extend timer is
  not terminated; ECProducer lease expiry needs checking
- Closing the filter pop-up with `c` leaks the keystroke to the main
  Dashboard, triggering a spurious clipboard copy
- If the currently selected Service terminates, the variables section is
  not updated
- `K` (Kill Service) assumes the Service runs on the local host — it
  should send a terminate message or find the right ProcessManager
- On resize, recreated frames do not remove their old handlers

Additionally, `FilterPopupMenu` menu items apply filters only via their
keyboard shortcuts — selecting a menu item with Enter computes a value and
discards it (handler body is commented out).

Planned (highlights):

- "Waiting for Registrar" display, and surfacing primary / secondary
  Registrar status from `TOPIC_REGISTRAR_BOOT`
- More keys: publish to a Service, remote terminate / kill dialogue,
  multiple-Service log pages, generic Service page, new-Service creation
- Show Service uptime / statistics; sort and filter variables; add /
  remove variables from the Dashboard
- An ArchiveService so History can extend beyond the Registrar's window
  (see [Recorder](recorder.md))
- A Web browser Dashboard over MQTT / WebSockets
- An AI REPL analysing Aiko Services logs and MQTT messages

## Related concepts

- [Design overview](design_overview.md)
- [Dashboard plug-in](dashboard_plugin.md) — adding custom pages per
  Service name or protocol
- [Service](service.md) — what the Dashboard observes
- [Share](share.md) — ECProducer / ECConsumer, the live-variables
  mechanism and `(update …)` wire command
- [Registrar](registrar.md) — the source of the Services list and history
- [Connection](connection.md) — the connection states behind the
  "Registrar not found" pop-up
- [Recorder](recorder.md) — log records the Log page tails
