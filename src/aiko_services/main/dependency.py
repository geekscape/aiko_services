# Aiko Services: Dependency
# ~~~~~~~~~~~~~~~~~~~~~~~~~
# Is a "reference" to a distributed Service, containing ...
# - Local or remote Service instance reference (when discovered)
# - ServiceFilter for Service discovery
# - LifeCycleManager URL for the Actor that manages the Service (load / unload)
# - Storage URL for the Actor that persists the Service Definition / Content
#
# Usage
# ~~~~~
#   topic_path = "*"
#   service_name = name
#   protocol = "*"
#   transport = "*"
#   owner = "*"
#   tags = "*"
#
#   service_filter = ServiceFilter(         # Used for Service discovery
#       topic_path, service_name, protocol, transport, owner, tags)
#   lifecycle_manager_url = None            # TODO: Implement lifecycle_manager
#   storage_url = None                      # TODO: Implement storage
#
#   init_args = dependency_args(
#       None, service_filter, lifecycle_manager_url, storage_url)
#   dependency = compose_instance(DependencyImpl, init_args)
#
# To Do
# ~~~~~
# * Consider Dependency.update() same as Category.update() for "service_filter"
#
# * Consider use of ServiceFields rather than ServiceFilter ?
#
# * Replace current Pipeline prototype implementation with this improved design
#   * Once full Dependency resolution, information flow, etc is completed
#
# - Properties: Dependency direction, Information direction, Strong, Weak, Group
#
# - DependencyManager maintaining in-memory list of Dependencies ?
#
# - Security model design and implementation

from abc import abstractmethod

__all__ = ["Dependency", "dependency_args", "DependencyImpl"]

from aiko_services.main import *

# --------------------------------------------------------------------------- #

class Dependency(Interface):
    Interface.default(
        "Dependency", "aiko_services.main.dependency.DependencyImpl")

    @abstractmethod
    def is_type(self, type_name):
        pass

    @abstractmethod
    def update(self, entry_name, service=None,
        service_filter=None, lifecycle_manager_url=None, storage_url=None):
        pass

def dependency_args(service=None,
    service_filter=None, lifecycle_manager_url=None, storage_url=None):

    init_args = context_args()
    init_args.update({
        "service": service,
        "service_filter": service_filter,
        "lifecycle_manager_url": lifecycle_manager_url,
        "storage_url": storage_url})
    return init_args

# --------------------------------------------------------------------------- #
# "self.service" reference values ...
#     - None: Service not discovered or absent
#     - Local instance reference (running uithin the same process)
#     - Remote reference (running in a different process or host)
#
# TODO: "self.lifecycle_manager_url" and "self.storage_url" values ...
#     - None: Service (dependency) is manually started
#     - "*":  Discover ProcessManager and/or Storage (default)
#     - "URL" Specified ProcessManager and/or Storage

class DependencyImpl(Dependency):
    def __init__(self, context, service=None,
        service_filter=None, lifecycle_manager_url=None, storage_url=None):

        self.service = service                     # Service instance reference
        self.service_filter = service_filter       # Used for discovery
        self.lifecycle_manager_url = lifecycle_manager_url
        self.storage_url = storage_url

    def is_type(self, type_name):
        return type_name.lower() == "dependency"

    def __repr__(self):
        return f"({self.service_filter} "  \
               f"{self.lifecycle_manager_url} "  \
               f"{self.storage_url})"

# Note: "entry_name" only needed for Category, not Dependency, ignore it here

    def update(self, entry_name, service=None,
        service_filter=None, lifecycle_manager_url=None, storage_url=None):

        if service:
            self.service = service
        if service_filter:
            self.service_filter = service_filter
        if lifecycle_manager_url:
            self.lifecycle_manager_url = lifecycle_manager_url
        if storage_url:
            self.storage_url = storage_url

# --------------------------------------------------------------------------- #
