#!/usr/bin/env python3
#
# Aiko Service: HyperSpace(Category)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Create, List(Read), Update and Destroy a Graph of Categories and Dependencies
#
# Usage: Distributed Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~
#   export HYPERSPACE_RANDOM_HASH=false  # use incrementing hash value
#
#   ./hyperspace.py run     [hyperspace_url]  # file, in-memory, sqlite, mqtt
#   ./hyperspace.py dump
#   ./hyperspace.py exit
#
#   ./hyperspace.py add     ...
#   ./hyperspace.py create  ...  # Category or Dependency
#   ./hyperspace.py destroy ...
#   ./hyperspace.py link    ...  # TODO: "link" to existing Dependency
#   ./hyperspace.py list    ...
#   ./hyperspace.py read    ...
#   ./hyperspace.py remove  ...  # TODO: Also performs "unlink"
#   ./hyperspace.py update  ...
#
# Usage: Bootstrap
# ~~~~~~~~~~~~~~~~
#   export HYPERSPACE_RANDOM_HASH=false  # use incrementing hash value
#
#   ./hyperspace.py initialize
#   ./hyperspace.py ln      new_link  node        # node | category
#   ./hyperspace.py ls      [-l] [-n] [-r] [path]
#   ./hyperspace.py mk      node                  # node only
#   ./hyperspace.py mkdir   category              # category only
#   ./hyperspace.py rm      node                  # node | category
#   ./hyperspace.py storage [-s]
#
# Functions
# ~~~~~~~~~
#   _initialize()
#   _ln(link_path, target_path)
#   _ls(path, long_format, node_count, recursive))
#   _mk(name)
#   _mkdir(name)
#   _rm(name)
#   _storage(sort_by_name)
#
# To Do
# ~~~~~
# * HyperSpace as-a CategoryManager as-a LifeCycleManager as-a Category
#
# * HyperSpace/StorageFile uses FileSystemEventPatternMatch in "scheme_file.py"
#
# * aiko_hyperspace export output_filename.hyperspace --> hyperspace commands
#
# * Validate hyperspace structure
#   * Checks "storage/tracked_paths" is correct (using predictable hash)
#   * Checks file-system ensuring everything linked together properly
#   * Checks file-system ensuring that soft-links aren't "dead"
#   * Checks that file contents are correct (using predicatable data)
#   * Checks that directory contents are correct
#   * Checks file-system against a known good "backed-up" copy
#
# - Consider current "storage/tracked_paths" versus reference counting ?
#
# * ProcessManager bootstraps (read only) by directly using Python functions
#   * Implement HyperSpace(Actor) CRUD API ... used by ProcessManager bootstrap
#     * File-system listener --> event
#
# * Registrar(Actor) requires Category plus implement "(update)" for all fields
#
# * HyperSpace(Actor) requires Category and Dependencies
#   - Services that implement Category assign tag "category=true" (temporary)
#
# * Aiko Dashboard plug-in for HyperSpace(Actor), e.g tree view
#
# * Implement Category "owner" field and populate automatically
#   * Implement "destroy --force" flag to destroy other owner's Categories
#   * System Categories owned by "aiko"
#
# * Consider only one primary HyperSpace per host (refactor Registrar code)
#   * Don't allow two HyperSpace with the same name
# * HyperSpace primary / watchdog: monitor and relaunch primary
# * Unify HyperSpace on different hosts in the same namespace ?
#     * All the home/office servers plus handle mobile laptops (discovery) ?
#
# * HyperSpace uses Leases to enable lazy Category loading, running, unloading
#   - "aiko_hyperspace run" option for Category lease-time and maximum loaded
#   - ProcessManager(LifeCycleManager): Complete Service LifeCycle State
#     - Improvements to "src/aiko_services/main/state.py"
#   - ProcessManager(LifeCycleManager): Lazy loading of HyperSpace nodes
#
# - StorageManager (content, definition) backed by ...
#   - ❌ In-memory, ✅ File-system, ❌ SQLite3, ❌ MQTT
# - HyperSpace (links) backed by ...
#   - ❌ In-memory, ✅ File-system, ❌ SQLite3, ❌ MQTT, ❌ Knowledge Graph

from abc import abstractmethod
import click
import errno
import hashlib
import os
from pathlib import Path
import stat
import sys

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = ["HyperSpace"]

