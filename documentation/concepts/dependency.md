---
title: Dependency
description: A reference to a distributed Service — discovery filter,
  LifeCycleManager URL and Storage URL — the Component of the Composite pattern
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/dependency.py
related: [design_overview, category, hyperspace, storage, process_manager]
version: "0.6"
last_updated: 2026-07-05
---

# Dependency

## Overview

A **Dependency** is a *reference* to a distributed Service — a Service,
Actor, Agent, PipelineElement or Pipeline. It is the atom of the Aiko
Services structural model: the *Component* (leaf) of the Composite pattern,
where [Category](category.md) is the *Container* and
[HyperSpace](hyperspace.md) is the root.

Think of a Dependency the way you would think of a symbolic link or a URL:
it names and locates something without *being* that something, and it
remains valid whether or not the target currently exists. Alongside the
discovery filter (**what** to find), a Dependency carries two URLs saying
**who** manages the target's lifecycle and **where** its definition is
persisted.

**Why you'd use it**: to describe system structure independently of what is
currently running. For example, an application that consumes a camera feed
records a Dependency on "any Service named `camera_0`" rather than a
hard-wired host and port — the camera Service can move hosts, restart, or
not exist yet, and the reference stays valid and (in the planned lifecycle
loop) can even cause the camera Service to be started on demand:

```python
dependency = compose_instance(DependencyImpl, dependency_args(
    None, ServiceFilter("*", "camera_0", "*", "*", "*", "*"), None, None))
```

## For application developers

### Command-line usage

Dependency has no CLI of its own. Dependencies are created, listed, updated
and removed through the [Category](category.md), [HyperSpace](hyperspace.md)
and [Storage](storage.md) CLI commands, e.g.

```bash
aiko_hyperspace add agents/llm_gemma -p '*' -o andyg -t model=gemma4
```

### Public API

`Dependency` is a plain `Interface` (not an Actor — a Dependency has no
independent network presence; it lives inside a Category or other owner):

```python
class Dependency(Interface):
    Interface.default("Dependency",
        "aiko_services.main.dependency.DependencyImpl")

    @abstractmethod
    def get_type(self): ...           # returns "dependency"

    @abstractmethod
    def is_type(self, type_name): ... # case-insensitive type check

    @abstractmethod
    def update(self, entry_name, service=None, service_filter=None,
        lifecycle_manager_url=None, storage_url=None): ...
```

Construction uses the standard Aiko Services composition machinery.
Creating a Dependency that will match any Service named `my_service`:

```python
from aiko_services.main import *

service_filter = ServiceFilter(          # used for Service discovery
    "*",            # topic_path: any
    "my_service",   # service name
    "*",            # protocol:   any
    "*",            # transport:  any
    "*",            # owner:      any
    "*")            # tags:       any

init_args = dependency_args(
    None,           # service: not yet discovered
    service_filter,
    None,           # lifecycle_manager_url  (TODO: implement lifecycle_manager)
    None)           # storage_url            (TODO: implement storage)
dependency = compose_instance(DependencyImpl, init_args)
```

`dependency_args()` builds on `context_args()`, so a Dependency participates
in interface composition like any other Aiko Services component.

In practice you rarely construct Dependencies directly: `Category.add()` and
`HyperSpace.add()` create them for you from a ServiceFilter and the two URLs.
Note the convenience rule applied by those callers: if
`service_filter.name` is `"*"`, it is replaced with the Entry name.

**Wire representation.** `__repr__()` renders the Dependency as an
S-expression-friendly triple used in Category/HyperSpace `list` responses:

```
(SERVICE_FILTER LIFECYCLE_MANAGER_URL STORAGE_URL)
e.g.  ((* my_service * * * (a=b)) None None)
```

In transmitted records, `None` values are substituted with the sentinel
`0:` (see [Category](category.md) for the record format).

## For framework developers (internals)

### Design

A Dependency bundles four pieces of information:

| Field | Role | Values |
|-------|------|--------|
| `service` | Live Service instance reference, once discovered | `None` (not discovered / absent) · local instance reference (same process) · remote proxy reference (different process or host) |
| `service_filter` | **WHAT** — how to discover the Service via the Registrar | a `ServiceFilter(topic_path, name, protocol, transport, owner, tags)` |
| `lifecycle_manager_url` | **WHO** — the Actor that manages the Service lifecycle (load / unload), e.g. a [ProcessManager](process_manager.md) | `None` (manually started) · `"*"` (discover, planned default) · explicit URL — *semantics work-in-progress* |
| `storage_url` | **WHERE** — the Actor that persists the Service definition / content, see [Storage](storage.md) | same value scheme as above — *work-in-progress* |

This separation is what lets HyperSpace describe a distributed system that
is only partially running: the *structure* (paths, filters, ownership) is
always present, while `service` transitions between `None` and a live
reference as Services come and go. The `lifecycle_manager_url` and
`storage_url` fields are the hooks for the planned lazy-loading loop, where
resolving a Dependency can *cause* the Service to be started and its
definition loaded.

### Implementation notes

- `DependencyImpl` is a straightforward value holder. `update()` applies
  only the arguments that are truthy — it merges rather than replaces, so
  callers can update a single field without disturbing the rest. The
  `entry_name` parameter exists only for signature compatibility with
  `Category.update()` and is ignored by `DependencyImpl`.
- **Type identity, not isinstance.** Composite traversal code (Category,
  HyperSpace, StorageFile) never uses `isinstance()` to distinguish
  Entries; it uses `is_type("Category")` / `is_type("Dependency")`.
  `CategoryImpl.is_type()` answers `True` for "category" and then delegates
  down to its Dependency implementation — mirroring the is-a relationship
  of the Composite pattern. Use `is_type()` in any code that walks Entries.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Dependency` (Interface) | Declare the Service-reference contract: `get_type()`, `is_type()`, `update()`; bind the default implementation | Interface composition machinery (`Interface.default`, `compose_instance`) |
| `DependencyImpl` | Hold `service`, `service_filter`, `lifecycle_manager_url`, `storage_url`; merge-style `update()`; render the S-expression wire triple via `__repr__()` | `ServiceFilter` (discovery); [Category](category.md) (containing owner); [HyperSpace](hyperspace.md) (path addressing); [Storage](storage.md) (persistence target); [ProcessManager](process_manager.md) (intended `lifecycle_manager_url` target) |

## Current limitations and roadmap

From the source `To Do` list — not yet implemented:

- `DependencyImpl.create_dependency()` class method (mirroring
  `HyperSpaceImpl.create_hyperspace()`)
- Resolution of `lifecycle_manager_url` / `storage_url`, including `"*"`
  discovery defaults
- Dependency *properties*: dependency direction, information direction,
  strong / weak / group semantics
- A DependencyManager maintaining an in-memory list of Dependencies
- Replacing the current Pipeline prototype implementation with this design,
  once full Dependency resolution and information flow are completed
- Security model design and implementation

## Related concepts

- [Design overview](design_overview.md) — where Dependency fits
- [Category](category.md) — the container that holds Dependencies
- [HyperSpace](hyperspace.md) — path-addressable graph of Dependencies
- [Storage](storage.md) — persists Dependencies as files + symbolic links
- [ProcessManager](process_manager.md) — the intended target of
  `lifecycle_manager_url`
