#!/usr/bin/env python3
#
# Aiko Services tests: the Category's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# asciimatics has no screen double, so CategoryPage and CategoryTree hold
# every decision and are pure, and the Frame is drawn by the shared
# pseudo-terminal fixture.  No broker, no Category, no screen for the pure
# part.
#
# The shared state and the "(list ...)" records below were measured from a
# running Category and a running HyperSpace, rather than written from the
# source, because the fields that a person sees come through the codec:
# the codec's None arrives as the string "None" in shared state and as
# "0:" on the wire, and a Dependency is three fields of which the first is
# a ServiceFilter of six.
#
# To Do
# ~~~~~
# - Key events through the pseudo-terminal, for the dialogues and the trail
# - A response that arrives while the frame is being drawn

import pytest

asciimatics = pytest.importorskip("asciimatics")

from aiko_services.main import CATEGORY_PROTOCOL                # noqa: E402
from aiko_services.ide.tui.dashboard.category_plugin import (   # noqa: E402
    ABSENT, CATEGORY, DEPENDENCY, KEEP, WILDCARD,
    CategoryFrame, CategoryPage, CategoryTree,
    entry_of, entry_path_join, entry_path_parent, field_text,
    plugins, protocol_terse, protocol_type,
)
from aiko_services.tests.unit.dashboard_screen import (         # noqa: E402
    draw_frame, pty_available,
)

FOO = "aiko/protocol/foo:0"

def dependency(name, protocol=FOO, owner="andyg", tags=("key=value",)):
    """What a Category holds for a Dependency, as the shared state has it"""

    return [[WILDCARD, name, protocol, WILDCARD, owner, list(tags)],
        "None", "None"]

def category(name):
    return [[WILDCARD, name, CATEGORY_PROTOCOL, WILDCARD, WILDCARD, []],
        "None", "None"]

# A Category with one Dependency and one Category Entry
CACHE = {
    "lifecycle": "ready", "running": "False", "entries_count": "2",
    "entries": {"dep_one": dependency("dep_one"),
        "sub_cat": category("sub_cat")},
}

# What a "(list ...)" answers, with the codec's None as "0:"
def record(level, name, protocol=FOO):
    return [str(level), name,
        [[WILDCARD, name, protocol, WILDCARD, WILDCARD, []], None, None]]

RECORDS = [record(0, "nomad", CATEGORY_PROTOCOL), record(0, "sensor")]

@pytest.fixture
def page():
    return CategoryPage()

needs_pty = pytest.mark.skipif(
    not pty_available(), reason="needs a POSIX pseudo-terminal")

# The plug-in registration ------------------------------------------------ #

def test_the_plugin_key_is_the_protocol_type():
    assert list(plugins) == ["category"]

def test_the_default_plugin_module_registers_it():
    from aiko_services.ide.tui.dashboard.plugins import plugins as default

    assert sorted(default) == ["category", "hyperspace", "process_manager",
        "recorder", "registrar"]

def test_the_dashboard_derives_that_key_from_the_protocol():
    from aiko_services.ide.tui.dashboard.dashboard import FrameCommon

    assert FrameCommon._short_name(
        None, CATEGORY_PROTOCOL).split(":")[0] == "category"

# The keys ---------------------------------------------------------------- #

def test_each_key_asks_for_one_thing(page):
    assert page.action(ord("a")) == ("add",)
    assert page.action(ord("d")) == ("remove",)
    assert page.action(ord("u")) == ("update",)
    assert page.action(ord("r")) == ("refresh",)
    assert page.action(ord("g")) == ("follow",)
    assert page.action(ord("G")) == ("back",)
    assert page.action(ord("L")) == ("log_level",)
    assert page.action(ord("H")) == ("help",)

def test_the_dashboards_own_keys_are_left_alone(page):
    for reserved in "DxXS?":
        assert page.action(ord(reserved)) is None

def test_a_key_that_is_not_a_character_is_ignored(page):
    for key_code in (-1, -204, 0x110000):
        assert page.action(key_code) is None

def test_the_help_names_every_key_the_page_takes(page):
    text = page.help_text()

    for key in page.KEYS:
        assert key in text
    for word in ("add", "update", "remove", "refresh", "follow"):
        assert word in text

