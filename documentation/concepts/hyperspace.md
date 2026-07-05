---
title: HyperSpace
description: The root Category and LifeCycleManager for Categories — a
  unified, persistent, navigable network graph of distributed Service
  references
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/hyperspace.py
related: [design_overview, category, dependency, storage, process_manager,
  actor, share, discovery, lifecycle]
version: "0.6"
last_updated: 2026-07-05
---

# HyperSpace

## Overview

**HyperSpace** is the root [Category](category.md) and the LifeCycleManager
of Categories. It composes Categories and [Dependencies](dependency.md) into
a single unified network graph of distributed Service / Actor / Agent /
PipelineElement / Pipeline references — a deliberate mash-up of hypermedia,
directed-network-graph and file-system concepts.

If Dependency is the symbolic link and Category is the directory, HyperSpace
is the mounted file-system: it provides **path addressing**
(`category_a/category_b/entry_c`), **persistence** (via the
[Storage](storage.md) SPI) and **lifecycle management** (Categories are
created, loaded and destroyed by HyperSpace, and each one is a live
[Actor](actor.md)).

**Why you'd use it**: to give a distributed system a durable, navigable
structure that outlives the processes in it. For example, registering a
model reference under a meaningful path that any host can query, and that
survives a restart of every Service involved:

```bash
aiko_hyperspace create models/shared
aiko_hyperspace add    models/shared/llm_gemma -p '*' -t model=gemma4
aiko_hyperspace list   models -l -r
```

## For application developers

### Command-line usage

`aiko_hyperspace` (preferred) or `./hyperspace.py`. The target HyperSpace is
selected with `--hyperspace_name / -hn`, defaulting to the local hostname.

Bootstrap a fresh host:

```bash
export STORAGE_RANDOM_UID=False   # optional: predictable UIDs for debugging

aiko_storage_file initialize      # set up .root and the storage directory
aiko_storage_file dump -b         # inspect low-level storage (standalone)
aiko_storage_file list -b -l -r   # inspect as entries (standalone)
```

Run the HyperSpace Actor:

```bash
aiko_hyperspace run [STORAGE_URL]   # backends: file (today); in-memory,
                                    # sqlite, mqtt, valkey (planned)
aiko_hyperspace dump                # log top-level state (not recursive)
aiko_hyperspace exit
```

On startup it loads the persisted graph and reports
`Dependencies: N, Categories: M`.

Work with the graph:

```bash
aiko_hyperspace create models/shared          # Categories along the path
aiko_hyperspace add    models/shared/llm_gemma \
    -p '*' -o andyg -t model=gemma4           # Dependency with ServiceFilter
aiko_hyperspace list                          # top level
aiko_hyperspace list models -l -r             # long format, recursive
aiko_hyperspace update models/shared/llm_gemma -p aiko/llm:0
aiko_hyperspace remove models/shared/llm_gemma
aiko_hyperspace destroy models/shared         # only if empty
aiko_hyperspace link NEW_PATH EXISTING_PATH   # TODO: not yet implemented;
                                              # use "aiko_storage_file link"
```

`add` and `update` accept the ServiceFilter options
`-n/--service_name`, `-p/--protocol`, `-tr/--transport`, `-o/--owner`,
`-t/--tags` (repeatable), plus `-lcm/--lifecycle_manager_url` and
`-s/--storage_url`. As with Category: `add` defaults fields to `*`,
`update` defaults to `0:` (leave unchanged).

### Public API

```python
class HyperSpace(Category, Actor):
    Interface.default("HyperSpace",
        "aiko_services.main.hyperspace.HyperSpaceImpl")

    @abstractmethod
    def create(self, category_path): ...   # plus destroy(), dump()
```

`HyperSpace` adds `create()`, `destroy()` and `dump()` to the Category
interface (`add`, `list`, `remove`, `update`, `exit`) — and every
operation takes an *entry path* (`models/shared/llm_gemma`) rather than a
bare name.

In-process use:

```python
from aiko_services.main import *
from aiko_services.main.hyperspace import HyperSpaceImpl

hyperspace = HyperSpaceImpl.create_hyperspace("my_host")

hyperspace.create("agents")                     # Category
hyperspace.add("agents/llm_gemma",              # Dependency
    ServiceFilter("*", "*", "*", "*", "*", []),
    lifecycle_manager_url=None, storage_url=None)
hyperspace.list(None, None, long_format=False, recursive=True)
aiko.process.run()
```

