#!/usr/bin/env python3
#
# Usage
# ~~~~~
# Can use either "aiko_storage_file" (preferred) or "./storage_file.py"
#
# # export STORAGE_RANDOM_UID=False      # Use predictable incrementing UIDs
# ./aiko_storage_file initialize [STORAGE_URL]
# ./aiko_storage_file run [STORAGE_URL]  # file in-memory sqlite mqtt valkey
# ./aiko_storage_file exit
#
# aiko_storage_file add  [-b] DEPENDENCY  # file
# aiko_storage_file list [-b] [-l] [-r] [PATH]
#
# To Do
# ~~~~~
# * Default "_STORAGE_FILENAME" becomes "_storage_", override via "storage_url"
#   * HyperSpace "storage_url" value will become "_hyperspace_"
#
# - Consider database-based and ValKey(Redis distributed) implementation(s)
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
from aiko_services.main.utilities import generate, get_hostname

__all__ = ["StorageFileImpl"]

_VERSION = 0

PROTOCOL_TYPE = "storage"
ACTOR_TYPE = f"{PROTOCOL_TYPE}_file"
PROTOCOL = f"{SERVICE_PROTOCOL_AIKO}/{PROTOCOL_TYPE}:{_VERSION}"

_CWD_URL = "file://./"         # relative URL for the current working directory
_RESPONSE_TOPIC = f"{aiko.topic_in}"
_ROOT_FILENAME = ".root"
_STORAGE_FILENAME = "_hyperspace_"      # TODO: Default will become "_storage_"
_TRACKED_PATHNAME = f"{_STORAGE_FILENAME}/tracked_paths"
_UID_LENGTH = 12  # 12 hex digits = 6 bytes
_UID_PATHNAME = f"{_STORAGE_FILENAME}/uid_counter"

# --------------------------------------------------------------------------- #

class StorageFileImpl(Storage):
    @classmethod
    def create_storage(cls, storage_name, storage_url=_CWD_URL):
        tags = ["ec=true"]
        init_args = actor_args(storage_name, protocol=PROTOCOL, tags=tags)
        init_args["storage_url"] = storage_url
        return compose_instance(StorageFileImpl, init_args)

    def __init__(self, context, storage_url):
        context.call_init(self, "Actor", context)

        self.share.update({                                # Inherit from Actor
            "source_file": f"v{_VERSION}⇒ {__file__}",
            "storage_url": storage_url,
            "uid_counter": 0
        })
        self.ec_producer = ECProducer(self, self.share)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            self.logger.setLevel(str(item_value).upper())

# --------------------------------------------------------------------------- #
# Storage Bootstrap: File-system based implementation

    @classmethod
    def _check_root_symbolic_link(cls):
        root_pathname = Path.cwd() / _ROOT_FILENAME
        if not os.path.lexists(root_pathname):
            raise FileExistsError(
                f'Storage: symbolic link "./{_ROOT_FILENAME}" must exist')
        else:
            if not os.path.islink(root_pathname):
                raise FileExistsError(
                    f'Storage: File "./{_ROOT_FILENAME}" is not a symbolc link')

    # Generate a unique storage path avoiding collisions

    def _create_unique_path(self):
        storage_path = Path(_STORAGE_FILENAME)
        existing_paths = set()
        if Path(_TRACKED_PATHNAME).exists():
            existing_paths.update(
                Path(_TRACKED_PATHNAME).read_text().splitlines())
        while True:
            uid = self._generate_uid()
            path_parts = [uid[i:i+2] for i in range(0, len(uid), 2)]
            new_path = storage_path.joinpath(*path_parts)
            if not new_path.exists() and str(new_path) not in existing_paths:
                return str(new_path)

    # Generate UID, persisting the "uid_counter" when using incremental mode

    def _generate_uid(self):
        if os.environ.get("STORAGE_RANDOM_UID","true").lower() in ("true", "t"):
            uid = hashlib.sha256(os.urandom(16)).hexdigest()
        else:
            uid_counter = self.share["uid_counter"]
            uid = str(uid_counter).zfill(_UID_LENGTH)
            uid_counter += 1
            self.ec_producer.update("uid_counter", uid_counter)
            Path(_UID_PATHNAME).write_text(f"{uid_counter}\n")
        return uid[- _UID_LENGTH:]

    # Normalize path to relative from CWD

    @classmethod
    def _normalize_path(self, target_path):
        absolute_target_path = Path(target_path).resolve()
        cwd = Path.cwd()
        try:
            relative_path = absolute_target_path.relative_to(cwd)
            return f"./{relative_path}"
        except ValueError:
            return str(absolute_target_path)

    # Track a created storage path

    def _track_path(self, path):
        relative_path = self._normalize_path(path)
        Path(_TRACKED_PATHNAME).parent.mkdir(parents=True, exist_ok=True)
        with open(_TRACKED_PATHNAME, "a+") as tracked_paths_file:
            tracked_paths_file.seek(0)
            tracked_paths = tracked_paths_file.read().splitlines()
            if relative_path not in tracked_paths:
                tracked_paths_file.write(relative_path + "\n")

