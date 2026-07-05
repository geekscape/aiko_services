---
title: Category
description: An Actor that groups Entries — Dependencies and other
  Categories — into a named, shareable, observable collection
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/category.py
related: [design_overview, dependency, hyperspace, storage, actor,
  service, share, discovery]
version: "0.6"
last_updated: 2026-07-05
---

# Category

## Overview

A **Category** is an Actor representing a group of **Entries**, where each
Entry is either a [Dependency](dependency.md) (a Service reference) or
another Category. It is the *Container* of the Composite pattern — the
directory to Dependency's file — and the building block from which
[HyperSpace](hyperspace.md) assembles its network graph.

Because a Category **is-a** Dependency, Categories nest arbitrarily. Because
a Category **is-an** [Actor](actor.md), every Category is independently
discoverable, remotely operable over MQTT, and its entries are live shared
state visible in the Aiko Services [Dashboard](dashboard.md).

**Why you'd use it**: whenever a component needs to manage a queryable,
observable collection of Service references. For example, a fleet of camera
Services grouped under one name that any host can inspect remotely:

```bash
./category.py add team_a camera_0 -p aiko/video:0 -o andyg
./category.py list team_a
```

Planned Categories throughout the system include HyperSpace, Registrar,
LifeCycleManager and WorkSpace — the intent is that "a queryable, observable
group of Service references" becomes the standard idiom for any component
that manages a collection.

## For application developers

### Command-line usage

There is currently no `aiko_category` console script; run the module
directly (an entry point is expected to follow the same naming convention as
the other tools):

```bash
cd src/aiko_services/main
./category.py --help
```

Run and terminate a Category Actor:

```bash
./category.py run   CATEGORY_NAME    # create a Category instance (testing)
./category.py exit  CATEGORY_NAME    # terminate the running instance
```

Manage Entries:

```bash
# Add an Entry (ServiceFilter fields via options)
./category.py add CATEGORY_NAME ENTRY_NAME \
    -n service_name -p protocol -tr transport -o owner \
    -t key_0=value_0 -t key_1=value_1 \
    -lcm LIFECYCLE_MANAGER_URL -s STORAGE_URL

# List all Entries, or one Entry; -l adds LifeCycleManager and Storage URLs
./category.py list CATEGORY_NAME [ENTRY_NAME] [--long_format | -l]

# Update selected fields of an Entry (unspecified fields are unchanged)
./category.py update CATEGORY_NAME ENTRY_NAME -p protocol -t key_0=value_0

# Remove an Entry
./category.py remove CATEGORY_NAME ENTRY_NAME
```

Option defaults: `add` defaults ServiceFilter fields to `*` (match
anything); `update` defaults them to `0:` (meaning *leave unchanged*).

Example session:

```bash
./category.py run team_a &
./category.py add team_a camera_0 -p aiko/video:0 -o andyg
./category.py list team_a
# Name  Protocol  Owner
# camera_0             video:0 andyg
./category.py exit team_a
```

### Public API

```python
class Category(Actor, Dependency):
    Interface.default("Category", "aiko_services.main.category.CategoryImpl")
```

Core operations (CRUD on the collection):

| Operation | Effect |
|-----------|--------|
| `add(entry_name, service_filter, lcm_url, storage_url)` | Create a Dependency and store it under `entry_name` (no-op if the name exists) |
| `list(topic_path_response, entry_name, long_format, ...)` | Publish (or print) Entry records, optionally for a single Entry |
| `update(entry_name, service, service_filter, lcm_url, storage_url)` | Merge non-null fields into an existing Entry |
| `remove(entry_name)` | Delete the Entry from the collection |
| `exit()` | Terminate the Category Actor's process |

Creating and using a Category in-process:

```python
from aiko_services.main import *

init_args = actor_args("my_category", None, None, CATEGORY_PROTOCOL,
    tags=["ec=true"])
category = compose_instance(CategoryImpl, init_args)

category.add("camera_0",
    ServiceFilter("*", "camera_0", "*", "*", "*", []),
    lifecycle_manager_url=None, storage_url=None)
```

For most applications, prefer operating through
[HyperSpace](hyperspace.md), which creates and manages Categories for you
and adds path-based addressing and persistence.

**Remote operation.** All CLI verbs use the standard Aiko Services idiom —
discover, invoke, terminate (see [Discovery](discovery.md)):

```python
do_command(Category,
    ServiceFilter(name=category_name, protocol=CATEGORY_PROTOCOL),
    lambda category: category.add(...), terminate=True)
aiko.process.run()
```

`list` uses `do_request()` with a response handler subscribed to
`aiko.topic_in` of the invoking process:

```
Client process                          Category Actor
      │                                       │
      │ do_request(): discover via Registrar, │
      │ subscribe to own aiko.topic_in        │
      │                                       │
      │──(list TOPIC_RESPONSE [ENTRY] …)─────►│  one-way MQTT message
      │                                       │  gather Entry records
      │◄─(item_count N)───────────────────────│
      │◄─(response ENTRY_RECORD)  × N ────────│
      │                                       │
      │ print records, terminate              │
```

**Wire protocol.** `list()` publishes to the requester's response topic:

```
(item_count N)
(response ENTRY_RECORD)      # repeated N times
```

