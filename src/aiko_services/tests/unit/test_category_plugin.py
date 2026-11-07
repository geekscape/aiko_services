#!/usr/bin/env python3
#
# Aiko Services tests: the Category's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# asciimatics has no screen double, so CategoryPage holds every decision
# and is pure, and the Frame is drawn by the shared pseudo-terminal
# fixture.  No broker, no Category, no screen for the pure part.
#
# The model underneath — an Entry, the tree, and the cycle check — is
# "main/category_view.py", and "test_category_view.py" covers it.  These
# tests are what a terminal adds: which key does what, what each row
# looks like, where a function applies, and the syntax of one text field.
#
# The shared state below was measured from a running Category, because
# what a person sees comes through the codec.
#
# To Do
# ~~~~~
# - Key events through the pseudo-terminal, for the dialogues and the trail
# - A response that arrives while the frame is being drawn

import pytest

asciimatics = pytest.importorskip("asciimatics")

from aiko_services.ide.tui.dashboard.category_plugin import (  # noqa: E402
    CategoryFrame,
    CategoryPage,
    plugins,
)
from aiko_services.main import CATEGORY_PROTOCOL  # noqa: E402
from aiko_services.main.category_view import (  # noqa: E402
    ABSENT,
    CATEGORY,
    DEPENDENCY,
    KEEP,
    PATH_DELIMITER,
    WILDCARD,
    entry_of,
)
from aiko_services.tests.unit.dashboard_screen import (  # noqa: E402
    draw_frame,
    pty_available,
)

FOO = "aiko/protocol/foo:0"


def dependency(name, protocol=FOO, owner="andyg", tags=("key=value",)):
    """What a Category holds for a Dependency, as the shared state has it"""

    return [[WILDCARD, name, protocol, WILDCARD, owner, list(tags)], "None", "None"]


def category(name):
    return [[WILDCARD, name, CATEGORY_PROTOCOL, WILDCARD, WILDCARD, []], "None", "None"]


# A Category with one Dependency and one Category Entry
CACHE = {
    "lifecycle": "ready",
    "running": "False",
    "entries_count": "2",
    "entries": {"dep_one": dependency("dep_one"), "sub_cat": category("sub_cat")},
}


@pytest.fixture
def page():
    return CategoryPage()


needs_pty = pytest.mark.skipif(not pty_available(), reason="needs a POSIX pseudo-terminal")

# The plug-in registration ------------------------------------------------ #


def test_the_plugin_key_is_the_protocol_type():
    assert list(plugins) == ["category"]


def test_the_default_plugin_module_registers_it():
    from aiko_services.ide.tui.dashboard.plugins import plugins as default

    assert sorted(default) == ["category", "hyperspace", "process_manager", "recorder", "registrar"]


def test_the_dashboard_derives_that_key_from_the_protocol():
    from aiko_services.ide.tui.dashboard.dashboard import FrameCommon

    assert FrameCommon._short_name(None, CATEGORY_PROTOCOL).split(":")[0] == "category"


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
        ((f"> sub_cat/", CATEGORY, WILDCARD, "category:0"), "sub_cat"),
    ]


def test_a_category_page_marks_a_category_as_one_to_follow(page):
    """A Category knows only its own Entries, so Enter follows a Category
    Entry to its own Service instead of opening it here"""

    page.refresh_root(CACHE, "cat_a")

    assert page.marker(page.tree.node("sub_cat")) == ">"
    assert page.toggle("sub_cat") == "follow"
    assert page.toggle("dep_one") == "detail"
    assert page.toggle("absent") is None


# What a person sees of a cycle ------------------------------------------ #


def test_a_cycle_is_shown_and_does_not_open(page):
    """ "test_category_view.py" holds how a cycle is found.  This is what
    a person sees of one"""

    page.refresh_root({"entries": {"a": category("a")}}, "root")
    page.tree.merge("a", [entry_of("back", category("a"))])

    node = page.tree.node("a/back")
    assert page.marker(node) == "^"
    assert page.row_type(node) == "category (cycle)"
    assert page.toggle("a/back") == "cycle"


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


