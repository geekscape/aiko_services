#!/usr/bin/env python3
#
# Aiko Services: the Category's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# A Category is a group of Entries, and an Entry is either a Dependency or
# another Category, so a Category is a node in a graph of Services.  This
# page navigates that graph the way a file manager navigates directories,
# and performs the Category functions add, remove and update on the
# Category that the cursor is in.
#
# Registered through "plugins.py", the Dashboard's default "--plugin"
# module, so this page needs no flag.  The key is the protocol type.
#
# The Dashboard hides Categories from its Service list by default, because
# a HyperSpace of any size has a great many of them.  Press "f" then "c"
# on the Dashboard page to show them, then "S" to open this page.
#
# Design
# ~~~~~~
# Progressive discovery, in two steps, because a Category knows only its
# own Entries:
#
# - The Entries of the selected Category come from the Dashboard's own
#   ECConsumer.  They need no request and they stay live.
# - An Entry that is itself a Category is a reference to another Service.
#   "Enter" follows it: the page finds that Service among the ones the
#   Registrar knows, and asks the Dashboard to select it, which re-roots
#   this page there.  The Services followed so far are the trail, and "G"
#   walks back along it.
#
# A HyperSpace resolves a whole Entry path itself, so its page expands a
# node in place instead, with one "(list ...)" request for each node.
# "CategoryPage.resolves_paths" is the whole of that difference, and
# "hyperspace_plugin.py" is the rest of what a HyperSpace adds.
#
# Categories form a cyclic graph, not a tree, so each descent is checked:
#
# - A node whose target repeats one of its own ancestors is marked "^",
#   and does not open.
# - A Service that is already on the trail is not followed again.
#
# asciimatics has no screen double, so the decisions live in CategoryPage
# and CategoryTree, which are pure, and the Frame below is the thin part.
# Unlike the other pages, these decisions are instance methods, because
# the HyperSpace page overrides them.
#
# State comes from the Dashboard's own ECConsumer, never from a second
# consumer of this page's own: two consumers of one producer would each
# hold a lease, and the Dashboard already has one.
#
# To Do
# ~~~~~
# - A LISP REPL pane, which the Dashboard's own To Do asks for
# - Follow a Dependency to the Service it refers to, as Enter follows a
#   Category
# - Match an Entry to its Service by the whole ServiceFilter, rather than
#   by the name and the protocol type
# - An Entry that is a link to an existing Category, once "hyperspace.py"
#   implements "link"

from collections import namedtuple
from functools import partial
import time

from asciimatics.event import KeyboardEvent
from asciimatics.widgets import (
    Label, Layout, MultiColumnListBox, PopUpDialog, PopupMenu, Text,
)

import aiko_services as aiko
from aiko_services.main.category import Category
from aiko_services.main.connection import ConnectionState
from aiko_services.main.utilities import parse
from aiko_services.ide.tui.dashboard import (
    LogLevelPopupMenu, LogUI, ServiceFrame,
)

__all__ = [
    "CategoryFrame", "CategoryNode", "CategoryPage", "CategoryTree",
    "Entry", "entry_of", "entry_path_join", "entry_path_parent",
    "field_text", "plugins", "protocol_terse", "protocol_type",
]

PATH_DELIMITER = "/"
CATEGORY = "category"
DEPENDENCY = "dependency"

ABSENT = "-"            # a field that the Actor sent as the codec's None
WILDCARD = "*"
KEEP = "0:"             # what an update sends for a field to leave alone

# Every field of one Entry, as a person reads it.  "target" is what the
# Entry refers to: the name in its ServiceFilter, or its own name
Entry = namedtuple("Entry",
    "name kind target protocol transport owner tags lcm_url storage_url")

def entry_path_join(path, name):
    """One Entry path from a Category path and an Entry name"""

    return f"{path}{PATH_DELIMITER}{name}" if path else name

def entry_path_parent(path):
    """The Category that holds the Entry at path, "" being the root"""

    return path.rpartition(PATH_DELIMITER)[0]

def protocol_type(protocol):
    """"category" from ".../protocol/category:0", and "" from nothing"""

    if not protocol or protocol in (WILDCARD, ABSENT):
        return ""
    return protocol.rpartition(PATH_DELIMITER)[2].split(":")[0]

