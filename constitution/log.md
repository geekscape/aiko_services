# Constitution journal (public)

The dated journal of changes to the public constitution tree, newest first.
Every substantive change appends an entry under its date heading
(`**Creation**` / `**Update**` bullets). Typo-level fixes are exempt.
This journal begins at the constitution's first public release. The
pre-publication history is maintained privately.

## 2026-11-09

- **Update** — [g_03_AgentContext.md](g_03_AgentContext.md) and
  [e_06_TestingStrategy.md](e_06_TestingStrategy.md): the commands an agent
  runs match the CI workflow again. CI runs the unit tests through
  `hatch run test`, which reports coverage, and a bare `pytest` runs the
  tests alone. The lint command excludes the in-tree environment
  directories, because the workflow makes `.venv` and `.hatch` in the
  repository itself. In e_06 the supported range reads Python 3.9 to 3.14,
  in §3.7 and in the §4 gate order. That is what `requires-python` and the
  CI matrix hold. §3.7 said that current CI omits the version matrix.
  CI runs it on Ubuntu, and macOS is the part that remains. The T14 entry
  records the same division: the matrix and the coverage report are in
  place, and the macOS job, the mosquitto job, the type-check job and the
  coverage gate remain.

## 2026-11-05

- **Creation** — [adr/ADR-028_PowerManagement.md](adr/ADR-028_PowerManagement.md),
  with its row in [adr/ReadMe.md](adr/ReadMe.md): power management becomes an
  Aiko Services concern. One `PowerManager` Interface extends Actor and has
  one Implementation for each platform, in the way that ADR-026 did for
  `DaemonSupervisor`. The record states why the power hold does not use the
  GPIO character device. That device releases the pin when the process
  exits. Thus an Actor that held it would cut the power of a Device each
  time it restarted. Only the shutdown hook releases the hold, and never on
  a restart. Safe and unsafe postures follow `ProcessManager`, under
  ADR-023. Before the power ends, the host synchronizes its file systems
  and tells its applications to stop writing. At the floor voltage it
  remounts them read-only, and the cell damage limit is never a trigger.
  The power-off and the remount both need a grant from the operating
  system, which `render` prints before `install` writes it.

  The record is a proposal. It is committed on the lead's direction, and it
  waits for acceptance: a move asks the lead to accept the ADR as written
  or to amend it, and ADR-025 and ADR-026 became `normative` on the dates
  their own moves merged.

  Up-time is requested as a `PoweredUpLease`, which extends the framework's
  Lease so that an expiry acts at the time that was agreed. It has two
  conditions. The lease time is the period for which it is valid, and a
  client extends it. A constraint is a quantity of a finite resource, in
  whatever unit measures it, and the host must still be able to meet it. A
  constraint in a unit the host cannot measure is refused, because granting
  what cannot be checked would have a client plan on a promise that nothing
  can keep.

  The move claims 028 and not 027. The registry shows 027 as free, and an
  unmerged branch holds a written ADR-027 for P11. The note under the
  registry records this, so that the two cannot collide.

## 2026-11-02

