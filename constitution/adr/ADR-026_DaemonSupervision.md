---
title: "ADR-026 — Daemon supervision: the DaemonSupervisor Interface, one daemon for each host, render before install"
description: Makes the operating system start one daemon for each host, the
  ProcessManager, through a DaemonSupervisor Interface with one Implementation
  for each platform. Keeps the Interface off the message bus for now, splits
  the pure render from the privileged install, and records Supervisor as an
  aspect for composition later
type: adr
audience: [project-lead, architects, developers, ai-coding-agents]
status: proposal
ste: adapted
related: [ReadMe, ADR-022_CompositionBoundary, ADR-023_GuardedEvalDefaultDeny,
  ADR-025_RemoteDisplayAbstraction, ../p_00_DesignPrinciples,
  ../p_02_CandidatePrinciples, ../s_02_InterfaceComposition,
  ../s_01_RepositoryLayout]
last_updated: 2026-10-21
---

# ADR-026 — Daemon supervision: the `DaemonSupervisor` Interface, one daemon for each host, render before install

**Proposed 2026-10-21** by the aiko01 Raspberry Pi work, Epic 0, whose plan the technical
lead approved on 2026-10-21. The number is claimed in this move. The reference
implementation is `src/aiko_services/main/daemon_supervisor/`, which ships in the wheel.

## Context

Aiko Services must start when a host starts. Before this change, the only example was
`aiko_display.service`. It was a systemd unit written by hand. The account, the virtual
environment and the broker host were written into the file. Each new Actor needed another such
file, for each host, and each file could go stale on its own.

The ProcessManager already starts and stops processes from a definition file. So a host
needs the operating system to start one process only. Everything else — the broker, the
Registrar, Actors, Agents and Pipelines — comes from that definition. This makes the
operating system's part small, and keeps the knowledge of what a host runs in one file that
Aiko Services owns.

Three platforms matter: systemd on Linux, launchd on macOS, and later the Windows Task
Scheduler. Their service descriptions have little in common, but what Aiko Services must
say to each of them is nearly the same.

## Decision

1. **One daemon for each host.** The operating system starts
   `aiko_process run --name NAME DEFINITION`, and nothing else. The ProcessManager
   definition file starts the rest. A host's composition is data, which agrees with P8.

2. **`DaemonDefinition` says what to supervise. `DaemonSupervisor` says how.**
   `DaemonDefinition` is a frozen value type, under the ADR-022 "value or data type"
   exemption. `DaemonSupervisor` is an `Interface` with one Implementation for each
   platform: `SystemdDaemonSupervisorImpl` and `LaunchdDaemonSupervisorImpl`.
   `choose_daemon_supervisor()` selects one, in the way `choose_output()` selects a
   display backend (P7). `UnsupportedDaemonSupervisorImpl` is the registered default, so a platform
   without an Implementation reports itself instead of doing something that cannot work.

3. **`render` before `install`.** `render()` returns the service description as text and
   changes nothing. Thus it is a pure function. A test can compare it with a golden
   string, and a person can read it before they trust it. `install()` is the only operation that changes
   the host, and it is always explicit. Nothing is enabled or started as a side effect.

4. **Not an Actor, and not on the message bus — for now.** The DaemonSupervisor runs
   before Aiko Services runs. It has no protocol, so it adds no wire surface and no
   ADR-023 allow-list. The command line `aiko_supervisor` is its only client, under the
   ADR-022 "presentation or command line shell" exemption.

5. **Supervisor is an aspect, and this is the direction, not the state.** The Interface is
   already aspect-shaped, in the sense of ADR-025: `compose_class()` can mix it into an
   Actor exactly as `Display` composes `Canvas`, `Screen` and `Interaction`. Composing it
   gives a host an Actor that reports and manages its own daemon. That step is additive
   (CP-G), and it is not taken here, because it needs the authority question in
   Consequences answered first. Until it is taken, no `supervisor=0` aspect tag is
   advertised: CP-M says a capability is advertised, not assumed.

6. **The name.** "Supervisor", not "Launcher": the Interface starts, stops, installs,
   removes and reports, which is more than launching, and "Launcher" reads as the macOS
   `launchd` daemon beside it. A daemon is the first thing supervised, not necessarily the
   only one, so the Interface name keeps "Daemon" and the command name does not.

## Consequences

* **Authority moves when the aspect is composed.** Today the operating system protects
  `install`: writing `/etc/systemd/system` needs root. As an aspect on an Actor, `install`,
  `uninstall`, `start` and `stop` become remote operations that change a host, and the
  protocol must protect them instead. That is ADR-023 deny-by-default work, and CP-C
  suggests a capability rather than a list. **This ADR does not open that surface.** The
  decision to compose the aspect must carry the authority design with it.

* **The stop timeout is a correctness rule, not a preference.** The operating system must
  wait longer than the ProcessManager waits for its own processes. If it does not, the
  operating system kills the ProcessManager while its processes are still stopping. Those
  processes stay alive, and a clean shutdown becomes impossible. `DaemonDefinition` refuses a
  timeout that is too short.

* **Two defaults record what the hardware taught.** `restart` is `always`, because the
  ProcessManager `--watchdog` option is recorded but nothing relaunches anything yet.
  `PYTHONUNBUFFERED` is set, because Python buffers stdout when it is a pipe, which is what
  a service gets: without it the log stays in the buffer and the service looks silent.
  Both become unnecessary when their causes are fixed, and both are documented where they
  are set.

* **Windows is absent, and says so.** The platform reports that it has no Implementation.
  Adding one is a new Implementation and a renderer, with no change to `DaemonDefinition`.

* **A second definition kind now exists.** The ProcessManager definition file lists
  processes. A `DaemonDefinition` describes the daemon that reads it. Both are
  "definitions", which is deliberate. The project lead has a wider idea: one `Definition`
  schema over PipelineDefinition, AgentDefinition, ActorDefinition and
  ServiceDefinition, expressed as S-expressions. That is future work, and it needs its
  own record.

## Alternatives rejected

* **A unit file for each Actor.** This is what `aiko_display.service` did. It puts host
  knowledge in as many files as there are Actors, and the operating system then supervises
  things that the ProcessManager supervises better. Rejected because the ProcessManager
  already exists for this.

* **A Supervisor Actor from the start.** Attractive, because everything else on a host is
  an Actor, and because deployment would then be observable on the bus (CP-I). Rejected for
  now: it must start before the bus exists, and it would open a remote host-changing
  surface before the authority design for it is written. Decision 5 keeps the path open.

* **`install` as the only operation, with no `render`.** Fewer steps for the common case.
  Rejected for three reasons. The common case is to read what will be written. A pure
  function is testable without root. A privileged operation must never be the default.

* **One generic "service" abstraction over systemd, launchd and containers.** Rejected as
  speculative generality. The three platforms here are enough to find the shape, and P10
  prefers what is proven over what is anticipated.
