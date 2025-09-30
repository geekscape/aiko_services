# Aiko Services: Storage SPI
# ~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# To Do
# ~~~~~
# - Complete Interface method signatures using "from typing"
#
# - Consider "dependency_name" --> "dependency_path"
# - Consider "category_name" --> "category_path"
# - Consider "entry_name" --> "entry_path"

from abc import abstractmethod

from aiko_services.main import Actor, Interface

__all__ = ["Storage"]

# --------------------------------------------------------------------------- #

class Storage(Actor):
    Interface.default("Storage",
        "aiko_services.main.storage.storage_file.StorageFileImpl")

    @abstractmethod
    def add(self, dependency_name, dependency=None):
        pass

    @abstractmethod
    def create(self, category_name):
        pass

    @abstractmethod
    def destroy(self, entry_name):     # Entry is either Category or Dependency
        pass

    @abstractmethod
    def dump(self, sort_by_name):
        pass

    @abstractmethod
    def exit(self):
        pass

    @abstractmethod
    def initialize(self, storage_url):
        pass

    @abstractmethod
    def link(self, entry_path_new, entry_path_existing):
        pass

    @abstractmethod
    def list(self, topic_path_response, entry_name=None,
        long_format=False, recursive=False, entry_records=None):
        pass

    @abstractmethod
    def remove(self, entry_name):      # Entry is either Category or Dependency
        pass

    @abstractmethod
    def update(self, entry_name, service=None,
        service_filter=None, lifecycle_manager_url=None, storage_url=None):
        pass

# --------------------------------------------------------------------------- #
