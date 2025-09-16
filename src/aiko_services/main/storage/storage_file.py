#!/usr/bin/env python3
#
# Usage
# ~~~~~
# AIKO_LOG_LEVEL=DEBUG aiko_storage initialize [STORAGE_URL]
#
# AIKO_LOG_LEVEL=DEBUG aiko_storage run [STORAGE_URL]
#
# AIKO_LOG_LEVEL=DEBUG aiko_storage test_command [command_0]
#   Storage command: test_command(command_0)
#
# AIKO_LOG_LEVEL=DEBUG aiko_storage test_request [request_0]
#   Responses ...
#     ['request_0']
#
# To Do
# ~~~~~
# - Consider database-based and ValKey(Redis) implementation(s)
#     import sqlite3
#     self.connection = sqlite3.connect(storage_url)
#     @click.argument("storage_url", default="file://./aiko_storage.db")

from abc import abstractmethod
import click
import hashlib
import os
from pathlib import Path
import stat
import sys

from aiko_services.main import *
from aiko_services.main.storage import *
from aiko_services.main.utilities import get_hostname

__all__ = ["StorageFileImpl", "StorageTest"]

_VERSION = 0

PROTOCOL_TYPE = "storage"
ACTOR_TYPE = f"{PROTOCOL_TYPE}_file"
PROTOCOL = f"{SERVICE_PROTOCOL_AIKO}/{PROTOCOL_TYPE}:{_VERSION}"

_CWD_URL = "file://./"  # relative URL for the current working directory
_HASH_LENGTH = 12  # 6 bytes = 12 hex digits
_RESPONSE_TOPIC = f"{aiko.topic_in}"
_ROOT_FILENAME = ".root"
_STORAGE_FILENAME = "storage"
_TRACKED_PATHNAME = f"{_STORAGE_FILENAME}/tracked_paths"
_HASH_PATHNAME = f"{_STORAGE_FILENAME}/hash_counter"

# --------------------------------------------------------------------------- #

class StorageTest(Storage):  # TODO: Move further down, add StorageTestImpl
    Interface.default("StorageTest",
        "aiko_services.main.storage.storage_file.StorageFileImpl")

    @abstractmethod
    def test_command(self, parameter):
        pass

    @abstractmethod
    def test_request(self, topic_path_response, request):
        pass

# --------------------------------------------------------------------------- #

class StorageFileImpl(StorageTest):  # TODO: "StorageTest" --> "Storage"
    def __init__(self, context, storage_url):
        context.call_init(self, "Actor", context)

        self.share.update({                                # Inherit from Actor
            "source_file": f"v{_VERSION}⇒ {__file__}",
            "hash_counter": 0,
            "storage_url": storage_url
        })
        self.ec_producer = ECProducer(self, self.share)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    @classmethod
    def create_storage(cls,
        storage_name=None, storage_url=_CWD_URL):  # current working directory

        tags = ["ec=true"]
        init_args = actor_args(storage_name, protocol=PROTOCOL, tags=tags)
        init_args["storage_url"] = storage_url
        return compose_instance(StorageFileImpl, init_args)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            self.logger.setLevel(str(item_value).upper())

# --------------------------------------------------------------------------- #
# Storage API: File-system based implementation
#
# initialize() --> _initialize()
# add()        --> _mk() --[rename]--> add()
# create()     --> _mkdir()
# destroy()    --> _rm()
# dump()       --> _storage()
# exit
# link()       --> _ln()
# list()       --> _ls()
# remove()     --> _rm()
# update()     --> update()

    def add(self, entry_name,
        service_filter=None, lifecycle_manager_url=None, storage_url=None):
        pass

    def create(self, category_path):
        pass

    def destroy(self, category_path):
        pass

    def dump(self):
        pass

    def exit(self):
        aiko.process.terminate()

    def initialize(self, storage_url=_CWD_URL):  # TODO: "storage_url" ????????
        print("### StorageFileImpl.initialize() unimplemented ###")

    def list(self, topic_path_response, entry_name=None, recursive=False):
        pass

    def link(self, entry_path_new, entry_path_existing):
        pass

    def remove(self, entry_name):
        pass

    def update(self, entry_name, service=None,
        service_filter=None, lifecycle_manager_url=None, storage_url=None):
        pass

    def test_command(self, parameter):
        print(f"Storage command: test_command({parameter})")

    def test_request(self, topic_path_response, request):
        aiko.message.publish(topic_path_response, "(item_count 1)")
        aiko.message.publish(topic_path_response, f"(response {request})")

