#!/usr/bin/env python3
#
# Aiko Services tests: the HyperSpace's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The HyperSpace page is the Category page with the differences a
# HyperSpace makes, so these tests are about those differences, and
# "test_category_plugin.py" covers everything the two share.  Each one
# that the page keeps is checked here as well, because a page that
# duplicated it instead would still pass its own tests.
#
# The frame's hooks are called on an instance built without __init__,
# because what they decide needs no screen and no layout: which function
# the page sends, and what it names.  The pseudo-terminal fixture covers
# the parts that do need a screen.
#
# To Do
# ~~~~~
# - Key events through the pseudo-terminal, for the create dialogue

import pytest

asciimatics = pytest.importorskip("asciimatics")

from aiko_services.main import CATEGORY_PROTOCOL                  # noqa: E402
from aiko_services.main.hyperspace import HyperSpace              # noqa: E402
from aiko_services.main.category_view import (                    # noqa: E402
    CATEGORY, DEPENDENCY, WILDCARD, entry_of,
)
from aiko_services.ide.tui.dashboard.category_plugin import (     # noqa: E402
    CategoryFrame, CategoryPage,
)
from aiko_services.ide.tui.dashboard.hyperspace_plugin import (   # noqa: E402
    HyperSpaceFrame, HyperSpacePage, plugins,
)
from aiko_services.tests.unit.dashboard_screen import (           # noqa: E402
    draw_frame, pty_available,
)

FOO = "aiko/protocol/foo:0"

def dependency(name):
    return [[WILDCARD, name, FOO, WILDCARD, "andyg", []], "None", "None"]

def category(name):
    return [[WILDCARD, name, CATEGORY_PROTOCOL, WILDCARD, WILDCARD, []],
        "None", "None"]

CACHE = {
    "lifecycle": "ready", "running": "False", "entries_count": "2",
    "storage_url": "file:", "metrics": {"created": "3", "running": "1"},
    "entries": {"hosts": category("hosts"), "dep_one": dependency("dep_one")},
}

