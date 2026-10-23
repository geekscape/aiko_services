#!/usr/bin/env python3
#
# Aiko Services tests: the Aiko Dashboard application
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The first tests for "actors/dashboard/dashboard.py", which had none.
#
# What they aim at is the class of bug that is tricky and not obviously
# visible, rather than coverage:
#
# - the "--plugin" default is a string that "load_module()" resolves, and
#   a failure to resolve it is caught and discarded.  A stale default
#   gives a Dashboard with no pages at all, no error and no log line.
#   This is the only guard against that
# - the plug-in key is derived from the protocol, in one place, and a page
#   that is registered under a key nobody derives is simply never shown
# - a frame that raises in its constructor, its layout or its first draw
#   raises the first time a person opens the page, and never before.  So
#   every shipped frame is built and drawn on a real terminal
#
# What they do not cover, and needs a person: the update loop over time,
# key events through process_event(), the popup dialogues and their
# on_close callbacks, and a terminal resize.
#
# To Do
# ~~~~~
# - Drive key events through the pseudo-terminal

import os

import pytest

asciimatics = pytest.importorskip("asciimatics")

from aiko_services.main.utilities import load_module            # noqa: E402
from aiko_services.actors.dashboard import dashboard            # noqa: E402
from aiko_services.tests.unit.dashboard_screen import (         # noqa: E402
    draw_frame, pty_available,
)

PLUGIN_DEFAULT = "aiko_services.actors.dashboard.plugins"

needs_pty = pytest.mark.skipif(
    not pty_available(), reason="needs a POSIX pseudo-terminal")

# The plug-in registry ---------------------------------------------------- #

def test_the_plugin_default_is_the_registry_module():
    """The option's default, read from the command itself rather than from
    a copy of the string in this test"""

    option = next(parameter for parameter in dashboard.main.params
        if parameter.name == "plugin")

    assert list(option.default) == [PLUGIN_DEFAULT]

def test_the_plugin_default_actually_resolves():
    """The one that matters.  "main()" wraps load_module() in
    "except ModuleNotFoundError: module = None", and then registers
    nothing, so a stale default is silent: the Dashboard comes up with no
    pages, no error and no log line"""

    module = load_module(PLUGIN_DEFAULT)

    assert hasattr(module, "plugins"), f"{PLUGIN_DEFAULT} has no plugins"
    assert module.plugins, "the registry is empty"

def test_the_registry_holds_a_frame_for_each_page():
    module = load_module(PLUGIN_DEFAULT)

    assert sorted(module.plugins) ==  \
        ["process_manager", "recorder", "registrar"]
    for name, frame_class in module.plugins.items():
        assert issubclass(frame_class, dashboard.ServiceFrame), name

def test_update_plugins_seeds_the_applications_own_pages():
    dashboard._PLUGINS.clear()
    dashboard.update_plugins({"example": dashboard.LogFrame})

    assert dashboard._PLUGINS["Dashboard"] is dashboard.DashboardFrame
    assert dashboard._PLUGINS["Log"] is dashboard.LogFrame
    assert dashboard._PLUGINS["example"] is dashboard.LogFrame
    dashboard._PLUGINS.clear()

def test_update_plugins_merges_and_does_not_reseed():
    dashboard._PLUGINS.clear()
    dashboard.update_plugins({})
    seeded = dict(dashboard._PLUGINS)
    dashboard.update_plugins({"example": dashboard.LogFrame})

    assert set(dashboard._PLUGINS) == set(seeded) | {"example"}
    dashboard._PLUGINS.clear()

# The plug-in interface -------------------------------------------------- #

def test_the_package_presents_the_whole_plugin_interface():
    """A plug-in imports these from the package, so that the modules below
    can be reorganized without touching a plug-in.  This asserts the names
    are the same objects, not merely that they exist"""

    from aiko_services.actors.dashboard import (
        FrameCommon, LogLevelPopupMenu, LogUI, ServiceFrame,
    )
    from aiko_services.actors.dashboard import frames

    assert FrameCommon is frames.FrameCommon
    assert LogUI is frames.LogUI
    assert ServiceFrame is frames.ServiceFrame
    assert LogLevelPopupMenu is dashboard.LogLevelPopupMenu

def test_the_facade_still_offers_the_interface():
    """Every plug-in written before the move says "aiko.ServiceFrame", and
    the Registrar's page still does"""

    import aiko_services as aiko
    from aiko_services.actors.dashboard import frames

    assert aiko.ServiceFrame is frames.ServiceFrame
    assert aiko.LogUI is frames.LogUI