- **Update** — [adr/ReadMe.md](adr/ReadMe.md),
  [adr/ADR-025_RemoteDisplayAbstraction.md](adr/ADR-025_RemoteDisplayAbstraction.md)
  and [adr/ADR-026_DaemonSupervision.md](adr/ADR-026_DaemonSupervision.md):
  both ADRs become `normative`, accepted on the dates that their moves
  merged. ADR-025 was accepted on 2026-09-27 (#108), and ADR-026 on
  2026-10-21 (#119). Each move asked the lead to accept the ADR as written
  or to amend it, and the lead merged it.

- **Update** — [adr/ReadMe.md](adr/ReadMe.md) and
  [adr/ADR-025_RemoteDisplayAbstraction.md](adr/ADR-025_RemoteDisplayAbstraction.md):
  the registry row and the ADR's `last_updated` record the amendment of
  2026-11-02 (a `down` holds a key for 2 s at most), which the previous
  move made without them.

- **Update** — the operating lessons of the Display Actor session (CC6a), from
  bringing an edge host into production and from four framework pull requests:
  - [g_02_ClaudeCodeOperatingGuide.md](g_02_ClaudeCodeOperatingGuide.md)
    section 2: a deployed host has a production account and a development
    account, and an agent tests in a copy under `/tmp`. Section 9: six
    failure modes. They are a pattern as the target, an editable install
    that points elsewhere, a commit after the review push, a copy that
    carries its host's metadata, a verb that names no object, and a sharp
    edge that outlives its fix.
  - [g_03_AgentContext.md](g_03_AgentContext.md): the ECProducer encoding
    entry is removed, because incremental updates use `generate()` since
    2026-10-15. New entries: the ProcessManager does not relaunch a process
    that exits, and `CaptureLimit` has no unlimited mode.
  - [adr/ADR-002_SExpressionWireEncoding.md](adr/ADR-002_SExpressionWireEncoding.md):
    the ECProducer deviation is marked closed (2026-10-15).
  - [e_06_TestingStrategy.md](e_06_TestingStrategy.md): two rules. A timing
    test waits for its outcome, and the full suite runs on each target host.

- **Update** — the Display Actor's Epic 1 learning, brought up to date with the
  work that merged after it:
  - [adr/ADR-025_RemoteDisplayAbstraction.md](adr/ADR-025_RemoteDisplayAbstraction.md)
    decision 3: an amendment records that a `down` holds a key for 2 s at most
    (`KEY_DOWN_MAXIMUM`). A client that holds a key sends `down` again.
  - [adr/ADR-002_SExpressionWireEncoding.md](adr/ADR-002_SExpressionWireEncoding.md):
    the ProcessManager `(list ...)` reply is a fourth known deviation, closed
    the same day. An argument such as `8080:127.0.0.1:8080` was read as a
    length prefix.
  - [g_03_AgentContext.md](g_03_AgentContext.md): the Registrar entry no longer
    tells an operator to clear a stale announcement, because the s_00 §1.4
    liveness probe replaces it (since 2026-10-01). The `.local` IPv6 entry is
    removed, because the MQTT client tries IPv4 first and connects to the
    address that answered (2026-10-01). The two `remove_message_handler()`
    entries become one, which cites PR #55. A new entry: patch process-global
    state on its class, not on `aiko.process`.
  - [e_03_FirstClassAgents.md](e_03_FirstClassAgents.md) task T6 names the
    shape document, `documentation/actors/display/parameters_streams_shape.md`.
  - [e_06_TestingStrategy.md](e_06_TestingStrategy.md): the rule "Fixtures
    reset process-global state" cites `tests/unit/conftest.py`, which restores
    the event loop's timers and mailboxes after each unit test.

- **Update** — [../documentation/ReadMe.md](../documentation/ReadMe.md):
  the map gains the two areas it never listed, `quick_start_guide.md` and
  `tutorials/`, and a fast path for deploying an instance. A new tutorial,
  `tutorials/production_instance.md`, documents a 24x7 instance on Linux.
  One ProcessManager starts with the operating system, and it owns the
  Registrar, HyperSpace and the Aiko Chat Server. The same change marks the
  sanctioned private-directory reference in
  `tutorials/using_a_private_constitution.md`, which names the private
  repository's own map. The self-containment check now reports an exception
  there rather than a violation.

- **Update** — [adr/ADR-002_SExpressionWireEncoding.md](adr/ADR-002_SExpressionWireEncoding.md):
  the consequence that a value holding a space must round-trip through
  `generate()` now names each known deviation, and the helper that closes
  one. `utilities/parser.py:generate_symbol()` applies the canonical rule
  to a single value, for code that must assemble an expression itself.
  `Dependency.__repr__()` was a deviation, closed the same day: a
  `storage_url` holding a space broke every Category `(list ...)` response
  that carried it. `ServiceFilter.__repr__()` is still one, for its tags.

- **Update** — [s_00_Specifications.md](s_00_Specifications.md) section
  1.1: the canonical length prefix is extracted as a rule, which the
  section's `[VERIFY]` asks for. A value holding a delimiter, or beginning
  `digits:`, must carry the prefix. A reader counts more arguments than the
  writer sent otherwise, and loses the message with no error. The rest of
  the grammar stays open.

- **Update** — [g_02_ClaudeCodeOperatingGuide.md](g_02_ClaudeCodeOperatingGuide.md)
  section 9: a new failure mode. A code path that only a person can reach
  survives review, merge and a demonstration. Build the frame and draw it
  in the test. Evidence: a Dashboard dialog raised on its first draw,
  every time anyone pressed the key, for a widget whose value was never
  set.

- **Update** — [g_03_AgentContext.md](g_03_AgentContext.md): four sharp
  edges join the list. `ServiceFilter.__repr__()` does not escape its
  tags. `pipeline.py` declares no `FUNCTIONS`, so `create_stream()` takes
  its parameters from the message bus with no allow list. P12 / ADR-023 is
  not in force there. A `PopUpDialog` hides a widget that does not fit it,
  and a `Text` widget raises unless its value is set.

## 2026-11-01

- **Update** — [s_02_InterfaceComposition.md](s_02_InterfaceComposition.md): the
  `ProcessManager` entry records the functions the Interface declares. The entry
  named `spawn` and `terminate`, which it never had. `create` takes a fourth
  parameter, `cwd`. It is the working directory of the process. A Service that
  finds its state by the working directory cannot start any other way.
  HyperSpace file Storage is such a Service, and so is the Chat server that
  embeds one. Reference implementation
  `src/aiko_services/main/process_manager.py`.

## 2026-10-30

- **Update** — [g_02_ClaudeCodeOperatingGuide.md](g_02_ClaudeCodeOperatingGuide.md)
  section 9: each failure mode is compressed to the constitution register
  (project-lead direction). The rule comes first. The narration around it is
  gone. Three defects go with the compression. The `Agent-claimed "done"` and
  `D starving` entries shared one paragraph, so neither read as a rule of its
  own. The `inherited diagnosis` entry now names a note, a memory and a
  session summary as handovers. A wrong mechanism reached this session from a
  memory file. `A guard that refuses everything` says `function`, which is
  the framework's word, not `command`.

## 2026-10-26

- **Update** — [s_01_RepositoryLayout.md](s_01_RepositoryLayout.md): the
  Dashboard moved again, to `ide/tui/dashboard/`, and an `ide/` tier joins
  the tree. The Dashboard is a development environment for a person, not
  an Actor tier Service, so `actors/dashboard/` of 2026-10-23 was the
  wrong home (project-lead direction). Migration step 5 is amended,
  because `dashboard` is no longer part of the Actor split. The root
  `__init__.py` facade re-exports the plug-in interface, so `main/`
  imports neither tier. The move is two commits, as
  [g_02_ClaudeCodeOperatingGuide.md](g_02_ClaudeCodeOperatingGuide.md)
  section 9 directs, so git keeps the history of each file through a
  second move.

## 2026-10-23

- **Update** — [s_02_InterfaceComposition.md](s_02_InterfaceComposition.md): the `Registrar`
  entry records that a `history` record appends `time_add` and `time_remove`, both
  `time.monotonic()`, so a reader accepts six fields or more. Giving the Registrar a
  wall-clock record of each Service is deferred, because the design needs the Registrar to
  be the one source of that time. Reference implementation
  `src/aiko_services/main/registrar.py`.
- **Update** — [s_02_InterfaceComposition.md](s_02_InterfaceComposition.md): the `Recorder`
  entry amended. It refines `Actor`, and its functions are `record_start(topic_filter)` and
  `record_stop(topic_filter)`, because `stop` is the framework's control verb. Reference
  implementation `src/aiko_services/main/recorder.py`.
- **Update** — [s_01_RepositoryLayout.md](s_01_RepositoryLayout.md): migration step 5's
  `dashboard` move, done ahead of the other steps. The root façade re-exports the plug-in
  interface, so `main/` does not import `actors/`.
- **Update** — [s_02_InterfaceComposition.md](s_02_InterfaceComposition.md):
  the `FunctionGate` aspect joins the runtime Interface list. It holds which
  functions a Service accepts from the message bus (P12, ADR-023). `Actor`
  composes it, and its default allows every function, so no Service changed
  behavior. `interface_functions()` removes what `Actor` and `Service`
  declare, which enforces ADR-025 decision 1. ADR-023 holds the
  deny-by-default decision, so the aspect needs no ADR of its own. Reference
  implementation `src/aiko_services/main/function_gate.py`.
- **Update** — [adr/ADR-025_RemoteDisplayAbstraction.md](adr/ADR-025_RemoteDisplayAbstraction.md)
  decision 1, amended: function name aliases are dropped, so one function has
  one name and a client that sends `(oled:text ...)` or `(exit)` is denied. A
  client of the MicroPython `aiko_engine_mp` vocabulary must send the plain
  names. Registry row 025 records the amendment. Reference implementation
  `src/aiko_services/main/function_gate.py`.
- **Update** — [g_02_ClaudeCodeOperatingGuide.md](g_02_ClaudeCodeOperatingGuide.md)
  section 9: three failure modes from the aiko01 WhisPlay Actor work, 2026-10-22
  and 2026-10-23. A deny-by-default guard that called a function which does not
  exist, with refusal tests that all passed. Three conclusions drawn from broken
  measurements. A vendor driver read for its constants and not for its comments.
  The machine-specific findings stay out of this tree.

## 2026-10-21

- **Creation** — [adr/ADR-026_DaemonSupervision.md](adr/ADR-026_DaemonSupervision.md):
  the operating system starts one daemon for each host, the ProcessManager, and
  the ProcessManager definition file starts the rest. A `DaemonSupervisor`
  Interface has one Implementation for each platform, `render` changes nothing
  and `install` is the only privileged operation. The Interface stays off the
  message bus for now. Supervisor as an aspect is recorded as the direction, with
  the authority question that composition must answer. Registry row 026
  claimed in the same change (024 stays reserved). Reference implementation
  `src/aiko_services/main/daemon_supervisor/`.

- **Update** — [g_02_ClaudeCodeOperatingGuide.md](g_02_ClaudeCodeOperatingGuide.md)
  section 9: three failure modes from the aiko01 WhisPlay HAT audio work,
  2026-10-20. An inherited diagnosis that named the symptom and guessed the
  mechanism. An output file that nothing writes any more. A recovery path never
  exercised against the real fault. The machine-specific findings stay out of
  this tree.

## 2026-09-27

- **Creation** — [adr/ADR-025_RemoteDisplayAbstraction.md](adr/ADR-025_RemoteDisplayAbstraction.md):
  the `display:0` composite of three aspect Interfaces. Aspects as tags,
  the key map on the device, settings as one declaration, and a bounded
  leased frame mirror. Registry row 025 claimed in the same change (024
  stays reserved). Reference implementation `src/aiko_services/actors/display/`.
- **Update** — [s_01_RepositoryLayout.md](s_01_RepositoryLayout.md): the
  `actors/` tier has its first package, `actors/display/`. It moved from
  `examples/oled/`, because a design that must ship lives under `actors/`.
  Shipped tests import only shipped packages.
- **Update** — [s_02_InterfaceComposition.md](s_02_InterfaceComposition.md):
  a default Implementation registered for several Interfaces works without
  its own constructor. Evidence: the display outputs seam.
- **Update** — [s_00_Specifications.md](s_00_Specifications.md) §1.3 and
  §1.4: several protocol ids per Service (aspects as tags until then), and
  the Registrar liveness probe for a stale retained announcement.
- **Update** — [p_02_CandidatePrinciples.md](p_02_CandidatePrinciples.md):
  evidence for CP-A and CP-F from the Display Actor. New candidate CP-M,
  "capabilities are advertised, not assumed". Letter registered in t_03.
- **Update** — [g_03_AgentContext.md](g_03_AgentContext.md): the `actors/`
  map entry and five sharp edges found by the display work.
- **Update** — [e_06_TestingStrategy.md](e_06_TestingStrategy.md): the
  power-cycle Registrar scenario, fixtures reset process-global state,
  broker-backed tests need a CI broker.
- **Update** — [e_03_FirstClassAgents.md](e_03_FirstClassAgents.md) T6:
  the Display Actor's settings and mirror are the pilot for the
  Parameter/Stream extraction.
- **Update** — [t_03_IdentifierGlossary.md](t_03_IdentifierGlossary.md):
  CP-M registered. The protocol/Interface naming rule (`display:0`,
  `Display`, "the Display Actor").
- **Update** — [g_02_ClaudeCodeOperatingGuide.md](g_02_ClaudeCodeOperatingGuide.md)
  §9 and [g_01_ReleaseProcessGuide.md](g_01_ReleaseProcessGuide.md) §7.2:
  gate a moving document once at the end of an Epic, a package move is
  three commits, the wheel check for excluded imports.
  All directed by the project lead from the display work's session.

## 2026-09-02

- **Update** — [g_01_ReleaseProcessGuide.md](g_01_ReleaseProcessGuide.md):
  v0.8 release learnings — hardened test baseline [hatch run test, pytest
  pinned to the unit suite], CI matrix Python 3.9–3.14 plus tag-push runs,
  per-release documentation artifacts, concrete announcement channels, a
  "scope frozen" checklist item, and the v0.8 sharp edges. Prepared
  2026-08-28 by the v0.8 release session; promoted from the private
  pending queue after the matrix itself went live on master.

## 2026-09-01

- **Creation** — [adr/ADR-003_UidAddressSpaces.md](adr/ADR-003_UidAddressSpaces.md):
  HyperSpace/Storage UID address-space allocation — 48-bit MAC-style
  spaces, class-octet / identity-octets split, space-fill extension
  embedding rule. Number claimed from the registry in the same change;
  shared specification with the CRC-cards session.
- **Update** — .constitution-guard: added the personal-note case-variant
  patterns [zZ]_* and [zZ][zZ]*_*, at top level and at depth, and the
  matching ignore rules are committed in the same change [.gitignore].
  The multi-z form deliberately needs an underscore, so ordinary files
  that merely start with "zz" are never swept up. Evidence: ZZ-prefixed
  personal notes found uncovered by the 2026-08-31 cleanup.

## 2026-08-31

- **Creation** — [diagrams/ReadMe.md](diagrams/ReadMe.md): index for the
  three architecture diagrams with rendered-view links, because GitHub
  shows raw HTML source rather than the diagram output. The Related
  section of [ReadMe.md](ReadMe.md) now points at it.

## 2026-08-27

- **Creation** — the constitution goes public. The governance corpus moved
  from an untracked internal tree to this top-level `constitution/`
  directory: principles (p_00–p_02), specifications and design (s_00–s_05),
  plans (e_00, e_03, e_06), guides (g_01–g_04),
  analysis (a_00), templates (t_00–t_03), the ADR registry with ADR-002,
  ADR-021–ADR-023, and three architecture diagrams. Forward-looking and
  commercially sensitive material remains in the private constitution and
  promotes here through the governance process. Reserved numbers and
  "[Privately maintained]" markers show where. The `.constitution-guard`
  denylist, the pre-commit and pre-push guards, and the self-containment
  check (zero violations at first publication) took effect in the same
  change. Directed and approved by the project lead.