Remote clients use the ordinary [discovery idiom](discovery.md)
(`do_command(HyperSpaceImpl, ServiceFilter(name=..., protocol=...), ...)`)
— which is exactly what the CLI does.

**Write-through persistence.** Mutating calls update the in-memory graph
*and* the embedded Storage in one step:

```
Client                HyperSpace Actor              StorageFile (embedded)
  │                         │                              │
  │──create("models/shared")►                              │
  │                         │ _find_entry(): walk path     │
  │                         │ new CategoryImpl Actor per   │
  │                         │   missing path component     │
  │                         │ ec_producer.update(entries.…)│
  │                         │──storage.create(path)───────►│
  │                         │                              │ mkdir UID path,
  │                         │                              │ plant .root link,
  │                         │                              │ symlink entry name
```

**Wire protocol.** `list()` uses the shared Category record format —
`(item_count N)` / `(response ENTRY_RECORD)`, negative levels introducing
nested Categories — see [Category](category.md) for the full record
grammar. Invalid or missing paths produce `text` records
(`"Entry path is invalid"` / `"Entry path not found"`).

## For framework developers (internals)

### Design

```
   aiko_hyperspace CLI ──MQTT──►  HyperSpace Actor (protocol: hyperspace:0)
                                  │
                                  │  root Category "/"
                                  ├── models/            Category Actor
                                  │    └── yolo_v8       Dependency
                                  └── agents/            Category Actor
                                       └── llm_gemma     Dependency
                                  │
                                  │ persists / reloads
                                  ▼
                                  StorageFile (embedded, not registered)
                                  directories + files + symbolic links
```

Key design points:

- **Paths, not just names.** Every operation takes an *entry path* like
  `models/shared/llm_gemma`; HyperSpace traverses its in-memory Categories
  to find the parent Category and the leaf Entry.
- **Write-through persistence.** `add()` and `create()` update the
  in-memory graph *and* the embedded Storage; at startup,
  `_hyperspace_load()` replays Storage back into memory, so the graph
  survives restarts.
- **Categories are live Actors.** Each Category created through HyperSpace
  is a `CategoryImpl` instance registered as a Service inside the
  HyperSpace process — individually addressable and observable.
- **Graph, not tree.** The Storage layer supports linking one Entry at
  multiple paths (`link`, currently CLI-TODO at HyperSpace level), so the
  logical structure is a directed graph.
- **One HyperSpace per host** (by convention) named after the hostname,
  like the Registrar and ProcessManager.

### Implementation notes

**Class structure.** `HyperSpaceImpl` delegates Category behaviour through
`self.category = context.get_implementation("Category")`, and its shared
state adds `storage_url` and `metrics` (`created`, `running` Category
counts) to the Category share. Use
`HyperSpaceImpl.create_hyperspace(name, storage_url, protocol, tags,
transport)` to construct one — it composes an Actor with `ec=true` tagging.

**Path resolution: `_find_entry()`.**
`_find_entry(entry_path, strict=True)` walks path components through nested
Category `share["entries"]` dicts. Return values:

| `entry_path` | Returns |
|---------------|---------|
| `""`, `"."`, `"/"`, `None` | `(HyperSpace, "")` — the root itself |
| `"…/category"` | `(parent_category, category_name)` |
| `"…/dependency"` | `(parent_category, dependency_name)` |
| leaf not found (strict) | `(parent_category, None)` |
| invalid intermediate path | `(None, None)` |

With `strict=False` (used when adding), the final name is returned even if
it does not exist yet. Intermediate components must be existing Categories.

**`add()` and `create()` — the `use_storage` flag.** Both methods carry
`use_storage=True` by default: they mutate the in-memory graph *and*
persist via `self.storage` (`storage.add(entry_path, dependency)` /
`storage.create(category_path)`). During startup replay,
`_hyperspace_load()` calls them with `use_storage=False` so Storage is not
re-written with its own contents.

- `add(entry_path, service_filter, lcm_url, storage_url, use_storage)` —
  requires an existing parent Category and (when using storage) no existing
  Entry of that name. Applies the same ServiceFilter normalisation as
  Category (`"*"` name → entry name).
