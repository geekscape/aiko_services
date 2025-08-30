#!/usr/bin/env python3
#
# Aiko Service: Category(Dependency)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Create, Read, Update and Destroy Categories
# Add to, List and Remove from a Category (which is a group of Dependencies)
#
# Usage
# ~~~~~
# ./category.py --help
# ./category.py run     CATEGORY_NAME  # Creates Category instance for testing
# ./category.py exit    CATEGORY_NAME  # Terminates running Category instance
#
# ./category.py add     CATEGORY_NAME DEPENDENCY_NAME -p p -o a -t key_0=value_0
# ./category.py list    CATEGORY_NAME [--long_format | -l]
# ./category.py read    CATEGORY_NAME # TODO: Design and implement
# ./category.py remove  CATEGORY_NAME DEPENDENCY_NAME
# ./category.py update  CATEGORY_NAME DEPENDENCY_NAME -p q -o b -t key_1=value_1
#
# To Do
# ~~~~~
# - Categories: HyperSpace, Registrar, LifeCycleManager, WorkSpace
#   - LifeCycleManagers: HyperSpace, ProcessManager, Pipeline
#   - Distributed Garbage Collection: Use of Leases by LifeCycleManagers ?
#     - LifeCycleManagers also "reference count" Categories references ?
#     - Interaction with Storage for managing persistence life-time ?
#
# * Update design and implementation, so that Category truly is-a Dependency
#   - Also, consider LifeCycleManager as-a Category as-a DependencyManager
#
# * Fix CLI "(add    dn (None * * * * (a=b c=d)) 0: 0:)"  # None --> 0:
# * Fix CLI "(update dn (None * * * * (a=b c=d)) 0: 0:)"  # None --> 0:
# * Fix list():    "(dn (None * * * * (a=b c=d)) 0: 0:)"  # None --> 0:
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
from aiko_services.main.utilities import *

__all__ = ["Category"]

ACTOR_TYPE = "category"
VERSION = 0
PROTOCOL = f"{SERVICE_PROTOCOL_AIKO}/{ACTOR_TYPE}:{VERSION}"

_RESPONSE_TOPIC = f"{aiko.topic_in}"

# --------------------------------------------------------------------------- #

class Category(Actor):
    Interface.default("Category", "aiko_services.main.category.CategoryImpl")

    @abstractmethod
    def add(self, dependency_name,
        service_filter, lifecycle_manager_url=None, storage_url=None):
        pass

    @abstractmethod
    def destroy(self):
        pass

    @abstractmethod
    def exit(self):
        pass

    @abstractmethod
    def list(self, topic_path_response, dependency_name=None):
        pass

    @abstractmethod
    def read(self, topic_path_response):
        pass

    @abstractmethod
    def remove(self, dependency_name):
        pass

    @abstractmethod
    def update(self, dependency_name,
        service_filter, lifecycle_manager_url=None, storage_url=None):
        pass

# --------------------------------------------------------------------------- #

