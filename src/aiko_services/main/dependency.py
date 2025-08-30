#!/usr/bin/env python3
#
# Aiko Service: Dependency
# ~~~~~~~~~~~~~~~~~~~~~~~~
#
# To Do
# ~~~~~
# * Consider use of ServiceFields rather than ServiceFilter ?
#
# * Replace current Pipeline prototype implementation with this improveed design
#   * Once full Dependency resolution, information flow, etc is completed
#
# - Properties: Dependency direction, Information direction, Strong, Weak, Group
#
# - DependencyManager maintaining in-memory list of Dependencies ?
#
# - Security model design and implementation

from abc import abstractmethod
import click

from aiko_services.main import *

__all__ = ["Dependency"]

# --------------------------------------------------------------------------- #
# TODO: lifecycle_manager_url and storage_url values ...
#     - None: Manually  started
#     - "*":  Default:  discover ProcessManager or Storage
#     - "URL" Specified ProcessManager or Storage

class Dependency:
    def __init__(self, service_filter,  # TODO: Or ServiceFields ?
        lifecycle_manager_url=None, storage_url=None):

        self.service_filter = service_filter
        self.lifecycle_manager_url = lifecycle_manager_url
        self.storage_url = storage_url

    def __repr__(self):
        return f"({self.service_filter} "  \
               f"{self.lifecycle_manager_url} "  \
               f"{self.storage_url})"

    def update(self, service_filter=None,
        lifecycle_manager_url=None, storage_url=None):

        if service_filter:
            self.service_filter = service_filter
        if lifecycle_manager_url:
            self.lifecycle_manager_url = lifecycle_manager_url
        if storage_url:
            self.storage_url = storage_url

# --------------------------------------------------------------------------- #
