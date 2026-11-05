#!/usr/bin/env python3
#
# Aiko Services tests: the power manager's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Phase 4 of the power management plan
# (actors/power_manager/dashboard_plugin.py).
#
# Two kinds of test, for two kinds of mistake:
#
# - the pure ones, against PowerManagerPage.  A replica of the shared
#   state goes in and rows come out, so a wrong row is a wrong value
#   here and not a screenshot somebody has to read
# - the drawn ones, through draw_frame(), on a real pseudo-terminal.
#   asciimatics has no screen double, and a frame that forgets fix(), or
#   holds a widget taller than itself, or reads an attribute before it
#   exists, raises the first time a person opens the page and never
#   before
#
# The Information view has a test of its own, and it is the reason that
# view exists: a page that shows "mode_reason hook_missing" and leaves an
# operator to find out what that means has not finished the job.  The
# test asserts coverage against the Actor's own vocabulary, so a new
# reason added to the policy fails here until it is explained.

import itertools

import pytest

asciimatics = pytest.importorskip("asciimatics")

import aiko_services as aiko                                  # noqa: E402
from aiko_services.actors.power_manager import (              # noqa: E402
    MockPowerManagerImpl, PROTOCOL, power_manager_args,
)
from aiko_services.actors.power_manager import (              # noqa: E402
    dashboard_plugin as plugin,
)
from aiko_services.actors.power_manager.policy import (       # noqa: E402
    MODES, REASONS, SUPPLY_WARNINGS,
)
from aiko_services.actors.power_manager.power_manager import (  # noqa: E402
    THRESHOLDS,
)
from aiko_services.ide.tui.dashboard import dashboard         # noqa: E402
from aiko_services.tests.unit.dashboard_screen import (       # noqa: E402
    draw_frame, pty_available,
)

needs_pty = pytest.mark.skipif(
    not pty_available(), reason="needs a POSIX pseudo-terminal")

_counter = itertools.count()

MODULE = "aiko_services.actors.power_manager.dashboard_plugin"

@pytest.fixture(scope="module")
def cache():
    """A real Actor's shared state, and not a hand-written fixture: a
    page that draws a dictionary nobody publishes proves nothing"""

    actor = aiko.compose_instance(MockPowerManagerImpl, power_manager_args(
        f"power_page_{next(_counter)}", "mock",
        declared=MockPowerManagerImpl.DECLARED_PROPERTIES,
        log_directory=None, telemetry=False, timer=False))
    actor.sample()
    return actor.share

# The registry -------------------------------------------------------------- #

def test_the_page_is_registered_under_the_derived_key():
    """A page registered under a key nobody derives is never shown"""

    key = dashboard.FrameCommon._short_name(None, PROTOCOL).split(":")[0]

    assert key == "power_manager"
    assert list(plugin.plugins) == ["power_manager"]
    assert issubclass(plugin.plugins[key], dashboard.ServiceFrame)

def test_the_page_is_not_in_the_frameworks_own_registry():
    """"main" must not depend on "actors", so an Actor's page is loaded
    with "-p", the way the Display Actor's page is"""

    from aiko_services.main.utilities import load_module

    registry = load_module("aiko_services.ide.tui.dashboard.plugins")

    assert "power_manager" not in registry.plugins

# The keys ------------------------------------------------------------------ #

def test_the_keys_avoid_the_ones_the_dashboard_reserves():
    """A page that takes a reserved key makes the Dashboard inconsistent
    for the person using it, not only for this page"""

    reserved = set("?TabEnterxXDLSlcfsCK") | set("DLSK")

    assert not (set(plugin.KEYS) & set("xXDLSlcfsCK?"))
    assert "v" in plugin.KEYS and "I" in plugin.KEYS
    assert reserved                        # the list above is not empty

def test_an_unclaimed_key_falls_through():
    page = plugin.PowerManagerPage()

    assert page.action(ord("q")) is None
    assert page.action(-203) is None       # A function key, not a character

