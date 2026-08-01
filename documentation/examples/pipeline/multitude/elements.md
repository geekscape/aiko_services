---
title: Multitude alias elements
description: PE_A0 / PE_B0 / PE_C0 and PE_000 .. PE_090 — empty
  subclasses of PE_Add that give remote-deployed PipelineElements the
  class names the multitude PipelineDefinitions need
type: concept
audience: [developers, end-users]
status: draft
ste: adapted
source:
  - src/aiko_services/examples/pipeline/multitude/elements.py
related: [pipeline_element, pipeline, elements]
version: "0.6"
last_updated: 2026-08-01
---

# Multitude alias elements

## Overview

`multitude/elements.py` contains no behavior at all — thirteen empty
subclasses of
[`PE_Add`](../elements.md):

```python
from aiko_services.examples.pipeline.elements import PE_Add

# pipeline_small_*.json
class PE_A0(PE_Add): pass
...
# pipeline_large_*.json
class PE_000(PE_Add): pass
...
class PE_090(PE_Add): pass
```

The classes exist, per the source comment, "to workaround a
short-coming in the PipelineElement Definition for `"deploy":"remote"`
PipelineElements". A **local** deployment can alias any class to any
graph node name through `deploy.local.class_name`. The
[multitude PipelineDefinitions](ReadMe.md) do exactly that for their
local `PE_Add` nodes. A **remote** deployment has no `class_name`
field. The *node name* inside `deploy.remote.module` resolves the
proxy. Thus a node name used as a remote proxy must exist in this
module, as a real class of that name.

**Why to use it**: as the pattern to copy when your own
PipelineDefinition needs a remote PipelineElement whose node name does
not match an existing class.

## For application developers

### Command-line usage

Nothing here is run directly — the module is named as the
`deploy.remote.module` of the chained multitude Pipelines, for example, in
`pipeline_small_a.json`:

```json
{ "name":   "PE_B0",
  "input":  [{ "name": "i", "type": "int" }],
  "output": [{ "name": "i", "type": "int" }],
  "deploy": {
    "remote": {
      "module": "aiko_services.examples.pipeline.multitude.elements",
      "service_filter": {
        "topic_path": "*", "name": "p_small_b",
        "owner": "*", "protocol": "*", "transport": "*", "tags": "*"
      }
    }
  }
}
```

See [multitude/ReadMe](ReadMe.md) for the `run_*.sh` driver scripts
that start the Pipelines.

### Public API

| Class | Used as remote proxy by | Behavior |
|-------|-------------------------|-----------|
| `PE_A0` | (none — defined for symmetry) | inherited `PE_Add` |
| `PE_B0` | `pipeline_small_a.json` → `p_small_b` (and the tiny variant) | inherited `PE_Add` |
| `PE_C0` | `pipeline_small_b.json` → `p_small_c` | inherited `PE_Add` |
| `PE_000` | (none — defined for symmetry) | inherited `PE_Add` |
| `PE_010` .. `PE_090` | `pipeline_large_0N0.json` → `p_large_0(N+1)0` | inherited `PE_Add` |

All inherit `PE_Add` unchanged: protocol `add:0`, input `i` → output
`i`, parameters `constant` (default 1) and `delay` (default 0
seconds). See [Pipeline example elements](../elements.md#pe_add).

## For framework developers (internals)

### Design

The remote-deploy resolution rule is the whole story:

```
pipeline_small_a.json                    multitude/elements.py
graph node "PE_B0"
  deploy.remote.module ---------------> class PE_B0(PE_Add): pass
  deploy.remote.service_filter                   |
    name: "p_small_b" --> discovery --> p_small_b Pipeline (remote)
```

The local `deploy.local.class_name` indirection is deliberately *not*
used here for remote nodes, because the remote deploy schema does not
offer it. Instead the node-name namespace (`PE_B0`, `PE_010`, ...) is
materialized as Python classes. Removing this module would break every
remote hop in the multitude examples.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `PE_A0` / `PE_B0` / `PE_C0` | Give `PE_Add` under the small-chain remote node names | [`PE_Add`](../elements.md), [PipelineElement](../../../concepts/pipeline_element.md) |
| `PE_000` .. `PE_090` | Give `PE_Add` under the large-chain remote node names | [`PE_Add`](../elements.md), [Pipeline](../../../concepts/pipeline.md) remote deploy |

## Current limitations and roadmap

- The module exists only because `deploy.remote` lacks a `class_name`
  field — if the PipelineDefinition schema gains one, these thirteen
  classes become unnecessary. No To Do list is recorded in the source.
- `PE_A0` and `PE_000` are never referenced by any `deploy.remote`
  entry (the chain heads are always deployed locally). They are
  defined only to keep the naming pattern complete.

## Related concepts

- [Pipeline example elements](../elements.md) — `PE_Add`, the single
  behavior behind all of these names
- [multitude/ReadMe](ReadMe.md) — the PipelineDefinitions and driver
  scripts that use these classes
- [Pipeline](../../../concepts/pipeline.md) — local versus remote
  deployment in the PipelineDefinition
- [PipelineElement](../../../concepts/pipeline_element.md) — the
  underlying element contract