ACTOR_TYPE = "hyperspace"
VERSION = 0
PROTOCOL = f"{SERVICE_PROTOCOL_AIKO}/{ACTOR_TYPE}:{VERSION}"

_HASH_LENGTH = 12  # 6 bytes = 12 hex digits
_ROOT_FILENAME = ".root"
_STORAGE_FILENAME = "storage"
_TRACKED_PATHNAME = f"{_STORAGE_FILENAME}/tracked_paths"
_HASH_PATHNAME = f"{_STORAGE_FILENAME}/hash_counter"

# --------------------------------------------------------------------------- #

class HyperSpace(Category, Actor):
    Interface.default(
        "HyperSpace", "aiko_services.main.hyperspace.HyperSpaceImpl")

    @abstractmethod
    def dump(self):
        pass

    @abstractmethod
    def exit(self):
        pass

# --------------------------------------------------------------------------- #

class HyperSpaceImpl(HyperSpace):
    def __init__(self, context, hyperspace_url):
        context.call_init(self, "Actor", context)
        context.call_init(self, "Category", context)

    #   self.root_category = CategoryImpl.create("root")

        self.share = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(self.logger),
            "source_file": f"v{VERSION}⇒ {__file__}",
            "hyperspace_url": hyperspace_url,
            "metrics": {
                "created": 1  # Including self 😅
            #   "running": len(self.dependencies)               # TODO: Running
            #   "runtime": 0                                    # TODO: Runtime
            },
        }
        self.ec_producer = ECProducer(self, self.share)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    #   self.thread = Thread(target=self._run, daemon=True, name=_THREAD_NAME)
    #   self.thread.start()                           # TODO: Use ThreadManager

    #   if not hyperspace_url:
    #       hyperspace_url = PATHNAME_OF_CURRENT_WORKING_DIRECTORY
    #   self._load_hyperspace(hyperspace_url)

        self.category = context.get_implementation("Category")

    def __str__(self):
        return "HyperSpace_State"

    def create(self):
        print(f"### Unimplemented: HyperSpace.create() ###")

    def destroy(self):
        print(f"### Unimplemented: HyperSpace.destroy() ###")

    def dump(self):
        if len(self.dependencies):
            state = f" ...\n{self}"
        else:
            state = ": no dependencies"
        self.logger.info(f"Dump state{state}")

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            self.logger.setLevel(str(item_value).upper())

    def exit(self):
        aiko.process.terminate()

    def list(self):
        print(f"### Unimplemented: HyperSpace.list() ###")

    def update(self):
        print(f"### Unimplemented: HyperSpace.update() ###")

# --------------------------------------------------------------------------- #

_hash_counter = 0

# Initialize storage directory and .root symlink

def _check_root_symlink():
    root_pathname = Path.cwd() / _ROOT_FILENAME
    if not os.path.lexists(root_pathname):
        raise FileExistsError(
            f'HyperSpace: Symlink "./{_ROOT_FILENAME}" must exist')
    else:
        if not os.path.islink(root_pathname):
            raise FileExistsError(
                f'HyperSpace: File "./{_ROOT_FILENAME}" must be a symlink')

def _initialize():
    cwd = Path.cwd()
    root_pathname = cwd / _ROOT_FILENAME
    if not root_pathname.is_symlink():
        root_pathname.symlink_to(cwd)
        print(f"Created {_ROOT_FILENAME} --> {cwd}")

    storage_pathname = cwd / _STORAGE_FILENAME
    if not storage_pathname.is_dir():
        storage_pathname.mkdir(parents=True)
        print(f"Created {_STORAGE_FILENAME}")

    global _hash_counter
    hash_pathname = cwd / _HASH_PATHNAME
    if not hash_pathname.exists():
        hash_pathname.write_text("0")
    try:
        _hash_counter = int(hash_pathname.read_text())
    except ValueError:
        _hash_counter = 0

# Generate hash UID, persisting the hash_counter when using incremental mode

def _generate_hash():
    global _hash_counter
    if os.environ.get("HYPERSPACE_RANDOM_HASH", "true").lower() == "true":
        hash = hashlib.sha256(os.urandom(16)).hexdigest()
    else:
        hash = str(_hash_counter).zfill(_HASH_LENGTH)
        _hash_counter += 1
        Path(_HASH_PATHNAME).write_text(f"{_hash_counter}\n")
    return hash[- _HASH_LENGTH:]

