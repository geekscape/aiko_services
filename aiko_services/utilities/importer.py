# Usage
# -----
# from aiko_services.utilities import load_module
# module = load_module("pathname/filename.py")
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

def load_module(module_pathname):
    pathname, filename = os.path.split(module_pathname)
    if pathname not in sys.path:
        sys.path.append(pathname)
    module_name = os.path.splitext(filename)[0]
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