# One field, as a person reads it ---------------------------------------- #

def test_the_codecs_none_is_a_dash_in_both_of_its_forms():
    assert field_text(None) == ABSENT          # parsed from the wire
    assert field_text("None") == ABSENT        # the shared state's form
    assert field_text(KEEP) == ABSENT
    assert field_text("") == ABSENT

def test_a_field_that_holds_something():
    assert field_text("file:") == "file:"
    assert field_text(["a=b", "c=d"]) == "a=b c=d"
    assert field_text([]) == ABSENT

def test_the_protocol_type_is_what_the_plugin_key_matches():
    assert protocol_type(CATEGORY_PROTOCOL) == CATEGORY
    assert protocol_type(FOO) == "foo"
    assert protocol_type(WILDCARD) == ""
    assert protocol_type(ABSENT) == ""
    assert protocol_type("") == ""

def test_the_protocol_is_shown_as_the_command_line_shows_it():
    assert protocol_terse(CATEGORY_PROTOCOL) == "category:0"
    assert protocol_terse(FOO) == "foo:0"
    assert protocol_terse(ABSENT) == ABSENT

def test_a_path_is_joined_and_taken_apart():
    assert entry_path_join("", "hosts") == "hosts"
    assert entry_path_join("hosts", "nomad") == "hosts/nomad"
    assert entry_path_parent("hosts/nomad") == "hosts"
    assert entry_path_parent("hosts") == ""

# One Entry --------------------------------------------------------------- #

def test_an_entry_carries_every_field_of_its_service_filter():
    entry = entry_of("dep_one", dependency("dep_one"))

    assert entry.name == "dep_one"
    assert entry.kind == DEPENDENCY
    assert entry.target == "dep_one"
    assert entry.protocol == FOO
    assert entry.transport == WILDCARD     # a filter matches any
    assert entry.owner == "andyg"
    assert entry.tags == ["key=value"]
    assert entry.lcm_url == ABSENT and entry.storage_url == ABSENT

def test_the_protocol_says_whether_an_entry_is_a_category():
    assert entry_of("sub_cat", category("sub_cat")).kind == CATEGORY
    assert entry_of("dep_one", dependency("dep_one")).kind == DEPENDENCY

def test_the_target_is_what_the_entry_refers_to_not_what_holds_it():
    """A Category Entry may name a Service of another name"""

    entry = entry_of("devices", category("hosts"))

    assert entry.name == "devices" and entry.target == "hosts"

def test_an_entry_whose_name_is_a_wildcard_refers_to_itself():
    assert entry_of("dep", dependency(WILDCARD)).target == "dep"

def test_an_entry_of_nonsense():
    """A field the Actor has never sent must not raise"""

    for fields in (None, [], "text", [[]], [[WILDCARD]], [None, None, None]):
        entry = entry_of("name", fields)
        assert entry.name == "name" and entry.kind == DEPENDENCY

# The Entries of the selected Category ----------------------------------- #

def test_the_entries_come_from_the_shared_state_by_name(page):
    assert [entry.name for entry in page.entries_from_cache(CACHE)] ==  \
        ["dep_one", "sub_cat"]

def test_no_shared_state_at_all(page):
    assert page.entries_from_cache({}) == []
    assert page.entries_from_cache({"entries": "nonsense"}) == []
    assert page.table_rows() == []
    assert page.state_rows({}) == []

# What a "(list ...)" answers --------------------------------------------- #

def test_the_records_of_one_category(page):
    entries, diagnostics = page.parse_records(RECORDS)

    assert [(entry.name, entry.kind) for entry in entries] ==  \
        [("nomad", CATEGORY), ("sensor", DEPENDENCY)]
    assert diagnostics == []

def test_what_the_actor_says_went_wrong(page):
    entries, diagnostics = page.parse_records(
        [["text", "Entry path not found"]])

    assert entries == [] and diagnostics == ["Entry path not found"]

