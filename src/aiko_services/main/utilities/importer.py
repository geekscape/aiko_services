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

import hashlib
import importlib
import importlib.util
import os
import pathlib
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
            module = _load_module_from_path(module_descriptor)
        else:
            # Load module from "installed" modules, e.g "package.module"
            module_name = module_descriptor
            module = importlib.import_module(module_name)
        MODULES_LOADED[module_descriptor] = module
    return module

def _module_name(pathname):
    """A name of this file's own, which is stable across calls.

    The digest of the resolved path makes it unique, and the file name
    in front of it makes a traceback readable"""

    resolved = str(pathlib.Path(pathname).resolve())
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]
    stem = pathlib.Path(pathname).stem or "module"
    return f"aiko_file_{stem}_{digest}"

def _load_module_from_path(pathname):
    """Load a Python source file as a module of its own.

    Every file loaded this way used to be named "module", and the
    deprecated Loader.load_module() reuses an existing entry of that name
    in sys.modules.  So the second file was run INTO the first file's
    namespace, and whatever names they shared, the second one won.

    Two Dashboard plug-ins loaded with "-p a.py -p b.py" found this on
    2026-11-06: one imported the Display Actor's "Screen" Interface, the
    other imported the asciimatics "Screen", and the page built a remote
    proxy from the wrong class.  It failed at the call, far from the
    cause, with "ServiceRemoteProxy object has no attribute mirror".

    Each file now gets a name of its own, and the module is registered
    under it, which is what a dataclass, a pickle and a traceback need"""

    name = _module_name(pathname)
    spec = importlib.util.spec_from_file_location(name, pathname)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load a module from: {pathname}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)     # A half-run module helps nobody
        raise
    return module

def load_modules(module_pathnames):
    modules = []
    for module_pathname in module_pathnames:
        if module_pathname:
            modules.append(load_module(module_pathname))
        else:
            modules.append(None)
    return modules