def protocol_terse(protocol):
    """"category:0" from ".../protocol/category:0", which is how the
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
    tags = [str(tag) for tag in tags]  \
        if isinstance(tags, (list, tuple)) else []
    protocol = field_text(filter_field(2))
    filter_name = field_text(filter_field(1))
    target = name if filter_name in (ABSENT, WILDCARD) else filter_name

    return Entry(name,
        CATEGORY if protocol_type(protocol) == CATEGORY else DEPENDENCY,
        target, protocol, field_text(filter_field(3)),
        field_text(filter_field(4)), tags,
        field_text(field(1)), field_text(field(2)))

def root_entry(name):
    """The Entry of the Category that this page is rooted at"""

    return Entry(name, CATEGORY, name,
        aiko.CATEGORY_PROTOCOL, ABSENT, ABSENT, [], ABSENT, ABSENT)

# --------------------------------------------------------------------------- #

class CategoryNode:
    """One Entry, and what the viewer knows about it"""

    def __init__(self, path, entry):
        self.path = path
        self.entry = entry
        self.children = []        # Entry names, in the order they are shown
        self.expanded = False
        self.loaded = False       # its children have arrived
        self.cycle = None         # the path of the ancestor that it repeats

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

        Returns False when path is not a node of this tree
        """

        parent = self.nodes.get(path)
        if parent is None:
            return False

        targets = {node.entry.target: node.path
            for node in self.ancestors(path)}
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
        for key in [key for key in self.nodes
                if key == path or key.startswith(prefix)]:
            del self.nodes[key]

    def rows(self, path="", level=0):
        """[(node, level)] for each row the viewer shows, from path down
        through every node that is open.  The root's own row is not one of
        them: the title bar says which Service this is"""

        node = self.nodes.get(path)
        rows = []
        if node is None:
            return rows
        for name in node.children:
            child = self.nodes.get(entry_path_join(path, name))
            if child is None:            # merged away while being drawn
                continue
            rows.append((child, level))
            if child.expanded and child.kind == CATEGORY:
                rows += self.rows(child.path, level + 1)
        return rows

# --------------------------------------------------------------------------- #

