---
title: ProcessManager
description: Create, list and destroy operating system processes in a
  unified, distributed fashion — analogous to Unix init (pid 1)
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/main/process_manager.py
related: [design_overview, hyperspace, dependency, storage, actor, share,
  lifecycle]
version: "0.8"
last_updated: 2026-11-01
---

# ProcessManager

## Overview

Source code: [`src/aiko_services/main/process_manager.py`](../../src/aiko_services/main/process_manager.py)

**ProcessManager** is an [Actor](actor.md) that makes, lists and destroys
operating system processes on its host. It is the muscle behind the
structural model. [HyperSpace](hyperspace.md) says *what must exist*, and
a [Dependency](dependency.md)'s `lifecycle_manager_url` says *who runs
it*. ProcessManager is the component that launches and reaps the OS
processes. It is analogous to the Unix `init` process (pid 1): typically
one per host, named after the hostname, supervising everything beneath it.

**Why to use it**: because it is a distributed Actor, any authorized
client anywhere in the namespace can start a process on any host with one
command:

```bash
aiko_process create --name that_host aiko_pipeline create my_pipeline.json
```

## For application developers

### Command-line usage

`aiko_process`. The target ProcessManager is selected with `--name / -n`,
defaulting to the local hostname.

Lifecycle:

```bash
aiko_process run  [--name NAME] [--watchdog] [--unsafe] [DEFINITION_PATHNAME]
aiko_process dump [--name NAME]
aiko_process exit [--name NAME] [--grace_time SECONDS]   # default 5 s
```

### What a ProcessManager accepts from the message bus

A ProcessManager starts and stops processes on its host. Any client on the
broker can reach it, so `run` is `--safe` by default. In that posture it
accepts two functions from the bus: `(list ...)` and `(set_log_level ...)`.
Neither one starts or stops a process. It denies every other function,
`(create ...)`, `(destroy ...)`, `(exit ...)` and `(stop)` among them.

So `aiko_process create`, `destroy` and `exit` work only against a
ProcessManager that was started with `--unsafe`:

```bash
aiko_process run --unsafe            # accepts create, destroy, dump, exit
```

`--unsafe` is appropriate where the broker is not reachable from outside a
trusted network. ADR-023 decision 6 allows that posture for an isolated
deployment, as long as the policy is explicit and advertised.

A diagnostic function is not a safe function. `dump` starts and stops
nothing, and it is denied in safe mode. It writes the process table to the
log, and internal data that a client reads is internal data that helps a
client compromise the system. A function becomes safe after a design and a
test campaign, not because it looks harmless.

The command line and the definition file are not affected, because neither
one goes through the bus. A ProcessManager that starts the processes in its
definition file needs nothing but the default.

Two shared-state keys make the posture observable. `safe` is `true` or
`false`, and `metrics.denied` counts each denied function. `last_error`
holds the reason and the name of the last one.

These keys are a report of the posture, not a control for it. Each one is
writable from the Actor's `control` topic, which the `FunctionGate` does
not guard, so the ProcessManager defends the report. A write to `safe` is
reverted to the value in force, and counted as a denial with the reason
`read_only`. The Actor holds the count of denials, and publishes it again
at the next denial. Thus a value that a client wrote is corrected.
A write could never change what is enforced, because the gate holds its
own allow list.

The `FunctionGate` aspect applies the policy. Its allow list is derived
from the `ProcessManager` Interface, so the list and the contract cannot
drift apart.

One more rule applies to `(list TOPIC)`, in each posture. The caller names
the topic that the reply goes to, so the ProcessManager checks it: no
wildcard, a suffix that a Service owns, a well-formed Service topic path,
and the namespace this ProcessManager is in. A topic that fails any of
these is denied, and nothing is published.

`DEFINITION_PATHNAME` must be a `.json` file that contains an array of
command strings, started at startup. Each string starts with an `enabled`
flag, `true` or `false`, and then the command and its arguments:

```json
[
  "true  mosquitto -c 0_mosquitto.conf",
  "true  aiko_registrar",
  "false aiko_pipeline create pipeline.json -ll debug"
]
```

The flag lets you disable a process, but keep it in the definition. The
flag is necessary. An entry without a flag is an error. The ProcessManager
reports the error, then skips that entry. A command that does not start,
and gives no diagnostic, is worse. One bad entry does not stop the other
processes. The flag applies to the definition file only. Thus
`aiko_process create true` still runs the `true` command.

An entry is either that string, or an object. The object form carries a
working directory. It also keeps an argument that contains a space, which
the string form cannot do:

```json
[
  {"enabled": true, "command": "aiko_hyperspace run",
   "cwd": "/home/claude/hyperspace"},
  {"enabled": true, "command": ["aiko_chat", "run"],
   "cwd": "/home/claude/chat_server"}
]
```