# Clean up empty storage directories up to root

def _clean_storage(tracked_directory):
    tracked_path = Path(tracked_directory)
    storage_path = Path(_STORAGE_FILENAME)
    while tracked_path != storage_path and tracked_path != Path("."):
        if tracked_path.is_dir() and not any(tracked_path.iterdir()):
            tracked_path.rmdir()
            tracked_path = tracked_path.parent
        else:
            break

# Generate a unique storage path avoiding collisions

def _create_path():
    storage_path = Path(_STORAGE_FILENAME)
    existing_paths = set()
    if Path(_TRACKED_PATHNAME).exists():
        existing_paths.update(Path(_TRACKED_PATHNAME).read_text().splitlines())
    while True:
        hash = _generate_hash()
        path_parts = [hash[i:i+2] for i in range(0, len(hash), 2)]
        new_path = storage_path.joinpath(*path_parts)
        if not new_path.exists() and str(new_path) not in existing_paths:
            return str(new_path)

# Normalize path to relative from CWD

def _normalize_path(target_path):
    absolute_target_path = Path(target_path).resolve()
    cwd = Path.cwd()
    try:
        relative_path = absolute_target_path.relative_to(cwd)
        return f"./{relative_path}"
    except ValueError:
        return str(absolute_target_path)

# Compute relative path using os.path.relpath

def _relative_path(target_path, start_path):
    return os.path.relpath(target_path, start=start_path)

# Track a created storage path

def _track_path(path):
    relative_path = _normalize_path(path)
    Path(_TRACKED_PATHNAME).parent.mkdir(parents=True, exist_ok=True)
    with open(_TRACKED_PATHNAME, "a+") as tracked_paths_file:
        tracked_paths_file.seek(0)
        tracked_paths = tracked_paths_file.read().splitlines()
        if relative_path not in tracked_paths:
            tracked_paths_file.write(relative_path + "\n")

# Untrack a removed storage path

def _untrack_path(path):
    relative_path = _normalize_path(path)
    tracked_path = Path(_TRACKED_PATHNAME)
    if tracked_path.is_file():
        tracked_paths = tracked_path.read_text().splitlines()
        tracked_path.write_text(
            "\n".join(l for l in tracked_paths if l != relative_path))

# Create new link to an existing node or category
#
# ./hyperspace.py ln new_link  node  # node | category

def _ln(link_path, target_path):
    if not Path(target_path).exists():
        print(f'Error: target "{target_path}" does not exist', file=sys.stderr)
        return 1
    resolved_path = Path(target_path).resolve()
    cwd = Path.cwd()
    if _STORAGE_FILENAME not in resolved_path.parts:
        print(f'Error: target "{target_path}" is not in the storage directory',
            file=sys.stderr)
        return 1
    base_directory = Path(link_path).parent or Path(".")
    base_root = base_directory / _ROOT_FILENAME
    link_base = base_root if base_root.is_symlink() else Path(_ROOT_FILENAME)

    # Determine path under ".root/storage/"
    try:
        relative_path = resolved_path.relative_to(cwd / _STORAGE_FILENAME)
        relative_storage_path =  \
            f"{_STORAGE_FILENAME}/{relative_path.as_posix()}"
    except ValueError:
        relative_storage_path = resolved_path.relative_to(cwd).as_posix()

    # Construct full path under .root
    dot_root_path = link_base / relative_storage_path
    relative_path = _relative_path(str(dot_root_path), str(base_directory))
    try:
        Path(link_path).symlink_to(relative_path)
    except FileExistsError:
        print(f'Error: "{link_path}" already exists', file=sys.stderr)
        return 1

# List nodes and categories in a tree-style recursive format
#
# ./hyperspace.py ls [-l] [-n] [-r] [path]