class CategoryImpl(Category):
    def __init__(self, context):
        context.call_init(self, "Actor", context)

        self.dependencies = {}

        self.share.update({                                # Inherit from Actor
            "source_file": f"v{VERSION}⇒ {__file__}",
            "dependencies": len(self.dependencies)
        })
        self.ec_producer = ECProducer(self, self.share)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    def add(self, dependency_name,
        service_filter, lifecycle_manager_url=None, storage_url=None):

        if not isinstance(service_filter, ServiceFilter):
            service_filter = ServiceFilter(*service_filter)

        if dependency_name not in self.dependencies:
            dependency = Dependency(
                service_filter, lifecycle_manager_url, storage_url)
            self.dependencies[dependency_name] = dependency
            self.ec_producer.update("dependencies", len(self.dependencies))

    def destroy(self):
        pass

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            self.logger.setLevel(str(item_value).upper())

    def exit(self):
        aiko.process.terminate()

    def list(self, topic_path_response, dependency_name=None):
        responses = []
        for dependency_key in self.dependencies.keys():
            if dependency_name is None or dependency_name == dependency_key:
                dependency_record = str(self.dependencies[dependency_key])
            # TODO: "(dn (None * * * * (a=b c=d)) 0: 0:)"         # None --> 0:
                dependency_record = dependency_record.replace("None", "0:")
                response = f"{dependency_key} {dependency_record}"
                responses.append(response)
        aiko.message.publish(
            topic_path_response, f"(item_count {len(responses)})")
        for response in responses:
            aiko.message.publish(
                topic_path_response, f"(response {response})")

    def read(self, topic_path_response):
        print(f"### Unimplemented: Category.read() ###")

    def remove(self, dependency_name):
        if dependency_name in self.dependencies:
            del self.dependencies[dependency_name]
            self.ec_producer.update("dependencies", len(self.dependencies))

    def update(self, dependency_name,
        service_filter, lifecycle_manager_url=None, storage_url=None):

    # Prevent ServiceFilter() from overriding "name" with "hostname()"
        service_filter_name_null = service_filter[1] is None
        if not isinstance(service_filter, ServiceFilter):
            service_filter = ServiceFilter(*service_filter)
            if service_filter_name_null:
                service_filter.name = None

        if dependency_name in self.dependencies:
            dependency = self.dependencies[dependency_name]
            service_filter_current = dependency.service_filter

            if service_filter:
                if service_filter.name:
                    service_filter_current.name = service_filter.name
                if service_filter.protocol:
                    service_filter_current.protocol = service_filter.protocol
                if service_filter.transport:
                    service_filter_current.transport = service_filter.transport
                if service_filter.owner:
                    service_filter_current.owner = service_filter.owner
                if service_filter.tags:
                    service_filter_current.tags = service_filter.tags

            if lifecycle_manager_url:
                dependency.lifecycle_manager_url = lifecycle_manager_url

            if storage_url:
                dependency.storage_url = storage_url

# --------------------------------------------------------------------------- #

@click.group()

def main():
    """Create, Read/List, Update and Destroy Categories"""
    pass

@main.command(name="add", no_args_is_help=True)
@click.argument("category_name", type=str, required=True, default=None)
@click.argument("dependency_name", type=str, required=True, default=None)
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

def add_command(category_name, dependency_name,
    service_name, protocol, transport, owner, tags,
    lifecycle_manager_url, storage_url):

    """Add Category Dependency

    aiko_category add CATEGORY_NAME DEPENDENCY_NAME

    \b
    • CATEGORY_NAME:   Category name
    • DEPENDENCY_NAME: Dependency name
    """

    tags = tags if tags else ()                 # Assign default tags value
    service_filter = ServiceFilter(             # TODO: Or use ServiceFields ??
        "0:", service_name, protocol, transport, owner, tags)     # None --> 0:

# TODO: "(add dn (None * * * * (a=b c=d)) 0: 0:)"                 # None --> 0:
    do_command(Category, ServiceFilter(name=category_name, protocol=PROTOCOL),
        lambda category: category.add(dependency_name,
            service_filter, lifecycle_manager_url, storage_url), terminate=True)
    aiko.process.run()

@main.command(name="destroy", no_args_is_help=True)
@click.argument("category_name", required=True)

def destroy_command(category_name):
    """Destroy Category

    aiko_category destroy CATEGORY_NAME

    \b
    • CATEGORY_NAME: Category name
    """

    do_command(Category, ServiceFilter(name=category_name, protocol=PROTOCOL),
        lambda category: category.destroy(), terminate=True)
    aiko.process.run()

@main.command(name="exit", no_args_is_help=True)
@click.argument("category_name", required=True)

def exit_command(category_name):
    """Exit Category

    aiko_category exit CATEGORY_NAME

    \b
    • CATEGORY_NAME: Category name
    """

    do_command(Category, ServiceFilter(name=category_name, protocol=PROTOCOL),
        lambda category: category.exit(), terminate=True)
    aiko.process.run()

