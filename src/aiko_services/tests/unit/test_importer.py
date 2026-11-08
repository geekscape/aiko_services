#!/usr/bin/env python3
#
# Aiko Services tests: loading a module from a pathname
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# main/utilities/importer.py.
#
# Every file loaded by pathname used to be named "module", and the
# deprecated Loader.load_module() reuses an existing entry of that name
# in sys.modules.  So the second file ran INTO the first file's
# namespace, and where they shared a name, the second one won.
#
# Two Dashboard plug-ins found it on 2026-11-06.  One imports the
# Display Actor's "Screen" Interface, the other imports the asciimatics
# "Screen".  The Display page then built a remote proxy from the wrong
# class and raised at the call, far from the cause:
#
#     AttributeError: 'ServiceRemoteProxy' object has no attribute
#     'mirror'
#
# A plug-in interface that cannot tolerate two plug-ins is not one, so
# the isolation test below is the important one here.

import sys
import textwrap

import pytest

from aiko_services.main.utilities import load_module, load_modules
from aiko_services.main.utilities.importer import MODULES_LOADED


@pytest.fixture(autouse=True)
def _forget_what_a_test_loaded():
    """The loader caches by descriptor, and a test must not leave its
    temporary files in the cache of the next one"""

    before = dict(MODULES_LOADED)
    modules = set(sys.modules)
    yield
    MODULES_LOADED.clear()
    MODULES_LOADED.update(before)
    for name in set(sys.modules) - modules:
        if name.startswith("aiko_file_"):
            del sys.modules[name]


def write(directory, name, source):
    path = directory / name
    path.write_text(textwrap.dedent(source))
    return str(path)


# Two files, two namespaces ------------------------------------------------- #


def test_two_files_do_not_share_a_namespace(tmp_path):
    """The defect itself.  Both files bind "Screen", and each must keep
    its own"""

    first = write(
        tmp_path,
        "first.py",
        """
        Screen = "the Interface"
        def which():
            return Screen
    """,
    )
    second = write(
        tmp_path,
        "second.py",
        """
        Screen = "the terminal"
    """,
    )

    one = load_module(first)
    assert one.Screen == "the Interface"

    two = load_module(second)

    assert one is not two
    assert one.Screen == "the Interface"  # Not replaced
    assert two.Screen == "the terminal"
    assert one.which() == "the Interface"  # And the functions agree


def test_two_files_of_the_same_name_in_different_directories(tmp_path):
    """Both Dashboard plug-ins are called "dashboard_plugin.py", which is
    how the defect reached a person"""

    one = tmp_path / "display"
    two = tmp_path / "power_manager"
    one.mkdir()
    two.mkdir()
    first = write(one, "dashboard_plugin.py", 'plugins = {"display": 1}\n')
    second = write(two, "dashboard_plugin.py", 'plugins = {"power_manager": 2}\n')

    display = load_module(first)
    power = load_module(second)

    assert display is not power
    assert display.plugins == {"display": 1}
    assert power.plugins == {"power_manager": 2}


def test_each_file_is_named_after_itself(tmp_path):
    """A traceback that says "module" names every file at once"""

    path = write(tmp_path, "readable.py", "value = 1\n")

    module = load_module(path)

    assert module.__name__.startswith("aiko_file_readable_")
    assert sys.modules[module.__name__] is module


# What has not changed ------------------------------------------------------ #


def test_the_same_pathname_is_loaded_once(tmp_path):
    path = write(tmp_path, "once.py", "import itertools\ncount = next(itertools.count())\n")

    first = load_module(path)
    second = load_module(path)

    assert first is second


def test_a_package_module_still_loads_by_name():
    module = load_module("aiko_services.main.utilities.importer")

    assert module.load_module is load_module


def test_load_modules_takes_a_list_and_keeps_the_gaps(tmp_path):
    path = write(tmp_path, "listed.py", "value = 3\n")

    modules = load_modules([path, None])

    assert modules[0].value == 3
    assert modules[1] is None


# What a failure does ------------------------------------------------------- #


def test_a_file_that_raises_is_not_left_half_loaded(tmp_path):
    """A module that raised while it ran is not importable state, and
    leaving it in sys.modules hands the next caller a broken one"""

    path = write(tmp_path, "broken.py", "raise RuntimeError('no')\n")

    with pytest.raises(RuntimeError):
        load_module(path)

    assert not [name for name in sys.modules if name.startswith("aiko_file_broken_")]


def test_a_pathname_that_is_not_there_is_reported(tmp_path):
    with pytest.raises((ImportError, OSError)):
        load_module(str(tmp_path / "absent.py"))


# --------------------------------------------------------------------------- #