def _ls(path, long_format=False, node_count=False, recursive=False):
    def _get_hash_path(link):
        absolute_target_path = Path(link).resolve()
        try:
            relative_path =  \
                absolute_target_path.relative_to(Path.cwd() / _STORAGE_FILENAME)
            return str(relative_path)
        except ValueError:
            return ""

    def _file_count(link_directory):
        target_path = Path(link_directory).resolve()
        return sum(1 for f in target_path.rglob("*")  \
                      if f.is_file() and f.stat().st_size > 0)

    def _list_links(current, indent=""):
        for directory_entry in sorted(Path(current).iterdir()):
            if not directory_entry.is_symlink():
                continue
            entry_name = directory_entry.name
            if entry_name.startswith("."):  # Skip hidden directory entries
                continue
            hash = _get_hash_path(directory_entry)
            if directory_entry.is_dir():
                if long_format:
                    print(f"{hash}  {indent}{entry_name}/", end="")
                else:
                    print(f"{indent}{entry_name}/", end="")
                if node_count:
                    count = _file_count(directory_entry)
                    if count > 0:
                        print(f" ({count})", end="")
                print()
                if recursive and not entry_name.startswith("."):
                    _list_links(directory_entry, indent + "  ")
            else:
                if long_format:
                    print(f"{hash}  {indent}{entry_name}")
                else:
                    print(f"{indent}{entry_name}")

    _list_links(path)

# Create a node (file)
#
# ./hyperspace.py mk node  # node only