- `create(category_path, use_storage)` — walks the path, creating a
  `CategoryImpl` Actor (protocol `CATEGORY_PROTOCOL`, tag `ec=true`) for
  each missing component, wiring it into the parent's `entries` via
  ECProducer updates.

**`destroy()` and `remove()`.** `destroy(category_path)` only removes
**empty** Categories (`entries_count == 0`): it deletes the parent's entry,
removes the Category Actor's Service registration
(`aiko.process.remove_service()`), and calls `storage.destroy()`.
`remove(entry_path)` routes Categories to `_destroy()` and Dependencies to
`category.remove()` — note the source marks the Category branch and the
storage removal as TODO/under review (`remove()` should eventually be
*unlink*, with destruction only on last reference).

**Startup: `_hyperspace_load()`.** At construction, HyperSpace instantiates
an embedded
`StorageFileImpl.create_storage(f"{hostname}_hs", register_service=False)`
— it is a private persistence engine, not a discoverable Storage Service.
It then calls `storage.list(None, None, False, True, entry_records)` to
collect the full recursive record list and replays each record:
negative-level records set the current Category path; positive records are
re-created via `create(path, use_storage=False)` when the record's protocol
is `CATEGORY_PROTOCOL`, otherwise `add(path, ..., use_storage=False)`.
It prints a summary: `Dependencies: N, Categories: M`.

**`list()`.** Resolves the path via `_find_entry()`, then recursively
gathers records using the shared Category record format. Listing a
Dependency path filters to that single Entry.

**Bootstrap coupling.** The `aiko_hyperspace` CLI group checks
`StorageFileImpl._check_root_symbolic_link()` for subcommands that need an
initialized storage area and advises running the initialize command
otherwise. Note the [Storage](storage.md) file layout — currently rooted at
`_hyperspace_/` — is created by `aiko_storage_file initialize`, not by
HyperSpace itself.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `HyperSpace` (Interface) | Extend the Category contract with `create()`, `destroy()`, `dump()`; is-a Category, is-an Actor | [Category](category.md), `Actor` (parent Interfaces) |
| `HyperSpaceImpl` | Path resolution (`_find_entry()`); create/destroy Category Actors along paths; write-through persistence and startup replay (`_hyperspace_load()`); maintain `storage_url` and Category-count metrics in shared state; `create_hyperspace()` factory | `CategoryImpl` (delegation and per-node Actors); [Dependency](dependency.md) / `DependencyImpl` (leaf Entries); `StorageFileImpl` (embedded persistence, see [Storage](storage.md)); `ECProducer` (shared state); [ProcessManager](process_manager.md) (planned LifeCycleManager counterpart) |

## Current limitations and roadmap

Highlights from the source `To Do` list:

- Separate HyperSpace and Storage design more cleanly (Categories with
  different roots; Storage owning Definition/Content)
- `link` and true unlink-style `remove` at HyperSpace level; recursive
  `destroy`; `--force` and ownership/ACL checks
- Registrar as-a HyperSpace: query filters, sort order, pagination, and
  shareable result Categories
- Leases for lazy Category loading / running / unloading, with
  [ProcessManager](process_manager.md) as the LifeCycleManager completing
  the Service lifecycle state machine
- Maintain `running` / `active` Category counts; `aiko_hyperspace export`;
  structure validation; REPL; Dashboard plug-in (tree view)
- Primary/watchdog HyperSpace per host; unify HyperSpaces across hosts in
  one namespace
- Known issue: `do_command()` against a remote proxy fails for `create()`
  (`ServiceRemoteProxy` attribute error) — the CLI works around this by
  targeting `HyperSpaceImpl`
- Backends beyond the file-system (in-memory, SQLite3, MQTT, ValKey,
  knowledge graph) are planned but not implemented

## Related concepts

- [Design overview](design_overview.md)
- [Category](category.md) — the node type HyperSpace manages
- [Dependency](dependency.md) — the leaf type
- [Storage](storage.md) — the persistence SPI beneath HyperSpace
- [ProcessManager](process_manager.md) — the LifeCycleManager counterpart
- [Actor](actor.md) / [Share (Eventual Consistency)](share.md) — the
  machinery every Category node is built on
- [LifeCycle](lifecycle.md) — the manager/client pattern HyperSpace applies
  to Categories