@main.command(name="list", no_args_is_help=True)
@click.argument("category_name", type=str, required=True, default=None)
@click.argument("dependency_name", type=str, required=False, default=None)
@click.option("--long_format", "-l", is_flag=True,
    help="Long format with Service, LifeCycleManager URL, Storage URL")

def list_command(category_name, dependency_name, long_format):
    """List Category Dependencies

    aiko_category list CATEGORY_NAME [DEPENDENCY_NAME]

    \b
    • CATEGORY_NAME:   Category name
    • DEPENDENCY_NAME: Dependency name
    """

    def response_handler(response):
        if len(response):
            if long_format:
                output =  "Name: (Service) LifeCycleManager URL, Storage URL\n"
                output += "      (Topic Name Protocol Transport Owner Tags)"
            else:
                output = "Name: Protocol Owner"
            for record in response:
                dependency_name = record[0]
                record[1][0] = ServiceFilter(*record[1][0])
                dependency = Dependency(*record[1])
                service_filter = dependency.service_filter
                if long_format:
                    output += f"\n  {dependency_name}: "  \
                              f"{service_filter} "  \
                              f"{dependency.lifecycle_manager_url}, "  \
                              f"{dependency.storage_url}"
                else:
                    name = service_filter.name
                    if name is None or name == "*" or name == dependency_name:
                        name = ""
                    output += f"\n  {dependency_name}: "  \
                              f"{service_filter.protocol} "  \
                              f"{service_filter.owner}  {name}"
        else:
            output = "No dependencies"
        print(output)

    do_request(Category, ServiceFilter(name=category_name, protocol=PROTOCOL),
        lambda category: category.list(_RESPONSE_TOPIC, dependency_name),
        response_handler, _RESPONSE_TOPIC, terminate=True)
    aiko.process.run()

@main.command(name="read", no_args_is_help=True)
@click.argument("category_name", type=str, required=True, default=None)

def read_command(category_name):
    """Read Category details

    aiko_category read CATEGORY_NAME

    \b
    • CATEGORY_NAME: Category name
    """

    do_command(Category, ServiceFilter(name=category_name, protocol=PROTOCOL),
        lambda category: category.read(_RESPONSE_TOPIC), terminate=True)
    aiko.process.run()

@main.command(name="remove", no_args_is_help=True)
@click.argument("category_name", type=str, required=True, default=None)
@click.argument("dependency_name", type=str, required=True, default=None)

def remove_command(category_name, dependency_name):
    """Remove Category Dependency

    aiko_category remove CATEGORY_NAME DEPENDENCY_NAME

    \b
    • CATEGORY_NAME: Category name
    • DEPENDENCY_NAME: Dependency name
    """

    do_command(Category, ServiceFilter(name=category_name, protocol=PROTOCOL),
        lambda category: category.remove(dependency_name), terminate=True)
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
    init_args = actor_args(category_name, None, None, PROTOCOL, tags)
    category = compose_instance(CategoryImpl, init_args)
    aiko.process.run()

@main.command(name="update", no_args_is_help=True)
@click.argument("category_name", type=str, required=True, default=None)
@click.argument("dependency_name", type=str, required=True, default=None)
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

def update_command(category_name, dependency_name,
    service_name, protocol, transport, owner, tags,
    lifecycle_manager_url, storage_url):

    """Update Category Dependency

    aiko_category update CATEGORY_NAME DEPENDENCY_NAME

    \b
    • CATEGORY_NAME: Category name
    • DEPENDENCY_NAME: Dependency name
    """

    tags = tags if tags else ()                 # Assign default tags value
    service_filter = ServiceFilter(             # TODO: Or use ServiceFields ??
        "0:", service_name, protocol, transport, owner, tags)     # None --> 0:

# TODO: "(update dn (None None None None None (a=b c=d)) 0: 0:)"  # None --> 0:
    do_command(Category, ServiceFilter(name=category_name, protocol=PROTOCOL),
        lambda category: category.update(dependency_name,
            service_filter, lifecycle_manager_url, storage_url), terminate=True)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