The string form splits on whitespace. The object form splits the command
with `shlex`, which keeps a quoted argument together. A command given as a
list needs no quoting rules at all. The `enabled` flag is necessary in
both forms, and `cwd` is optional. An unknown key is an error. The
ProcessManager reports the error, then skips that entry, because a key
that is nearly correct is the one worth a diagnostic.

### The working directory

A process inherits the ProcessManager's working directory. The `--cwd`
option, and the `cwd` key in a definition entry, give it a different one.

Some Services find their state by the working directory and nothing else.
HyperSpace file [Storage](storage.md) is one. It resolves `_hyperspace_`
and `.root` against the working directory. Thus `aiko_hyperspace run`
reads the storage of the directory it starts in, and a Service of this
type needs `cwd`.

The ProcessManager makes sure that the directory exists before it starts
the process. If the directory does not exist, the ProcessManager reports
the error and starts no process. `Popen` reports this condition as a file
not found error. That error names the command, not the directory. Thus
the ProcessManager does the check itself.

Manage processes:

`create` and `destroy` travel on the message bus, so they need a
ProcessManager started with `--unsafe`. `list` works in each posture.

### The Dashboard page

`aiko_dashboard` has a page for each ProcessManager. Select the Service,
then press `S`. The page needs no `--plugin` flag, because
`ide/tui/dashboard/plugins.py` is the default module and registers it.

The page shows the process table, the shared state and the log. The title
bar carries the posture and the count of denied functions, which is what an
operator looks for first. The keys are `c` create, `d` destroy with SIGTERM,
`k` destroy with SIGKILL, `u` dump, `K` exit, `L` log level and `H` help.

A ProcessManager in the default posture denies each of those functions.
Thus the page says which posture it is in, and why a key does nothing,
instead of appearing to act. It reads the posture from the shared state.

### The ProcessManagerCache

Each client that wants the process table can hold a live replica of it,
instead of a request for each look:

```python
cache = ProcessManagerCache(aiko.process, name="aiko01")
cache.get_processes()    # {uid: (pid, command)}
cache.get_safe()         # True, False, or None when not reported
cache.get_denied()       # how many functions this ProcessManager denied
```

The replica is local, and a read of it does not use the network. The
Registrar's ServicesCache is the same idea for Services. `ECCache` does the
work: discovery, one leased `ECConsumer` for each ProcessManager that
matches, and the replica of each one. `add_handler()` reports each change.

`aiko_process list --watch` is the same cache on the command line.

```bash
aiko_process create [--name NAME] [--uid UID] [--cwd CWD]
                    COMMAND [ARGUMENTS ...]
aiko_process list   [--name NAME] [UID]
aiko_process destroy [--name NAME] [--kill] UID
```

Examples from the source header — shell and Python scripts:

```bash
aiko_process create -u uid:0 date
aiko_process create -u uid:1 sleep 5
aiko_process create -u uid:2 aiko_process exit -gt 0   # self terminate !
aiko_process create -u uid:3 -c /home/claude/hyperspace aiko_hyperspace run
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

### Public API

Core operations:

| Operation | Effect |
|-----------|--------|
| `create(command, arguments, uid)` | Launch a process (`Popen`, no shell); UID auto-assigned (`000001`, `000002`, …) if not given |
| `list(topic_path_response, uid)` | Publish `uid pid command…` records for all or one process |
| `destroy(uid, kill=False)` | SIGTERM (catchable, clean-up possible) or, with `kill`, SIGKILL |
| `dump()` | Log current process table |
| `exit(grace_time)` | SIGTERM everything, wait `grace_time` seconds, SIGKILL survivors, terminate self |

Embedding in your own process:

```python
from aiko_services.main import *
from aiko_services.main.process_manager import ProcessManagerImpl, PROTOCOL