# What a form says about an Entry ---------------------------------------- #


def test_a_form_names_a_dependency(page):
    assert page.form_entry({"name": "sensor", "kind": DEPENDENCY}) == ("sensor", DEPENDENCY, WILDCARD, WILDCARD, [])


def test_a_form_names_a_category(page):
    """A Category Entry needs the Category protocol, or nothing would
    know that it is one"""

    name, kind, protocol, owner, tags = page.form_entry({"name": "devices", "kind": CATEGORY})

    assert (name, kind) == ("devices", CATEGORY)
    assert protocol == CATEGORY_PROTOCOL


def test_a_category_may_be_given_a_protocol_of_its_own(page):
    assert page.form_entry({"name": "devices", "kind": CATEGORY, "protocol": FOO})[2] == FOO


def test_every_field_of_a_new_entry(page):
    assert page.form_entry(
        {"name": "sensor", "kind": DEPENDENCY, "protocol": FOO, "owner": "andyg", "tags": "a=b c=d"}
    ) == ("sensor", DEPENDENCY, FOO, "andyg", ["a=b", "c=d"])


def test_a_field_left_empty_matches_any(page):
    assert page.form_entry({"name": "sensor", "protocol": "  ", "owner": ""})[2:4] == (WILDCARD, WILDCARD)


def test_a_word_that_is_not_a_tag_is_not_one(page):
    assert page.form_entry({"name": "sensor", "tags": "a=b nonsense c=d"})[4] == ["a=b", "c=d"]


def test_a_form_that_names_nothing(page):
    assert page.form_entry({}) is None
    assert page.form_entry({"name": "   "}) is None
    assert page.form_entry({"name": PATH_DELIMITER}) is None


def test_a_trailing_delimiter_is_not_part_of_a_name(page):
    """A person who types a Category the way a directory is written"""

    assert page.form_entry({"name": "devices/"})[0] == "devices"


def test_an_update_keeps_the_fields_left_empty(page):
    assert page.form_update({}) == (KEEP, KEEP, [])
    assert page.form_update({"owner": "bob"}) == (KEEP, "bob", [])
    assert page.form_update({"protocol": FOO}) == (FOO, KEEP, [])


def test_an_update_form_starts_with_the_entry_as_it_is(page):
    """A field the Actor never set starts empty, rather than showing the
    dash that the table shows for it"""

    assert page.field_value(FOO) == FOO
    assert page.field_value(ABSENT) == ""
    assert page.field_value(WILDCARD) == ""


# Filtering and sorting --------------------------------------------------- #


def test_every_entry_is_shown_until_a_filter_says_otherwise(page):
    page.refresh_root(CACHE, "cat_a")

    assert page.keep() is None
    assert [path for _, path in page.table_rows()] == ["dep_one", "sub_cat"]


def test_a_filter_matches_any_field_a_person_can_see(page):
    page.refresh_root(CACHE, "cat_a")

    for pattern, shown in (
        ("dep", ["dep_one"]),  # the name
        ("DEP", ["dep_one"]),  # without regard to case
        ("category", ["sub_cat"]),  # the type, and the protocol
        ("andyg", ["dep_one"]),  # the owner
        ("key=value", ["dep_one"]),  # a tag
        ("nothing", []),
    ):
        page.pattern = pattern
        assert [path for _, path in page.table_rows()] == shown, pattern


def test_a_filter_keeps_the_way_to_what_it_found(page):
    """A Category that is open and holds a match is shown, so that the
    Entry a person searched for can be reached"""

    page.refresh_root(CACHE, "cat_a")
    page.tree.node("sub_cat").expanded = True
    page.tree.merge("sub_cat", [entry_of("camera", dependency("camera"))])
    page.pattern = "camera"

    assert [path for _, path in page.table_rows()] == ["sub_cat", "sub_cat/camera"]


