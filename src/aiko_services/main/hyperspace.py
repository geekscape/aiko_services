#!/usr/bin/env python3
#
# Aiko Service: HyperSpace(Category(Dependency))
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# HyperSpace is a LifeCycleManager of Categories (category.py and lifecycle.py)
# Create, Read, Update and Destroy a network graph of Categories
# Add to, List and Remove from any Category, which is a group of Entries
# Entries can be either a Category or a Dependency
# Category paths support a tree-like structure "category_a/category_b/entry_c"
#
# Usage: Distributed Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~
#   export HYPERSPACE_RANDOM_HASH=false    # use incrementing hash value
#
#   ./hyperspace.py run     [storage_url]  # file, in-memory, sqlite, mqtt
#   ./hyperspace.py dump
#   ./hyperspace.py exit
#
#   ./hyperspace.py add     ENTRY_PATH
#   ./hyperspace.py create  CATEGORY_PATH
#   ./hyperspace.py destroy CATEGORY_PATH
#   ./hyperspace.py link    ENTRY_PATH_NEW ENTRY_PATH_EXIST    # TODO: "link"
#   ./hyperspace.py list    [ENTRY_PATH] [--long_format | -l] [--recursive | -r]
#   ./hyperspace.py remove  ENTRY_PATH_EXIST                   # TODO: "unlink"
#   ./hyperspace.py update  ENTRY_PATH -p protocol -t key_0=value_0
#
# Usage: Bootstrap
# ~~~~~~~~~~~~~~~~
#   export HYPERSPACE_RANDOM_HASH=false  # use incrementing hash value
#
#   ./hyperspace.py initialize
#   ./hyperspace.py ln      new_link entry        # dependency | category
#   ./hyperspace.py ls      [-l] [-n] [-r] [path]
#   ./hyperspace.py mk      dependency            # dependency
#   ./hyperspace.py mkdir   category              # category only
#   ./hyperspace.py rm      entry                 # dependency | category
#   ./hyperspace.py storage [-s]
#
# Functions
# ~~~~~~~~~
#   _initialize()
#   _ln(link_path, target_path)
#   _ls(path, long_format, dependency_count, recursive))
#   _mk(name)
#   _mkdir(name)
#   _rm(name)
#   _storage(sort_by_name)
#
# To Do
# ~~~~~
# - Separate the design and implementation of HyperSpace and Storage
#   - Move HyperSpace file-system based implementation into StorageFile ?
#   - HyperSpace: create(): Category with different HyperSpace root ?
#   - Storage:    create(): Category or Dependency (Definition and Contents)
#
# - Implement "aiko_hyperspace repl" for interactive CRUD, etc
#
# * FIX: Consolidate service.py:ServiceFilter into ServiceFields (and use this)
#
# * FIX: "service.py:service_args()" to include "owner" --> "run_command()"
#
# * FIX: AttributeError: 'ServiceRemoteProxy' object has no attribute 'create'
#        do_command(HyperSpace, ServiceFilter(...),  # But HyperSpaceImpl works
#            lambda hyperspace: hyperspace.create(), ...)      # create() fails
#
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
# * Aiko Dashboard plug-in for HyperSpace(Actor), e.g REPL and tree view
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
#   - ProcessManager(LifeCycleManager): Lazy loading of HyperSpace entries
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
_PATH_DELIMITER = "/"
_RESPONSE_TOPIC = f"{aiko.topic_in}"
_ROOT_FILENAME = ".root"
_STORAGE_FILENAME = "storage"
_TRACKED_PATHNAME = f"{_STORAGE_FILENAME}/tracked_paths"
_HASH_PATHNAME = f"{_STORAGE_FILENAME}/hash_counter"

# --------------------------------------------------------------------------- #

class HyperSpace(Category, Actor):
    Interface.default(
        "HyperSpace", "aiko_services.main.hyperspace.HyperSpaceImpl")

    @abstractmethod
    def create(self, category_path):
        pass

    @abstractmethod
    def destroy(self, category_path):
        pass

    @abstractmethod
    def dump(self):
        pass

# --------------------------------------------------------------------------- #

