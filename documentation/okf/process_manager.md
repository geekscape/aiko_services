---
title: ProcessManager
description: Create, list and destroy operating system processes in a
  unified, distributed fashion — analogous to Unix init (pid 1)
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/process_manager.py
related: [design_overview, hyperspace, dependency, storage]
version: "0.6"
last_updated: 2026-07-04
---

# ProcessManager

## At a glance

**ProcessManager** is an Actor that creates, lists and destroys operating
system processes on its host — the muscle behind the structural model:
where [HyperSpace](hyperspace.md) says *what should exist* and a
[Dependency](dependency.md)'s `lifecycle_manager_url` says *who runs it*,
ProcessManager is the component that actually launches and reaps OS
processes. It is analogous to the Unix `init` process (pid 1): typically
one per host, named after the hostname, supervising everything beneath it.

Because it is a distributed Actor, any authorised client anywhere in the
namespace can start a process on any host with one command:

```bash
aiko_process create --name that_host aiko_pipeline create my_pipeline.json
```

## Design

```
   aiko_process CLI ──MQTT──►  ProcessManager Actor (protocol: process_manager:0)
                               │
                               │  processes (uid → command_line, Popen)
                               ├── <000000>  aiko_process run     ◄─ itself 🤔
                               ├── <000001>  date
                               ├── <uid:1>   sleep 5
                               └── <000002>  python my_agent.py
                               │
                               ├── reaper thread: poll every 1 s,
                               │   reap exited processes, fire exit handler
                               └── metrics: created, running  (ECProducer)
```

| Operation | Effect |
|-----------|--------|
| `create(command, arguments, uid)` | Launch a process (`Popen`, no shell); UID auto-assigned (`000001`, `000002`, …) if not given |
| `list(topic_path_response, uid)` | Publish `uid pid command…` records for all or one process |
| `destroy(uid, kill=False)` | SIGTERM (catchable, clean-up possible) or, with `kill`, SIGKILL |
| `dump()` | Log current process table |
| `exit(grace_time)` | SIGTERM everything, wait `grace_time` seconds, SIGKILL survivors, terminate self |

A **definition file** (JSON array of command strings) can pre-populate the
process table at startup — the `init`-style "boot this host" use case.
ProcessManager registers *itself* in its own table as UID `000000`
(self-aware 🤔), wrapped in a `ProcessCurrent` shim so uniform bookkeeping
applies; it is protected from `destroy()`.

The design direction (see roadmap) is **ProcessManager as-a
LifeCycleManager as-a Category**: driving the full Service lifecycle
(`create, enable, start, status, stop, disable, destroy`) from the
HyperSpace/Storage structure, including lazy loading of HyperSpace entries.

## Developer guide (internals)

### Concurrency model

This is the file's central design note. Every method except `_run()`
executes on the Actor main thread — serialized, one at a time, so no
locking is needed. `_run()` is a daemon *reaper thread* that:

- copies iterators before looping (insulating itself from concurrent
  mutation of `self.processes`), and
- never mutates shared data directly — it posts reap work back to the
  Actor main thread with
  `self._post_message(ActorTopic.IN, "_remove", [zombies])`.

`_remove()` (on the main thread) fires the `process_exit_handler` for each
exited UID, deletes the table entries and updates `metrics.running`. The
poll interval is 1 second (`_PROCESS_POLL_TIME`).

Follow the same rule in any extension: post to the main thread rather than
touching `self.processes` from another thread.

### Process creation details

- Commands ending in `.py` / `.sh` run as given. Any other command is
  first resolved as a *Python module name* via
  `importlib.util.find_spec()`; if found, the module's file path is
  executed instead — so `aiko_process create my_package.my_module` works
  without knowing the installation path.
- `Popen(command_line, bufsize=0, shell=False)` — no shell interpretation;
  to use shell features, invoke the shell explicitly
  (`/bin/sh -c "…"`, see examples below).
- Duplicate UIDs are rejected with a warning (process not started);
  `FileNotFoundError` and other exceptions are logged, not raised.
- A pluggable `process_exit_handler(uid)` can be supplied at construction;
  the default logs UID, PID, command and return code on exit.

### Shared state

