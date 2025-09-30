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
# Can use either "aiko_hyperspace" (preferred) or "./hyperspace.py"
#
# Usage: Distributed Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~
# aiko_hyperspace.py run     [storage_url]  # file in-memory sqlite mqtt valkey
# aiko_hyperspace.py dump
# aiko_hyperspace.py exit
#
# aiko_hyperspace.py add     ENTRY_PATH
# aiko_hyperspace.py create  CATEGORY_PATH
# aiko_hyperspace.py destroy CATEGORY_PATH
# aiko_hyperspace.py link    ENTRY_PATH_NEW ENTRY_PATH_EXIST    # TODO: "link"
# aiko_hyperspace.py list    [ENTRY_PATH] [--long_format|-l] [--recursive|-r]
# aiko_hyperspace.py remove  ENTRY_PATH_EXIST                   # TODO: "unlink"
# aiko_hyperspace.py update  ENTRY_PATH -p protocol -t key_0=value_0
#
# Usage: Bootstrap
# ~~~~~~~~~~~~~~~~
# export STORAGE_RANDOM_UID=False  # debug using predictable incrementing UIDs
#
# aiko_storage_file initialize [STORAGE_URL]  # set-up a file-system directory
# aiko_storage_file dump -b [--sort_by_name]  # show low-level storage files
# aiko_storage_file list -b [-l] [-r] [PATH]  # show file-system files
#
# To Do
# ~~~~~
# - Separate the design and implementation of HyperSpace and Storage
#   - HyperSpace: create(): Category with different HyperSpace root ?
#   - Storage:    create(): Category or Dependency (Definition and Contents)
#
# * HyperSpace/Registrar(Category): Filters(Code), Order(Sort), Pagination
#
# - Implement "aiko_hyperspace run --register_storage_service" optional flag
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
# * Validate HyperSpace structure, see StorageFile structure validation
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

from aiko_services.main import *
from aiko_services.main.storage import StorageFileImpl
from aiko_services.main.utilities import dir_base_name, get_hostname

__all__ = ["HyperSpace"]

ACTOR_TYPE = "hyperspace"
VERSION = 0
PROTOCOL = f"{SERVICE_PROTOCOL_AIKO}/{ACTOR_TYPE}:{VERSION}"

_CWD_URL = "file://./"  # relative URL for the current working directory
_PATH_DELIMITER = "/"
# _RESPONSE_TOPIC = f"{aiko.topic_in}"

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
    @classmethod
    def create_hyperspace(cls, hyperspace_name=None,
        storage_url=_CWD_URL, protocol=PROTOCOL, tags=None, transport=None):

        tags = list(tags) + ["ec=true"]
        init_args = actor_args(
            hyperspace_name, None, None, protocol, tags, transport)
        init_args["storage_url"] = storage_url
        return compose_instance(HyperSpaceImpl, init_args)

    def __init__(self, context, storage_url=_CWD_URL):
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

        self._hyperspace_load(storage_url)

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

    # Default outcome is to use StorageFile to persist the new Dependency.
    # "_hyperspace_load()" only needs to create the in-memory representation
    # from Storage persistence, hence "use_storage=False"

    def add(self, entry_path,
        service_filter, lifecycle_manager_url=None, storage_url=None,
        use_storage=True):

        category, entry_name = self._category_traverse(entry_path)
        if category:
            if service_filter and not isinstance(service_filter, ServiceFilter):
                service_filter = ServiceFilter(*service_filter)
            if service_filter.name == "*":
                service_filter.name = entry_name
            self.category.add(category, entry_name,
                service_filter, lifecycle_manager_url, storage_url)
            dependency = compose_instance(DependencyImpl, dependency_args(
                None, service_filter, lifecycle_manager_url, storage_url))

            if use_storage:
                self.storage.add(entry_name, dependency)

    # Default outcome is to use StorageFile to persist the new Category.
    # "_hyperspace_load()" only needs to create the in-memory representation
    # from Storage persistence, hence "use_storage=False"

    def create(self, category_path, use_storage=True):
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

                if use_storage:
                    self.storage.create(str(category_path))

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

    def _hyperspace_load(self, storage_url=_CWD_URL):
        entry_records = []
        storage_name = f"{get_hostname()}_hs"
        storage_url = None                 # TODO: Implement "storage_url" ?
        self.storage = StorageFileImpl.create_storage(
            storage_name, storage_url, register_service=False)
        self.storage.list(None, None, False, True, entry_records)

        metrics = [0, 0]  # [Dependencies, Categories]
        entry_path = ""
        for record in entry_records:
            level = int(record[0])
            entry_name = record[1]
            if level < 0:
                entry_path = entry_name
            else:
                if record[2][0]:
                    service_filter = ServiceFilter(*record[2][0])
                    is_category = service_filter.protocol == CATEGORY_PROTOCOL
                else:
                    service_filter = ServiceFilter(name=entry_name)
                    is_category = False
                if entry_path:
                    entry_name = f"{entry_path}/{entry_name}"
                if is_category:
                    self.create(entry_name, use_storage=False)
                else:
                    self.add(entry_name,
                        service_filter, None, None, use_storage=False)
                metrics[1 if is_category else 0] += 1
        print(f"Dependencies: {metrics[0]}, Categories: {metrics[1]}")

    def is_type(self, type_name):
        if type_name.lower() == "hyperspace":
            return True
        return self.category.is_type(self, type_name)

    def list(self, topic_path_response, entry_path=None,
        long_format=False, recursive=False, entry_records=None):

        if not isinstance(long_format, bool):
            long_format = long_format.lower() in ("true", "t")
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
        CategoryImpl._list_publish(
            topic_path_response, entry_records, long_format)

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

@click.group()

def main():
    """Create, Read/List, Update and Destroy HyperSpace"""

    subcommand = click.get_current_context().invoked_subcommand
    subcommands_which_work_anywhere = [
        "add", "create", "destroy", "dump", "exit", "list", "remove", "update"]

    if subcommand not in subcommands_which_work_anywhere:
        diagnostic = None
        try:
            StorageFileImpl._check_root_symbolic_link()
        except FileExistsError as file_exists_error:
            diagnostic = str(file_exists_error)
        if diagnostic:
            advice = 'Consider running "aiko_storage initialize"'
            raise SystemExit(f"{diagnostic}\n{advice}")

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
    hyperspace = HyperSpaceImpl.create_hyperspace(
        hyperspace_name, storage_url, protocol, tags, transport)
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