class HyperSpaceImpl(HyperSpace):
    def __init__(self, context, storage_url):
        context.call_init(self, "Actor", context)
        context.call_init(self, "Category", context)

        self.category = context.get_implementation("Category")        # methods

        self.share.update({                             # Inherit from Category
            "source_file": f"v{VERSION}⇒ {__file__}",
            "storage_url": storage_url,
            "metrics": {
                "created": 0,
                "running": 1 + len(self.entries)   # Including self 😅
            #   "time_started": 0            # TODO: UTC time started --> Actor
            },                               #       or time.monotonic()
        })
        self.ec_producer = ECProducer(self, self.share)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    #   self.thread = Thread(target=self._run, daemon=True, name=_THREAD_NAME)
    #   self.thread.start()                           # TODO: Use ThreadManager

    #   if not storage_url:
    #       storage_url = PATHNAME_OF_CURRENT_WORKING_DIRECTORY
    #   self._load_hyperspace(storage_url)

    def _category_path_iterator(self, category_path, delimiter=_PATH_DELIMITER):
        for name in category_path.split(delimiter):
            yield name

    def _category_traverse(self, category_path, delimiter=_PATH_DELIMITER):
        dirname, basename = dir_base_name(category_path)
        current_category = self
        if dirname == ".":
            return current_category, basename

        for category_name in self._category_path_iterator(dirname):
            if category_name in current_category.entries:
                entry = current_category.entries[category_name]
                if entry.service_filter.protocol != CATEGORY_PROTOCOL:
                    return None, None
                current_category = entry
            else:
                return None, None
        return current_category, basename

    def add(self, entry_path,
        service_filter, lifecycle_manager_url=None, storage_url=None):

        category, entry_name = self._category_traverse(entry_path)
        if category:
            if service_filter and not isinstance(service_filter, ServiceFilter):
                service_filter = ServiceFilter(*service_filter)
            if service_filter.name == "*":
                service_filter.name = entry_name
            self.category.add(category, entry_name,
                service_filter, lifecycle_manager_url, storage_url)

    def create(self, category_path):
        current_category = self
        category_created = False
        tags = ["ec=true"]

        for category_name in self._category_path_iterator(category_path):
            if category_name in current_category.entries:
                entry = current_category.entries[category_name]
                if entry.service_filter.protocol != CATEGORY_PROTOCOL:
                    break
                category = entry
            else:
                init_args = actor_args(
                    category_name, None, None, CATEGORY_PROTOCOL, tags)
                init_args["service_filter"] = ServiceFilter(
                    name=category_name, protocol=CATEGORY_PROTOCOL, tags=[])
                category = compose_instance(CategoryImpl, init_args)
                current_category.entries[category_name] = category
                category_created = True
            current_category = category

        if category_created:
            self.ec_producer.update("entries", len(self.entries))

# TODO: Categories destroy() versus Dependencies remove() ?  Check protocol ?
# TODO: Recursively remove Categories ... using "limit" argument
# TODO: Replace "destroy()" with "remove()", only destroy when last reference
# TODO: Remove Dependencies and clean-up any resources ?

    def destroy(self, category_path):
        category_parent, category_name = self._category_traverse(category_path)
        self._destroy(category_parent, category_name)

    def _destroy(self, category_parent, category_name):
        if category_parent and category_name in category_parent.entries:
            category = category_parent.entries[category_name]
            if category.service_filter.protocol == CATEGORY_PROTOCOL:
                del category_parent.entries[category_name]
                aiko.process.remove_service(category.service_id)
                self.ec_producer.update("entries", len(self.entries))

    def dump(self):
        if len(self.entries):
            state = f" ...\n{self}"
        else:
            state = ": no entries"
        self.logger.info(f"Dump state{state}")

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            self.logger.setLevel(str(item_value).upper())

    def exit(self):
        aiko.process.terminate()

    def is_type(self, type_name):
        if type_name.lower() == "hyperspace":
            return True
        return self.category.is_type(self, type_name)

    def list(self, topic_path_response, entry_path=None, recursive=False):
        if not isinstance(recursive, bool):
            recursive = recursive.lower() in ("true", "t")

        category, entry_name = self._category_traverse(entry_path)
        if category and entry_name in category.entries:
            entry = category.entries[entry_name]
            if entry.service_filter.protocol == CATEGORY_PROTOCOL:
                category = entry

        def get_entry_records(entry_records, category, category_name, level):
            if level > 0:
                entry_records += [f"{-level} {category_name}"]
            entry_records += category._get_entry_records(None, level)
            if recursive:
                for entry_name, entry in category.entries.items():
                    if entry.is_type("Category"):
                        get_entry_records(
                            entry_records, entry, entry_name, level+1)

        entry_records = []
        get_entry_records(entry_records, category, None, 0)
        category._list_publish(topic_path_response, entry_records)