init_args = actor_args(get_hostname(), None, None, PROTOCOL, ["ec=true"])
init_args["definition_pathname"] = None
init_args["watchdog"] = False
process_manager = compose_instance(ProcessManagerImpl, init_args)
aiko.process.run()
```

A custom `process_exit_handler(uid)` may be passed through `init_args` to react
to child exits (relaunch policies, notifications, …). The default logs UID,
PID, command and return code on exit.

**Wire protocol.** `list()` follows the standard response idiom on the
requester's topic (see [Category](category.md) for the general pattern):

```
(item_count N)
(response UID PID COMMAND ARG…)      # repeated
```

## For framework developers (internals)

### Design

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

A **definition file** (JSON array of command strings, each with an
`enabled` flag) can pre-populate the process table at startup — the
`init`-style "boot this host" use case.
ProcessManager registers *itself* in its own table as UID `000000`
(self-aware 🤔), wrapped in a `ProcessCurrent` shim so uniform bookkeeping
applies. It is protected from `destroy()`.

The design direction (see roadmap) is **ProcessManager as-a
[LifeCycleManager](lifecycle.md) as-a Category**: driving the full Service
lifecycle
(`create, enable, start, status, stop, disable, destroy`) from the
HyperSpace/Storage structure, including lazy loading of HyperSpace entries.

### Implementation notes

**Concurrency model.** This is the file's central design note. Every method
except `_run()` executes on the Actor main thread — serialized, one at a
time, so no locking is needed. `_run()` is a daemon *reaper thread* that:

- copies iterators before looping (insulating itself from concurrent
  mutation of `self.processes`), and
- never mutates shared data directly — it posts reap work back to the
  Actor main thread with
  `self._post_message(ActorTopic.IN, "_remove", [zombies])`.

`_remove()` (on the main thread) fires the `process_exit_handler` for each
exited UID, erases the table entries and updates `metrics.running`. The
poll interval is 1 second (`_PROCESS_POLL_TIME`).

Follow the same rule in any extension: post to the main thread rather than
touching `self.processes` from another thread.

**Process creation details:**

- Commands ending in `.py` / `.sh` run as given. For any other command, an
  executable on `PATH` wins. A command that is not on `PATH` is resolved as
  a *Python module name* through `importlib.util.find_spec()`. The module's
  own file runs, but only if the name is a module and that file is
  executable. Thus `aiko_process create my_package.my_module` needs no
  knowledge of the installation path. A command that is neither runs as
  given, so that `Popen` reports the command it did not find.
- `PATH` wins because a console script and an importable package often
  share a name. `aiko_chat` is both, and the package resolved to its
  `__init__.py`, so the process ran a file nobody asked for.
- A package is never that file. The file mode does not decide this,
  because some installations give every library file the execute bit. The
  hosted Python of the CI runner is one, for Python 3.11 and later.
- `Popen(command_line, bufsize=0, shell=False, cwd=cwd)` does no shell
  interpretation. To use shell features, invoke the shell explicitly
  (`/bin/sh -c "…"`, refer to the command-line examples above). A `cwd` of
  `None` is the inherited working directory.
- Duplicate UIDs are rejected with a warning, and the process does not
  start. `FileNotFoundError` and other exceptions are logged, not
  raised.

**Shared state.** `self.share` publishes `lifecycle`, `log_level`,
`source_file`, `definition_pathname`, `watchdog` and `metrics`. The
`metrics` value holds `created` and `running`, and both include
ProcessManager itself 😅. Publication is through
[ECProducer](share.md) — so the [Dashboard](dashboard.md) sees the process
population of every host in real time.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ProcessManager` (Interface) | Declare the process-table contract: `create()`, `list()`, `destroy()`, `dump()`, `exit()`; is-an Actor | `Actor` (parent Interface) |
| `ProcessManagerImpl` | Maintain the `uid → (command_line, Popen)` table; launch through `Popen` with the given working directory, and command resolution that prefers `PATH`; reap exits on the reaper thread and marshal them back to the main thread; publish metrics through ECProducer; load definition files; graceful `exit()` escalation (SIGTERM → SIGKILL) | `ProcessCurrent` (self-entry shim); `ECProducer` (shared state); [HyperSpace](hyperspace.md) / [Storage](storage.md) (planned lifecycle-driving structure); [Dependency](dependency.md) (`lifecycle_manager_url` target) |
| `ProcessCurrent` | Present the ProcessManager's own OS process with the same interface as a `Popen` child, so UID `000000` gets uniform bookkeeping | `ProcessManagerImpl` (sole user) |

## Current limitations and roadmap

Highlights from the source `To Do` list:

- Refactor ProcessManager to give functionality without being an Actor
  (then update LifeCycleManager accordingly). ProcessManager as-a
  LifeCycleManager as-a Category, using the HyperSpace API and
  [Storage](storage.md) SPI
- The HyperSpace-path lifecycle verbs (`enable/disable/start/status/stop`)
  and disambiguating CLI `create` from `start`, and `destroy` from `stop`
- The `--watchdog` flag is recorded in shared state, but primary/watchdog
  monitor-and-relaunch behavior is still to come. Likewise "one primary
  ProcessManager per host" enforcement and cross-host unification
- Capture child stdout/stderr. Relaunch failed processes (with
  back-off). Add auto-scaling workers. Add scheduled (crontab-style)
  lifecycle changes
- Process `owner` field, `destroy --force`, system processes owned by
  `aiko`. Runtime and resource-usage metrics (psutil). Process events to
  Dashboard / time-series databases (OpenTelemetry schema)
- Windows testing. Integration with systemd / launchd / task scheduler

## Related concepts

- [Design overview](design_overview.md)
- [Dependency](dependency.md) — `lifecycle_manager_url` points here
- [HyperSpace](hyperspace.md) — the structure ProcessManager will realize
- [Storage](storage.md) — future read-only bootstrap source
- [LifeCycle](lifecycle.md) — the manager/client pattern ProcessManager is
  slated to implement
- [Actor](actor.md) — the mailbox/main-thread model behind the concurrency
  rules above