def test_the_views_cycle_both_ways():
    page = plugin.PowerManagerPage()
    assert page.view == plugin.SUMMARY

    assert [page.cycle_view(1) for _ in range(3)] == list(
        plugin.VIEWS[1:]) + [plugin.SUMMARY]
    assert page.cycle_view(-1) == plugin.VIEWS[-1]

def test_the_log_source_toggles():
    page = plugin.PowerManagerPage()
    assert page.source == plugin.RECORDS

    assert page.cycle_source() == plugin.TELEMETRY
    assert page.cycle_source() == plugin.RECORDS

# The posture --------------------------------------------------------------- #

@pytest.mark.parametrize("value,expected", [
    (True, True), (False, False), ("True", True), ("False", False),
    ("true", True), (None, None),
])
def test_the_posture_is_read_from_the_replica(value, expected):
    """It arrives as a bool from a local Actor and as a string off the
    wire, and it is absent from an Actor older than the posture"""

    cache = {} if value is None else {"safe": value}

    assert plugin.PowerManagerPage.read_safe(cache) is expected

def test_only_an_unsafe_actor_is_editable():
    """An unknown posture is not editable: an Actor that does not publish
    one does not have set_threshold either"""

    assert plugin.PowerManagerPage.editable({"safe": False}) is True
    assert plugin.PowerManagerPage.editable({"safe": True}) is False
    assert plugin.PowerManagerPage.editable({}) is False

def test_the_legend_says_the_posture_and_what_it_denies():
    page = plugin.PowerManagerPage()

    assert "safe" in page.legend({"safe": True})
    assert "denies" in page.legend({"safe": True})
    assert "UNSAFE" in page.legend({"safe": False})
    assert "denies" not in page.legend({"safe": False})

# The rows ------------------------------------------------------------------ #

def test_every_view_draws_rows_before_any_state_arrives():
    """The state arrives after the page opens, and the page must say so
    rather than raise or show nothing"""

    page = plugin.PowerManagerPage()
    for view in plugin.VIEWS:
        page.view = view
        rows = page.rows({})
        assert rows, view
        assert all(len(row) == 2 for row in rows), view

def test_the_summary_is_short_enough_to_read(cache):
    """It is the headline.  A headline that fills a terminal is a dump"""

    rows = plugin.PowerManagerPage().summary_rows(cache)

    assert 10 <= len(rows) <= 18

def test_the_summary_carries_the_numbers_an_operator_acts_on(cache):
    page = plugin.PowerManagerPage()
    text = "\n".join(f"{name} {value}"
        for name, value in page.summary_rows(cache))

    for wanted in ("supply", "battery pack", "above the floor", "policy",
            "mode", "docked", "working", "sampled", "last error"):
        assert wanted in text, wanted

def test_the_summary_shows_the_margin_and_not_only_the_threshold(cache):
    """"1.22 V above the floor" is the number an operator acts on"""

    rows = dict(plugin.PowerManagerPage().summary_rows(cache))

    assert "floor" in rows["  above the floor"]

def test_the_sample_time_is_local(cache):
    """Local time everywhere a person reads one, as Agents.md says"""

    rows = dict(plugin.PowerManagerPage().summary_rows(cache))

    assert not rows["sampled"].endswith("Z")

def test_the_detail_view_shows_every_threshold(cache):
    rows = plugin.PowerManagerPage().detail_rows(cache)
    names = {name.strip() for name, _ in rows}

    for threshold in THRESHOLDS:
        assert threshold in names, threshold

def test_the_detail_view_marks_what_the_posture_allows(cache):
    page = plugin.PowerManagerPage()
    safe = dict(cache, safe=True)
    unsafe = dict(cache, safe=False)

    assert any("(--safe)" in name for name, _ in page.detail_rows(safe))
    assert any("(Enter)" in name for name, _ in page.detail_rows(unsafe))