# TODO: Categories destroy() versus Dependencies remove() ?  Check protocol ?

    def remove(self, entry_path):
        category_parent, entry_name = self._category_traverse(entry_path)
        if category_parent and entry_name in category_parent.entries:
            entry = category_parent.entries[entry_name]
            if entry.service_filter.protocol == CATEGORY_PROTOCOL:
                self._destroy(category_parent, entry_name)
            else:
                self.category.remove(category_parent, entry_name)

    def __str__(self):
        result = ""
        for entry_name, entry in self.entries.items():
            entry_type = "/" if entry.is_type("Category") else ""
            new_line = "\n" if result else ""
            result += f"{new_line}  {entry_name}{entry_type}"
        return result

    def update(self, entry_path, service=None,
        service_filter=None, lifecycle_manager_url=None, storage_url=None):

        category_parent, entry_name = self._category_traverse(entry_path)
        if category_parent and entry_name in category_parent.entries:
            self.category.update(category_parent, entry_name, service,
                service_filter, lifecycle_manager_url, storage_url)

# --------------------------------------------------------------------------- #
# HyperSpace Storage: File-system based persistance

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

# Create new link to an existing dependency or category
#
# ./hyperspace.py ln new_link entry  # dependency | category

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

# List categories and depedencies in a tree-style recursive format
#
# ./hyperspace.py ls [-l] [-n] [-r] [path]

def _ls(path, long_format=False, entry_count=False, recursive=False):
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
                if entry_count:
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

# Create a Dependency (file)
#
# ./hyperspace.py mk entry  # Dependency only

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

# Delete a Dependency (file) or Category (directory)
#
# ./hyperspace.py rm entry  # Dependency | Category

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

# ./hyperspace.py ln new_link_entry existing_entry

@main.command(name="ln")
@click.argument("link_path")
@click.argument("target_path")

def ln_command(link_path, target_path):
    "Create new link to an existing dependency or category"
    _ln(link_path, target_path)

# ./hyperspace.py ls [-l] [-n] [-r] [path]

@main.command(name="ls")
@click.argument("path", required=False, default=".")
@click.option("--entry_count", "-c", default=False, is_flag=True,
    help="Show category's entry count")
@click.option("--long_format", "-l", default=False, is_flag=True,
    help="Long format with hash identifiers")
@click.option("--recursive", "-r", default=False, is_flag=True,
    help="Recursive listing")

def ls_command(path, entry_count, long_format, recursive):
    "List dependencies (files) and categories (directories)"
    _ls(path, long_format, entry_count, recursive)

# ./hyperspace.py mk entry  # dependency only

@main.command(name="mk")
@click.argument("name")

def mk_command(name):
    "Create a dependency (file)"
    _mk(name)

# ./hyperspace.py mkdir category  # category only

@main.command(name="mkdir")
@click.argument("name")

def mkdir_command(name):
    "Create a category (directory)"
    _mkdir(name)

# ./hyperspace.py rm entry  # dependency | category

@main.command(name="rm")
@click.argument("name")

def rm_command(name):
    "Remove a dependency or category"
    _rm(name)

# ./hyperspace.py storage [-s]

@main.command(name="storage")
@click.option("--sort_by_name", "-s", default=False, is_flag=True,
    help="Sort by name")

def storage_command(sort_by_name):
    "List entry storage/tracked_paths and linked entries"
    _storage(sort_by_name)

# --------------------------------------------------------------------------- #
# HyperSpace CLI: Distributed Actor commands
#
# To Do
# ~~~~~
# add
# ~~~
# * Protocol well-known short names, e.g "category" --> CATEGORY_PROTOCOL
# * Created and modified time
# - Owner defaults to current user, ACLs "u:name g:name o:name rwx:name ..." ?
# - ServiceFilter fields (see aiko_hyperspace create)
#
# create
# ~~~~~~
# * Differentiate Categories with same name, e.g ENTRY_PATH tag ?
# * Protocol well-known short names, e.g "category" --> CATEGORY_PROTOCOL
# * Created and modified time
# - Owner defaults to current user, ACLs "u:name g:name o:name rwx:name ..." ?
# - ServiceFilter fields ...
#   -n,   --service_name TEXT           # Service name
#   -p,   --protocol TEXT               # CATEGORY_PROTOCOL (default)
#   -tr,  --transport TEXT              # Service transport (MQTT default)
# * -o,   --owner TEXT                  # Service owner     (current user)
#   -t,   --tags TEXT                   # Service tags
# * -lcm, --lifecycle_manager_url TEXT  # LifeCycleManager URL
# * -s,   --storage_url TEXT            # Storage URL (file, sqlite, MQTT, etc)
#
# destroy
# ~~~~~~~
# * Clean-up all Process, Service, Actor, Dependency, Category resources
# * Only destroy() Categories with a LifeCycleManager of "HyperSpaceImpl.self"
# - Regex, e.g wildcards "*", "+", ...
# - [r]ecursive [level]  # default: 1, * means no limit
# - Only owner can destroy ... implement ACLs later
#
# list
# ~~~~
# * Specific "entry_path"
# * Regex, e.g wildcards "*", "+", ...
# * [c]ount  # Category Entry count
# * [l]ong_format
# * [r]ecursive [level]  # default: 1 or * ? (* means no limit)
#
# remove
# ~~~~~~
# - Regex, e.g wildcards "*", "+", ...
# - [r]ecursive [level]  # default: 1, * means no limit
# - Only owner can remove ... ACLs later
#
# update
# ~~~~~~
# * category_path tree: category/category/category
# * Protocol well-known short names, e.g "category" --> CATEGORY_PROTOCOL
# - Regex, e.g wildcards "*", "+", ...
# - ServiceFilter fields (see aiko_hyperspace create)
# - Only owner can update ... implement ACLs later