def _mk(name):
    path = Path(_create_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    try:
        Path(name).symlink_to(f"{_ROOT_FILENAME}/{path}")
    except FileExistsError:
        print(f'Error: "{name}" already exists', file=sys.stderr)
        return 1
    _track_path(path)

# Create a category (directory)
#
# ./hyperspace.py mkdir category  # category only

def _mkdir(name):
    path = Path(_create_path())
    path.mkdir(parents=True, exist_ok=True)
    rel_back = _relative_path(str(Path.cwd() / _ROOT_FILENAME), path)
    try:
        Path(path, _ROOT_FILENAME).symlink_to(rel_back)
    except FileExistsError:
        print(f'Error: internal .root link in "{path}" already exists',
            file=sys.stderr)
        return 1
    try:
        Path(name).symlink_to(f"{_ROOT_FILENAME}/{path}")
    except FileExistsError:
        print(f'Error: "{name}" already exists', file=sys.stderr)
        return 1
    _track_path(path)

# Delete a node (file) or category (directory)
#
# ./hyperspace.py rm node  # node | category

def _rm(name):
    path = Path(name)
    if path.is_symlink():
        absolute_target_path = path.resolve()
        path.unlink()
        cwd = Path.cwd()
        try:
            storage_path = cwd / _STORAGE_FILENAME
            relative_path = absolute_target_path.relative_to(storage_path)
        except ValueError:
            return

        others = [x for x in cwd.rglob("*")  \
                     if x.is_symlink() and x.resolve() == absolute_target_path]
        if not others:
            _untrack_path(str(absolute_target_path))
            if absolute_target_path.is_dir():
                for sub in absolute_target_path.rglob("*"):
                    sub.unlink() if sub.is_file() else sub.rmdir()
                absolute_target_path.rmdir()
            else:
                absolute_target_path.unlink()
            _clean_storage(absolute_target_path.parent)
    else:
        print(f'Error: "{name}" is not a symbolic link', file=sys.stderr)
        return 1

# List storage in reverse-mapped form with deduplication and optional name sort
#
# ./hyperspace.py storage [-s]

def _storage(sort_by_name=False):
    tracked_paths = set()
    cwd = Path.cwd()
    for path in cwd.rglob("*"):
        if path.is_symlink():
            absolute_target_path = path.resolve()
            try:
                absolute_path = cwd / _STORAGE_FILENAME
                relative_path = absolute_target_path.relative_to(absolute_path)
                tracked_paths.add((str(relative_path), path.name))
            except ValueError:
                continue
    items = sorted(tracked_paths, key=lambda x: x[1] if sort_by_name else x[0])
    for relative_path, name in items:
        print(f"{relative_path}  {name}")

# --------------------------------------------------------------------------- #
# HyperSpace CLI: Bootstrap commands

@click.group()

def main():
    """Create, Read/List, Update and Destroy HyperSpace"""

    subcommand = click.get_current_context().invoked_subcommand
    subcommands_which_run_anywhere = ["create", "dump", "exit", "initialize"]

    if subcommand not in subcommands_which_run_anywhere:
        diagnostic = None
        try:
            _check_root_symlink()
        except FileExistsError as file_exists_error:
            diagnostic = str(file_exists_error)
        if diagnostic:
            advice = 'Consider running "aiko_hyperspace initialize"'
            raise SystemExit(f"{diagnostic}\n{advice}")

# ./hyperspace.py initialize

@main.command(name="initialize")
def initialize_command():
    "Initialize HyperSpace: .root and storage/"
    _initialize()

# ./hyperspace.py ln new_link_node existing_node

@main.command(name="ln")
@click.argument("link_path")
@click.argument("target_path")
def ln_command(link_path, target_path):
    "Create new link to an existing node or category"
    _ln(link_path, target_path)

# ./hyperspace.py ls [-l] [-n] [-r] [path]

@main.command(name="ls")
@click.argument("path", required=False, default=".")
@click.option("--long_format", "-l", default=False, is_flag=True,
    help="Long format with hash identifiers")
@click.option("--node_count", "-n", default=False, is_flag=True,
    help="Show category's node count")
@click.option("--recursive", "-r", default=False, is_flag=True,
    help="Recursive listing")
def ls_command(path, long_format, node_count, recursive):
    "List nodes (files) and categories (directories)"
    _ls(path, long_format, node_count, recursive)

# ./hyperspace.py mk node  # node only

@main.command(name="mk")
@click.argument("name")
def mk_command(name):
    "Create a node (file)"
    _mk(name)

# ./hyperspace.py mkdir category  # category only

@main.command(name="mkdir")
@click.argument("name")
def mkdir_command(name):
    "Create a category (directory)"
    _mkdir(name)

# ./hyperspace.py rm node  # node | category

@main.command(name="rm")
@click.argument("name")
def rm_command(name):
    "Remove a node or category"
    _rm(name)

# ./hyperspace.py storage [-s]

@main.command(name="storage")
@click.option("--sort_by_name", "-s", default=False, is_flag=True,
    help="Sort by name")
def storage_command(sort_by_name):
    "List node storage/tracked_paths and linked nodes"
    _storage(sort_by_name)

# --------------------------------------------------------------------------- #
# HyperSpace CLI: Distributed Actor commands

@main.command(name="create", no_args_is_help=False)
@click.option("--name", "-n", type=str, default=None,
    help="HyperSpace name, default is the hostname")

def create_command(name):
    """Create HyperSpace dependency

    aiko_hyperspace create [--name NAME]

    \b
    • NAME: HyperSpace name, default is the hostname
    """

    do_command(HyperSpace, ServiceFilter(name=name, protocol=PROTOCOL),
        lambda actor: actor.create(), terminate=True)
    aiko.process.run()

@main.command(name="destroy")

def destroy_command():
    print(f"### Unimplemented CLI: HyperSpace.destroy() ###")

@main.command(name="dump", help="Dump HyperSpace state")
@click.option("--name", "-n", type=str, default=None,
    help="HyperSpace name, default is the hostname")

def dump_command(name):
    do_command(HyperSpace, ServiceFilter(name=name, protocol=PROTOCOL),
        lambda hyperspace: hyperspace.dump(), terminate=True)
    aiko.process.run()

@main.command(name="exit", help="Exit HyperSpace")
@click.option("--name", "-n", type=str, default=None,
    help="HyperSpace name, default is the hostname")

def exit_command(name):
    do_command(HyperSpace, ServiceFilter(name=name, protocol=PROTOCOL),
        lambda hyperspace: hyperspace.exit(), terminate=True)
    aiko.process.run()

@main.command(name="list")

def list_command():
    print(f"### Unimplemented CLI: HyperSpace.list() ###")

@main.command(name="run")
@click.option("--name", "-n", type=str, default=None,
    help="HyperSpace name, default is the hostname")
@click.argument("hyperspace_url", required=False, default=None)

def run_command(name, hyperspace_url):
    """Run HyperSpace

    aiko_hyperspace run [--name NAME] [HYPERSPACE_PATHNAME]

    \b
    • NAME:                HyperSpace name, default is the hostname
    • HYPERSPACE_PATHNAME: HyperSpace storage file-system location
    """

    name = name if name else get_hostname()

    tags = ["ec=true"]       # TODO: Add ECProducer tag before add to Registrar
    init_args = actor_args(name, None, None, PROTOCOL, tags)
    init_args["hyperspace_url"] = hyperspace_url
    hyperspace = compose_instance(HyperSpaceImpl, init_args)
    aiko.process.run()

@main.command(name="update")

def update_command():
    print(f"### Unimplemented CLI: HyperSpace.update() ###")

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
