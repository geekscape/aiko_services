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
    assert list(plugin.plugins) == ["power_manager", "power_manager_chart"]
    assert issubclass(plugin.plugins[key], dashboard.ServiceFrame)
    assert issubclass(plugin.plugins["power_manager_chart"],
        dashboard.ServiceFrame)

def test_the_chart_page_is_reached_by_a_key_and_not_by_a_protocol():
    """No Service has the protocol "power_manager_chart".  That page is
    raised by name from the page beside it, which is how one view cycle
    spans two Frames"""

    assert plugin.CHART_SCENE == "power_manager_chart"
    assert plugin.PAGE_SCENE == "power_manager"

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

    assert [page.cycle_view(1) for _ in range(len(plugin.VIEWS))] == list(
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
    "chart": "PowerManagerChart",
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

# The chart ----------------------------------------------------------------- #
#
# The arithmetic is the part that is wrong silently: a bucket that drops
# a sample, a pan that runs off the end, a zoom with no limit.  It is all
# pure, so it is tested without a terminal.

def filled_page(count=120, step=15.0, start=1_000_000.0):
    page = plugin.PowerManagerPage()
    for index in range(count):
        page.samples.append((start + index * step,
            11.4, 0.7, 8.0, 11.1, 0.7, 7.8, 32.0, 52.0))
    return page

def test_a_reading_is_kept_once():
    """_update() re-reads the replica on every draw, several times a
    second, and the wall clock has one second of resolution.  The Actor's
    monotonic clock is what says a reading is new"""

    page = plugin.PowerManagerPage()
    cache = {"sampled_monotonic": "100.0",
        "sampled_utc": "2026-11-06T01:02:03Z",
        "supply": {"volts": "11.4"}, "battery": {"volts": "11.1"}}

    assert page.observe(cache) is True
    assert page.observe(cache) is False
    assert len(page.samples) == 1

def test_a_reading_with_no_time_is_not_kept():
    page = plugin.PowerManagerPage()

    assert page.observe({"sampled_monotonic": "1.0",
        "sampled_utc": "-"}) is False
    assert page.observe({}) is False

def test_the_window_bounds_what_is_drawn():
    page = filled_page()
    page.span = 300.0
    start, end = page.window()

    assert end - start == 300.0
    assert end == page.samples[-1][0]          # It follows the newest

def test_a_bucket_holds_the_lowest_the_highest_and_the_mean():
    """A column is a bucket, not a sample: twelve hours at the production
    period is seven hundred samples across a hundred columns.  Drawing
    the mean alone would average a spike away"""

    page = plugin.PowerManagerPage()
    for index, volts in enumerate((11.0, 12.0, 13.0)):
        page.samples.append((1000.0 + index,
            volts, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    page.span = 10.0
    buckets = page.buckets(2)
    entry = [bucket[0] for bucket in buckets if 0 in bucket][-1]
    low, high, total, count = entry

    assert (low, high) == (11.0, 13.0)
    assert total / count == 12.0

def test_every_sample_in_the_window_lands_in_a_bucket():
    page = filled_page(count=50, step=1.0)
    page.span = 60.0
    buckets = page.buckets(10)
    counted = sum(entry[3] for bucket in buckets
        for index, entry in bucket.items() if index == 0)

    assert counted == 50

def test_a_zoom_has_limits_both_ways():
    page = plugin.PowerManagerPage()
    for _ in range(40):
        page.zoom(0.5)
    assert page.span == plugin.SPAN_LOWEST_S

    for _ in range(40):
        page.zoom(2.0)
    assert page.span == plugin.SPAN_HIGHEST_S

def test_the_reset_goes_back_to_live():
    page = filled_page()
    page.zoom(0.5)
    page.pan(-0.5)
    assert page.end is not None

    page.zoom(None)

    assert page.span == plugin.SPAN_DEFAULT_S
    assert page.end is None

def test_panning_back_and_then_forward_follows_the_newest_again():
    """Reaching the newest sample is how the chart becomes live again,
    so a person never has to find a second key for it"""

    page = filled_page()
    page.pan(-0.5)
    assert page.end is not None

    for _ in range(6):
        page.pan(0.25)

    assert page.end is None

def test_panning_stops_before_the_oldest_sample():
    page = filled_page()
    for _ in range(100):
        page.pan(-1.0)
    start, _ = page.window()

    assert start >= page.samples[0][0] - page.span

def test_a_series_toggles_and_the_panel_follows():
    page = plugin.PowerManagerPage()
    assert page.enabled == set(range(len(plugin.SERIES)))

    assert page.toggle_series(0) is False
    assert 0 not in page.enabled
    assert page.toggle_series(0) is True

def test_every_series_has_a_key_and_every_key_a_series():
    """"1" to "8" toggle them, so the two tables must stay the same
    length or a series is unreachable"""

    keys = [action[1] for action in plugin.KEYS.values()
        if action[0] == "series"]

    assert sorted(keys) == list(range(len(plugin.SERIES)))

def test_every_series_names_a_panel_that_exists():
    for label, position, panel in plugin.SERIES:
        assert 0 <= panel < len(plugin.PANELS), label
        assert 1 <= position <= 8, label

def test_the_extent_leaves_room_above_and_below():
    """A line drawn on the frame of its own panel cannot be read"""

    page = filled_page()
    buckets = page.buckets(20)
    low, high = page.extent(buckets, {0})

    assert low < 11.4 < high

def test_the_extent_of_nothing_is_nothing():
    page = plugin.PowerManagerPage()

    assert page.extent([], {0}) is None

@needs_pty
def test_the_chart_draws_its_lines(tmp_path):
    drawn = draw_frame("aiko_services.tests.unit.dashboard_screen",
        "PowerManagerChartFilled", {}, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    text = "\n".join(drawn["lines"])
    assert "Volts" in text and "Celsius" in text
    assert "pan" in text                       # the legend
    drawing = [character for character in text
        if character not in " |-+_.0123456789:" and not character.isalpha()]
    assert drawing, "no line characters were drawn"

# --------------------------------------------------------------------------- #