def test_a_recursive_listing_keeps_only_the_first_level(page):
    """"(response -1 hosts)" names a nested Category without its path, so
    a record below the first level cannot be placed"""

    records = [record(0, "nomad", CATEGORY_PROTOCOL),
        ["-1", "hosts"], record(1, "sensor")]
    entries, _ = page.parse_records(records)

    assert [entry.name for entry in entries] == ["nomad"]

def test_records_of_nonsense(page):
    records = [None, [], ["text"], ["x", "y"], ["0"], "string"]
    entries, diagnostics = page.parse_records(records)

    assert entries == []
    assert diagnostics == ["no reason given"]

# The tree ---------------------------------------------------------------- #

def test_the_root_is_the_selected_service(page):
    page.refresh_root(CACHE, "cat_a")

    assert page.tree.node("").name == "cat_a"
    assert page.tree.node("").expanded
    assert page.breadcrumb("") == "cat_a/"
    assert page.breadcrumb("sub_cat") == "cat_a/sub_cat"

def test_another_service_starts_the_tree_again(page):
    page.refresh_root(CACHE, "cat_a")
    page.tree.node("sub_cat").expanded = True
    page.refresh_root({"entries": {}}, "cat_b")

    assert page.tree.node("sub_cat") is None
    assert page.table_rows() == []

def test_the_table_shows_one_row_for_each_entry(page):
    page.refresh_root(CACHE, "cat_a")

    assert page.table_rows() == [
        (("  dep_one", DEPENDENCY, "andyg", "foo:0"), "dep_one"),
        ((f"> sub_cat/", CATEGORY, WILDCARD, "category:0"), "sub_cat")]

def test_a_category_page_marks_a_category_as_one_to_follow(page):
    """A Category knows only its own Entries, so Enter follows a Category
    Entry to its own Service instead of opening it here"""

    page.refresh_root(CACHE, "cat_a")

    assert page.marker(page.tree.node("sub_cat")) == ">"
    assert page.toggle("sub_cat") == "follow"
    assert page.toggle("dep_one") == "detail"
    assert page.toggle("absent") is None

def test_merging_keeps_what_a_child_already_knows(page):
    page.refresh_root(CACHE, "cat_a")
    page.tree.node("sub_cat").expanded = True
    page.tree.merge("sub_cat", [entry_of("leaf", dependency("leaf"))])
    page.refresh_root(CACHE, "cat_a")               # the next frame

    assert page.tree.node("sub_cat").expanded
    assert page.tree.node("sub_cat/leaf") is not None

def test_an_entry_that_is_gone_takes_its_own_entries_with_it(page):
    page.refresh_root(CACHE, "cat_a")
    page.tree.merge("sub_cat", [entry_of("leaf", dependency("leaf"))])
    page.refresh_root({"entries": {"dep_one": dependency("dep_one")}}, "cat_a")

    assert page.tree.node("sub_cat") is None
    assert page.tree.node("sub_cat/leaf") is None
    assert [path for _, path in page.table_rows()] == ["dep_one"]

def test_an_entry_that_changes_kind_is_a_different_entry(page):
    page.refresh_root({"entries": {"x": category("x")}}, "cat_a")
    page.tree.merge("x", [entry_of("leaf", dependency("leaf"))])
    page.refresh_root({"entries": {"x": dependency("x")}}, "cat_a")

    assert page.tree.node("x").kind == DEPENDENCY
    assert page.tree.node("x/leaf") is None

def test_merging_into_a_node_that_is_not_there(page):
    assert page.tree.merge("absent", []) is False

def test_the_ancestors_of_a_path(page):
    page.refresh_root({"entries": {"a": category("a")}}, "root")
    page.tree.merge("a", [entry_of("b", category("b"))])
    page.tree.merge("a/b", [entry_of("c", dependency("c"))])

    assert [node.name for node in page.tree.ancestors("a/b/c")] ==  \
        ["root", "a", "b"]

# Categories form a cyclic graph, not a tree ----------------------------- #

def test_a_category_that_refers_to_one_of_its_own_ancestors(page):
    page.refresh_root({"entries": {"a": category("a")}}, "root")
    page.tree.merge("a", [entry_of("back", category("a"))])

    node = page.tree.node("a/back")
    assert node.cycle == "a"                   # the ancestor it repeats
    assert page.marker(node) == "^"
    assert page.row_type(node) == "category (cycle)"
    assert page.toggle("a/back") == "cycle"    # and it does not open

