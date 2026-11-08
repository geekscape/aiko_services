#!/usr/bin/env python3
#
# Aiko Services: CategoryView, a client's view of a Category graph
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# What a client needs to show a Category and the Categories below it: an
# Entry as a person reads it, and a tree of the Entries discovered so far.
# No user interface, no screen and no network, so a terminal page, a REPL,
# a web page and a test each use the same model.
#
# A client sees a Category's Entries two ways, and this module takes both:
#
# - "entries_of_cache()" reads the "entries" item of the shared state,
#   which an ECConsumer keeps current for the one Category it consumes.
# - "parse_entry_records()" reads the records of a "(list ...)", which a
#   Category answers for itself and a HyperSpace answers for any Entry
#   path.
#
# Both arrive through the codec, so a field needs reading rather than
# using: the codec's None is the string "None" in shared state and "0:" on
# the wire, a Dependency is three fields of which the first is a
# ServiceFilter of six, and a ServiceFilter's "*" means "any", which is
# not the same as absent.
#
# Categories form a cyclic graph, not a tree, so "CategoryTree.merge()"
# marks a node whose target repeats one of its own ancestors.  A client
# shows such a node and does not descend through it.  The same target in
# two branches is not a cycle: a graph that is not a tree is still shown
# in full under each Category that refers to it.
#
# Usage
# ~~~~~
#   tree = CategoryTree("category_name")      # the Category a client is at
#   tree.merge("", entries_of_cache(cache))   # its own Entries
#   tree.merge("hosts", entries)              # the Entries of one below it
#   for node, level in tree.rows():           # what to show, and how deep
#       ...
#
# To Do
# ~~~~~
# - A recursive "(list ...)" names a nested Category without its path, so
#   a record below the first level cannot be placed.  Carry the path, and
#   "parse_entry_records()" loads a whole subtree from one answer
# - Consider "__repr__()" and "__str__()" on Category and Dependency, and
#   read those here, so that one place decides how a field reads
# - A Dependency's own Service, as "target" gives for a Category

from collections import namedtuple

from aiko_services.main import CATEGORY_PROTOCOL

__all__ = [
    "ABSENT",
    "CATEGORY",
    "DEPENDENCY",
    "KEEP",
    "PATH_DELIMITER",
    "WILDCARD",
    "CategoryNode",
    "CategoryTree",
    "Entry",
    "entries_of_cache",
    "entry_of",
    "entry_path_join",
    "entry_path_parent",
    "field_text",
    "parse_entry_records",
    "protocol_terse",
    "protocol_type",
    "root_entry",
]

# --------------------------------------------------------------------------- #

PATH_DELIMITER = "/"
CATEGORY = "category"
DEPENDENCY = "dependency"

ABSENT = "-"  # a field that the Actor sent as the codec's None
WILDCARD = "*"
KEEP = "0:"  # what an update sends for a field to leave alone

# Every field of one Entry, as a person reads it.  "target" is what the
# Entry refers to: the name in its ServiceFilter, or its own name
Entry = namedtuple("Entry", "name kind target protocol transport owner tags lcm_url storage_url")


def entry_path_join(path, name):
    """One Entry path from a Category path and an Entry name"""

    return f"{path}{PATH_DELIMITER}{name}" if path else name


def entry_path_parent(path):
    """The Category that holds the Entry at path, "" being the root"""

    return path.rpartition(PATH_DELIMITER)[0]


def protocol_type(protocol):
    """ "category" from ".../protocol/category:0", and "" from nothing"""

    if not protocol or protocol in (WILDCARD, ABSENT):
        return ""
    return protocol.rpartition(PATH_DELIMITER)[2].split(":")[0]


def protocol_terse(protocol):
    """ "category:0" from ".../protocol/category:0", which is how the
    command line and the Dashboard's own Service list show a protocol"""

    return protocol.rpartition(PATH_DELIMITER)[2] if protocol else protocol


def field_text(value):
    """A field as a person reads it.  The shared state carries the codec's
    None as the string "None", and a list as a list"""

    if value is None:
        return ABSENT
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value) or ABSENT
    value = str(value)
    return ABSENT if value in ("None", KEEP, "") else value


def entry_of(name, fields):
    """One Entry from the fields that a Category holds for it ...

    ((topic_paths name protocol transport owner (tags)) lcm storage)
    """

    fields = fields if isinstance(fields, (list, tuple)) else []
    service_filter = fields[0] if fields else None
    if not isinstance(service_filter, (list, tuple)):
        service_filter = []

    def filter_field(index):
        return service_filter[index] if index < len(service_filter) else None

    def field(index):
        return fields[index] if index < len(fields) else None

    tags = filter_field(5)
    tags = [str(tag) for tag in tags] if isinstance(tags, (list, tuple)) else []
    protocol = field_text(filter_field(2))
    filter_name = field_text(filter_field(1))
    target = name if filter_name in (ABSENT, WILDCARD) else filter_name

    return Entry(
        name,
        CATEGORY if protocol_type(protocol) == CATEGORY else DEPENDENCY,
        target,
        protocol,
        field_text(filter_field(3)),
        field_text(filter_field(4)),
        tags,
        field_text(field(1)),
        field_text(field(2)),
    )