class _Proxy:
    """Every function the page sends, and what it named"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def closure(*arguments):
            self.calls.append((name, arguments))
        return closure

def frame_of(frame_class):
    """A frame with only what its hooks read.  asciimatics needs a screen
    for __init__, and these hooks need none of what it builds"""

    frame = frame_class.__new__(frame_class)
    frame.page = frame_class.PAGE()
    frame.proxy = _Proxy()
    return frame

@pytest.fixture
def page():
    return HyperSpacePage()

@pytest.fixture
def frame():
    return frame_of(HyperSpaceFrame)

needs_pty = pytest.mark.skipif(
    not pty_available(), reason="needs a POSIX pseudo-terminal")

# The plug-in registration ------------------------------------------------ #

def test_the_plugin_key_is_the_protocol_type():
    assert list(plugins) == ["hyperspace"]

def test_the_dashboard_derives_that_key_from_the_protocol():
    from aiko_services.ide.tui.dashboard.dashboard import FrameCommon
    from aiko_services.main.hyperspace import PROTOCOL

    assert FrameCommon._short_name(
        None, PROTOCOL).split(":")[0] == "hyperspace"

def test_the_page_speaks_to_a_hyperspace():
    assert HyperSpaceFrame.INTERFACE is HyperSpace
    assert HyperSpaceFrame.FRAME_NAME != CategoryFrame.FRAME_NAME

# It extends the Category page, rather than repeating it ----------------- #

def test_it_is_a_category_page():
    assert issubclass(HyperSpacePage, CategoryPage)
    assert issubclass(HyperSpaceFrame, CategoryFrame)

def test_every_key_the_category_page_takes_is_still_taken(page):
    for key, action in CategoryPage.KEYS.items():
        assert page.action(ord(key)) == action

def test_the_keys_a_hyperspace_adds(page):
    assert page.action(ord("c")) == ("create",)
    assert page.action(ord("k")) == ("destroy",)
    assert page.action(ord("U")) == ("dump",)
    assert page.action(ord("K")) == ("exit",)

def test_the_dashboards_own_keys_are_still_left_alone(page):
    for reserved in "DxXS?":
        assert page.action(ord(reserved)) is None

def test_the_help_names_every_key_including_the_ones_it_adds(page):
    text = page.help_text()

    for key in page.KEYS:
        assert key in text
    for word in ("create", "destroy", "dump", "exit", "add", "remove"):
        assert word in text

def test_the_state_table_names_the_storage_too(page):
    assert [name for name, _ in page.state_rows(CACHE)] == [
        "entries_count", "storage_url", "lifecycle", "running",
        "metrics.created", "metrics.running"]

# A HyperSpace resolves a whole Entry path ------------------------------- #

def test_a_category_opens_where_it_is(page):
    """A HyperSpace answers for any path, so a Category is opened rather
    than followed to its own Service"""

    page.refresh_root(CACHE, "hs_a")

    assert page.resolves_paths is True
    assert page.marker(page.tree.node("hosts")) == "+"
    assert page.toggle("hosts") == "request"       # it asks for its Entries
    assert page.tree.node("hosts").expanded

def test_a_category_whose_entries_have_arrived_needs_no_request(page):
    page.refresh_root(CACHE, "hs_a")
    page.toggle("hosts")
    page.tree.merge("hosts", [entry_of("nomad", category("nomad"))])

    assert page.toggle("hosts") == "collapse"
    assert page.toggle("hosts") == "expand"        # already loaded

def test_the_tree_goes_as_deep_as_it_is_opened(page):
    page.refresh_root(CACHE, "hs_a")
    page.toggle("hosts")
    page.tree.merge("hosts", [entry_of("nomad", category("nomad"))])
    page.toggle("hosts/nomad")
    page.tree.merge("hosts/nomad", [entry_of("sensor", dependency("sensor"))])

    assert [path for _, path in page.table_rows()] ==  \
        ["dep_one", "hosts", "hosts/nomad", "hosts/nomad/sensor"]

def test_a_nested_entry_is_indented(page):
    page.refresh_root(CACHE, "hs_a")
    page.toggle("hosts")
    page.tree.merge("hosts", [entry_of("nomad", category("nomad"))])
    labels = {path: columns[0] for columns, path in page.table_rows()}

    assert labels["hosts"] == "- hosts/"
    assert labels["hosts/nomad"] == "  + nomad/"

def test_a_category_that_has_been_asked_for_says_so(page):
    page.refresh_root(CACHE, "hs_a")
    page.toggle("hosts")

    assert page.marker(page.tree.node("hosts")) == "."

# What the page names, and which function it sends ----------------------- #

def test_a_hyperspace_names_a_path_where_a_category_names_an_entry():
    assert HyperSpaceFrame._entry_path(None, "hosts", "nomad") ==  \
        "hosts/nomad"
    assert CategoryFrame._entry_path(None, "hosts", "nomad") == "nomad"

def test_a_path_from_the_root(frame):
    assert frame._entry_path("", "hosts") == "hosts"

def test_a_category_is_created_and_persisted(frame):
    frame._create_category("hosts", "nomad", CATEGORY_PROTOCOL, WILDCARD, [])

    assert frame.proxy.calls == [("create", ("hosts/nomad",))]

def test_a_category_page_adds_a_reference_to_a_category_instead():
    """A Category cannot create one, so it adds an Entry whose protocol
    says that it refers to a Category Service"""

    frame = frame_of(CategoryFrame)
    frame._create_category("hosts", "nomad", CATEGORY_PROTOCOL, "andyg", [])

    name, arguments = frame.proxy.calls[0]
    assert name == "add"
    assert arguments[0] == "nomad"                 # an Entry name, not a path
    assert arguments[1].protocol == CATEGORY_PROTOCOL
    assert arguments[1].name == "nomad"

def test_a_category_entry_is_destroyed(frame):
    frame.page.refresh_root(CACHE, "hs_a")
    frame._remove("", frame.page.tree.node("hosts"))

    assert frame.proxy.calls == [("destroy", ("hosts",))]

def test_a_dependency_entry_is_removed(frame):
    frame.page.refresh_root(CACHE, "hs_a")
    frame._remove("", frame.page.tree.node("dep_one"))

    assert frame.proxy.calls == [("remove", ("dep_one",))]

def test_a_nested_entry_is_removed_by_its_path(frame):
    frame.page.refresh_root(CACHE, "hs_a")
    frame.page.tree.merge("hosts", [entry_of("nomad", category("nomad"))])
    frame._remove("hosts", frame.page.tree.node("hosts/nomad"))

    assert frame.proxy.calls == [("destroy", ("hosts/nomad",))]

def test_a_category_page_removes_both_kinds_the_same_way():
    """A Category has no destroy: every Entry it holds is removed"""

    frame = frame_of(CategoryFrame)
    frame.page.refresh_root(CACHE, "cat_a")
    frame._remove("", frame.page.tree.node("hosts"))
    frame._remove("", frame.page.tree.node("dep_one"))

    assert frame.proxy.calls ==  \
        [("remove", ("hosts",)), ("remove", ("dep_one",))]

def test_what_each_kind_of_entry_is(frame):
    frame.page.refresh_root(CACHE, "hs_a")

    assert frame.page.tree.node("hosts").kind == CATEGORY
    assert frame.page.tree.node("dep_one").kind == DEPENDENCY

# A cycle is still a cycle ----------------------------------------------- #

def test_a_category_that_refers_to_one_of_its_own_ancestors(page):
    page.refresh_root({"entries": {"a": category("a")}}, "hs_a")
    page.tree.merge("a", [entry_of("back", category("a"))])

    assert page.tree.node("a/back").cycle == "a"
    assert page.marker(page.tree.node("a/back")) == "^"
    assert page.toggle("a/back") == "cycle"

# The frame, on a real terminal ------------------------------------------ #

@needs_pty
def test_the_page_is_built_and_drawn(tmp_path):
    from aiko_services.main.hyperspace import PROTOCOL

    drawn = draw_frame("aiko_services.ide.tui.dashboard.hyperspace_plugin",
        "HyperSpaceFrame", CACHE, tmp_path,
        service=["aiko/host/1234/1", "hs_a", PROTOCOL, "mqtt", "andyg", []])

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    text = "\n".join(drawn["lines"])
    assert "+ hosts/" in text and "dep_one" in text
    assert "file:" in text                     # the storage, in the state
    assert "c create" in text and "k destroy" in text      # the legend

@needs_pty
@pytest.mark.parametrize("size", [(80, 24), (132, 48)],
    ids=["80x24", "132x48"])
def test_the_page_fits_a_small_terminal(size, tmp_path):
    drawn = draw_frame("aiko_services.ide.tui.dashboard.hyperspace_plugin",
        "HyperSpaceFrame", CACHE, tmp_path, size=size)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    assert drawn["size"] == list(size)

@needs_pty
def test_the_page_draws_with_an_empty_shared_state(tmp_path):
    """The state arrives after the page opens"""

    drawn = draw_frame("aiko_services.ide.tui.dashboard.hyperspace_plugin",
        "HyperSpaceFrame", {}, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")

# --------------------------------------------------------------------------- #
