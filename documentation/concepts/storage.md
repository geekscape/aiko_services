---
title: Storage
description: The persistence SPI for Categories and Dependencies, and
  StorageFile — its file-system implementation using directories, files and
  symbolic links
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/storage/storage.py
  - src/aiko_services/main/storage/storage_file.py
related: [design_overview, dependency, category, hyperspace]
version: "0.6"
last_updated: 2026-07-04
---

# Storage

## At a glance

**Storage** is the persistence SPI (Service Provider Interface) beneath
[HyperSpace](hyperspace.md): it stores [Categories](category.md) and
[Dependencies](dependency.md) so the distributed system's structure survives
process restarts. **StorageFile** is the current implementation, mapping the
Composite pattern directly onto the file-system:

| Concept | Composite role | File-system representation |
|---------|----------------|------------------------------|
| Dependency | Component (leaf) | a *file*, referenced by a symbolic link |
| Category | Container (and also a Component) | a *directory* of Entries, referenced by a symbolic link |
| Entry | either of the above | a *symbolic link* at a human-readable path |

StorageFile is unusual among Aiko Services components in that it runs two
ways: as a
**distributed Actor** (a Storage Service operated over MQTT) and as a
**standalone library in bootstrap mode** — the same commands working
directly against the local file-system with no Services running. Bootstrap
mode exists because you cannot use a distributed Storage Service to
bootstrap Storage itself.

## Design

### The Storage SPI

```python
class Storage(Actor):
    Interface.default("Storage",
        "aiko_services.main.storage.storage_file.StorageFileImpl")

    add(dependency_name, dependency)     # add a Dependency        (file)
    create(category_name)                # create a Category       (directory)
    destroy(entry_name)                  # destroy an Entry        (either)
    remove(entry_name)                   # remove an Entry         (either)
    link(entry_path_new, entry_path_existing)   # alias an Entry
    list(topic_path_response, entry_name, long_format, recursive,
         entry_records)                  # tree-style listing
    update(entry_name, service, service_filter,
           lifecycle_manager_url, storage_url)  # (unimplemented)
    dump(sort_by_name)                   # low-level reverse-mapped listing
    initialize(storage_url)              # prepare the backing store
    exit()                               # terminate the Storage Actor
```

Planned alternative backends behind the same SPI: in-memory, SQLite3, MQTT,
ValKey (distributed Redis). Today only the file-system implementation
exists.

### StorageFile on-disk layout

`initialize` prepares a working directory; subsequent operations build a
structure like this:

```
./                                      # the initialized root
├── .root -> /abs/path/to/root          # anchor: every link routes via .root
├── _hyperspace_/                       # storage area (default name; will
│   │                                   #   become "_storage_", overridable
│   │                                   #   via storage_url)
│   ├── tracked_paths                   # registry of created storage paths
│   ├── uid_counter                     # persisted counter (debug UID mode)
│   ├── ab/cd/ef/01/23/45/              # a Category: directory at a
│   │   │                               #   UID-derived path
│   │   ├── .root -> ../../../../../../..   # back-link to the root
│   │   └── camera_0 -> .root/_hyperspace_/67/…   # nested Entry link
│   └── 67/89/ab/cd/ef/01               # a Dependency: file at a
│                                       #   UID-derived path
├── models -> .root/_hyperspace_/ab/cd/ef/01/23/45   # Category Entry
└── camera_1 -> .root/_hyperspace_/67/89/ab/cd/ef/01 # Dependency Entry
```

Key mechanisms:

- **UID-addressed storage.** Every Category/Dependency gets a 12-hex-digit
  UID, split into six 2-character path segments (`ab/cd/ef/01/23/45`) to
  keep directories shallow. UIDs are random
  (`sha256(os.urandom(16))`) by default; set `STORAGE_RANDOM_UID=False`
  for predictable incrementing UIDs when debugging (persisted in
  `uid_counter`).
- **Names are symbolic links.** The human-readable namespace is a layer of
  symlinks over UID-addressed storage — exactly how HyperSpace can present
  a *graph*: `link` creates additional names for the same storage target,
  like hard-link aliasing.
- **`.root` anchoring.** All links are expressed relative to a `.root`
  symlink (at the root, and inside every Category directory pointing back
  up), so the whole tree remains valid regardless of where it is mounted
  or how deep the referring directory is.
- **`tracked_paths`.** An append-only-ish registry of created storage
  paths, used for collision avoidance and (eventually) validation.
- **Reference-counted destruction.** `destroy(entry_name)` unlinks the
  named symlink; only if *no other symlink in the tree* still resolves to
  the same storage target is the target itself deleted (recursively for
  directories) and empty parent directories cleaned up.

## Developer guide (internals)

### Construction and modes

```python
storage = StorageFileImpl.create_storage(
    storage_name,                 # usually the hostname
    storage_url="file:",          # relative URL: current working directory
    register_service=True)        # False = embedded/bootstrap use
```

- As a **Service**, StorageFile registers with protocol
  `…/storage:0`, tags `ec=true`, and shares `storage_url` and
  `uid_counter` via ECProducer.
- **Embedded**: HyperSpace creates one with `register_service=False` as its
  private persistence engine.
- **Bootstrap CLI**: each subcommand with `-b` constructs a throwaway
  instance and calls the method directly.

`_check_root_symbolic_link()` guards commands that need an initialized
root; the CLI converts the failure into
*"Consider running `aiko_storage_file initialize`"*.

### Operation notes