Entry records come in two shapes:

```
A) new child Category:  [-LEVEL, CATEGORY_NAME]                # negative level
B) Category Entry:      [ LEVEL, ENTRY_NAME,
                          [SERVICE_FILTER, LCM_URL, STORAGE_URL]]
```

`LEVEL` is the indentation depth; a *negative* level introduces a nested
Category header when listing recursively (used by HyperSpace and
StorageFile, which share this record format and printer). A record whose
first element is the string `text` carries a plain message, e.g.
`Entry path not found`. In transmitted records the sentinel `0:` stands for
*None* — S-expression-safe — which is also why the CLI `update` command
uses `0:` as its "leave unchanged" default.

Printed output comes in two formats:

```
Name  Protocol  Owner                                # short format
Name  (ServiceFields)  LifeCycleManager, Storage     # long format (-l)
```

## For framework developers (internals)

### Design

```
   Category (Actor, Dependency)
   ┌──────────────────────────────────────────────┐
   │ entries:                                     │
   │   "camera_0"  ─► Dependency (ServiceFilter,  │
   │                  lcm_url, storage_url)       │
   │   "models"    ─► Category  (nested)          │
   │ entries_count: 2                             │
   └──────────────────────────────────────────────┘
```

A Category is the Composite pattern's *Container*, realised as a live
Actor: the `entries` collection is eventually-consistent shared state, so
the collection itself is part of the distributed system — observable,
queryable and remotely mutable — rather than a private data structure.

### Implementation notes

**Class composition.** `CategoryImpl.__init__()` initializes both parents
via `context.call_init(self, "Actor", ...)` and
`context.call_init(self, "Dependency", ...)`, then grabs the Dependency
implementation with `context.get_implementation("Dependency")` so it can
delegate `is_type()` and `__repr__()` down the composite chain.

**Entries live in shared state.** Entries are not a private dict — they are
stored in `self.share["entries"]` and every mutation goes through the
[`ECProducer`](share.md):

```python
self.ec_producer.update(f"entries.{entry_name}", dependency)
self.ec_producer.update("entries_count", len(self.share["entries"]))
```

Consequences worth knowing:

- The whole collection is remotely observable (Dashboard, `ECConsumer`).
- `entries_count` is maintained alongside for cheap monitoring.
- The Dependency objects themselves are the values, so `update()` mutates
  the Dependency in place and then republishes it.

**`add()` normalisation rules:**

- A `service_filter` arriving as a list/tuple (the MQTT wire form) is
  re-hydrated with `ServiceFilter(*service_filter)`.
- If `service_filter.name == "*"`, it is replaced with `entry_name` — an
  Entry named `camera_0` matches a Service named `camera_0` by default.
- Adding an existing `entry_name` is silently ignored (no overwrite).

**`update()` merge semantics.** `update()` merges field-by-field: only
truthy fields of the incoming ServiceFilter (and non-null URLs) are
applied. It also guards against `ServiceFilter.__init__` substituting the
local hostname for a null name — it remembers whether the name was null and
restores it.

**Shared record utilities.** Entry records are assembled in
`_get_entry_records()` and interpreted by `_list_print()`.
`CategoryImpl.list_command()` and `CategoryImpl._list_print()` are
class-method utilities reused by the HyperSpace and StorageFile CLIs, so
all three present identical output.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Category` (Interface) | Declare the collection contract: `add()`, `list()`, `update()`, `remove()`, `exit()`; is-an Actor and is-a Dependency | `Actor`, [Dependency](dependency.md) (parent Interfaces) |
| `CategoryImpl` | Maintain `entries` / `entries_count` in ECProducer shared state; normalise ServiceFilters on `add()`; merge on `update()`; assemble and print/publish Entry records; provide `list_command()` / `_list_print()` reused by other CLIs | `DependencyImpl` (delegation via `context.get_implementation`); `ECProducer` (shared state); `ServiceFilter` (discovery fields); [HyperSpace](hyperspace.md) and [Storage](storage.md) (record-format co-users) |

## Current limitations and roadmap

From the source `To Do` list — highlights:

- Interactive REPL (`./category.py repl`) for CRUD and discovering running
  Services to add/update/remove
- Incorporate full Dependency semantics (strong / weak / group), and
  disambiguate function delivery to the Category itself versus its Entries
- Timestamps (create/add/remove/update) and Category metrics (operation
  rates, totals)
- `list` filters (by owner, protocol, ...), plus `__repr__`/`__str__`
  refactoring of `list()`
- A CategoryManager interface for use by HyperSpace et al; Categories that
  span different HyperSpace roots; self-changing custom Categories;
  a Queue(Category) with persistence options and a `queue://` DataScheme
- `owner` field populated automatically; system Categories owned by
  `aiko`; security (owners, roles, ACLs)

## Related concepts

- [Design overview](design_overview.md)
- [Dependency](dependency.md) — what Entries are made of
- [HyperSpace](hyperspace.md) — root Category, path addressing, persistence
- [Storage](storage.md) — how Category structures are persisted
- [Actor](actor.md) — what a Category is-a; mailbox and main-thread model
- [Share (Eventual Consistency)](share.md) — how entries become observable
  shared state
- [Service](service.md) — ServiceFilter and the Service fields