class CategoryPage:
    """The page's decisions, with no screen and no network"""

    resolves_paths = False     # a Category knows only its own Entries

    KEYS = {
        "a": ("add",),
        "d": ("remove",),
        "u": ("update",),
        "r": ("refresh",),
        "g": ("follow",),
        "G": ("back",),
        "L": ("log_level",),
        "H": ("help",),
    }

    STATE_KEYS = ("entries_count", "lifecycle", "log_level", "running")

    def __init__(self):
        self.tree = CategoryTree()

    def action(self, key_code):
        """What a key asks for, or None when this page does not take it"""

        if key_code < 0 or key_code > 0x10FFFF:
            return None
        return self.KEYS.get(chr(key_code))

    # What a Category holds ------------------------------------------- #

    @staticmethod
    def entries_from_cache(cache):
        """The Entries of the selected Category, from its shared state,
        by name, as the command line also sorts them"""

        entries = cache.get("entries")
        if not isinstance(entries, dict):
            return []
        return [entry_of(name, entries[name]) for name in sorted(entries)]

    @staticmethod
    def parse_records(records):
        """(entries, diagnostics) from the arguments of each "(response
        ...)" of a "(list ...)".  A record is one of ...

            level name ((topic_paths name protocol ...) lcm storage)
            -level name            a Category, in a recursive listing
            text "..."             what the Actor says went wrong

        Only the Entries of the Category that was asked for, which are the
        ones at level 0, are returned: a recursive listing names a nested
        Category without its path, and this page asks for one path at a
        time
        """

        entries, diagnostics = [], []
        for record in records:
            if not isinstance(record, (list, tuple)) or not record:
                continue
            if record[0] == "text":
                diagnostics.append(
                    str(record[1]) if len(record) > 1 else "no reason given")
                continue
            try:
                level = int(record[0])
            except (TypeError, ValueError):
                continue
            if level == 0 and len(record) > 2:
                entries.append(entry_of(str(record[1]), record[2]))
        return entries, diagnostics

    def refresh_root(self, cache, name=None):
        """The root's Entries, from the shared state.  A new name is a new
        Service, so the tree starts again"""

        if name is not None and name != self.tree.node("").name:
            self.tree.reset(name)
        self.tree.merge("", self.entries_from_cache(cache))

    # What the viewer shows ------------------------------------------- #

    def marker(self, node):
        """One character that says what Enter on this row does"""

        if node.kind != CATEGORY:
            return " "
        if node.cycle is not None:
            return "^"
        if not self.resolves_paths:
            return ">"                 # Enter follows it to its own Service
        if node.expanded:
            return "-" if node.loaded else "."
        return "+"

    def row_type(self, node):
        if node.cycle is not None:
            return f"{CATEGORY} (cycle)"
        return node.kind

    def table_rows(self):
        """[(columns, path)] for the Entry table, one row for each Entry
        that the viewer shows"""

        rows = []
        for node, level in self.tree.rows():
            suffix = PATH_DELIMITER if node.kind == CATEGORY else ""
            label = f"{'  ' * level}{self.marker(node)} {node.name}{suffix}"
            columns = (label, self.row_type(node),
                node.entry.owner, protocol_terse(node.entry.protocol))
            rows.append((columns, node.path))
        return rows

    def toggle(self, path):
        """What Enter on a row asks for: "collapse", "expand", "request",
        "follow", "cycle" or "detail" """

        node = self.tree.node(path)
        if node is None:
            return None
        if node.kind != CATEGORY:
            return "detail"
        if node.cycle is not None:
            return "cycle"
        if node.expanded:
            node.expanded = False
            return "collapse"
        if not self.resolves_paths:
            return "follow"
        node.expanded = True
        return "expand" if node.loaded else "request"

    def current_category(self, path):
        """Where add, remove and update apply: the selected Category when
        it is open, otherwise the Category that holds the selected Entry"""

        node = self.tree.node(path) if path else None
        if node is None:
            return ""
        if node.kind == CATEGORY and node.expanded and node.cycle is None:
            return node.path
        return entry_path_parent(path)

    def breadcrumb(self, path):
        """The current Category, as a person reads it"""

        return f"{self.tree.node('').name}{PATH_DELIMITER}{path}"

    def detail_lines(self, path):
        """Every field of one Entry"""

        node = self.tree.node(path)
        if node is None:
            return []
        entry = node.entry
        lines = [
            f"{self.breadcrumb(path)}", "",
            f"type        {self.row_type(node)}",
            f"target      {entry.target}",
            f"protocol    {entry.protocol}",
            f"transport   {entry.transport}",
            f"owner       {entry.owner}",
            f"tags        {field_text(entry.tags)}",
            f"lifecycle   {entry.lcm_url}",
            f"storage     {entry.storage_url}",
        ]
        if node.cycle is not None:
            above = node.cycle or self.tree.node("").name
            lines += ["", f"It refers to {above}, which is open above it"]
        return lines

    def state_rows(self, cache):
        """[(name, value)]: what this Category is, then its metrics"""

        rows = [(name, field_text(cache[name]))
            for name in self.STATE_KEYS if name in cache]
        metrics = cache.get("metrics")
        if isinstance(metrics, dict):
            rows += [(f"metrics.{name}", field_text(metrics[name]))
                for name in sorted(metrics)]
        return rows

    def title(self, cache):
        """What the page says beside the Service"""

        entries = len(self.entries_from_cache(cache))
        return f"entries: {entries}   shown: {len(self.tree.rows())}"

    # The Entry syntax, which one text field carries ------------------ #

    @staticmethod
    def parse_add(words):
        """(name, kind, protocol, owner, tags) from ...

            NAME[/] [PROTOCOL] [OWNER] [TAG=VALUE ...]

        A name that ends in "/" asks for a Category, as a trailing
        delimiter means a directory everywhere else.  A field of "-" is
        left unset, which a filter writes as "*"
        """

        words = [word for word in words if word]
        if not words:
            return None
        name = words[0]
        kind = CATEGORY if name.endswith(PATH_DELIMITER) else DEPENDENCY
        name = name.rstrip(PATH_DELIMITER)
        if not name:
            return None
        protocol, owner, tags = CategoryPage._fields(words[1:], WILDCARD)
        if kind == CATEGORY and protocol == WILDCARD:
            protocol = aiko.CATEGORY_PROTOCOL
        return name, kind, protocol, owner, tags

    @staticmethod
    def parse_update(words):
        """(protocol, owner, tags) from "[PROTOCOL] [OWNER] [TAG=VALUE
        ...]".  A field of "-", and a field that is not there, keep the
        value the Entry already has"""

        return CategoryPage._fields([word for word in words if word], KEEP)

    @staticmethod
    def _fields(words, absent):
        protocol = words[0] if len(words) > 0 else absent
        owner = words[1] if len(words) > 1 else absent
        tags = [word for word in words[2:] if "=" in word]
        return (absent if protocol == ABSENT else protocol,
                absent if owner == ABSENT else owner, tags)

    @staticmethod
    def update_words(entry):
        """What the update dialogue starts with: the Entry as it is"""

        return " ".join([entry.protocol, entry.owner] + list(entry.tags))

    # The help -------------------------------------------------------- #

    def help_text(self):
        return "\n".join(self.help_lines())

    def help_lines(self):
        return [
            "A Category is a group of Entries, and an Entry is either a",
            "Dependency or another Category, so Categories form a graph.",
            "",
            "  Enter   a Category: follow it to its own Service",
            "          a Dependency: every field it holds",
            "  g       follow the selected Category, as Enter does",
            "  G       back to the Category that was followed from",
            "  r       refresh: read this Category's Entries again",
            "",
            "The Category functions, sent on its in topic.  Each one acts",
            "on the Category named in the title bar:",
            "",
            "  a add     NAME[/] [PROTOCOL] [OWNER] [TAG=VALUE ...]",
            "            a name ending in / asks for a Category",
            "  u update  [PROTOCOL] [OWNER] [TAG=VALUE ...]",
            "            a field of - keeps the value it has",
            "  d remove  the selected Entry",
            "",
            "A Category marked ^ refers to one that is already open above",
            "it, and does not open again.",
            "",
            "This page: L log level  H this help",
            "Esc Backspace q back  x quit the Dashboard",
        ]

