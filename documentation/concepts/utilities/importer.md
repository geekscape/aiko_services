---
title: Importer utility
description: Dynamic module loading — by file pathname or dotted module
  name, with caching — used to load PipelineElements, Components and
  Dashboard plugins at runtime
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/importer.py
related: [design_overview]
version: "0.6"
last_updated: 2026-07-05
---

# Importer utility

## Overview

The importer utility loads Python modules chosen at *runtime* rather than
import time: a module descriptor is either a source pathname
(`directory/file.py`) or an installed dotted module name
(`package.module`). Loaded modules are cached, so repeated loads of the
same descriptor return the same module object. This is how Aiko Services
achieves late binding everywhere — Pipeline definitions, Interface
default implementations and Dashboard plugins all name their code as
strings resolved by `load_module()`.

**Why you'd use it**: a Pipeline definition file names each
PipelineElement's module, and the Pipeline loads it on demand:

```python
from aiko_services.main.utilities import load_module

module = load_module("aiko_services.elements.media.image_io")
element_class = getattr(module, "ImageReadFile")
```

## For application developers

### Command-line usage

There is no CLI; the module is exercised whenever `aiko_pipeline create`
loads the PipelineElements named in a Pipeline definition, and by
`aiko_dashboard` when loading Service page plugins.

### Public API

```python
load_module(module_descriptor)    # "dir/file.py" or "package.module"
load_modules(module_pathnames)    # list version; None entries pass through
```

Real call sites:

```python
# src/aiko_services/main/pipeline.py — load a PipelineElement's module
module = load_module(module_descriptor)
element_class = getattr(module, element_name)

# src/aiko_services/main/component.py — Interface default implementations
module = load_module(module_name)

# src/aiko_services/main/dashboard.py — optional Dashboard plugin
module = load_module(plugin_name) if plugin_name else None
```

Set `AIKO_IMPORTER_USE_CURRENT_DIRECTORY` (any non-empty value) to append
the current working directory to `sys.path` at import time, so dotted
module names can resolve against modules in the directory where the
process was started.

## For framework developers (internals)

### Design

```
   "dir/file.py" ──► SourceFileLoader("module", path).load_module()
                                                        │
   "pkg.module" ──► importlib.import_module(name)       │
                                                        ▼
                    MODULES_LOADED[descriptor] ◄── cache (per descriptor)
```

The descriptor's `.py` suffix selects the loading strategy. The cache is
keyed by the *descriptor string*, so `"a/b.py"` and an equivalent
absolute path are cached separately.

### Implementation notes

- The pathname branch uses the long-deprecated
  `SourceFileLoader(...).load_module()` API (deprecated in favour of
  `exec_module()` and slated for removal from CPython) — a migration
  hazard when moving to newer Python versions.
- Every pathname-loaded module is registered in `sys.modules` under the
  fixed name `"module"`, so loading a second file clobbers the first's
  `sys.modules` entry. The `MODULES_LOADED` cache keeps the module objects
  themselves distinct, but tooling that inspects `sys.modules` sees only
  the last one.
- There is no unload/reload support; a changed source file requires a
  process restart.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| *module* `importer` | Resolve a module descriptor to a loaded, cached Python module; optional CWD on `sys.path` | `importlib`; `pipeline.py`, `component.py`, `dashboard.py` (consumers) |

## Current limitations and roadmap

- The source `To Do` list is empty ("None, yet !") — but the deprecated
  `load_module()` API and the fixed `"module"` name (see Implementation
  notes) are worth recording as latent issues
- No unit tests anywhere in the repository
- The cache never invalidates — deliberate, but undocumented in the
  source header

## Related concepts

- [Design overview](../design_overview.md) — late binding of
  implementations is a core Aiko Services idiom, and this module is its
  mechanism
