# Constitution journal (public)

The dated journal of changes to the public constitution tree, newest first.
Every substantive change appends an entry under its date heading
(`**Creation**` / `**Update**` bullets). Typo-level fixes are exempt.
This journal begins at the constitution's first public release. The
pre-publication history is maintained privately.

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
