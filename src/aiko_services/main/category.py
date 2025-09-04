#!/usr/bin/env python3
#
# Aiko Service: Category(Dependency)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Create, Read, Update and Destroy a Category
# Add to, List and Remove from a Category, which is a group of Entries
# Entries can be either a Category or a Dependency
#
# Usage
# ~~~~~
# ./category.py --help
# ./category.py run     CATEGORY_NAME  # Creates Category instance for testing
# ./category.py exit    CATEGORY_NAME  # Terminates running Category instance
#
# ./category.py add     CATEGORY_NAME ENTRY_NAME -p p -o a -t key_0=value_0
# ./category.py list    CATEGORY_NAME [ENTRY_NAME] [--long_format | -l]
# ./category.py remove  CATEGORY_NAME ENTRY_NAME
# ./category.py update  CATEGORY_NAME ENTRY_NAME -p protocol -t key_0=value_0
#
# To Do
# ~~~~~
# - Categories: HyperSpace, Registrar, LifeCycleManager, WorkSpace
#   - LifeCycleManagers: HyperSpace, ProcessManager, Pipeline
#   - Distributed Garbage Collection: Use of Leases by LifeCycleManagers ?
#     - LifeCycleManagers also "reference count" Categories references ?
#     - Interaction with Storage for managing persistence life-time ?
#
# - Consider LifeCycleManager as-a Category as-a DependencyManager
#
# * Implement "./category.py repl" for interactive CRUD, etc
#   - REPL command to discover then add, update or remove a running Service
#
# * Fix: Implement "__repr__()", "__str__()" and refactor "list()" to use them ?
#   - https://stackoverflow.com/questions/1436703/what-is-the-difference-between-str-and-repr
#
# * Fix: list(): "(dn (None * * * * (a=b c=d)) 0: 0:)"  # None --> 0:
#
# * Incorporate Dependency design and implementation, e.g strong, weak, group
#   * Disambiguate function delivery to the Category versus the Entries 🤔
#
# * Timestamps: Category create, Dependency add(), remove(), update()
# * Category Metrics: add(), list(), remove(), update() rates, total counts
#
# * Implement "category.py list" filters, e.g by owner, by protocol, etc
#
# - Design a CategoryManager interface for use by HyperSpace et al
#
# - Categories that span different HyperSpace instances, e.g different "roots"
#
# - Consider design and implementation of "self-changing custom" Categories
#   - Custom Category implementations may want many Categories per Process
#
# - Design and implement Queue(Category) with different persistence options
#   - Implement "queue://" DataScheme, DataSource and DataTarget
#
# * Implement Category "owner" field and populate automatically
#   * System Categories owned by "aiko"
#   * Security design and implementation: owners, roles, ACLs

from abc import abstractmethod
import click

from aiko_services.main import *

__all__ = ["Category"]

_RESPONSE_TOPIC = f"{aiko.topic_in}"

# --------------------------------------------------------------------------- #

class Category(Actor, Dependency):
    Interface.default("Category", "aiko_services.main.category.CategoryImpl")

    @abstractmethod
    def add(self, entry_name,
        service_filter=None, lifecycle_manager_url=None, storage_url=None):
        pass

    @abstractmethod
    def exit(self):
        pass

    @abstractmethod
    def list(self, topic_path_response, entry_name=None, recursive=False):
        pass

    @abstractmethod
    def remove(self, entry_name):
        pass

# --------------------------------------------------------------------------- #

class CategoryImpl(Category):
    def __init__(self, context, service_filter=None):
        context.call_init(self, "Actor", context)
        context.call_init(self, "Dependency", context,
            service_filter=service_filter)

        self.dependency = context.get_implementation("Dependency")    # methods
        self.entries = {}                         # Categories and Dependencies

        self.share.update({                       # Inherit from Actor
            "source_file": f"v{CATEGORY_VERSION}⇒ {__file__}",
            "entries": len(self.entries)
        })
        self.ec_producer = ECProducer(self, self.share)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    def add(self, entry_name,
        service_filter, lifecycle_manager_url=None, storage_url=None):

        if service_filter and not isinstance(service_filter, ServiceFilter):
            service_filter = ServiceFilter(*service_filter)
        if service_filter.name == "*":
            service_filter.name = entry_name

        if entry_name not in self.entries:
            dependency = compose_instance(DependencyImpl, dependency_args(
                None, service_filter, lifecycle_manager_url, storage_url))
            self.entries[entry_name] = dependency
            self.ec_producer.update("entries", len(self.entries))

    def _ec_producer_change_handler(self, command, entry_name, entry_value):
        if entry_name == "log_level":
            self.logger.setLevel(str(entry_value).upper())

    def exit(self):
        aiko.process.terminate()

    def _get_entry_records(self, entry_name=None, level=0):
        entry_records = []
        for entry_key, entry in self.entries.items():
            if entry_name is None or entry_name == entry_key:
            # TODO: "(dn (None * * * * (a=b c=d)) 0: 0:)"         # None --> 0:
                entry = str(entry).replace("None", "0:")
                entry_record = f"{level} {entry_key} {entry}"
                entry_records.append(entry_record)
        entry_records.sort()
        return entry_records

    def is_type(self, type_name):
        if type_name.lower() == "category":
            return True
        return self.dependency.is_type(self, type_name)

