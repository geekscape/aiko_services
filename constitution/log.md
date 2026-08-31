# Constitution journal (public)

The dated journal of changes to the public constitution tree, newest first.
Every substantive change appends an entry under its date heading
(`**Creation**` / `**Update**` bullets). Typo-level fixes are exempt.
This journal begins at the constitution's first public release. The
pre-publication history is maintained privately.

## 2026-09-01

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
