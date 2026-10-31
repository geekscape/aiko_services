#!/usr/bin/env python3
#
# Aiko Services tests: the Aiko Dashboard application
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The first tests for "ide/tui/dashboard/dashboard.py", which had none.
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
from types import SimpleNamespace

import pytest

asciimatics = pytest.importorskip("asciimatics")

from aiko_services.main.utilities import load_module            # noqa: E402
from aiko_services.ide.tui.dashboard import dashboard            # noqa: E402
from aiko_services.main.service import (                        # noqa: E402
    Services, ServiceTopicPath,
)
from aiko_services.tests.unit.dashboard_screen import (         # noqa: E402
    draw_frame, pty_available,
)

PLUGIN_DEFAULT = "aiko_services.ide.tui.dashboard.plugins"

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

    from aiko_services.ide.tui.dashboard import (
        FrameCommon, LogLevelPopupMenu, LogUI, ServiceFrame,
    )
    from aiko_services.ide.tui.dashboard import frames

    assert FrameCommon is frames.FrameCommon
    assert LogUI is frames.LogUI
    assert ServiceFrame is frames.ServiceFrame
    assert LogLevelPopupMenu is dashboard.LogLevelPopupMenu

def test_the_facade_still_offers_the_interface():
    """Every plug-in written before the move says "aiko.ServiceFrame", and
    the Registrar's page still does"""

    import aiko_services as aiko
    from aiko_services.ide.tui.dashboard import frames

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

    from aiko_services.ide.tui.dashboard import ServiceFrame

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
    ("aiko_services.ide.tui.dashboard.dashboard", "LogFrame"),
    ("aiko_services.ide.tui.dashboard.registrar_plugin", "RegistrarFrame"),
    ("aiko_services.ide.tui.dashboard.process_manager_plugin",
     "ProcessManagerFrame"),
    ("aiko_services.ide.tui.dashboard.recorder_plugin", "RecorderFrame"),
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
        "aiko_services.ide.tui.dashboard.process_manager_plugin",
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
        "aiko_services.ide.tui.dashboard.process_manager_plugin",
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

# Which Service the selection means ---------------------------------------- #
#
# "DashboardFrame" cannot be built here, which is why it is absent from
# FRAMES above: its constructor calls "services_cache_create_singleton()",
# and that needs a broker and a thread.  So these tests call the real
# methods that read a selection back out of the widget, on an object that
# carries only the state those methods touch.
#
# What they aim at: the first column of each row is
# "ServiceTopicPath.terse", which abbreviates a topic path longer than 26
# characters.  Identifying the selected Service by that column handed an
# abbreviated path to "Services.get_service()", which keys on the full one,
# so it answered None and the Dashboard raised "TypeError: 'NoneType'
# object is not subscriptable" on the first frame that held a Service.  The
# fault needed a Service whose topic path is long enough, so it appeared on
# a remote broker and never on localhost

TOPIC_PATH_LONG = "aiko/amr-instance/1727706/1"   # 27 characters, abbreviated
TOPIC_PATH_SHORT = "aiko/nomad/5161/1"            # 17 characters, unchanged

def service_details(topic_path, name="actor", tags=None):
    return [topic_path, name, "protocol:0", "mqtt", "owner",
        tags if tags else ["a=b"]]

def services_holding(*topic_paths):
    services = Services()
    for topic_path in topic_paths:
        services.add_service(topic_path, service_details(topic_path))
    return services

class _Selection:
    """Just enough DashboardFrame for the methods under test, which are the
    real ones, bound here as class attributes"""

    _ec_consumer_reset = dashboard.DashboardFrame._ec_consumer_reset
    _ec_consumer_set = dashboard.DashboardFrame._ec_consumer_set
    _get_service_topic_path_next =  \
        dashboard.DashboardFrame._get_service_topic_path_next
    _on_change_services = dashboard.DashboardFrame._on_change_services

    def __init__(self, services=None, rows=(), value=None):
        self.ec_consumer = None
        self.service_cache = {}
        self.service_tags = None
        self.selected_service = None
        self.selected_topic_path = None
        self.services_cache = SimpleNamespace(get_services=lambda: services)
        # Each row as "_update()" builds it: the terse form on display,
        # and the full topic path as the option's internal value
        self._services_widget = SimpleNamespace(value=value, options=[
            ((ServiceTopicPath.parse(topic_path).terse,), topic_path)
            for topic_path in rows])

def test_the_terse_form_is_not_a_cache_key():
    """Why the display column cannot identify a Service.  Should this ever
    fail, "terse" has stopped abbreviating and the tests below prove
    nothing"""

    services = services_holding(TOPIC_PATH_LONG)
    terse = ServiceTopicPath.parse(TOPIC_PATH_LONG).terse

    assert terse != TOPIC_PATH_LONG
    assert services.get_service(terse) is None
    assert services.get_service(TOPIC_PATH_LONG) is not None