def test_a_category_that_refers_back_to_the_root(page):
    page.refresh_root({"entries": {"a": category("a")}}, "root")
    page.tree.merge("a", [entry_of("home", category("root"))])

    assert page.tree.node("a/home").cycle == ""      # the root's own path

def test_the_same_category_in_two_branches_is_not_a_cycle(page):
    """A graph that is not a tree is still shown, in full, under each
    Category that refers to it.  Only an ancestor stops the descent"""

    page.refresh_root(
        {"entries": {"a": category("a"), "b": category("b")}}, "root")
    page.tree.merge("a", [entry_of("shared", category("shared"))])
    page.tree.merge("b", [entry_of("shared", category("shared"))])

    assert page.tree.node("a/shared").cycle is None
    assert page.tree.node("b/shared").cycle is None

def test_a_cycle_is_closed_when_it_is_found(page):
    page.refresh_root({"entries": {"a": category("a")}}, "root")
    page.tree.node("a").expanded = True
    page.tree.merge("a", [entry_of("back", category("a"))])
    page.tree.node("a/back").expanded = True            # a stale open node
    page.tree.merge("a", [entry_of("back", category("a"))])

    assert page.tree.node("a/back").expanded is False

# Where the Category functions apply ------------------------------------- #

def test_the_cursor_is_in_the_category_that_holds_the_entry(page):
    page.refresh_root(CACHE, "cat_a")

    assert page.current_category("dep_one") == ""
    assert page.current_category("") == ""

def test_an_open_category_is_the_one_the_cursor_is_in(page):
    page.refresh_root(CACHE, "cat_a")
    page.tree.node("sub_cat").expanded = True

    assert page.current_category("sub_cat") == "sub_cat"

def test_a_closed_category_is_not_the_one_the_cursor_is_in(page):
    page.refresh_root(CACHE, "cat_a")

    assert page.current_category("sub_cat") == ""

def test_a_cycle_is_never_the_one_the_cursor_is_in(page):
    page.refresh_root({"entries": {"a": category("a")}}, "root")
    page.tree.merge("a", [entry_of("back", category("a"))])
    page.tree.node("a/back").expanded = True

    assert page.current_category("a/back") == "a"

# The Entry syntax, which one text field carries ------------------------- #

def test_a_name_that_ends_in_a_delimiter_asks_for_a_category(page):
    name, kind, protocol, owner, tags = page.parse_add(["devices/"])

    assert (name, kind) == ("devices", CATEGORY)
    assert protocol == CATEGORY_PROTOCOL       # a Category Entry's protocol
    assert (owner, tags) == (WILDCARD, [])

def test_a_name_on_its_own_asks_for_a_dependency(page):
    assert page.parse_add(["sensor"]) ==  \
        ("sensor", DEPENDENCY, WILDCARD, WILDCARD, [])

def test_every_field_of_a_new_entry(page):
    assert page.parse_add(["sensor", FOO, "andyg", "a=b", "c=d"]) ==  \
        ("sensor", DEPENDENCY, FOO, "andyg", ["a=b", "c=d"])

def test_a_field_that_is_a_dash_is_left_unset(page):
    assert page.parse_add(["sensor", ABSENT, "andyg"]) ==  \
        ("sensor", DEPENDENCY, WILDCARD, "andyg", [])

def test_a_word_that_is_not_a_tag_is_not_one(page):
    assert page.parse_add(["sensor", FOO, "andyg", "nonsense"])[4] == []

def test_a_category_may_be_given_a_protocol_of_its_own(page):
    assert page.parse_add(["devices/", FOO])[2] == FOO

def test_an_entry_with_no_name_at_all(page):
    assert page.parse_add([]) is None
    assert page.parse_add(["/"]) is None
    assert page.parse_add([""]) is None

def test_an_update_keeps_the_fields_it_does_not_name(page):
    assert page.parse_update([]) == (KEEP, KEEP, [])
    assert page.parse_update([ABSENT, "bob"]) == (KEEP, "bob", [])
    assert page.parse_update([FOO]) == (FOO, KEEP, [])

