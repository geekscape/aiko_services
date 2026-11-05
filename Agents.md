# Aiko Services: Agent instructions

The constitution lives in the top-level `constitution/` directory — in
particular `g_03_AgentContext.md` ("Conventions an agent must follow") and
`g_02_ClaudeCodeOperatingGuide.md`. Read those for architecture, coding
conventions and known sharp edges. The `.constitution-guard` denylist and
the git guard hooks are constitutional: never bypass them.

## Conventions

- **Naming:** always write "Aiko Services" in full — never abbreviate to
  "Aiko". Other Aiko sub-system and application concepts exist (e.g. Aiko
  Engine, Aiko Chat), often in other Git repositories, so the bare "Aiko"
  is ambiguous.
- **ReadMe files:** always name them `ReadMe.md` (CamelCase style), not
  `README.md`.
- **Date and time:** store and publish in UTC. Display in local time.
  Local time is the default everywhere a person reads a date/time: a
  terminal interface, a command's output, a graph, a report. It is what
  they compare against the clock on their own wall. A tool that shows
  date/times offers `--utc` for the stored form, which is what comparing
  hosts in different zones needs. `display_time()` in
  `main/utilities/utc_iso8601.py` is the one conversion. It leaves
  anything that is not a date/time with an offset exactly as it is.
  Display is the only place it applies. A date/time in JSON, in an
  S-expression, in a file name, or in a message on the bus is data, and
  it stays UTC. A reader parses it, and a machine's zone must not change
  what it reads.
- **STE:** when writing plans or documentation, use ASD-STE100 Simplified
  Technical English (STE) at the level the document's `ste:` front-matter
  field declares. Rules digest, project profile and global switch:
  the project STE profile [Privately maintained].
  Dictionary: `documentation/z_asd-ste100-issue-9.pdf` (local licensed <!-- future-ref-ok: never-commit instruction for a local-only licensed file -->
  copy — never commit it). American English spelling.