# Note: "recursive" only needed for HyperSpace, not Category, ignore it here

    def list(self, topic_path_response, entry_name=None, recursive=False):
        entry_records = self._get_entry_records(entry_name)
        self._list_publish(topic_path_response, entry_records)

    def _list_publish(self, topic_path_response, entry_records):
        aiko.message.publish(
            topic_path_response, f"(item_count {len(entry_records)})")
        for entry_record in entry_records:
            aiko.message.publish(
                topic_path_response, f"(response {entry_record})")

    def remove(self, entry_name):
        if entry_name in self.entries:
            del self.entries[entry_name]
            self.ec_producer.update("entries", len(self.entries))

    def __repr__(self):
        return self.dependency.__repr__(self)

    @classmethod
    def list_command(cls,
        actor_name, entry_name, long_format, recursive, protocol):

        #TODO: Turn this into @dataclass(es)
        # Record types: A) new child Category, B) current Catefory Entry
        # A) record[0]: -indent [1]: category_name
        # B) record[0]:  indent [1]: entry_name, [2] ServiceFilter LCM Storage
        # class ServiceFilter:    see src/aiko_services/main/service.py
        # class LifeCycleManager: see src/aiko_services/main/lifecycle.py
        # class StorageFile:      see src/aiko_services/main/storage.py

        def response_handler(response):
            if len(response):
                if long_format:
                    output =  "Name: (Service) LifeCycleManager, Storage\n"
                    output += "      (Topic Name Protocol Transport Owner Tags)"
                else:
                    output = "Name: Protocol Owner"

                for record in response:
                    indent = int(record[0]) * 2     # Category depth formatting
                    if indent < 0:                  # new child Category
                        indent = -indent
                        output += f"\n\n{' '*indent} {record[1]}/"
                    else:                           # current Category Entry
                        entry_name = record[1]
                        if record[2][0]:
                            service_filter = ServiceFilter(*record[2][0])
                            protocol = service_filter.protocol
                            after_slash = protocol.rfind("/") + 1
                            service_filter.protocol = protocol[after_slash:]
                        else:
                            service_filter = ServiceFilter()
                        if long_format:
                            lifecycle_manager_url = record[2][1]
                            storage_url = record[2][2]
                            output += f"\n   {' '*indent}{entry_name}: "  \
                                      f"{service_filter} "  \
                                      f"{lifecycle_manager_url}, "  \
                                      f"{storage_url}"
                        else:
                            name = service_filter.name
                            if name is None or name == "*" or name == entry_name:
                                name = ""
                                output += f"\n   {' '*indent}{entry_name}: "  \
                                          f"{service_filter.protocol} "  \
                                          f"{service_filter.owner}  {name}"
            else:
                output = "No category entries"
            print(output)

        do_request(Category,
            ServiceFilter(name=actor_name, protocol=protocol),
            lambda actor: actor.list(_RESPONSE_TOPIC, entry_name, recursive),
            response_handler, _RESPONSE_TOPIC, terminate=True)

    def update(self, entry_name, service=None,
        service_filter=None, lifecycle_manager_url=None, storage_url=None):

    # Prevent ServiceFilter() from overriding "name" with "hostname()"
        if service_filter and not isinstance(service_filter, ServiceFilter):
            service_filter_name_null = service_filter[1] is None
            service_filter = ServiceFilter(*service_filter)
            if service_filter_name_null:
                service_filter.name = None

        if entry_name in self.entries:
            entry = self.entries[entry_name]
            if service_filter:
                if service_filter.name:
                    entry.service_filter.name = service_filter.name
                if service_filter.protocol:
                    entry.service_filter.protocol = service_filter.protocol
                if service_filter.transport:
                    entry.service_filter.transport = service_filter.transport
                if service_filter.owner:
                    entry.service_filter.owner = service_filter.owner
                if service_filter.tags:
                    entry.service_filter.tags = service_filter.tags

            if lifecycle_manager_url:
                entry.lifecycle_manager_url = lifecycle_manager_url

            if storage_url:
                entry.storage_url = storage_url