# --------------------------------------------------------------------------- #
# Storage API and Bootstrap: File-system based implementation
#
# create()  --> _mkdir()
# destroy() --> _rm()
# dump()    --> _storage()
# link()    --> _ln()
# remove()  --> _rm()
# update()  --> update()

    # Create a Dependency (file)
    #
    # ./aiko_storage_file.py add entry  # Dependency only

    # TODO: Hyperspace: add(self, ENTRY_PATH, dependency):  # See "def list()"
    # TODO: Hyperspace:     cat, entry_name = _category_traverse(ENTRY_PATH)
    #
    # TODO: Store Dependency information ...
    #       service_filter=None, lifecycle_manager_url=None, storage_url=None

    def add(self, entry_name, dependency=None):
        path = Path(self._create_unique_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        try:
            Path(entry_name).symlink_to(f"{_ROOT_FILENAME}/{path}")
            self._track_path(path)
        except FileExistsError:
            print(f'Error: "{entry_name}" already exists', file=sys.stderr)

    def create(self, category_path):
        print("### StorageFileImpl.create() unimplemented ###")

    def destroy(self, category_path):
        print("### StorageFileImpl.destroy() unimplemented ###")

    def dump(self):
        print("### StorageFileImpl.dump() unimplemented ###")

    # Terminate Storage Actor(Service)
    #
    # ./aiko_storage_file.py exit

    def exit(self):
        aiko.process.terminate()

    # Initialize storage directory and ".root" symbolic_link
    #
    # ./aiko_storage_file.py initialize [STORAGE_URL]

    @classmethod
    def initialize(cls, storage_url=_CWD_URL):
        cwd = Path.cwd()
        storage_pathname = cwd / _STORAGE_FILENAME
        if not storage_pathname.is_dir():
            storage_pathname.mkdir(parents=True)
            print(f"Created directory {_STORAGE_FILENAME}/")

        root_pathname = cwd / _ROOT_FILENAME
        if not root_pathname.is_symlink():
            root_pathname.symlink_to(cwd)
            print(f"Created symbolic link {_ROOT_FILENAME} -->\n  {cwd}")

        uid_counter = 0
        uid_pathname = cwd / _UID_PATHNAME
        if uid_pathname.exists():
            try:
                uid_counter = int(uid_pathname.read_text())
            except ValueError:
                pass  # TODO: raise SystemExit
        else:
            uid_pathname.write_text(str(uid_counter))
    #   self.ec_producer.update("uid_counter", uid_counter)  # TODO: REMOVE

    # List categories and dependencies in a tree-style recursive format
    #
    # ./aiko_storage_file.py list [-c] [-l] [-r] [ENTRY_PATH]

    # TODO: #### [-c] Show Category entry count         ####
    # TODO: #### [-r] Set a recursion limit, default: 2 ####
    # TODO: #### [-u] Show entry UID                    ####

    # TODO: Hyperspace: list(self, ..., ENTRY_PATH=None, recursive=False):
    # TODO: Hyperspace:     cat, entry_name = _category_traverse(ENTRY_PATH)
    #
    # TODO: Load Dependency information ...
    #       service_filter=None, lifecycle_manager_url=None, storage_url=None

    def list(self, topic_path_response, entry_path=None,
        long_format=False, recursive=False):

        if not isinstance(long_format, bool):
            long_format = long_format.lower() in ("true", "t")
        if not isinstance(recursive, bool):
            recursive = recursive.lower() in ("true", "t")

    #   category, entry_name = self._category_traverse(entry_path)
    #   if category and entry_name in category.entries:
    #       entry = category.entries[entry_name]  
    #       if entry.service_filter.protocol == CATEGORY_PROTOCOL:
    #           category = entry

    #   def _file_count(link_directory):
    #       target_path = Path(link_directory).resolve()
    #       return sum(1 for file in target_path.rglob("*")  \
    #                     if file.is_file() and file.stat().st_size > 0)

        def _get_entry_records(entry_records, entry_path, level=0):
            if level > 0:
                entry_record = [-level, entry_path]
                if topic_path_response:
                    entry_record = generate(entry_record, [])[2:-2]  # TODO: Fix
                entry_records.append(entry_record)
            _traverse_entries(entry_records, entry_path, level,
                _handler_entry_records)
            _traverse_entries(entry_records, entry_path, level,
                _handler_next_level)

    #   def _get_uid_path(link):
    #       absolute_target_path = Path(link).resolve()
    #       try:
    #           storage_path = Path.cwd() / _STORAGE_FILENAME
    #           relative_path = absolute_target_path.relative_to(storage_path)
    #       except ValueError:
    #           relative_path = ""
    #       return str(relative_path)

        def _handler_entry_records(entry_records, entry, level):
        #   uid_path = _get_uid_path(entry.name)  # TODO: Show "uid_path"
            protocol = CATEGORY_PROTOCOL if entry.is_dir() else "*"

        #   service_filter = ServiceFilter("*", entry.name, protocol)
            service_filter = ["*", entry.name, protocol, "*", "*", []]
            lcm_url = None                 # lifecycle_manager_url
            storage_url = None
        #   dependency = DependencyImpl.create_dependency(...)
            dependency = [service_filter, lcm_url, storage_url]
            entry_record = [level, entry.name, dependency]

            if topic_path_response:
                entry_record = generate(entry_record, [])[2:-2]     # TODO: Fix
            entry_records.append(entry_record)

        def _handler_next_level(entry_records, entry, level):
            if entry.is_dir():
            #   if entry_count:
            #       count = _file_count(entry)
            #       if count > 0:
            #           entry_records.append(f" ({count})")
                if recursive:
                    _get_entry_records(entry_records, entry.name, level+1)

        def _traverse_entries(entry_records, entry_path, level, entry_handler):
            path = Path(entry_path)
            if path.is_dir():
                for entry in sorted(path.iterdir()):
                    if entry.is_symlink() and not entry.name.startswith("."):
                        entry_handler(entry_records, entry, level)

        entry_path = entry_path if entry_path else "."
        entry_records = []
    #   _get_entry_records(entry_records, category, None, 0)  # TODO: Later ?
        _get_entry_records(entry_records, entry_path)
        CategoryImpl._list_publish(
            topic_path_response, entry_records, long_format)

    def link(self, entry_path_new, entry_path_existing):
        print("### StorageFileImpl.link() unimplemented ###")

    def remove(self, entry_name):
        print("### StorageFileImpl.remove() unimplemented ###")

    def update(self, entry_name, service=None,
        service_filter=None, lifecycle_manager_url=None, storage_url=None):

        print("### StorageFileImpl.update() unimplemented ###")

# --------------------------------------------------------------------------- #
# Storage Bootstrap: File-system based implementation
"""
    # Clean up empty storage directories up to root

    @classmethod
    def _clean_storage(cls, tracked_directory):
        tracked_path = Path(tracked_directory)
        storage_path = Path(_STORAGE_FILENAME)
        while tracked_path != storage_path and tracked_path != Path("."):
            if tracked_path.is_dir() and not any(tracked_path.iterdir()):
                tracked_path.rmdir()
                tracked_path = tracked_path.parent
            else:
                break

    # Compute relative path using os.path.relpath

    @classmethod
    def _relative_path(cls, target_path, start_path):
        return os.path.relpath(target_path, start=start_path)

    # Untrack a removed storage path

    @classmethod
    def _untrack_path(cls, path):
        relative_path = _normalize_path(path)
        tracked_path = Path(_TRACKED_PATHNAME)
        if tracked_path.is_file():
            tracked_paths = tracked_path.read_text().splitlines()
            tracked_path.write_text(
                "\n".join(l for l in tracked_paths if l != relative_path))

    # Create new link to an existing dependency or category
    #
    # ./aiko_storage_file.py ln new_link entry  # dependency | category

    @classmethod
    def _ln(cls, link_path, target_path):
        if not Path(target_path).exists():
            print(
                f'Error: target "{target_path}" does not exist',
                file=sys.stderr)
            return 1
        resolved_path = Path(target_path).resolve()
        cwd = Path.cwd()
        if _STORAGE_FILENAME not in resolved_path.parts:
            print(
                f'Error: target "{target_path}" not in the storage directory',
                file=sys.stderr)
            return 1
        base_directory = Path(link_path).parent or Path(".")
        root = base_directory / _ROOT_FILENAME
        link_base = root if root.is_symlink() else Path(_ROOT_FILENAME)

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

    # Create a category (directory)
    #
    # ./aiko_storage_file.py mkdir category  # category only

    @classmethod
    def _mkdir(cls, name):
        path = Path(_create_unique_path())
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
    # ./aiko_storage_file.py rm entry  # Dependency | Category

    @classmethod
    def _rm(cls, name):
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
                            if x.is_symlink() and   \
                                x.resolve() == absolute_target_path]
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

    # List storage reverse-mapped with deduplication and optional name sort
    #
    # ./aiko_storage_file.py storage [-s]

    @classmethod
    def _storage(cls, sort_by_name=False):
        tracked_paths = set()
        cwd = Path.cwd()
        for path in cwd.rglob("*"):
            if path.is_symlink():
                absolute_target_path = path.resolve()
                try:
                    absolute_path = cwd / _STORAGE_FILENAME
                    relative_path = absolute_target_path.relative_to(
                                        absolute_path)
                    tracked_paths.add((str(relative_path), path.name))
                except ValueError:
                    continue
        items = sorted(
                    tracked_paths, key=lambda x: x[1] if sort_by_name else x[0])
        for relative_path, name in items:
            print(f"{relative_path}  {name}")
"""
# --------------------------------------------------------------------------- #
# Storage CLI: Bootstrap commands: File-system based implementation

@click.group()

def main():
    """Create, Read/List, Update and Destroy Storage"""

    subcommand = click.get_current_context().invoked_subcommand
    subcommands_which_work_anywhere =  \
        ["create", "dump", "exit", "initialize", "run"]

    if subcommand not in subcommands_which_work_anywhere:
        diagnostic = None
        try:
            StorageFileImpl._check_root_symbolic_link()
        except FileExistsError as file_exists_error:
            diagnostic = str(file_exists_error)
        if diagnostic:
            advice = 'Consider running "aiko_storage_file initialize"'
            raise SystemExit(f"{diagnostic}\n{advice}")

# aiko_storage_file initialize

@main.command(name="initialize")
@click.argument("storage_url", default=_CWD_URL)

def initialize_command(storage_url):
    """Initialize Storage (.root and storage/)

    aiko_storage_file initialize [STORAGE_URL]

    \b
    • STORAGE_URL: Storage file-system location, e.g file://./
    """

    storage_name = get_hostname()
    storage = StorageFileImpl.create_storage(storage_name, storage_url)
    storage.initialize()

# --------------------------------------------------------------------------- #
# Storage CLI: Distributed Actor commands: File-system based implementation

@main.command(name="add", no_args_is_help=True)
@click.argument("entry_path", type=str, required=True, default=None)
@click.option("--bootstrap", "-b", default=False, is_flag=True,
    help="Operate standalone (no Storage Service)")
@click.option("--storage_name", "-sn", type=str, default=None,
    help="Storage name, default is the local hostname")

def add_command(entry_path, bootstrap, storage_name):
    """Add Storage Entry

    aiko_storage_file add ENTRY_PATH [-b] [-sn STORAGE_NAME]

    \b
    • ENTRY_PATH: Entry PATH
    """

    dependency = None                         # TODO: Implement "dependency"

    if bootstrap:
        storage_url = None                    # TODO: Implement "storage_url" ?
        storage = StorageFileImpl.create_storage("<no_name>", storage_url)
        storage.add(entry_path, dependency)
    else:
        do_command(Storage,
            ServiceFilter(name=storage_name, protocol=PROTOCOL),
            lambda storage: storage.add(entry_path, dependency), terminate=True)
        aiko.process.run()

@main.command(name="exit", help="Exit Storage")
@click.option("--storage_name", "-sn", type=str, default=None,
    help="Storage name, default is the local hostname")

def exit_command(storage_name):
    do_command(Storage, ServiceFilter(name=storage_name, protocol=PROTOCOL),
        lambda storage: storage.exit(), terminate=True)
    aiko.process.run()

@main.command(name="list")
@click.argument("entry_path", type=str, required=False, default=None)
@click.option("--bootstrap", "-b", default=False, is_flag=True,
    help="Operate standalone (no Storage Service)")
@click.option("--storage_name", "-sn", type=str, default=None,
    help="Storage name, default is the local hostname")
@click.option("--long_format", "-l", is_flag=True,
    help="Long format with Service, LifeCycleManager URL, Storage URL")
@click.option("--recursive", "-r", is_flag=True,
    help="Recursively list Category entries")

def list_command(entry_path, bootstrap, storage_name, long_format, recursive):
    """List Storage Entries

    aiko_storage_file list ENTRY_PATH [-b] [-sn STORAGE_NAME] [-l] [-r]

    \b
    • ENTRY_PATH: Entry path
    """

    if bootstrap:
        storage_url = None                    # TODO: Implement "storage_url" ?
        storage = StorageFileImpl.create_storage("<no_name>", storage_url)
        storage.list(None, entry_path, long_format, recursive)
    else:
        CategoryImpl.list_command(
            storage_name, entry_path, long_format, recursive, PROTOCOL)
        aiko.process.run()

@main.command(name="run")
@click.argument("storage_url", default=_CWD_URL)  # TODO: "storage_url" ???????
@click.option("--storage_name", "-sn", type=str, default=None,
    help="Storage name, default is the local hostname")

def run_command(storage_name, storage_url):
    """Run Storage backed by the file-system

    aiko_storage_file run [-sn STORAGE_NAME] [STORAGE_URL]

    \b
    • STORAGE_URL: Storage file-system location, e.g file://./
    """

    storage_name = storage_name if storage_name else get_hostname()
    storage = StorageFileImpl.create_storage(storage_name, storage_url)
    aiko.process.run()  # TODO: Actor:aiko.process.run() or storage.run() ?

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