def root_entry(name):
    """The Entry of the Category that a client is at"""

    return Entry(name, CATEGORY, name, CATEGORY_PROTOCOL, ABSENT, ABSENT, [], ABSENT, ABSENT)


# --------------------------------------------------------------------------- #


class CategoryNode:
    """One Entry, and what the viewer knows about it"""

    def __init__(self, path, entry):
        self.path = path
        self.entry = entry
        self.children = []  # Entry names, in the order they are shown
        self.expanded = False
        self.loaded = False  # its children have arrived
        self.cycle = None  # the path of the ancestor that it repeats

    @property
    def name(self):
        return self.entry.name

    @property
    def kind(self):
        return self.entry.kind


class CategoryTree:
    """Every node discovered so far, by Entry path.  The root is "" """

    def __init__(self, name=""):
        self.reset(name)

    def reset(self, name=""):
        root = CategoryNode("", root_entry(name))
        root.expanded = True
        self.nodes = {"": root}

    def node(self, path):
        return self.nodes.get(path)

    def ancestors(self, path):
        """Each node from the root down to the Category that holds path"""

        names = [name for name in path.split(PATH_DELIMITER) if name]
        chain, walk = [self.nodes[""]], ""
        for name in names[:-1]:
            walk = entry_path_join(walk, name)
            node = self.nodes.get(walk)
            if node is None:
                break
            chain.append(node)
        return chain

    def merge(self, path, entries):
        """Attach entries as the children of path, keeping what a child
        already knows: whether it is open, and what it holds.

        Returns False when path is not a node of this tree, and when it
        is a Category that closes a cycle: a client that merged its way
        around one would never stop, so a node that repeats an ancestor
        holds nothing
        """

        parent = self.nodes.get(path)
        if parent is None or parent.cycle is not None:
            return False

        targets = {node.entry.target: node.path for node in self.ancestors(path)}
        targets.setdefault(parent.entry.target, parent.path)

        names = []
        for entry in entries:
            child_path = entry_path_join(path, entry.name)
            node = self.nodes.get(child_path)
            if node is None or node.kind != entry.kind:
                self.forget(child_path)
                node = CategoryNode(child_path, entry)
                self.nodes[child_path] = node
            else:
                node.entry = entry
            node.cycle = None
            if entry.kind == CATEGORY and entry.target in targets:
                node.cycle = targets[entry.target]
                node.expanded = False
            names.append(entry.name)

        for name in parent.children:
            if name not in names:
                self.forget(entry_path_join(path, name))
        parent.children = names
        parent.loaded = True
        return True

    def forget(self, path):
        """Drop a node and everything below it"""

        prefix = path + PATH_DELIMITER
        for key in [key for key in self.nodes if key == path or key.startswith(prefix)]:
            del self.nodes[key]

    def children(self, path):
        """Each node that the Category at path holds, in the order it was
        merged, and only those still there"""

        node = self.nodes.get(path)
        if node is None:
            return []
        children = []
        for name in node.children:
            child = self.nodes.get(entry_path_join(path, name))
            if child is not None:  # merged away while being drawn
                children.append(child)
        return children

    def rows(self, path="", level=0, keep=None, sort_key=None, reverse=False):
        """[(node, level)] for each row a client shows, from path down
        through every node that is open.  The root's own row is not one
        of them: a client names the Category it is at some other way.

        "sort_key(node)" orders what each Category holds, and "reverse"
        turns that order around.  "keep(node)" leaves a node out, unless
        something below it is kept, so that the way to a node a person
        searched for stays visible.  A Category that is not open holds
        nothing a client knows of, so a filter hides it on its own fields
        alone
        """

        rows = []
        children = self.children(path)
        if sort_key is not None:
            children.sort(key=sort_key, reverse=reverse)
        for child in children:
            below = []
            if child.expanded and child.kind == CATEGORY and child.cycle is None:
                below = self.rows(child.path, level + 1, keep, sort_key, reverse)
            if keep is not None and not below and not keep(child):
                continue
            rows.append((child, level))
            rows += below
        return rows


def entries_of_cache(cache):
    """The Entries of one Category, from its shared state, by name,
    as the command line also sorts them"""

    entries = cache.get("entries")
    if not isinstance(entries, dict):
        return []
    return [entry_of(name, entries[name]) for name in sorted(entries)]


def parse_entry_records(records):
    """(entries, diagnostics) from the arguments of each "(response
    ...)" of a "(list ...)".  A record is one of ...

        level name ((topic_paths name protocol ...) lcm storage)
        -level name            a Category, in a recursive listing
        text "..."             what the Actor says went wrong

    Only the Entries of the Category that was asked for, which are the
    ones at level 0, are returned: a recursive listing names a nested
    Category without its path, and a client asks for one path at a
    time
    """

    entries, diagnostics = [], []
    for record in records:
        if not isinstance(record, (list, tuple)) or not record:
            continue
        if record[0] == "text":
            diagnostics.append(str(record[1]) if len(record) > 1 else "no reason given")
            continue
        try:
            level = int(record[0])
        except (TypeError, ValueError):
            continue
        if level == 0 and len(record) > 2:
            entries.append(entry_of(str(record[1]), record[2]))
    return entries, diagnostics


# --------------------------------------------------------------------------- #