# --------------------------------------------------------------------------- #

@click.group()

def main():
    """Create, Read/List, Update and Destroy Categories"""
    pass

@main.command(name="add", no_args_is_help=True)
@click.argument("category_name", type=str, required=True, default=None)
@click.argument("entry_name", type=str, required=True, default=None)
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

def add_command(category_name, entry_name,
    service_name, protocol, transport, owner, tags,
    lifecycle_manager_url, storage_url):

    """Add Category Entry

    aiko_category add CATEGORY_NAME ENTRY_NAME

    \b
    • CATEGORY_NAME: Category name
    • ENTRY_NAME: Entry name
    """

    tags = tags if tags else []                 # Assign default tags value
    service_filter = ServiceFilter(             # TODO: Or use ServiceFields ??
        "*", service_name, protocol, transport, owner, tags)

    do_command(Category,
        ServiceFilter(name=category_name, protocol=CATEGORY_PROTOCOL),
        lambda category: category.add(entry_name,
            service_filter, lifecycle_manager_url, storage_url), terminate=True)
    aiko.process.run()

@main.command(name="exit", no_args_is_help=True)
@click.argument("category_name", required=True)

def exit_command(category_name):
    """Exit Category

    aiko_category exit CATEGORY_NAME

    \b
    • CATEGORY_NAME: Category name
    """

    do_command(Category,
        ServiceFilter(name=category_name, protocol=CATEGORY_PROTOCOL),
        lambda category: category.exit(), terminate=True)
    aiko.process.run()

@main.command(name="list", no_args_is_help=True)
@click.argument("category_name", type=str, required=True, default=None)
@click.argument("entry_name", type=str, required=False, default=None)
@click.option("--long_format", "-l", is_flag=True,
    help="Long format with Service, LifeCycleManager URL, Storage URL")

def list_command(category_name, entry_name, long_format):
    """List Category Entries

    aiko_category list CATEGORY_NAME [ENTRY_NAME]

    \b
    • CATEGORY_NAME: Category name
    • ENTRY_NAME: Entry name
    """

    CategoryImpl.list_command(
        category_name, entry_name, long_format, CATEGORY_PROTOCOL)
    aiko.process.run()

@main.command(name="remove", no_args_is_help=True)
@click.argument("category_name", type=str, required=True, default=None)
@click.argument("entry_name", type=str, required=True, default=None)

def remove_command(category_name, entry_name):
    """Remove Category Entry

    aiko_category remove CATEGORY_NAME ENTRY_NAME

    \b
    • CATEGORY_NAME: Category name
    • ENTRY_NAME: Entry name
    """

    do_command(Category,
        ServiceFilter(name=category_name, protocol=CATEGORY_PROTOCOL),
        lambda category: category.remove(entry_name), terminate=True)
    aiko.process.run()

@main.command(name="run", no_args_is_help=True)
@click.argument("category_name", required=True)

def run_command(category_name):
    """Run Category

    aiko_category run CATEGORY_NAME

    \b
    • CATEGORY_NAME: Category name
    """

    tags = ["ec=true"]       # TODO: Add ECProducer tag before add to Registrar
    init_args = actor_args(category_name, None, None, CATEGORY_PROTOCOL, tags)
    category = compose_instance(CategoryImpl, init_args)
    aiko.process.run()

@main.command(name="update", no_args_is_help=True)
@click.argument("category_name", type=str, required=True, default=None)
@click.argument("entry_name", type=str, required=True, default=None)
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

def update_command(category_name, entry_name,
    service_name, protocol, transport, owner, tags,
    lifecycle_manager_url, storage_url):

    """Update Category Entry

    aiko_category update CATEGORY_NAME ENTRY_NAME

    \b
    • CATEGORY_NAME: Category name
    • ENTRY_NAME: Entry name
    """

    tags = tags if tags else []                 # Assign default tags value
    service_filter = ServiceFilter(             # TODO: Or use ServiceFields ??
        "*", service_name, protocol, transport, owner, tags)

    do_command(Category,
        ServiceFilter(name=category_name, protocol=CATEGORY_PROTOCOL),
        lambda category: category.update(entry_name, None,
            service_filter, lifecycle_manager_url, storage_url), terminate=True)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