def test_a_threshold_row_selects_its_whole_group():
    """A heading selects its group, and so does any row under it, so an
    operator never has to find the heading first"""

    page = plugin.PowerManagerPage()

    assert page.group_of("  battery_volts_low")[0] == "voltages"
    assert page.group_of("voltages  (Enter)")[0] == "voltages"
    assert page.group_of("  supply.volts") is None

def test_every_threshold_belongs_to_exactly_one_group():
    """A threshold in no group cannot be edited, and one in two groups is
    edited twice with the second write winning"""

    seen = [name for _, names in plugin.GROUPS for name in names]

    assert len(seen) == len(set(seen))
    assert set(seen) == set(THRESHOLDS), set(seen) ^ set(THRESHOLDS)

# The Information view ------------------------------------------------------ #

def test_every_word_the_actor_publishes_is_explained():
    """The reason this view exists.  A new policy reason fails here until
    somebody writes down what it means"""

    explained = {name.strip() for name, _ in plugin.INFORMATION_TEXT}
    vocabulary = (set(REASONS) | set(MODES) | set(SUPPLY_WARNINGS)
        | {"advisory", "hold", "shutdown_pending", "shutting_down"}
        | {"policy", "docked", "battery", "hook_missing", "held",
           "application_grace", "undocked"})

    assert vocabulary <= explained, vocabulary - explained

def test_every_explanation_says_something():
    for name, text in plugin.INFORMATION_TEXT:
        if name:
            assert text, name

def test_the_information_view_says_a_threshold_is_not_persisted():
    text = " ".join(text for _, text in plugin.INFORMATION_TEXT)

    assert "not persisted" in text

# On a real terminal -------------------------------------------------------- #

PROBES = {
    "summary": "PowerManagerSummary",
    "detail": "PowerManagerDetail",
    "information": "PowerManagerInformation",
}

def test_there_is_a_probe_for_every_view():
    """draw_frame() delivers no key events, so each view is drawn through
    a probe.  A view with no probe is never drawn by any test"""

    assert set(PROBES) == set(plugin.VIEWS)

@needs_pty
@pytest.mark.parametrize("view", plugin.VIEWS)
def test_each_view_is_built_and_drawn(view, cache, tmp_path):
    drawn = draw_frame("aiko_services.tests.unit.dashboard_screen",
        PROBES[view], cache, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    assert any(line.strip() for line in drawn["lines"])

@needs_pty
def test_the_information_view_draws_its_explanations(cache, tmp_path):
    drawn = draw_frame("aiko_services.tests.unit.dashboard_screen",
        "PowerManagerInformation", cache, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    text = "\n".join(drawn["lines"])
    assert "advisory" in text

@needs_pty
def test_the_detail_view_draws_the_thresholds(cache, tmp_path):
    drawn = draw_frame("aiko_services.tests.unit.dashboard_screen",
        "PowerManagerDetail", cache, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    text = "\n".join(drawn["lines"])
    assert "battery_volts_floor" in text

@needs_pty
def test_the_page_draws_what_it_promises(cache, tmp_path):
    drawn = draw_frame(MODULE, "PowerManagerFrame", cache, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    text = "\n".join(drawn["lines"])
    assert "supply" in text
    assert "battery pack" in text
    assert "posture" in text

@needs_pty
@pytest.mark.parametrize("size", [(80, 24), (132, 48)])
def test_the_page_fits_the_terminals_people_use(size, cache, tmp_path):
    drawn = draw_frame(MODULE, "PowerManagerFrame", cache, tmp_path,
        size=size)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    assert drawn["size"] == list(size)

@needs_pty
def test_the_page_draws_with_an_empty_shared_state(tmp_path):
    """Every page's constructor runs at Dashboard start-up, before any
    Service is selected, so it touches no network and tolerates this"""

    drawn = draw_frame(MODULE, "PowerManagerFrame", {}, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")

# --------------------------------------------------------------------------- #
