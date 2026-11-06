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
# "main/category_view.py" holds the data model: an Entry, a tree of the
# Entries discovered so far, and the cycle check that a graph needs.  It
# is not a user interface, so a REPL or a web page uses the same model.
# This module is what a terminal adds to it.
#
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
# A HyperSpace resolves a whole Entry path itself, so its page opens a
# node where it is instead, with one "(list ...)" request for each node.
# "CategoryPage.resolves_paths" is the whole of that difference, and
# "hyperspace_plugin.py" is the rest of what a HyperSpace adds.
#
# asciimatics has no screen double, so the decisions live in CategoryPage,
# which is pure, and the Frame below is the thin part.  Unlike the other
# pages, those decisions are instance methods, because the HyperSpace page
# overrides them.
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
# - A one-field dialogue is what a PopUpDialog fits, because it takes its
#   height from its text.  A Frame of its own would take RadioButtons for
#   the kind of Entry, instead of a name that ends in a delimiter

from functools import partial

from asciimatics.event import KeyboardEvent
from asciimatics.widgets import (
    Divider, Label, Layout, MultiColumnListBox, PopUpDialog, PopupMenu,
)

import aiko_services as aiko
from aiko_services.main.category import Category
from aiko_services.main.category_view import (
    ABSENT, CATEGORY, DEPENDENCY, KEEP, PATH_DELIMITER, WILDCARD,
    CategoryTree, entries_of_cache, entry_path_parent, field_text,
    parse_entry_records, protocol_terse, protocol_type,
)
from aiko_services.main import CATEGORY_PROTOCOL
from aiko_services.main.connection import ConnectionState
from aiko_services.ide.tui.dashboard import (
    FormFrame, ListRequest, LogLevelPopupMenu, LogUI, ServiceFrame,
    choice_field, radio_field, text_field,
)

__all__ = ["CategoryFrame", "CategoryPage", "plugins"]

# How the Entries of each Category are ordered.  A field a person can see
# is a field they can sort on, and the name breaks every tie, so that one
# order is one order
SORT_KEYS = {
    "name": lambda node: node.name.lower(),
    "type": lambda node: (node.kind, node.name.lower()),
    "owner": lambda node: (node.entry.owner, node.name.lower()),
    "protocol": lambda node:
        (protocol_terse(node.entry.protocol), node.name.lower()),
    "arrived": None,            # the order the Category sent them in
}
SORT_DEFAULT = "name"
SORT_FIELDS = tuple((name, name) for name in SORT_KEYS)

def form_tags(values):
    """Every tag of a form's "tags" field: a word with an "=" in it, the
    way a ServiceFilter holds one"""

    return [word for word in values.get("tags", "").split() if "=" in word]