def test_the_entries_are_ordered_by_name_to_begin_with(page):
    assert page.sort_field == "name"
    assert page.sort_reverse is False
    assert page.sort_direction() == "ascending"


def test_the_entries_are_ordered_on_any_field(page):
    page.refresh_root(CACHE, "cat_a")

    for field, order in (
        ("name", ["dep_one", "sub_cat"]),
        ("type", ["sub_cat", "dep_one"]),  # category, dependency
        ("owner", ["sub_cat", "dep_one"]),  # "*" before "andyg"
        ("protocol", ["sub_cat", "dep_one"]),
    ):  # category:0, foo:0
        page.sort_field = field
        assert [path for _, path in page.table_rows()] == order, field


def test_the_order_is_turned_around(page):
    page.refresh_root(CACHE, "cat_a")
    page.sort_reverse = True

    assert [path for _, path in page.table_rows()] == ["sub_cat", "dep_one"]
    assert page.sort_direction() == "descending"


def test_the_order_a_category_sent_them_in(page):
    page.refresh_root(CACHE, "cat_a")
    page.sort_field = "arrived"

    assert page.sort_key() is None
    assert [path for _, path in page.table_rows()] == ["dep_one", "sub_cat"]


def test_a_sort_field_that_is_not_one(page):
    page.refresh_root(CACHE, "cat_a")
    page.sort_field = "nonsense"

    assert page.sort_key() is None  # the order they arrived in
    assert len(page.table_rows()) == 2


# What the page says ------------------------------------------------------ #


def test_the_title_says_how_much_the_category_holds(page):
    page.refresh_root(CACHE, "cat_a")

    assert page.title(CACHE) == "entries: 2   shown: 2   sort: name ^"


def test_the_title_of_a_category_that_holds_nothing(page):
    assert page.title({}) == "entries: 0   shown: 0   sort: name ^"


def test_the_title_says_what_is_hidden_and_how_it_is_ordered(page):
    page.refresh_root(CACHE, "cat_a")
    page.pattern = "dep"
    page.sort_field = "owner"
    page.sort_reverse = True

    assert page.title(CACHE) == 'entries: 2   shown: 1   sort: owner v   filter: "dep"'


def test_the_state_table_names_what_the_category_is(page):
    assert [name for name, _ in page.state_rows(CACHE)] == ["entries_count", "lifecycle", "running"]


def test_the_state_table_shows_the_metrics_too(page):
    rows = dict(page.state_rows({"metrics": {"created": 3, "running": 1}}))

    assert rows == {"metrics.created": "3", "metrics.running": "1"}


def test_every_field_of_one_entry(page):
    page.refresh_root(CACHE, "cat_a")
    text = "\n".join(page.detail_lines("dep_one"))

    assert "cat_a/dep_one" in text
    assert FOO in text  # the protocol, in full
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
    drawn = draw_frame(
        "aiko_services.ide.tui.dashboard.category_plugin",
        "CategoryFrame",
        CACHE,
        tmp_path,
        service=["aiko/host/1234/1", "cat_a", CATEGORY_PROTOCOL, "mqtt", "andyg", []],
    )

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    text = "\n".join(drawn["lines"])
    assert "dep_one" in text and "sub_cat/" in text
    assert "entries: 2" in text
    assert "cat_a/" in text  # the current Category
    assert "a add" in text  # the legend


@needs_pty
@pytest.mark.parametrize("size", [(80, 24), (132, 48)], ids=["80x24", "132x48"])
def test_the_page_fits_a_small_terminal(size, tmp_path):
    drawn = draw_frame("aiko_services.ide.tui.dashboard.category_plugin", "CategoryFrame", CACHE, tmp_path, size=size)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    assert drawn["size"] == list(size)


@needs_pty
def test_the_page_draws_with_an_empty_shared_state(tmp_path):
    """The state arrives after the page opens"""

    drawn = draw_frame("aiko_services.ide.tui.dashboard.category_plugin", "CategoryFrame", {}, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")


# --------------------------------------------------------------------------- #