@main.command(name="add", no_args_is_help=True)
@click.argument("entry_path", type=str, required=True, default=None)
@click.option("--hyperspace_name", "-hn", type=str, default=None,
    help="HyperSpace name, default is the local hostname")
@click.option("--service_name", "-n", type=str, default="*",
    help="Service name")
@click.option("--protocol", "-p", type=str, default="*",
    help="Service protocol")
@click.option("--transport", "-tr", type=str, default="*",
    help="Service transport")
@click.option("--owner", "-o", type=str, default="*",
    help="Service owner")
@click.option("--tags", "-t", type=str, multiple=True, default=None,
    help="Service tags")
@click.option("--lifecycle_manager_url", "-lcm", type=str, default=None,
    help="LifeCycleManager URL")
@click.option("--storage_url", "-s", type=str, default=None,
    help="Storage URL")

def add_command(entry_path, hyperspace_name,
    service_name, protocol, transport, owner, tags,
    lifecycle_manager_url, storage_url):

    """Add HyperSpace Entry

    aiko_hyperspace add ENTRY_PATH

    \b
    • ENTRY_PATH: Entry PATH
    """

    tags = tags if tags else []                 # Assign default tags value
    service_filter = ServiceFilter(             # TODO: Or use ServiceFields ??
        "*", service_name, protocol, transport, owner, tags)

    do_command(Category,
        ServiceFilter(name=hyperspace_name, protocol=PROTOCOL),
        lambda hyperspace: hyperspace.add(entry_path,
            service_filter, lifecycle_manager_url, storage_url), terminate=True)
    aiko.process.run()

@main.command(name="create", no_args_is_help=True)
@click.argument("category_path", type=str, required=True, default=None)
@click.option("--hyperspace_name", "-hn", type=str, default=None,
    help="HyperSpace name, default is the local hostname")

def create_command(category_path, hyperspace_name):
    """Create HyperSpace Category

    aiko_hyperspace create [-hn HYPERSPACE_NAME] CATEGORY_PATH

    \b
    • CATEGORY_PATH: Category path
    """

    do_command(HyperSpaceImpl,
        ServiceFilter(name=hyperspace_name, protocol=PROTOCOL),
        lambda hyperspace: hyperspace.create(category_path), terminate=True)
    aiko.process.run()

@main.command(name="destroy", no_args_is_help=True)
@click.argument("category_path", type=str, required=True, default=None)
@click.option("--hyperspace_name", "-hn", type=str, default=None,
    help="HyperSpace name, default is the local hostname")

def destroy_command(category_path, hyperspace_name):
    """Destroy HyperSpace Category

    aiko_hyperspace destroy [-hn HYPERSPACE_NAME] CATEGORY_PATH

    \b
    • CATEGORY_PATH: Category path
    """

    do_command(HyperSpaceImpl,
        ServiceFilter(name=hyperspace_name, protocol=PROTOCOL),
        lambda hyperspace: hyperspace.destroy(category_path), terminate=True)
    aiko.process.run()

@main.command(name="dump", help="Dump HyperSpace state")
@click.option("--hyperspace_name", "-hn", type=str, default=None,
    help="HyperSpace name, default is the local hostname")

def dump_command(hyperspace_name):
    do_command(HyperSpace,
        ServiceFilter(name=hyperspace_name, protocol=PROTOCOL),
        lambda hyperspace: hyperspace.dump(), terminate=True)
    aiko.process.run()

@main.command(name="exit", help="Exit HyperSpace")
@click.option("--hyperspace_name", "-hn", type=str, default=None,
    help="HyperSpace name, default is the local hostname")