def test_the_update_dialogue_starts_with_the_entry_as_it_is(page):
    entry = entry_of("dep_one", dependency("dep_one"))

    assert page.update_words(entry) == f"{FOO} andyg key=value"

# What the page says ------------------------------------------------------ #

def test_the_title_says_how_much_the_category_holds(page):
    page.refresh_root(CACHE, "cat_a")

    assert page.title(CACHE) == "entries: 2   shown: 2"

def test_the_title_of_a_category_that_holds_nothing(page):
    assert page.title({}) == "entries: 0   shown: 0"

def test_the_state_table_names_what_the_category_is(page):
    assert [name for name, _ in page.state_rows(CACHE)] ==  \
        ["entries_count", "lifecycle", "running"]

def test_the_state_table_shows_the_metrics_too(page):
    rows = dict(page.state_rows({"metrics": {"created": 3, "running": 1}}))

    assert rows == {"metrics.created": "3", "metrics.running": "1"}

def test_every_field_of_one_entry(page):
    page.refresh_root(CACHE, "cat_a")
    text = "\n".join(page.detail_lines("dep_one"))

    assert "cat_a/dep_one" in text
    assert FOO in text                        # the protocol, in full
    assert "andyg" in text and "key=value" in text

def test_the_detail_of_a_cycle_says_what_it_refers_to(page):
    page.refresh_root({"entries": {"a": category("a")}}, "root")
    page.tree.merge("a", [entry_of("back", category("a"))])
    text = "\n".join(page.detail_lines("a/back"))

    assert "open above it" in text

def test_the_detail_of_an_entry_that_is_not_there(page):
    assert page.detail_lines("absent") == []

# The extension point that the HyperSpace page uses ---------------------- #

def test_a_category_names_an_entry_and_not_a_path():
    """A Category holds only its own Entries, so add, remove and update
    name an Entry.  The HyperSpace page overrides this"""

    assert CategoryFrame._entry_path(None, "hosts", "nomad") == "nomad"

def test_the_root_is_never_a_selected_entry():
    """The root has no row of its own, so add, update and remove must not
    find it where there is no selection"""

    frame = CategoryFrame.__new__(CategoryFrame)
    frame.page = CategoryPage()
    frame.page.refresh_root(CACHE, "cat_a")
    frame._selected_path = lambda: ""

    assert frame._selected_node() is None

def test_a_selected_entry_is_found_by_its_path():
    frame = CategoryFrame.__new__(CategoryFrame)
    frame.page = CategoryPage()
    frame.page.refresh_root(CACHE, "cat_a")
    frame._selected_path = lambda: "dep_one"

    assert frame._selected_node().name == "dep_one"

# The frame, on a real terminal ------------------------------------------ #

@needs_pty
def test_the_page_is_built_and_drawn(tmp_path):
    drawn = draw_frame("aiko_services.ide.tui.dashboard.category_plugin",
        "CategoryFrame", CACHE, tmp_path,
        service=["aiko/host/1234/1", "cat_a", CATEGORY_PROTOCOL,
            "mqtt", "andyg", []])

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    text = "\n".join(drawn["lines"])
    assert "dep_one" in text and "sub_cat/" in text
    assert "entries: 2" in text
    assert "cat_a/" in text                    # the current Category
    assert "a add" in text                     # the legend

@needs_pty
@pytest.mark.parametrize("size", [(80, 24), (132, 48)],
    ids=["80x24", "132x48"])
def test_the_page_fits_a_small_terminal(size, tmp_path):
    drawn = draw_frame("aiko_services.ide.tui.dashboard.category_plugin",
        "CategoryFrame", CACHE, tmp_path, size=size)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    assert drawn["size"] == list(size)

@needs_pty
def test_the_page_draws_with_an_empty_shared_state(tmp_path):
    """The state arrives after the page opens"""

    drawn = draw_frame("aiko_services.ide.tui.dashboard.category_plugin",
        "CategoryFrame", {}, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")

# --------------------------------------------------------------------------- #