# --------------------------------------------------------------------------- #
# Storage Bootstrap: File-system based implementation

    @classmethod
    def _check_root_symlink(cls):
        root_pathname = Path.cwd() / _ROOT_FILENAME
        if not os.path.lexists(root_pathname):
            raise FileExistsError(
                f'Storage: symlink "./{_ROOT_FILENAME}" must exist')
        else:
            if not os.path.islink(root_pathname):
                raise FileExistsError(
                    f'Storage: File "./{_ROOT_FILENAME}" must be a symlink')

    # Initialize storage directory and .root symlink

    def _initialize(self):
        cwd = Path.cwd()
        root_pathname = cwd / _ROOT_FILENAME
        if not root_pathname.is_symlink():
            root_pathname.symlink_to(cwd)
            print(f"Created {_ROOT_FILENAME} --> {cwd}")

        storage_pathname = cwd / _STORAGE_FILENAME
        if not storage_pathname.is_dir():
            storage_pathname.mkdir(parents=True)
            print(f"Created {_STORAGE_FILENAME}")

        hash_counter = 0
        hash_pathname = cwd / _HASH_PATHNAME
        if hash_pathname.exists():
            try:
                hash_counter = int(hash_pathname.read_text())
            except ValueError:
                pass  # TODO: raise SystemExit
        else:
            hash_pathname.write_text(str(hash_counter))
        self.ec_producer.update("hash_counter", hash_counter)

# Generate hash UID, persisting the hash_counter when using incremental mode

def _generate_hash():
    if os.environ.get("STORAGE_RANDOM_HASH", "true").lower() == "true":
        hash = hashlib.sha256(os.urandom(16)).hexdigest()
    else:
        hash_counter = self.share["hash_counter"]
        hash = str(hash_counter).zfill(_HASH_LENGTH)
        hash_counter += 1
        self.ec_producer.update("hash_counter", hash_counter)
        Path(_HASH_PATHNAME).write_text(f"{hash_counter}\n")
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
# aiko_storage ln new_link entry  # dependency | category

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
# aiko_storage ls [-l] [-n] [-r] [path]

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
        return sum(1 for file in target_path.rglob("*")  \
                      if file.is_file() and file.stat().st_size > 0)

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
# aiko_storage mk entry  # Dependency only

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
# aiko_storage mkdir category  # category only

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
# aiko_storage rm entry  # Dependency | Category

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
# aiko_storage storage [-s]

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
# Storage CLI: File-system based implementation

@click.group()

def main():
    """Create, Read/List, Update and Destroy Storage"""

    subcommand = click.get_current_context().invoked_subcommand
    subcommands_which_run_anywhere = ["create", "dump", "exit", "initialize"]
# TODO: DEVELOPMENT ONLY: REMOVE ALONG WITH test_command() and test_request()
    subcommands_which_run_anywhere += ["run", "test_command", "test_request"]

    if subcommand not in subcommands_which_run_anywhere:
        diagnostic = None
        try:
            StorageFileImpl._check_root_symlink()
        except FileExistsError as file_exists_error:
            diagnostic = str(file_exists_error)
        if diagnostic:
            advice = 'Consider running "aiko_storage initialize"'
            raise SystemExit(f"{diagnostic}\n{advice}")

@main.command(name="exit", help="Exit Storage")
@click.option("--storage_name", "-sn", type=str, default=None,
    help="Storage name, default is the local hostname")

def exit_command(storage_name):
    do_command(Storage, ServiceFilter(name=storage_name, protocol=PROTOCOL),
        lambda storage: storage.exit(), terminate=True)
    aiko.process.run()

@main.command(name="initialize")
@click.argument("storage_url", default=_CWD_URL)  # TODO: "storage_url" ???????

def initialize_command(storage_url):
    """Initialize Storage (.root and storage/)

    aiko_storage initialize [STORAGE_URL]

    \b
    • STORAGE_URL: Storage file-system location, e.g file://./
    """

    storage_name = get_hostname()
    storage = StorageFileImpl.create_storage(storage_name, storage_url)
    storage.initialize()

@main.command(name="run")
@click.argument("storage_url", default=_CWD_URL)  # TODO: "storage_url" ???????
@click.option("--storage_name", "-sn", type=str, default=None,
    help="Storage name, default is the local hostname")

def run_command(storage_name, storage_url):
    """Run Storage backed by the file-system

    aiko_storage run [-sn STORAGE_NAME] [STORAGE_URL]

    \b
    • STORAGE_URL: Storage file-system location, e.g file://./
    """

    storage_name = storage_name if storage_name else get_hostname()

    storage = StorageFileImpl.create_storage(storage_name, storage_url)
    aiko.process.run()  # TODO: Actor:aiko.process.run() or storage.run() ?

@main.command(name="test_command", help="Test Storage invoke command")
@click.argument("argument", default="argument_0", required=False)
@click.option("--storage_name", "-sn", type=str, default=None,
    help="Storage name, default is the local hostname")

def test_command(storage_name, argument):
    do_command(StorageTest, ServiceFilter(name=storage_name, protocol=PROTOCOL),
        lambda storage: storage.test_command(argument), terminate=True)
    aiko.process.run()

@main.command(name="test_request", help="Test Storage invoke request")
@click.argument("request", default="request_0", required=False)
@click.option("--storage_name", "-sn", type=str, default=None,
    help="Storage name, default is the local hostname")

def test_request(storage_name, request):
    def response_handler(response):
        if len(response):
            output = f"Responses ..."
            for record in response:
                output += f"\n  {record}"
        else:
            output = "No response"
        print(output)

    do_request(StorageTest, ServiceFilter(name=storage_name, protocol=PROTOCOL),
        lambda storage: storage.test_request(_RESPONSE_TOPIC, request),
        response_handler, _RESPONSE_TOPIC, terminate=True)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