- `add()` creates the UID file, then symlinks
  `DEPENDENCY_NAME -> .root/_hyperspace_/<uid path>` and tracks the path.
  Storing the Dependency payload (ServiceFilter, LifeCycleManager URL,
  Storage URL) is still TODO — today the file is empty and `list`
  synthesises a wildcard ServiceFilter.
- `create()` additionally plants the internal `.root` back-link inside the
  new directory, computed with `os.path.relpath`.
- `link()` validates the existing target resolves inside the storage area,
  then creates the new symlink relative to the *nearest* `.root` (the one
  in the destination's directory if present, else the root's).
- `list()` walks symlinked entries (skipping dot-names), emitting the
  shared Category record format (see [Category](category.md)):
  `[level, entry_name, [service_filter, lcm_url, storage_url]]`, with
  `[-level, path]` headers for recursion into directories. Directory
  entries are reported with `CATEGORY_PROTOCOL`; files with protocol `*`.
  Records are either published to `topic_path_response`
  (`(item_count N)` / `(response …)`), appended to a caller-supplied
  `entry_records` list (how HyperSpace loads), or pretty-printed via
  `CategoryImpl._list_publish()`.
- `dump()` is the low-level truth: it reverse-maps every symlink in the
  tree to its storage path and prints `RELATIVE_STORAGE_PATH  NAME` pairs,
  deduplicated, sorted by path (or by name with `--sort_by_name`).
- `remove()` currently just calls `destroy()` — the intended unlink-only
  semantics are TODO.
- `update()` is **unimplemented** (prints a placeholder).

### Semantics still being worked through

The header flags that the add / create / destroy / remove semantics — and
whether `tracked_paths` should become true reference counting — are under
active review. Treat destructive operations as provisional. Structure
validation (dead links, tracked-path consistency, content checks) is
planned.

## User guide (application developers)

Standalone (bootstrap) use as a library:

```python
from aiko_services.main.storage import StorageFileImpl

storage = StorageFileImpl.create_storage("<no_name>", None)
StorageFileImpl.initialize()          # idempotent: .root, _hyperspace_/
storage.create("models")              # Category  (directory)
storage.add("models/yolo_v8")         # Dependency (file)   — via cwd paths
storage.link("best_model", "models/yolo_v8")
storage.list(None, None, long_format=False, recursive=True)
storage.destroy("best_model")         # unlink; target kept (still linked)
```

Distributed use goes through discovery, exactly as the CLI does:

```python
do_command(Storage, ServiceFilter(name=None, protocol=PROTOCOL),
    lambda storage: storage.create("models"), terminate=True)
aiko.process.run()
```

## User guide (command line)

`aiko_storage_file` (preferred) or `./storage_file.py`. Every data command
takes `--bootstrap / -b` (operate standalone on the local file-system, no
Storage Service required) and `--storage_name / -sn` (target Service name,
default: local hostname).

### Lifecycle

```bash
export STORAGE_RANDOM_UID=False   # optional: predictable UIDs for debugging

aiko_storage_file initialize [STORAGE_URL]  # set up .root and storage dir
aiko_storage_file run [STORAGE_URL]         # run as a distributed Actor
aiko_storage_file dump [-b] [--sort_by_name]# low-level reverse-mapped view
aiko_storage_file exit                      # terminate the Storage Service
```

### CRUD

```bash
aiko_storage_file add     [-b] DEPENDENCY             # file
aiko_storage_file create  [-b] CATEGORY               # directory
aiko_storage_file link    [-b] NEW_ENTRY EXISTING_ENTRY
aiko_storage_file list    [-b] [-l] [-r] [PATH]
aiko_storage_file remove  [-b] ENTRY                  # currently == destroy
aiko_storage_file destroy [-b] ENTRY
aiko_storage_file update  [-b] ENTRY …                # TODO: unimplemented
```

Example bootstrap session:

```bash
mkdir workspace && cd workspace
aiko_storage_file initialize
# Created directory _hyperspace_/
# Created symbolic link .root --> /…/workspace

aiko_storage_file create -b models
aiko_storage_file add    -b models/yolo_v8
aiko_storage_file link   -b best_model models/yolo_v8
aiko_storage_file list   -b -r
aiko_storage_file dump   -b
# ab/cd/ef/01/23/45           models
# 67/89/ab/cd/ef/01           yolo_v8
# 67/89/ab/cd/ef/01           best_model     ← two names, one storage target
```

## Current limitations and roadmap

Highlights from the source `To Do` lists:

- Default storage directory rename `_hyperspace_` → `_storage_`
  (HyperSpace then passes `_hyperspace_` explicitly via `storage_url`)
- Store and load the actual Dependency payload (ServiceFilter,
  LifeCycleManager URL, Storage URL) — needed by LifeCycleManager,
  HyperSpace and ProcessManager
- Implement `update`; make `remove` unlink-only; `destroy --recursive`;
  `list -c` (entry counts), `-u` (UIDs), recursion limits
- REPL; structure validation (tracked paths, dead links, contents,
  comparison against a known-good copy)
- File-system event integration (`FileSystemEventPatternMatch` in
  `scheme_file.py`) so HyperSpace/ProcessManager can react to storage
  changes; a read-only bootstrap API for ProcessManager
- Database (SQLite3) and ValKey/Redis distributed implementations

## Related concepts

- [Design overview](design_overview.md)
- [HyperSpace](hyperspace.md) — primary consumer of the Storage SPI
- [Category](category.md) / [Dependency](dependency.md) — what is stored
- [ProcessManager](process_manager.md) — future bootstrap-mode reader
