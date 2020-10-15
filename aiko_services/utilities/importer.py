# Usage
# -----
# from aiko_services.utilities import load_module
# module_descriptor = "pathname/filename.py"  # or "package.module"
# module = load_module(module_descriptor)
# module.some_class()
# module.some_function()
#
# To Do
# -----
# - None, yet !

import importlib
import os
import sys

__all__ = ["load_module", "load_modules"]

def load_module(module_descriptor):
    if module_descriptor.endswith(".py"):
        # Load module from Python source pathname, e.g "directory/file.py"
        module_pathname = module_descriptor
        module = importlib.machinery.SourceFileLoader('module', module_pathname).load_module()
    else:
        # Load module from "installed" modules, e.g "package.module"
        module_name = module_descriptor
        module = importlib.import_module(module_name)
    return module

def load_modules(module_pathnames):
    modules = []
    for module_pathname in module_pathnames:
        if module_pathname:
            modules.append(load_module(module_pathname))
        else:
            modules.append(None)
    return modules
