#!/usr/bin/env python3
#
# Aiko Services tests: a client's view of a Category graph
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The model has no user interface, no screen and no network, so these
# tests need none of them, and a terminal page, a REPL or a web page each
# inherit what they check.
#
# The shared state and the "(list ...)" records below were measured from a
# running Category and a running HyperSpace, rather than written from the
# source, because what a client reads comes through the codec: the codec's
# None arrives as the string "None" in shared state and as "0:" on the
# wire, a Dependency is three fields of which the first is a ServiceFilter
# of six, and a filter's "*" means "any", which is not absent.
#
# To Do
# ~~~~~
# - A recursive listing, once a record carries the path of its Category

import pytest

from aiko_services.main import CATEGORY_PROTOCOL
from aiko_services.main.category_view import (
    ABSENT, CATEGORY, DEPENDENCY, KEEP, WILDCARD,
    CategoryTree, entries_of_cache, entry_of, entry_path_join,
    entry_path_parent, field_text, parse_entry_records, protocol_terse,
    protocol_type, root_entry,
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
    "lifecycle": "ready", "entries_count": "2",
    "entries": {"dep_one": dependency("dep_one"),
        "sub_cat": category("sub_cat")},
}

def record(level, name, protocol=FOO):
    """What a "(list ...)" answers, with the codec's None as "0:" """

    return [str(level), name,
        [[WILDCARD, name, protocol, WILDCARD, WILDCARD, []], None, None]]

@pytest.fixture
def tree():
    return CategoryTree("root")

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

def test_a_wildcard_is_not_absent():
    """A ServiceFilter's "*" matches any, which a person must still see"""

    assert field_text(WILDCARD) == WILDCARD

def test_the_protocol_type_is_what_a_plugin_key_matches():
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

def test_the_entry_of_the_category_a_client_is_at():
    entry = root_entry("cat_a")

    assert entry.kind == CATEGORY and entry.target == "cat_a"
    assert entry.protocol == CATEGORY_PROTOCOL

# What a Category holds, from its shared state --------------------------- #

def test_the_entries_come_from_the_shared_state_by_name():
    assert [entry.name for entry in entries_of_cache(CACHE)] ==  \
        ["dep_one", "sub_cat"]

def test_no_shared_state_at_all():
    assert entries_of_cache({}) == []
    assert entries_of_cache({"entries": "nonsense"}) == []
    assert entries_of_cache({"entries": {}}) == []

# What a "(list ...)" answers --------------------------------------------- #

def test_the_records_of_one_category():
    entries, diagnostics = parse_entry_records(
        [record(0, "nomad", CATEGORY_PROTOCOL), record(0, "sensor")])

    assert [(entry.name, entry.kind) for entry in entries] ==  \
        [("nomad", CATEGORY), ("sensor", DEPENDENCY)]
    assert diagnostics == []

def test_what_the_actor_says_went_wrong():
    entries, diagnostics = parse_entry_records(
        [["text", "Entry path not found"]])

    assert entries == [] and diagnostics == ["Entry path not found"]

def test_a_recursive_listing_keeps_only_the_first_level():
    """"(response -1 hosts)" names a nested Category without its path, so
    a record below the first level cannot be placed"""

    entries, _ = parse_entry_records([record(0, "nomad", CATEGORY_PROTOCOL),
        ["-1", "hosts"], record(1, "sensor")])

    assert [entry.name for entry in entries] == ["nomad"]

def test_records_of_nonsense():
    entries, diagnostics = parse_entry_records(
        [None, [], ["text"], ["x", "y"], ["0"], "string"])

    assert entries == []
    assert diagnostics == ["no reason given"]

# The tree ---------------------------------------------------------------- #

def test_the_root_is_the_category_a_client_is_at(tree):
    assert tree.node("").name == "root"
    assert tree.node("").expanded
    assert tree.node("").kind == CATEGORY

def test_the_tree_starts_again(tree):
    tree.merge("", entries_of_cache(CACHE))
    tree.reset("other")

    assert tree.node("dep_one") is None
    assert tree.rows() == []

def test_one_node_for_each_entry(tree):
    tree.merge("", entries_of_cache(CACHE))

    assert [node.path for node, _ in tree.rows()] == ["dep_one", "sub_cat"]
    assert [level for _, level in tree.rows()] == [0, 0]

def test_a_node_that_is_open_shows_what_it_holds(tree):
    tree.merge("", entries_of_cache(CACHE))
    tree.node("sub_cat").expanded = True
    tree.merge("sub_cat", [entry_of("leaf", dependency("leaf"))])

    assert [(node.path, level) for node, level in tree.rows()] ==  \
        [("dep_one", 0), ("sub_cat", 0), ("sub_cat/leaf", 1)]

def test_a_node_that_is_closed_hides_what_it_holds(tree):
    tree.merge("", entries_of_cache(CACHE))
    tree.merge("sub_cat", [entry_of("leaf", dependency("leaf"))])

    assert [node.path for node, _ in tree.rows()] == ["dep_one", "sub_cat"]

def test_a_dependency_never_shows_children(tree):
    """Nothing asks a Dependency for Entries, and a tree that drew them
    would be showing something that cannot be there"""

    tree.merge("", entries_of_cache(CACHE))
    tree.node("dep_one").expanded = True
    tree.merge("dep_one", [entry_of("leaf", dependency("leaf"))])

    assert [node.path for node, _ in tree.rows()] == ["dep_one", "sub_cat"]

