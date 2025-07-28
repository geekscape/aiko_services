#!/usr/bin/env python3
#
# Usage
# ~~~~~
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
# * Persist "_hash_counter", e.g HASH_PATHNAME="$STORAGE_FILENAME/hash_counter"
#   - Ensure compatibility with "hyperspace.sh"
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
# - ProcessManager(LifeCycleManager): Complete Service LifeCycle State
#   - Improvements to "src/aiko_services/main/state.py"
# - ProcessManager(LifeCycleManager): Lazy loading of HyperSpace nodes
#
# - StorageManager (content, definition) backed by ...
#   - ✅ File-system, SQLite3, MQTT
# - HyperSpace (links) backed by ...
#   - ✅ File-system, SQLite3, MQTT, Knowledge Graph

import click
import errno
import hashlib
import os
from pathlib import Path
import stat
import sys

HASH_LENGTH = 12  # 6 bytes = 12 hex digits
ROOT_FILENAME = ".root"
STORAGE_FILENAME = "storage"
TRACKED_PATHNAME = f"{STORAGE_FILENAME}/tracked_paths"
HASH_PATHNAME = f"{STORAGE_FILENAME}/hash_counter"

_hash_counter = 0

# Initialize storage directory and .root symlink

def _check_root_symlink():
    root_pathname = Path.cwd() / ROOT_FILENAME
    if not os.path.lexists(root_pathname):
        raise FileExistsError(
            f'HyperSpace: Symlink "./{ROOT_FILENAME}" must exist')
    else:
        if not os.path.islink(root_pathname):
            raise FileExistsError(
                f'HyperSpace: File "./{ROOT_FILENAME}" must be a symlink')

def _initialize():
    cwd = Path.cwd()
    root_pathname = cwd / ROOT_FILENAME
    if not root_pathname.is_symlink():
        root_pathname.symlink_to(cwd)
        print(f"Created {ROOT_FILENAME} --> {cwd}")

    storage_pathname = cwd / STORAGE_FILENAME
    if not storage_pathname.is_dir():
        storage_pathname.mkdir(parents=True)
        print(f"Created {STORAGE_FILENAME}")

    global _hash_counter
    hash_pathname = cwd / HASH_PATHNAME
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
        hash = str(_hash_counter).zfill(HASH_LENGTH)
        _hash_counter += 1
        Path(HASH_PATHNAME).write_text(f"{_hash_counter}\n")
    return hash[-HASH_LENGTH:]

# Clean up empty storage directories up to root

def _clean_storage(tracked_directory):
    tracked_path = Path(tracked_directory)
    storage_path = Path(STORAGE_FILENAME)
    while tracked_path != storage_path and tracked_path != Path("."):
        if tracked_path.is_dir() and not any(tracked_path.iterdir()):
            tracked_path.rmdir()
            tracked_path = tracked_path.parent
        else:
            break

# Generate a unique storage path avoiding collisions

def _create_path():
    storage_path = Path(STORAGE_FILENAME)
    existing_paths = set()
    if Path(TRACKED_PATHNAME).exists():
        existing_paths.update(Path(TRACKED_PATHNAME).read_text().splitlines())
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
    Path(TRACKED_PATHNAME).parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKED_PATHNAME, "a+") as tracked_paths_file:
        tracked_paths_file.seek(0)
        tracked_paths = tracked_paths_file.read().splitlines()
        if relative_path not in tracked_paths:
            tracked_paths_file.write(relative_path + "\n")

# Untrack a removed storage path

def _untrack_path(path):
    relative_path = _normalize_path(path)
    tracked_path = Path(TRACKED_PATHNAME)
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
    if STORAGE_FILENAME not in resolved_path.parts:
        print(f'Error: target "{target_path}" is not in the storage directory',
            file=sys.stderr)
        return 1
    base_directory = Path(link_path).parent or Path(".")
    base_root = base_directory / ROOT_FILENAME
    link_base = base_root if base_root.is_symlink() else Path(ROOT_FILENAME)

    # Determine path under ".root/storage/"
    try:
        relative_path = resolved_path.relative_to(cwd / STORAGE_FILENAME)
        relative_storage_path = f"{STORAGE_FILENAME}/{relative_path.as_posix()}"
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
                absolute_target_path.relative_to(Path.cwd() / STORAGE_FILENAME)
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
        Path(name).symlink_to(f"{ROOT_FILENAME}/{path}")
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
    rel_back = _relative_path(str(Path.cwd() / ROOT_FILENAME), path)
    try:
        Path(path, ROOT_FILENAME).symlink_to(rel_back)
    except FileExistsError:
        print(f'Error: internal .root link in "{path}" already exists',
            file=sys.stderr)
        return 1
    try:
        Path(name).symlink_to(f"{ROOT_FILENAME}/{path}")
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
            storage_path = cwd / STORAGE_FILENAME
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
                absolute_path = cwd / STORAGE_FILENAME
                relative_path = absolute_target_path.relative_to(absolute_path)
                tracked_paths.add((str(relative_path), path.name))
            except ValueError:
                continue
    items = sorted(tracked_paths, key=lambda x: x[1] if sort_by_name else x[0])
    for relative_path, name in items:
        print(f"{relative_path}  {name}")

# --------------------------------------------------------------------------- #

@click.group()
def main():
    if not click.get_current_context().invoked_subcommand == "initialize":
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
@click.option("-l", "--long_format", default=False, is_flag=True,
    help="Long format with hash identifiers")
@click.option("-n", "--node_count", default=False, is_flag=True,
    help="Show category's node count")
@click.option("-r", "--recursive", default=False, is_flag=True,
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

# # ./hyperspace.py mkdir category  # category only

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
@click.option("-s", "--sort_by_name", default=False, is_flag=True,
    help="Sort by name")
def storage_command(sort_by_name):
    "List node storage/tracked_paths and linked nodes"
    _storage(sort_by_name)

# --------------------------------------------------------------------------- #