class _Stop(Exception):
    """Ends "_update()" at the assignment under test, because everything
    after it belongs to asciimatics and wants a real Frame"""

class _Recorder:
    def __init__(self):
        self.options = []

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name == "options" and value:
            raise _Stop

class _Update:
    """Just enough DashboardFrame for the part of "_update()" that fills
    the Services page"""

    _filter = dashboard.DashboardFrame._filter
    _service_selection_color =  \
        dashboard.DashboardFrame._service_selection_color
    _short_name = dashboard.DashboardFrame._short_name
    YELLOW = dashboard.DashboardFrame.YELLOW

    def __init__(self, services):
        self.adjust_palette_required = False
        self.filter_out = dashboard.DashboardFrame.FILTER_OUT.copy()
        self.selected_services = {}
        self.services_cache = SimpleNamespace(get_services=lambda: services)
        self._services_widget = _Recorder()

def test_each_row_carries_a_topic_path_the_cache_accepts():
    """The real "_update()", at the site that built the identity.  Each row
    must pair a display column with a value that selects its Service"""

    services = services_holding(TOPIC_PATH_LONG, TOPIC_PATH_SHORT)
    frame = _Update(services)

    with pytest.raises(_Stop):
        dashboard.DashboardFrame._update(frame, 0)

    rows = frame._services_widget.options
    assert len(rows) == 2
    for columns, topic_path in rows:
        assert services.get_service(topic_path) is not None, topic_path
    assert [columns[0] for columns, _ in rows] ==  \
        ["aiko/amr-inst+/1727706/1", TOPIC_PATH_SHORT]

def test_a_changed_selection_is_the_full_topic_path():
    selection = _Selection(rows=[TOPIC_PATH_LONG], value=TOPIC_PATH_LONG)
    handed = []
    selection._ec_consumer_set = handed.append

    selection._on_change_services()

    assert handed == [TOPIC_PATH_LONG]
    assert selection.selected_topic_path == TOPIC_PATH_LONG

def test_an_unchanged_selection_is_left_alone():
    selection = _Selection(rows=[TOPIC_PATH_LONG], value=TOPIC_PATH_LONG)
    selection.selected_topic_path = TOPIC_PATH_LONG
    handed = []
    selection._ec_consumer_set = handed.append

    selection._on_change_services()

    assert handed == []

def test_a_long_topic_path_selects_its_service():
    """The pairing, end to end: the value a row carries is accepted by the
    cache, and the Service's tags reach the frame"""

    selection = _Selection(services=services_holding(TOPIC_PATH_LONG),
        rows=[TOPIC_PATH_LONG], value=TOPIC_PATH_LONG)

    selection._on_change_services()

    assert selection.selected_service[0] == TOPIC_PATH_LONG
    assert selection.service_tags == ["a=b"]

def test_the_last_service_leaving_clears_the_selection():
    """The widget's value falls to None when no row is left, and a Service
    that has gone must not stay selected"""

    selection = _Selection(rows=[], value=None)
    selection.selected_topic_path = TOPIC_PATH_LONG
    selection.selected_service = service_details(TOPIC_PATH_LONG)
    selection.service_tags = ["a=b"]

    selection._on_change_services()

    assert selection.selected_topic_path is None
    assert selection.selected_service is None
    assert selection.service_tags is None

def test_a_service_that_exits_between_frames_does_not_raise():
    """"_update()" reads a copy of the cache, so the message bus thread can
    remove a Service before the selection is looked up"""

    selection = _Selection(services=services_holding(TOPIC_PATH_SHORT))

    selection._ec_consumer_set(TOPIC_PATH_LONG)

    assert selection.selected_service is None
    assert selection.service_tags is None
    assert selection.ec_consumer is None

def test_the_next_service_is_the_row_after_the_selected_one():
    """What "K" uses to move the selection off the Service it kills"""

    selection = _Selection(
        rows=[TOPIC_PATH_SHORT, TOPIC_PATH_LONG], value=TOPIC_PATH_SHORT)
    selection.selected_topic_path = TOPIC_PATH_SHORT

    assert selection._get_service_topic_path_next() == TOPIC_PATH_LONG

def test_there_is_no_next_service_after_the_last_row():
    selection = _Selection(
        rows=[TOPIC_PATH_SHORT, TOPIC_PATH_LONG], value=TOPIC_PATH_LONG)
    selection.selected_topic_path = TOPIC_PATH_LONG

    assert selection._get_service_topic_path_next() is None

def test_there_is_no_next_service_when_nothing_is_selected():
    selection = _Selection(rows=[TOPIC_PATH_SHORT])

    assert selection._get_service_topic_path_next() is None

# --------------------------------------------------------------------------- #