def exit_command(hyperspace_name):
    do_command(HyperSpace,
        ServiceFilter(name=hyperspace_name, protocol=PROTOCOL),
        lambda hyperspace: hyperspace.exit(), terminate=True)
    aiko.process.run()

@main.command(name="list")
@click.argument("entry_path", type=str, required=False, default=None)
@click.option("--hyperspace_name", "-hn", type=str, default=None,
    help="HyperSpace name, default is the local hostname")
@click.option("--long_format", "-l", is_flag=True,
    help="Long format with Service, LifeCycleManager URL, Storage URL")
@click.option("--recursive", "-r", is_flag=True,
    help="Recursively list Category entries")

def list_command(entry_path, hyperspace_name, long_format, recursive):
    """List HyperSpace Entries

    aiko_category list ENTRY_PATH [-l] [-r]

    \b
    • ENTRY_PATH: Entry path
    """

    CategoryImpl.list_command(
        hyperspace_name, entry_path, long_format, recursive, PROTOCOL)
    aiko.process.run()

@main.command(name="remove", no_args_is_help=True)
@click.argument("entry_path", type=str, required=True, default=None)
@click.option("--hyperspace_name", "-hn", type=str, default=None,
    help="HyperSpace name, default is the local hostname")

def remove_command(entry_path, hyperspace_name):
    """Remove HyperSpace Entry

    aiko_hyperspace remove [-hn HYPERSPACE_NAME] ENTRY_PATH

    \b
    • ENTRY_PATH: Entry path
    """

    do_command(HyperSpaceImpl,
        ServiceFilter(name=hyperspace_name, protocol=PROTOCOL),
        lambda hyperspace: hyperspace.remove(entry_path), terminate=True)
    aiko.process.run()

@main.command(name="run")
@click.argument("storage_url", required=False, default=None)  # TODO: Implement
@click.option("--hyperspace_name", "-hn", type=str, default=None,
    help="HyperSpace name, default is the local hostname")
@click.option("--protocol", "-p", type=str, default=PROTOCOL,
    help="Service protocol")
@click.option("--transport", "-tr", type=str, default=None,
    help="Service transport")
# @click.option("--owner", "-o", type=str, default=None,      # TODO: Implement
#     help="Service owner")
@click.option("--tags", "-t", type=str, multiple=True, default=None,
    help="Service tags")

def run_command(storage_url, hyperspace_name, protocol, transport, tags):
    """Run HyperSpace

    aiko_hyperspace run [-hn HYPERSPACE_NAME] [STORAGE_URL]

    \b
    • STORAGE_URL: HyperSpace storage location, e.g file://...
    """

    hyperspace_name = hyperspace_name if hyperspace_name else get_hostname()

    tags = list(tags) + ["ec=true"]
    init_args = actor_args(
        hyperspace_name, None, None, protocol, tags, transport)
    init_args["storage_url"] = storage_url
    hyperspace = compose_instance(HyperSpaceImpl, init_args)
    aiko.process.run()

@main.command(name="update", no_args_is_help=True)
@click.argument("entry_path", type=str, required=True, default=None)
@click.option("--hyperspace_name", "-hn", type=str, default=None,
    help="HyperSpace name, default is the local hostname")
@click.option("--service_name", "-n", type=str, default="0:",     # None --> 0:
    help="Service name")
@click.option("--protocol", "-p", type=str, default="0:",         # None --> 0:
    help="Service protocol")
@click.option("--transport", "-tr", type=str, default="0:",       # None --> 0:
    help="Service transport")
@click.option("--owner", "-o", type=str, default="0:",            # None --> 0:
    help="Service owner")
@click.option("--tags", "-t", type=str, multiple=True, default=None,
    help="Service tags")
@click.option("--lifecycle_manager_url", "-lcm", type=str, default=None,
    help="LifeCycleManager URL")
@click.option("--storage_url", "-s", type=str, default=None,
    help="Storage URL")

def update_command(entry_path, hyperspace_name,
    service_name, protocol, transport, owner, tags,
    lifecycle_manager_url, storage_url):

    """Update HyperSpace Entry

    aiko_hyperspace update [-hn HYPERSPACE_NAME] ENTRY_PATH

    \b
    • ENTRY_PATH: Entry path
    """

    tags = tags if tags else []                 # Assign default tags value
    service_filter = ServiceFilter(             # TODO: Or use ServiceFields ??
        "*", service_name, protocol, transport, owner, tags)

    do_command(HyperSpaceImpl,
        ServiceFilter(name=hyperspace_name, protocol=PROTOCOL),
        lambda hyperspace: hyperspace.update(entry_path, None,
            service_filter, lifecycle_manager_url, storage_url), terminate=True)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