# --------------------------------------------------------------------------- #

class CategoryFrame(ServiceFrame):
    """The Dashboard page: the Entry tree, the state, the log"""

    PAGE = CategoryPage
    INTERFACE = Category
    FRAME_NAME = "category_frame"
    RESPONSE_TIMEOUT = 5.0                                    # seconds

    def __init__(self, screen, dashboard):
        super().__init__(screen, dashboard, name=self.FRAME_NAME)

        self.page = self.PAGE()
        self.topic_path = None
        self.service_text = ""
        self.proxy = None
        self.trail = []                 # the Services followed to get here
        self._following = None          # the Service that "g" asked for
        self._diagnostic = ""
        self._merged = None             # a response, for the drawing thread
        self._pending = None            # the Entry path a "(list ...)" asks of
        self._pending_time = 0.0
        self._records = None
        self._records_count = 0

        state_height = min(len(self.page.STATE_KEYS) + 4,
            max(5, screen.height // 4))
        tree_height = max(3, screen.height - state_height - 14)

        self.tree_widget = MultiColumnListBox(tree_height,
            ["<40", "<18", "<10", "<0"], options=[],
            titles=["Entry", "Type", "Owner", "Protocol"],
            on_select=self._on_select)
        layout = Layout([1])
        self.add_layout(layout)
        layout.add_widget(self.tree_widget)

        self.state_widget = MultiColumnListBox(state_height,
            ["<22", "<0"], options=[], titles=["Variable", "Value"])
        layout = Layout([1])
        self.add_layout(layout)
        layout.add_widget(self.state_widget)

        self.legend = Label("", height=2)      # the keys need two lines
        layout = Layout([1])
        self.add_layout(layout)
        layout.add_widget(self.legend)

        self.log_ui = LogUI(self)
        self.fix()  # Prepare asciimatics_Frame for use

    # The Service ------------------------------------------------------ #

    def _response_topic(self):
        return aiko.process.topic_in

    def _service_frame_start(self, service, service_ec_consumer):
        topic_path = service[0]
        if topic_path == self.topic_path:
            return                                       # idempotent
        if self.topic_path is not None:                  # another Category
            aiko.process.remove_message_handler(
                self._response_handler, self._response_topic())
        if topic_path != self._following:
            self.trail = []                              # a fresh descent
        self._following = None
        self.topic_path = topic_path
        self.service_text = self._service_title.value
        self.proxy = aiko.get_service_proxy(
            f"{topic_path}/in", self.INTERFACE)
        self.page.tree.reset(service[1])
        self._pending = None
        self._merged = None
        self._diagnostic = ""
        aiko.process.add_message_handler(
            self._response_handler, self._response_topic())
        self.log_ui._service_frame_start(service, service_ec_consumer)

    def _service_frame_stop(self, service):
        if self.topic_path is None:
            return
        aiko.process.remove_message_handler(
            self._response_handler, self._response_topic())
        self.log_ui._service_frame_stop(service)
        self.topic_path = None
        self.proxy = None
        self.trail = []

    def _cache(self):
        """The Dashboard's own ECConsumer, never a second one of our own"""

        consumer = self.dashboard.ec_consumer
        return consumer.cache if consumer is not None else {}

    @staticmethod
    def _connected():
        return aiko.process.connection.is_connected(ConnectionState.TRANSPORT)

    def _services(self):
        """Every Service the Registrar knows, as the Dashboard holds them"""

        services_cache = getattr(self.dashboard, "services_cache", None)
        if services_cache is None:
            return []
        return services_cache.get_services().copy()

    # Requesting the Entries of a nested Category ---------------------- #

    def _request(self, path):
        """(list RESPONSE_TOPIC PATH true false), which only a Service
        that resolves a whole Entry path answers usefully"""

        if not self._connected():
            self._diagnostic = "not connected to the message bus"
            return
        self._pending = path
        self._pending_time = time.monotonic()
        self._records, self._records_count = None, 0
        self.proxy.list(self._response_topic(), path, True, False)

    def _response_handler(self, _aiko, topic, payload_in):
        """The response arrives on the event loop's thread, so it is left
        for the drawing thread to merge"""

        if self._pending is None:
            return False
        command, arguments = parse(payload_in)
        if command == "item_count" and len(arguments) == 1:
            try:
                self._records_count = int(arguments[0])
            except (TypeError, ValueError):
                return False
            self._records = []
        elif command == "response" and self._records is not None:
            self._records.append(arguments)
        if self._records is not None and  \
            len(self._records) >= self._records_count:
            self._merged = (self._pending, self._records)
            self._pending, self._records = None, None
        return False

    def _merge(self, path, records):
        entries, diagnostics = self.page.parse_records(records)
        node = self.page.tree.node(path)
        if diagnostics:
            self._diagnostic = f"{path}: {' '.join(diagnostics)}"
            if node is not None:
                node.expanded = False
            return
        self.page.tree.merge(path, entries)

    def _expire_request(self):
        if self._pending is None:
            return
        if time.monotonic() - self._pending_time < self.RESPONSE_TIMEOUT:
            return
        node = self.page.tree.node(self._pending)
        if node is not None:
            node.expanded = False
        self._diagnostic = f"{self._pending}: no answer"
        self._pending, self._records = None, None

    # Keys ------------------------------------------------------------- #

    def process_event(self, event):
        if isinstance(event, KeyboardEvent) and self.topic_path:
            action = self.page.action(event.key_code)
            if action is not None:
                self._act(action[0])
                return None
            self.log_ui.process_event(event)
        return super().process_event(event)

    def _act(self, kind):
        if kind == "log_level":
            self.scene.add_effect(LogLevelPopupMenu(
                self._screen, self.state_widget, self.topic_path))
        elif kind == "help":
            self._popup(self.page.help_text(), ["OK"])
        elif kind == "add":
            self._add_entry()
        elif kind == "remove":
            self._remove_entry()
        elif kind == "update":
            self._update_entry()
        elif kind == "refresh":
            self._refresh()
        elif kind == "follow":
            self._follow(self._selected_path())
        elif kind == "back":
            self._back()

    def _popup(self, text, buttons, on_close=None):
        self.scene.add_effect(PopUpDialog(
            self._screen, text, buttons, on_close=on_close, theme="nice"))

    def _text_dialog(self, prompt, button, send, value=""):
        """One text field, as the ProcessManager's create dialogue has"""

        text = Text("Entry:", "entry")
        text.value = value

        def _on_close(button_index):
            if button_index == 1 and text.value and self._connected():
                send(text.value.split())

        popup = PopUpDialog(self._screen, prompt + " " * 30,
            ["Cancel", button], on_close=_on_close, theme="nice")
        layout = Layout([1])
        popup.add_layout(layout)
        layout.add_widget(text)
        popup.fix()
        self.scene.add_effect(popup)

    def _selected_path(self):
        path = self.tree_widget.value
        return path if isinstance(path, str) else ""

    def _selected_node(self):
        """The Entry the cursor is on, or None when there is none.  The
        root has no row of its own, so an empty path is none of them"""

        path = self._selected_path()
        return self.page.tree.node(path) if path else None

    def _on_select(self):
        path = self._selected_path()
        outcome = self.page.toggle(path)
        if outcome == "request":
            self._request(path)
        elif outcome == "follow":
            self._follow(path)
        elif outcome == "detail":
            self._popup("\n".join(self.page.detail_lines(path)), ["OK"])
        elif outcome == "cycle":
            self._popup("\n".join(self.page.detail_lines(path)), ["OK"])

    # The Category functions ------------------------------------------- #

    def _entry_path(self, category_path, name):
        """What add, remove and update name.  A Category takes an Entry
        name, because it holds only its own Entries"""

        return name

    def _create_category(self, category_path, name, protocol, owner, tags):
        """A Category Entry, which a Category adds as a reference to a
        Category Service, the way the command line does"""

        self.proxy.add(self._entry_path(category_path, name),
            aiko.ServiceFilter(WILDCARD, name, protocol, WILDCARD,
                owner, tags), None, None)

    def _add_entry(self):
        category_path = self.page.current_category(self._selected_path())

        def send(words):
            fields = self.page.parse_add(words)
            if fields is None:
                return
            name, kind, protocol, owner, tags = fields
            if kind == CATEGORY:
                self._create_category(
                    category_path, name, protocol, owner, tags)
            else:
                self.proxy.add(self._entry_path(category_path, name),
                    aiko.ServiceFilter(WILDCARD, name, protocol, WILDCARD,
                        owner, tags), None, None)

        self._text_dialog(
            f"Add to {self.page.breadcrumb(category_path)}"
            "   NAME[/] [PROTOCOL] [OWNER] [TAG=VALUE ...]", "Add", send)

    def _update_entry(self):
        node = self._selected_node()
        if node is None:
            return self._popup("Select an Entry first.", ["OK"])
        path = node.path
        category_path = entry_path_parent(path)

        def send(words):
            protocol, owner, tags = self.page.parse_update(words)
            self.proxy.update(self._entry_path(category_path, node.name), None,
                aiko.ServiceFilter(WILDCARD, KEEP, protocol, KEEP,
                    owner, tags), None, None)

        self._text_dialog(f"Update {self.page.breadcrumb(path)}"
            "   [PROTOCOL] [OWNER] [TAG=VALUE ...]", "Update", send,
            self.page.update_words(node.entry))

    def _remove_entry(self):
        node = self._selected_node()
        if node is None:
            return self._popup("Select an Entry first.", ["OK"])
        path = node.path
        category_path = entry_path_parent(path)

        def _on_close(button_index):
            if button_index == 1 and self._connected():
                self._remove(category_path, node)

        self._popup(f"Remove the {node.kind} "
            f"{self.page.breadcrumb(path)} ?", ["Cancel", "Remove"], _on_close)

    def _remove(self, category_path, node):
        self.proxy.remove(self._entry_path(category_path, node.name))

    def _refresh(self):
        """Read the selected Category's Entries again.  The root's Entries
        arrive through the shared state, so they are never stale"""

        path = self.page.current_category(self._selected_path())
        if not path:
            return
        if self.page.resolves_paths:
            self._request(path)
        else:
            self._diagnostic = "the root's Entries are read continuously"

    # Following a Category to its own Service -------------------------- #

    def _category_services(self, entry):
        """Every Category Service that an Entry could refer to"""

        return [service for service in self._services()
            if service[1] == entry.target
            and protocol_type(service[2]) == CATEGORY]

    def _follow(self, path):
        node = self.page.tree.node(path) if path else None
        if node is None or node.kind != CATEGORY:
            return self._popup("Select a Category first.", ["OK"])
        if node.cycle is not None:
            return self._popup("\n".join(self.page.detail_lines(path)), ["OK"])

        matches = self._category_services(node.entry)
        if not matches:
            return self._popup(
                f"No Category Service named {node.entry.target} is running."
                "\n\nA Category Entry is a reference: the Service it names"
                "\nmay not be running, and the Dashboard hides Categories"
                "\nuntil \"f\" then \"c\" says to show them.", ["OK"])
        if len(matches) == 1:
            return self._select(matches[0][0])

        items = [("   Cancel", self.tree_widget.focus)]
        for service in matches:
            topic_path = service[0]
            items.append((str(aiko.ServiceTopicPath.parse(topic_path)),
                partial(self._select, topic_path)))
        self.scene.add_effect(PopupMenu(self._screen, items,
            self._screen.width // 2 - 4, self._screen.height // 3))

    def _select(self, topic_path):
        """Ask the Dashboard to select another Service, which re-roots
        this page there"""

        if topic_path in self.trail or topic_path == self.topic_path:
            return self._popup(
                f"{topic_path}\nis already open above this one.", ["OK"])
        select_service = getattr(self.dashboard, "select_service", None)
        if select_service is None:
            return self._popup(
                "This Dashboard cannot follow a Category.", ["OK"])
        trail = self.trail + [self.topic_path]
        self._following = topic_path
        if not select_service(topic_path):
            self._following = None
            return self._popup(
                f"{topic_path}\nis no longer running.", ["OK"])
        self.trail = trail

    def _back(self):
        if not self.trail:
            return self._popup("No Category was followed to get here.", ["OK"])
        trail = self.trail[:-1]
        topic_path = self.trail[-1]
        select_service = getattr(self.dashboard, "select_service", None)
        self._following = topic_path
        if select_service is None or not select_service(topic_path):
            self._following = None
            return self._popup(
                f"{topic_path}\nis no longer running.", ["OK"])
        self.trail = trail

    # Drawing ---------------------------------------------------------- #

    def _legend_text(self):
        keys = "keys: Enter open  a add  u update  d remove  r refresh"  \
               "  g follow  G back  L log level  H help"
        notes = [note for note in (self._trail_text(), self._diagnostic)
            if note]
        return f"{keys}   {'   '.join(notes)}" if notes else keys

    def _trail_text(self):
        """How far this page has followed, when it has"""

        return f"{len(self.trail)} deep: G goes back" if self.trail else ""

    def _update(self, frame_no):
        super()._update(frame_no)                 # may start the Service
        if self.topic_path is None:
            return

        merged = self._merged
        if merged is not None:
            self._merged = None
            self._merge(*merged)
        self._expire_request()

        cache = self._cache()
        self.page.refresh_root(cache, self.service[1])
        path = self.page.current_category(self._selected_path())

        self._service_title.value = (
            f"{self.service_text}    {self.page.breadcrumb(path)}"
            f"    {self.page.title(cache)}")
        self.tree_widget.options = [(columns, row_path)
            for columns, row_path in self.page.table_rows()]
        self.state_widget.options = [((name, value), index)
            for index, (name, value) in
            enumerate(self.page.state_rows(cache))]
        self.legend.text = self._legend_text()
        self.log_ui._update(frame_no)

# plugin key: the protocol type of category:0
plugins = {"category": CategoryFrame}

# --------------------------------------------------------------------------- #