def test_main_does_not_import_the_actors_tier():
    """The layering contract of s_01 step 7: "main" must not depend on
    "actors", which is why the facade re-exports the interface"""

    import aiko_services.main as main

    assert not hasattr(main, "ServiceFrame")
    assert not hasattr(main, "LogUI")

def test_the_service_hooks_default_to_doing_nothing():
    """A page overrides what it needs, so the base class must accept both
    hooks and do nothing"""

    from aiko_services.actors.dashboard import ServiceFrame

    assert ServiceFrame._service_frame_start(None, ["t"], None) is None
    assert ServiceFrame._service_frame_stop(None, ["t"]) is None

# The key that selects a page --------------------------------------------- #

@pytest.mark.parametrize("protocol,expected", [
    ("github.com/geekscape/aiko_services/protocol/process_manager:0",
     "process_manager"),
    ("github.com/geekscape/aiko_services/protocol/registrar:2", "registrar"),
    ("github.com/geekscape/aiko_services/protocol/display:0", "display"),
])
def test_the_page_key_is_derived_from_the_protocol(protocol, expected):
    """A page registered under a key that nobody derives is never shown,
    and nothing reports it"""

    short_name = dashboard.FrameCommon._short_name(None, protocol)

    assert short_name.split(":")[0] == expected

def test_each_shipped_service_has_a_page_under_a_derived_key():
    from aiko_services.main.process_manager import PROTOCOL as PROCESS_MANAGER
    from aiko_services.main.recorder import PROTOCOL as RECORDER
    from aiko_services.main import REGISTRAR_PROTOCOL

    module = load_module(PLUGIN_DEFAULT)
    for protocol in (PROCESS_MANAGER, RECORDER, REGISTRAR_PROTOCOL):
        key = dashboard.FrameCommon._short_name(None, protocol).split(":")[0]
        assert key in module.plugins, protocol

# Every shipped frame, on a real terminal --------------------------------- #

CACHE = {
    "lifecycle": "ready", "log_level": "INFO", "last_error": "-",
    "safe": True, "watchdog": False, "service_count": 2,
    "metrics": {"created": 2, "denied": 3, "running": 2},
    "process": {"000000": "4242 aiko_process run",
                "000001": "4301 sleep 60"},
}

FRAMES = [
    ("aiko_services.actors.dashboard.dashboard", "LogFrame"),
    ("aiko_services.actors.dashboard.registrar_plugin", "RegistrarFrame"),
    ("aiko_services.actors.dashboard.process_manager_plugin",
     "ProcessManagerFrame"),
    ("aiko_services.actors.dashboard.recorder_plugin", "RecorderFrame"),
]

@needs_pty
@pytest.mark.parametrize("module_name,class_name", FRAMES,
    ids=[class_name for _, class_name in FRAMES])
def test_a_shipped_frame_is_built_and_drawn(module_name, class_name, tmp_path):
    """The constructor, the layouts, fix(), the Service hook and the first
    _update() pass, on a real curses Screen"""

    drawn = draw_frame(module_name, class_name, CACHE, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    assert any(line.strip() for line in drawn["lines"]), "nothing was drawn"

@needs_pty
def test_the_process_manager_page_draws_what_it_promises(tmp_path):
    drawn = draw_frame(
        "aiko_services.actors.dashboard.process_manager_plugin",
        "ProcessManagerFrame", CACHE, tmp_path)
    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    text = "\n".join(drawn["lines"])

    assert "posture: safe" in text and "denied: 3" in text
    assert "aiko_process run" in text and "sleep 60" in text
    assert "last_error" in text

@needs_pty
@pytest.mark.parametrize("size", [(80, 24), (132, 48)],
    ids=["80x24", "132x48"])
def test_the_process_manager_page_fits_a_small_terminal(size, tmp_path):
    """A widget taller than its frame raises, and only at this moment"""

    drawn = draw_frame(
        "aiko_services.actors.dashboard.process_manager_plugin",
        "ProcessManagerFrame", CACHE, tmp_path, size=size)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    assert drawn["size"] == list(size)

@needs_pty
def test_a_page_draws_with_an_empty_shared_state(tmp_path):
    """The state arrives after the page opens, so every page is drawn at
    least once with nothing in the replica"""

    for module_name, class_name in FRAMES:
        drawn = draw_frame(module_name, class_name, {}, tmp_path)
        assert drawn["ok"], (
            class_name, drawn.get("traceback") or drawn.get("error"))

# --------------------------------------------------------------------------- #
