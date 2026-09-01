---
title: "Aiko Services: Release Process Guide"
description: How to release Aiko Services end-to-end — test, update the
  documentation and constitution, write the release notes, bump the version,
  tag, clean-clone build, token-based publish to PyPI, GitHub release page,
  release announcements and post-release fixes
type: guide
audience: [project-lead, ai-coding-agents]
status: operational
ste: adapted
related: [g_03_AgentContext, e_06_TestingStrategy]
last_updated: 2026-07-31
---

# Aiko Services: Release Process Guide

**Goal:**

Release a new version of Aiko Services to
[PyPI](https://pypi.org/project/aiko_services) reliably and repeatably.
This guide records the process as it was done for the v0.7 release
(2026-07-06), including the sharp edges discovered along the way.

**Status:**
Document g_01_ReleaseProcessGuide. Operational. Revise it as each release teaches.

---

## 1. The release process in one paragraph

A release is eight steps, in this order:

1. **Test** the release.
2. **Update the documentation and constitution.**
3. **Write the release notes.**
4. **Update the version identifier and date** (in *two* files).
5. **Tag** the local and the remote repository.
6. **Build and publish** to PyPI. Build from a *fresh git clone*, never
   from a development working tree. Use Hatch and an API token.
7. **Update the GitHub release web-page.**
8. **Announce** the release to the downstream users of Aiko Services and
   to the AI + ML + Robotics community.

PyPI releases are immutable. You can never overwrite or upload a
published file again. Thus you correct a mistake with a `X.Y.postN`
post-release. Never "fix" the original.

---

## 2. Step 1: Test the release

Test *before* touching versions, tags or packages — everything after this
step assumes the code being released works.

- Run the unit test suite on the primary development Python version, and
  confirm GitHub Actions Continuous Integration (Python *flake8* critical
  checks) is green on `master`
- Aiko Services supports Python 3.9.7 through 3.14.2 (see
  `pyproject.toml`). Spot-check the oldest and the newest supported versions
  when the release touches the runtime core
- Manually exercise the core distributed system: `mosquitto`,
  `aiko_registrar`, `aiko_dashboard` (`scripts/system_start.sh`), the
  `examples/aloha_honua/` Actors and a representative Pipeline
- Formal release test gates (conformance traces, golden traces) are being
  defined in [Testing Strategy](e_06_TestingStrategy.md). As those land,
  they become mandatory here.  `hatch test` in the top-level `ReadMe.md`
  remains "to be completed"

---

## 3. Step 2: Update the documentation and constitution

Bring the documentation up to date with what actually ships, *before*
writing the release notes (the notes then describe a finished release).

- Update the tracked `documentation/` tree for features shipping in the
  release: [concepts guide](../concepts/ReadMe.md),
  [PipelineElements guide](../elements/ReadMe.md),
  [examples guide](../examples/ReadMe.md) and the top-level `ReadMe.md`
  (Features, Documentation, Examples sections)
- Append the change to the [directory update log](../log.md) in the same
  change, per the standing rule
- Fold release-process lessons into *this* guide and the top-level
  `ReadMe.md` "Installing for package maintainers" section
- Note: the public constitution tree (`constitution/`) is tracked and
  ships with the release. The private constitution is maintained in its
  own repository and is never part of a public release. The
  `.constitution-guard` denylist and the guard hooks enforce the boundary

---

## 4. Step 3: Write the release notes

`documentation/release_notes.md` is a single Open Knowledge Format (OKF)
document holding the notes for *all* releases, most recent first.  Its
structure is ...

```markdown
---
title: Aiko Services release notes
description: Release notes for each Aiko Services version — GitHub full
  changelog link, features, testing and bug fixes — most recent release
  first
type: release-notes
audience: [developers, end-users]
status: operational
version: "<latest release, e.g 0.7>"
last_updated: <YYYY-MM-DD of latest release>
---

# Aiko Services release notes

<one-sentence intro>

---

## Release Notes vX.Y      <-- new release: insert here, above previous

### Features

### Testing

### Bug Fixes

---

## Release Notes vX.Y-1
...
```

For each release, in the same edit ...

1. Insert a new `## Release Notes vX.Y` section (with a `---` horizontal
   rule separator) *above* the previous release's section
2. Bump the front-matter `version` and `last_updated` fields to match

Content of the new section, in the established style ...

- **Full Changelog** link, for example
  `https://github.com/geekscape/aiko_services/compare/v0.6...v0.7`
- **`### Features`** — review the complete `git log vPREV..HEAD`, then
  select, group and summarize by theme.  A large theme (for example Pipeline
  improvements) becomes one bullet with a nested sub-list.  Flag API /
  import breaks in **bold**.  Omit WIP iterations, version-bump commits
  and typo fixes — the Full Changelog link covers those
- **`### Testing`** — supported Python version range, CI, new test
  capabilities
- **`### Bug Fixes`** — including community PR numbers, for example
  (PR#42, PR#45)

Note: the heading levels matter. Use one `#` document title only. Each
release is `##` and its Features / Testing / Bug Fixes subsections are
`###`, so the file remains a single well-formed OKF document.  Do not
start the body with a bare `---` line, which would be misread as
front-matter.

The project lead reviews the release notes before the release continues.
The notes are used again, word for word, for the GitHub release web-page
(step 7). They are also the source for the announcement highlights
(step 8).

---

## 5. Step 4: Update the version identifier and date

### 5.1 Version bump — two files, always both

| File | Field | Example (v0.7) |
|------|-------|----------------|
| `src/aiko_services/__init__.py` | `__version__` | `"v0.7"` |
| `src/aiko_services/__init__.py` | `__id__` | `"2026-07-06_a"` |
| `pyproject.toml` | `version` | `"0.7"` |

**Sharp edge:** `pyproject.toml:version` is static and is what Hatch uses
for the package version.  It is *not* derived from `__init__.py`.  During
the v0.7 release the tag was applied first, before the `pyproject.toml`
bump. That sequence would have built and published as 0.6. The tag had
to be
force-moved (`git tag -fa v0.7 <commit>` then
`git push origin v0.7 --force`).  Bump both files *before* tagging.

---

## 6. Step 5: Tag the local and remote repository

Commit the release preparation (version bump plus release notes), push,
then tag the commit that contains *both* version bumps and push the tag ...

```
git add src/aiko_services/__init__.py pyproject.toml  \
        documentation/release_notes.md
git commit    # descriptive release-preparation commit message
git push      # manual: performed by the project lead
git tag -a v0.7 -m "Release version v0.7: 2026-07-06_a"
git push origin v0.7
```

Note: the project lead always does `git push` manually. AI coding agents
prepare commits, but they never push.  The tag message repeats
the `__id__` date. Make sure that it agrees with `__init__.py` (the v0.7 tag initially
carried a typo'd date and had to be force-retagged).

---

## 7. Step 6: Build and publish the release on PyPI

### 7.1 Build — always from a fresh clone

**Sharp edge:** Hatch bundles *all* directory contents into the package,
including untracked local files.  Building v0.7 from the development
working tree produced a 36 MB wheel containing local test videos
(`data_in/`, `data_230/`, `data_231/`) and scratch back-up copies
(`pipeline.py_*`, `hyperspace.py_0`, ...).  The correct wheel is ~300 KB.
Never build from a working tree. Always build from a fresh `git clone` ...

```
git clone https://github.com/geekscape/aiko_services.git aiko_services_release
cd aiko_services_release
python3 -m venv venv
source venv/bin/activate
pip install -U pip hatch
hatch build   # produces dist/*.whl and dist/*.tar.gz
```

### 7.2 Verify the build before publishing

```
ls -la dist/                          # wheel and sdist well under 1 MB
unzip -l dist/aiko_services-*.whl     # ~126 files: source code plus a few
                                      # small sample data files, nothing else
```

If the wheel is more than ~1 MB or contains media files or back-up
copies, the build is contaminated — do not publish it.

### 7.3 Publish — API token only

PyPI no longer supports username / password uploads (they fail with
`403 Forbidden`).  To publish needs a
[PyPI API token](https://pypi.org/manage/account/token/), preferably
scoped to the *aiko-services* project only ...

```
HATCH_INDEX_USER=__token__ HATCH_INDEX_AUTH=pypi-YOUR_API_TOKEN  \
    hatch publish dist/
```

Note: `hatch build` only builds. `hatch publish` uploads.  (The v0.6-era
ReadMe conflated the two.)

### 7.4 Verify the release is live

```
curl -s https://pypi.org/pypi/aiko-services/X.Y/json | python3 -m json.tool
```

... or simply visit `https://pypi.org/project/aiko-services/X.Y/` and
check the version, description and file sizes.

---

## 8. Step 7: Update the GitHub release web-page

Turn the pushed `vX.Y` tag into a published GitHub Release. Then the
release appears on the "Releases" page of the repository and in the
releases Atom feed. It also notifies each person who watches the
repository for releases.

Through the web interface:
[github.com/geekscape/aiko_services/releases](https://github.com/geekscape/aiko_services/releases)
→ *Draft a new release* → *Choose a tag*: select the existing `vX.Y` tag
(do not create a new one) → *Release title*: `Aiko Services vX.Y` →
paste the release's `## Release Notes vX.Y` section body from
`documentation/release_notes.md` (the Full Changelog link and the
Features / Testing / Bug Fixes subsections) → *Publish release*.

Or through the GitHub CLI, extracting the section from the release notes ...

```
gh release create vX.Y --verify-tag  \
    --title "Aiko Services vX.Y"     \
    --notes-file release_vX.Y_notes.md   # the extracted vX.Y section body
```

Notes ...

- The GitHub Release body renders standalone, so the pasted section works
  without a change. Leave the heading levels unchanged (`###` subsections)
- Do not attach the wheel / sdist as release assets — PyPI is the single
  distribution channel. The tag gives the source snapshot
- To publish a GitHub Release is outward-facing. It is done by the project
  lead, or by an agent only with explicit per-release confirmation

---

## 9. Step 8: Announce the release

Inform (a) all downstream users of Aiko Services and (b) the broader
AI + ML + Robotics community that the new release has been published.

**Audiences ...**

- Downstream users: dependent projects and repositories (for example Aiko Engine,
  Aiko Chat and other Aiko sub-systems), plus anyone installing or
  pinning the PyPI package.  GitHub Release watchers (step 7) are
  notified automatically. You contact the other known downstream users
  directly
- Community: the AI + Machine Learning + Robotics community channels
  where Aiko Services participates

**Announcement content** (draft from the release notes) ...

- Version, release date and a one-sentence positioning line
- Two or three headline features (from `### Features`), plus any
  **breaking change** called out explicitly
- Upgrade command: `pip install -U aiko_services`
- Links: GitHub Release page, `documentation/release_notes.md`, PyPI
  project page and the Full Changelog compare link

**Channel list** — the project lead maintains it here. Extend it as
channels are adopted ...

| Channel | How | Status |
|---------|-----|--------|
| GitHub Release page | Automatic notification to release watchers (step 7) | operational |
| Known downstream projects | Direct message / issue to each dependent repository | operational |
| Social media (for example LinkedIn, Mastodon, X) | Post the announcement content | per release, project lead |
| Community meet-ups and conferences (for example Everything Open, PyCon AU, microPython meet-up Melbourne) | Mention at the next relevant session | opportunistic |
| Mailing list / chat (Discord, Slack, ...) | To be established | placeholder |

Announcements are outward-facing publications. An AI coding agent may
*draft* the announcement text. Only the project lead sends and posts it.

---

## 10. Correcting a published release

PyPI releases are **immutable by design** (an anti-supply-chain-attack
guarantee).  Once `aiko_services-0.7.tar.gz` is uploaded, that filename is
permanently reserved — deleting the release does *not* allow re-upload.

- **Never** try to overwrite or erase-and-upload-again a version
- Deleting a version outright breaks users who pinned `==X.Y` — avoid
- Metadata-only mistakes (for example a typo in the ReadMe, which becomes the
  PyPI project description): either leave it until the next release, or
  publish a post-release
- **Post-release** is the standard correction: bump `pyproject.toml` to
  `version = "X.Y.postN"`, commit, tag `vX.Y.postN`, then build and
  publish as above.  `pip install aiko_services` prefers `X.Y.postN`
  over `X.Y`. The v0.6 cycle used this heavily (`v0.6.post1` ... `post35`)
- A GitHub Release (step 7) *can* be edited after publishing — fixing its
  page text is safe and does not affect PyPI

Also note: the PyPI project page renders the description from the
*uploaded package metadata*, not from GitHub. To correct `ReadMe.md` on
GitHub does not change the PyPI page of a version already published.

---

## 11. Release checklist

1. [ ] Tests pass: unit tests locally, GitHub Actions CI green on
       `master`, core examples exercised manually
2. [ ] Documentation updated for shipping features: `concepts/`,
       `elements/`, `examples/` guides and the top-level `ReadMe.md`.
       `constitution/log.md` entry appended
3. [ ] Constitution updated with any process or design lessons —
       public lessons in `constitution/` with a `constitution/log.md`
       journal entry, private lessons in the private constitution
4. [ ] `documentation/release_notes.md` new `## Release Notes vX.Y`
       section written and reviewed by the project lead ... and OKF
       front-matter `version` and `last_updated` fields bumped
5. [ ] `__version__` and `__id__` updated in `src/aiko_services/__init__.py`
6. [ ] `version` updated in `pyproject.toml` (Hatch uses this one)
7. [ ] Committed and pushed (push is manual, by the project lead)
8. [ ] Annotated tag `vX.Y` on the commit that contains *both* version
       bumps. The tag message date agrees with `__id__`. The tag is pushed
9. [ ] Fresh `git clone`, then `hatch build`
10. [ ] Wheel verified: well under 1 MB, source only
11. [ ] Published with `hatch publish dist/` using `__token__` + API token
12. [ ] Live release verified on pypi.org
13. [ ] GitHub Release published from the `vX.Y` tag with the release
        notes section as its body
14. [ ] Release announced to downstream users and the AI + ML + Robotics
        community per the channel list
15. [ ] Any process lessons learned folded back into this guide and the
        top-level `ReadMe.md` "Installing for package maintainers" section

---

## 12. Related documentation

- Top-level `ReadMe.md` — "Installing for package maintainers" section
  (the public, condensed form of step 6)
- `documentation/release_notes.md` — the release notes themselves
- [Testing Strategy](e_06_TestingStrategy.md) — the formal test gates
  that will back step 1 as they land
- [Claude Code Operating Guide](g_02_ClaudeCodeOperatingGuide.md) — the
  broader operating model within which releases happen
