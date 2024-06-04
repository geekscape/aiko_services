# Usage
# -----
# from aiko_services.main.utilities import *
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

if os.environ.get("AIKO_IMPORTER_USE_CURRENT_DIRECTORY"):
    sys.path.append(os.getcwd())

MODULES_LOADED = {}

def load_module(module_descriptor):
    if module_descriptor in MODULES_LOADED:
        module = MODULES_LOADED[module_descriptor]
    else:
        if module_descriptor.endswith(".py"):
            # Load module from Python source pathname, e.g "directory/file.py"
            module_pathname = module_descriptor
            module = importlib.machinery.SourceFileLoader(
                'module', module_pathname).load_module()
        else:
            # Load module from "installed" modules, e.g "package.module"
            module_name = module_descriptor
            module = importlib.import_module(module_name)
        MODULES_LOADED[module_descriptor] = module
    return module

def load_modules(module_pathnames):
    modules = []
    for module_pathname in module_pathnames:
        if module_pathname:
            modules.append(load_module(module_pathname))
        else:
            modules.append(None)
    return modules