class CategoryPage:
    """The page's decisions, with no screen and no network"""

    resolves_paths = False     # a Category knows only its own Entries

    KEYS = {
        "a": ("add",),
        "d": ("remove",),
        "u": ("update",),
        "r": ("refresh",),
        "f": ("filter",),
        "s": ("sort",),
        "F": ("clear",),
        "g": ("follow",),
        "G": ("back",),
        "L": ("log_level",),
        "H": ("help",),
    }

    STATE_KEYS = ("entries_count", "lifecycle", "log_level", "running")

    def __init__(self):
        self.tree = CategoryTree()
        self.pattern = ""          # show only the Entries that match it
        self.sort_field = SORT_DEFAULT
        self.sort_reverse = False

    def action(self, key_code):
        """What a key asks for, or None when this page does not take it"""

        if key_code < 0 or key_code > 0x10FFFF:
            return None
        return self.KEYS.get(chr(key_code))

    # What a Category holds ------------------------------------------- #

    def refresh_root(self, cache, name=None):
        """The root's Entries, from the shared state.  A new name is a new
        Service, so the tree starts again"""

        if name is not None and name != self.tree.node("").name:
            self.tree.reset(name)
        self.tree.merge("", entries_of_cache(cache))

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

    def matches(self, node):
        """Whether an Entry matches the filter, on any field a person can
        see, without regard to case"""

        if not self.pattern:
            return True
        pattern = self.pattern.lower()
        entry = node.entry
        fields = [node.name, node.kind, entry.target, entry.protocol,
            entry.transport, entry.owner] + list(entry.tags)
        return any(pattern in str(field).lower() for field in fields)

    def sort_key(self):
        """How each Category's Entries are ordered, or None for the order
        they arrived in"""

        return SORT_KEYS.get(self.sort_field)

    def keep(self):
        """What the filter hides, or None when it hides nothing"""

        return self.matches if self.pattern else None

    def rows(self):
        """Each row the viewer shows, filtered and ordered"""

        return self.tree.rows(keep=self.keep(),
            sort_key=self.sort_key(), reverse=self.sort_reverse)

    def sort_direction(self):
        return "descending" if self.sort_reverse else "ascending"

    def table_rows(self):
        """[(columns, path)] for the Entry table, one row for each Entry
        that the viewer shows"""

        rows = []
        for node, level in self.rows():
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
        """What the page says beside the Service: how much it holds, how
        much of that is shown, and why"""

        entries = len(entries_of_cache(cache))
        title = f"entries: {entries}   shown: {len(self.rows())}"
        title += f"   sort: {self.sort_field}"
        title += " v" if self.sort_reverse else " ^"
        if self.pattern:
            title += f'   filter: "{self.pattern}"'
        return title

    # What a form says about an Entry --------------------------------- #

    @staticmethod
    def form_entry(values):
        """(name, kind, protocol, owner, tags) from the values of an add
        form, or None when it names nothing.  A field left empty matches
        any, which a ServiceFilter writes as "*" """

        name = values.get("name", "").strip().strip(PATH_DELIMITER)
        if not name:
            return None
        kind = values.get("kind") or DEPENDENCY
        protocol = values.get("protocol", "").strip() or WILDCARD
        owner = values.get("owner", "").strip() or WILDCARD
        if kind == CATEGORY and protocol == WILDCARD:
            protocol = CATEGORY_PROTOCOL
        return name, kind, protocol, owner, form_tags(values)

    @staticmethod
    def form_update(values):
        """(protocol, owner, tags) from the values of an update form.  A
        field left empty keeps the value the Entry has, because an update
        says what to change and not what everything is"""

        return (values.get("protocol", "").strip() or KEEP,
            values.get("owner", "").strip() or KEEP, form_tags(values))

    @staticmethod
    def field_value(value):
        """What a form field starts with: a field the Actor never set is
        empty, rather than the dash that the table shows"""

        return "" if value in (ABSENT, WILDCARD, KEEP) else str(value)

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
            "  a add     a Dependency, or a Category Entry",
            "  u update  the selected Entry: a field left empty keeps",
            "            the value it has",
            "  d remove  the selected Entry",
            "",
            "What the table shows:",
            "",
            "  f       show only the Entries that match, on any field",
            "  s       order each Category's Entries, up or down",
            "  F       show every Entry again, by name",
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
    ADD_NOTE = ("A Category Entry refers to a Category Service of its own"
                "\nname, which this Category does not start.")

    def __init__(self, screen, dashboard):
        super().__init__(screen, dashboard, name=self.FRAME_NAME)

        self.page = self.PAGE()
        self.topic_path = None
        self.service_text = ""
        self.proxy = None
        self.trail = []                 # the Services followed to get here
        self._following = None          # the Service that "g" asked for
        self._diagnostic = ""
        self.request = ListRequest(self.RESPONSE_TIMEOUT)

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

        layout = Layout([1])          # the Entries above, the state below
        self.add_layout(layout)
        layout.add_widget(Divider())

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

    def _service_frame_start(self, service, service_ec_consumer):
        topic_path = service[0]
        if topic_path == self.topic_path:
            return                                       # idempotent
        if self.topic_path is not None:                  # another Category
            self.request.stop()
        if topic_path != self._following:
            self.trail = []                              # a fresh descent
        self._following = None
        self.topic_path = topic_path
        self.service_text = self._service_title.value
        self.proxy = aiko.get_service_proxy(
            f"{topic_path}/in", self.INTERFACE)
        self.page.tree.reset(service[1])
        self._diagnostic = ""
        self.request.start()
        self.log_ui._service_frame_start(service, service_ec_consumer)

    def _service_frame_stop(self, service):
        if self.topic_path is None:
            return
        self.request.stop()
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
        self.request.request(path, lambda topic:
            self.proxy.list(topic, path, True, False))

    def _close(self, path):
        node = self.page.tree.node(path)
        if node is not None:
            node.expanded = False

    def _merge(self, path, records):
        entries, diagnostics = parse_entry_records(records)
        if diagnostics:
            self._diagnostic = f"{path}: {' '.join(diagnostics)}"
            self._close(path)
            return
        self.page.tree.merge(path, entries)

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
        elif kind == "filter":
            self._filter_form()
        elif kind == "sort":
            self._sort_form()
        elif kind == "clear":
            self.page.pattern = ""
            self.page.sort_field = SORT_DEFAULT
            self.page.sort_reverse = False
        elif kind == "follow":
            self._follow(self._selected_path())
        elif kind == "back":
            self._back()

    def _popup(self, text, buttons, on_close=None):
        self.scene.add_effect(PopUpDialog(
            self._screen, text, buttons, on_close=on_close, theme="nice"))

    def _form(self, title, fields, button, on_accept, note=""):
        """A dialogue of more than one field, which a PopUpDialog cannot
        hold: it takes its height from its text"""

        self.scene.add_effect(FormFrame(self._screen, title, fields,
            button, on_accept, note=note))

    # Filtering and sorting -------------------------------------------- #

    def _filter_form(self):
        """Show only the Entries that match, on any field a person sees"""

        def accept(values):
            self.page.pattern = values["pattern"].strip()

        self._form("Filter the Entries",
            [text_field("pattern", "Matches", self.page.pattern)],
            "Filter", accept,
            note="An Entry is shown when any field it has contains this."
                 "\nNothing shows every Entry.  A Category that is not open"
                 "\nis matched on its own fields alone.")

    def _sort_form(self):
        """Order the Entries of each Category, up or down"""

        def accept(values):
            self.page.sort_field = values["field"]
            self.page.sort_reverse = values["direction"] == "descending"

        self._form("Sort the Entries", [
            choice_field("field", "Field", list(SORT_FIELDS),
                self.page.sort_field),
            radio_field("direction", "Order",
                [("Ascending", "ascending"), ("Descending", "descending")],
                self.page.sort_direction()),
        ], "Sort", accept)

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

        def accept(values):
            fields = self.page.form_entry(values)
            if fields is None or not self._connected():
                return
            name, kind, protocol, owner, tags = fields
            if kind == CATEGORY:
                self._create_category(
                    category_path, name, protocol, owner, tags)
            else:
                self.proxy.add(self._entry_path(category_path, name),
                    aiko.ServiceFilter(WILDCARD, name, protocol, WILDCARD,
                        owner, tags), None, None)

        self._form(f"Add to {self.page.breadcrumb(category_path)}", [
            text_field("name", "Name"),
            radio_field("kind", "Entry",
                [("Dependency", DEPENDENCY), ("Category", CATEGORY)]),
            text_field("protocol", "Protocol"),
            text_field("owner", "Owner"),
            text_field("tags", "Tags"),
        ], "Add", accept, note=self.ADD_NOTE)

    def _update_entry(self):
        node = self._selected_node()
        if node is None:
            return self._popup("Select an Entry first.", ["OK"])
        path = node.path
        category_path = entry_path_parent(path)
        value = self.page.field_value

        def accept(values):
            if not self._connected():
                return
            protocol, owner, tags = self.page.form_update(values)
            self.proxy.update(self._entry_path(category_path, node.name), None,
                aiko.ServiceFilter(WILDCARD, KEEP, protocol, KEEP,
                    owner, tags), None, None)

        self._form(f"Update {self.page.breadcrumb(path)}", [
            text_field("protocol", "Protocol", value(node.entry.protocol)),
            text_field("owner", "Owner", value(node.entry.owner)),
            text_field("tags", "Tags", " ".join(node.entry.tags)),
        ], "Update", accept,
            note="A field left empty keeps the value the Entry has.")

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
               "  f filter  s sort  F clear  g follow  G back"  \
               "  L log level  H help"
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

        answer = self.request.take()
        if answer is not None:
            self._merge(*answer)
        expired = self.request.expired()
        if expired is not None:
            self._close(expired)
            self._diagnostic = f"{expired}: no answer"

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