def test_merging_keeps_what_a_child_already_knows(tree):
    tree.merge("", entries_of_cache(CACHE))
    tree.node("sub_cat").expanded = True
    tree.merge("sub_cat", [entry_of("leaf", dependency("leaf"))])
    tree.merge("", entries_of_cache(CACHE))            # the next frame

    assert tree.node("sub_cat").expanded
    assert tree.node("sub_cat/leaf") is not None

def test_merging_takes_the_fields_an_entry_now_has(tree):
    tree.merge("", [entry_of("dep", dependency("dep", owner="andyg"))])
    tree.merge("", [entry_of("dep", dependency("dep", owner="bob"))])

    assert tree.node("dep").entry.owner == "bob"

def test_an_entry_that_is_gone_takes_its_own_entries_with_it(tree):
    tree.merge("", entries_of_cache(CACHE))
    tree.merge("sub_cat", [entry_of("leaf", dependency("leaf"))])
    tree.merge("", [entry_of("dep_one", dependency("dep_one"))])

    assert tree.node("sub_cat") is None
    assert tree.node("sub_cat/leaf") is None
    assert [node.path for node, _ in tree.rows()] == ["dep_one"]

def test_an_entry_that_changes_kind_is_a_different_entry(tree):
    tree.merge("", [entry_of("x", category("x"))])
    tree.merge("x", [entry_of("leaf", dependency("leaf"))])
    tree.merge("", [entry_of("x", dependency("x"))])

    assert tree.node("x").kind == DEPENDENCY
    assert tree.node("x/leaf") is None

def test_a_node_is_forgotten_with_everything_below_it(tree):
    tree.merge("", [entry_of("a", category("a"))])
    tree.merge("a", [entry_of("b", category("b"))])
    tree.merge("a/b", [entry_of("c", dependency("c"))])
    tree.forget("a")

    assert tree.node("a") is None and tree.node("a/b/c") is None
    assert tree.node("") is not None

def test_merging_into_a_node_that_is_not_there(tree):
    assert tree.merge("absent", []) is False

def test_rows_of_a_node_that_is_not_there(tree):
    assert tree.rows("absent") == []

def test_the_ancestors_of_a_path(tree):
    tree.merge("", [entry_of("a", category("a"))])
    tree.merge("a", [entry_of("b", category("b"))])
    tree.merge("a/b", [entry_of("c", dependency("c"))])

    assert [node.name for node in tree.ancestors("a/b/c")] ==  \
        ["root", "a", "b"]
    assert [node.name for node in tree.ancestors("a")] == ["root"]

# Categories form a cyclic graph, not a tree ----------------------------- #

def test_a_category_that_refers_to_one_of_its_own_ancestors(tree):
    tree.merge("", [entry_of("a", category("a"))])
    tree.merge("a", [entry_of("back", category("a"))])

    assert tree.node("a/back").cycle == "a"      # the ancestor it repeats

def test_a_category_that_refers_back_to_the_root(tree):
    tree.merge("", [entry_of("a", category("a"))])
    tree.merge("a", [entry_of("home", category("root"))])

    assert tree.node("a/home").cycle == ""       # the root's own path

def test_a_category_that_refers_to_the_one_that_holds_it(tree):
    tree.merge("", [entry_of("a", category("a"))])
    tree.merge("a", [entry_of("b", category("b"))])
    tree.merge("a/b", [entry_of("parent", category("b"))])

    assert tree.node("a/b/parent").cycle == "a/b"

def test_the_same_category_in_two_branches_is_not_a_cycle(tree):
    """A graph that is not a tree is still shown, in full, under each
    Category that refers to it.  Only an ancestor stops the descent"""

    tree.merge("",
        [entry_of("a", category("a")), entry_of("b", category("b"))])
    tree.merge("a", [entry_of("shared", category("shared"))])
    tree.merge("b", [entry_of("shared", category("shared"))])

    assert tree.node("a/shared").cycle is None
    assert tree.node("b/shared").cycle is None

def test_a_dependency_of_an_ancestors_name_is_not_a_cycle(tree):
    """Only a Category is descended through, so only a Category closes"""

    tree.merge("", [entry_of("a", category("a"))])
    tree.merge("a", [entry_of("a", dependency("a"))])

    assert tree.node("a/a").cycle is None

def test_a_cycle_is_closed_when_it_is_found(tree):
    tree.merge("", [entry_of("a", category("a"))])
    tree.merge("a", [entry_of("back", category("a"))])
    tree.node("a/back").expanded = True             # a stale open node
    tree.merge("a", [entry_of("back", category("a"))])

    assert tree.node("a/back").expanded is False

def test_a_cycle_holds_nothing_however_hard_a_client_asks(tree):
    """The whole point: a client that merged its way around a cycle would
    never stop, so the node that closes one takes no Entries, and the rows
    stay finite even when a client opens it anyway"""

    tree.merge("", [entry_of("a", category("a"))])
    tree.node("a").expanded = True
    tree.merge("a", [entry_of("back", category("a"))])
    tree.node("a/back").expanded = True

    assert tree.merge("a/back", [entry_of("deeper", category("a"))]) is False
    assert tree.node("a/back/deeper") is None
    assert len(tree.rows()) == 2            # "a" and the cycle it closes

# --------------------------------------------------------------------------- #