`self.share` publishes `lifecycle`, `log_level`, `source_file`,
`definition_pathname`, `watchdog` and `metrics` (`created` and `running`,
both including ProcessManager itself 😅) via ECProducer — so the Dashboard
sees the process population of every host in real time.

### Wire protocol

`list()` follows the standard response idiom on the requester's topic:

```
(item_count N)
(response UID PID COMMAND ARG…)      # repeated
```

### Embedding in your own process

```python
from aiko_services.main import *
from aiko_services.main.process_manager import ProcessManagerImpl, PROTOCOL

init_args = actor_args(get_hostname(), None, None, PROTOCOL, ["ec=true"])
init_args["definition_pathname"] = None
init_args["watchdog"] = False
process_manager = compose_instance(ProcessManagerImpl, init_args)
aiko.process.run()
```

A custom `process_exit_handler` may be passed via `init_args` to react to
child exits (relaunch policies, notifications, …).

## User guide (command line)

`aiko_process`. The target ProcessManager is selected with `--name / -n`,
defaulting to the local hostname.

### Lifecycle

```bash
aiko_process run  [--name NAME] [--watchdog] [DEFINITION_PATHNAME]
aiko_process dump [--name NAME]
aiko_process exit [--name NAME] [--grace_time SECONDS]   # default 5 s
```

`DEFINITION_PATHNAME` must be a `.json` file containing an array of command
strings, launched at startup:

```json
["aiko_registrar", "aiko_pipeline create pipeline.json -ll debug"]
```

### Manage processes

```bash
aiko_process create [--name NAME] [--uid UID] COMMAND [ARGUMENTS ...]
aiko_process list   [--name NAME] [UID]
aiko_process destroy [--name NAME] [--kill] UID
```

Examples from the source header — shell and Python scripts:

```bash
aiko_process create -u uid:0 date
aiko_process create -u uid:1 sleep 5
aiko_process create -u uid:2 aiko_process exit -gt 0   # self terminate !
```

Simultaneous processes terminating at different times:

```bash
aiko_process create -u uid:0 /bin/sh -c "echo Start A; sleep 10; echo Stop A"
aiko_process create -u uid:1 /bin/sh -c "echo Start B; sleep 15; echo Stop B"
aiko_process create -u uid:2 /bin/sh -c "echo Start C; sleep  5; echo Stop C"
aiko_process list
# Processes ...
#   uid: 000000, pid: 4242, aiko_process run
#   uid: uid:0,  pid: 4301, /bin/sh -c echo Start A; sleep 10; echo Stop A
#   …
aiko_process destroy uid:1          # SIGTERM: catchable, clean-up possible
aiko_process destroy --kill uid:2   # SIGKILL: can't catch, no clean-up
```

Planned (not yet implemented) — Service lifecycle driven from HyperSpace:

```bash
aiko_process enable | disable | start | status | stop HYPERSPACE_PATH
```

## Current limitations and roadmap

Highlights from the source `To Do` list:

- Refactor ProcessManager to provide functionality without being an Actor
  (then update LifeCycleManager accordingly); ProcessManager as-a
  LifeCycleManager as-a Category, using the HyperSpace API and
  [Storage](storage.md) SPI
- The HyperSpace-path lifecycle verbs (`enable/disable/start/status/stop`)
  and disambiguating CLI `create` vs `start`, `destroy` vs `stop`
- The `--watchdog` flag is recorded in shared state, but primary/watchdog
  monitor-and-relaunch behaviour is still to come; likewise "one primary
  ProcessManager per host" enforcement and cross-host unification
- Capture child stdout/stderr; relaunch failed processes (with back-off);
  auto-scaling workers; scheduled (crontab-style) lifecycle changes
- Process `owner` field, `destroy --force`, system processes owned by
  `aiko`; runtime and resource-usage metrics (psutil); process events to
  Dashboard / time-series databases (OpenTelemetry schema)
- Windows testing; integration with systemd / launchd / task scheduler

## Related concepts

- [Design overview](design_overview.md)
- [Dependency](dependency.md) — `lifecycle_manager_url` points here
- [HyperSpace](hyperspace.md) — the structure ProcessManager will realise
- [Storage](storage.md) — future read-only bootstrap source
