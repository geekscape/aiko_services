# Constitution journal (public)

The dated journal of changes to the public constitution tree, newest first.
Every substantive change appends an entry under its date heading
(`**Creation**` / `**Update**` bullets). Typo-level fixes are exempt.
This journal begins at the constitution's first public release. The
pre-publication history is maintained privately.

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
