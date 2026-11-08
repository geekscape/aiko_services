#!/usr/bin/env python3
#
# Aiko Services: the ProcessManager's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Everything "aiko_process" does on the command line, in the Dashboard: the
# process table, the posture, and the functions create, destroy, dump and
# exit.
#
# Registered through "plugins.py", which is the Dashboard's
# default "--plugin" module, so this page needs no flag.  The key is the
# protocol type, "process_manager".
#
# Design
# ~~~~~~
# asciimatics has no screen double, so the decisions live in
# ProcessManagerPage, which is pure: it takes a key code or a replica of the
# shared state and returns what to do or what to show.  The Frame below is
# the thin part.  That is the same division the Display Actor's page uses.
#
# State comes from the Dashboard's own ECConsumer, never from a second
# consumer of this page's own: two consumers of one producer would each hold
# a lease, and the Dashboard already has one.
#
# A ProcessManager runs "--safe" by default and denies create, destroy and
# exit (ADR-023).  A page that offered them anyway would look broken, so it
# reads the posture from the shared state and says why instead.
#
# To Do
# ~~~~~
# - Runtime for each process, when "metrics.runtime" exists
# - A create dialogue that remembers the last command, like a shell history

from asciimatics.event import KeyboardEvent
from asciimatics.widgets import (
    Divider,
    Label,
    Layout,
    MultiColumnListBox,
    PopUpDialog,
    Text,
    VerticalDivider,
)

import aiko_services as aiko
from aiko_services.ide.tui.dashboard import (
    FormFrame,
    ListRequest,
    LogLevelPopupMenu,
    LogUI,
    ServiceFrame,
    choice_field,
    text_field,
)
from aiko_services.main.category_view import (
    CATEGORY,
    CategoryTree,
    entry_path_join,
    entry_path_parent,
    parse_entry_records,
    protocol_type,
)
from aiko_services.main.connection import ConnectionState
from aiko_services.main.hyperspace import HyperSpace
from aiko_services.main.process_definition import (
    command_line,
    definition_json,
    process_of_entry,
    process_url,
)
from aiko_services.main.process_manager import (
    SAFE_FUNCTIONS,
    ProcessManager,
    parse_process_share,
)

__all__ = ["ProcessManagerFrame", "ProcessManagerPage", "plugins"]

# The keys this page acts on, and what each one asks for.  "D" is the
# Dashboard's own "back", so it is never taken here
KEYS = {
    "c": ("create",),
    "d": ("destroy", False),
    "k": ("destroy", True),
    "u": ("dump",),
    "K": ("exit",),
    "n": ("definition",),
    "s": ("start",),
    "t": ("stop",),
    "e": ("enabled",),
    "J": ("json",),
    "L": ("log_level",),
    "H": ("help",),
}

# What the legend says while no definition Category has been named.  The
# definition table is too narrow for a sentence, and an empty table with
# a word beside the keys is clearer than a truncated one
DEFINITION_ABSENT = 'no definition: "n" names one'

# The functions this page sends, and the shared-state key that reports
# whether the Actor is in safe mode
FUNCTIONS_DENIED_WHEN_SAFE = tuple(sorted({"create", "destroy", "dump", "exit"} - set(SAFE_FUNCTIONS)))

# What the Actor is asked for, for a key that asks by another name.  A
# definition Entry is started by creating a process and stopped by
# destroying one, so each is denied in safe mode exactly as those are
FUNCTION_OF_KEY = {"start": "create", "stop": "destroy"}

STATE_KEYS = (
    "safe",
    "watchdog",
    "definition_pathname",
    "lifecycle",
    "log_level",
    "last_error",
)


class ProcessManagerPage:
    """The page's decisions, with no screen and no network.

    read_safe() reads the posture out of a replica of the shared state.
    may_send() says whether a function would reach the Actor.  rows() turns
    the replica into the two tables the Frame shows
    """

    def action(self, key_code):
        """What a key asks for, or None when this page does not take it"""

        if key_code < 0 or key_code > 0x10FFFF:
            return None
        return KEYS.get(chr(key_code))

    @staticmethod
    def read_safe(cache):
        """True, False, or None when the Actor has not said.  A share value
        arrives as a string once a client has written it, so both forms are
        read"""

        safe = cache.get("safe")
        if safe is None or isinstance(safe, bool):
            return safe
        return str(safe).lower() == "true"

    @staticmethod
    def function_of(kind):
        """The Actor's own function for what a key asks for"""

        return FUNCTION_OF_KEY.get(kind, kind)

    def may_send(self, cache, function):
        """(True, "") when the function would reach the Actor.  Otherwise
        (False, why), which the page shows instead of acting"""

        if function not in FUNCTIONS_DENIED_WHEN_SAFE:
            return True, ""
        safe = self.read_safe(cache)
        if safe is False:
            return True, ""
        if safe is None:
            return False, (
                f"This ProcessManager does not report a posture, so"
                f" ({function} ...) may be denied.\n"
                "It is an Actor from before --safe existed."
            )
        return False, (
            f"This ProcessManager runs --safe, so it denies ({function} ...)"
            " from the message bus.\n\n"
            "Each of " + ", ".join(FUNCTIONS_DENIED_WHEN_SAFE) + " needs an Actor started with:\n"
            "    aiko_process run --unsafe\n\n"
            "The command line and the definition file are not affected,"
            " because neither goes through the bus."
        )

    @staticmethod
    def process_rows(cache):
        """[(uid, pid, command)] from the "process" share item"""

        processes = cache.get("process") or {}
        if not isinstance(processes, dict):
            return []
        rows = []
        for uid in sorted(processes):
            pid, command = parse_process_share(processes[uid])
            rows.append((uid, pid, command))
        return rows

    @staticmethod
    def state_rows(cache):
        """[(name, value)]: the keys that say what this Actor is, then its
        metrics.  "source_file" is left out, as the Dashboard leaves it"""

        rows = [(name, str(cache[name])) for name in STATE_KEYS if name in cache]
        metrics = cache.get("metrics")
        if isinstance(metrics, dict):
            rows += [(f"metrics.{name}", str(metrics[name])) for name in sorted(metrics)]
        return rows

    @staticmethod
    def title(cache):
        """What the page says about the posture, beside the Service"""

        safe = ProcessManagerPage.read_safe(cache)
        if safe is None:
            return "posture: not reported"
        denied = cache.get("metrics", {})
        denied = denied.get("denied", 0) if isinstance(denied, dict) else 0
        posture = "safe" if safe else "UNSAFE"
        return f"posture: {posture}   denied: {denied}"

    # The definition, held in a Category -------------------------------- #

    @staticmethod
    def live_processes(cache):
        """{command line: (uid, pid)} for each process that is running, so
        that a definition Entry can be matched to one.

        The ProcessManager does not say which Entry a process came from,
        so the command line is all there is to match on.  Two Entries of
        one command line are one row here, which is honest: the
        ProcessManager cannot tell them apart either"""

        processes = cache.get("process") or {}
        if not isinstance(processes, dict):
            return {}
        live = {}
        for uid in sorted(processes):
            pid, command = parse_process_share(processes[uid])
            live.setdefault(command, (uid, pid))
        return live

    @staticmethod
    def definition_rows(nodes, cache):
        """[(columns, path)] for the definition table: what each Entry
        says to run, whether it is enabled, and whether it is running"""

        live = ProcessManagerPage.live_processes(cache)
        rows = []
        for node, level in nodes:
            indent = "  " * level
            if node.kind == CATEGORY:
                rows.append(((f"{indent}{node.name}/", "", "", ""), node.path))
                continue
            process, diagnostic = process_of_entry(node.entry)
            if process is None:
                rows.append(((f"{indent}{node.name}", "", "-", diagnostic), node.path))
                continue
            command = command_line(process)
            enabled = "yes" if process.enabled else "no"
            if command in live:
                state = f"pid {live[command][1]}"
            elif process.enabled:
                state = "stopped"
            else:
                state = "disabled"
            rows.append(((f"{indent}{node.name}", enabled, state, command), node.path))
        return rows

    @staticmethod
    def definition_processes(nodes):
        """Each Process of a definition, in the order it is shown, for the
        JSON that "aiko_process run" reads"""

        processes = []
        for node, _ in nodes:
            process, _ = process_of_entry(node.entry)
            if process is not None:
                processes.append(process)
        return processes

    @staticmethod
    def definition_text(nodes):
        processes = ProcessManagerPage.definition_processes(nodes)
        if not processes:
            return "The definition Category holds no process Entry."
        return definition_json(processes)

    @staticmethod
    def hyperspace_options(services):
        """[(label, topic_path)] for each HyperSpace or Category Service
        the Registrar knows, which is a closed set, so a person chooses
        from it rather than typing a topic path"""

        options = []
        for service in services:
            if protocol_type(service[2]) not in ("hyperspace", CATEGORY):
                continue
            topic_path = str(aiko.ServiceTopicPath.parse(service[0]))
            options.append((f"{service[1]}  {topic_path}", service[0]))
        return sorted(options)

    @staticmethod
    def help_text():
        return "\n".join(
            [
                "The ProcessManager's functions, sent on its in topic:",
                "  c create a process      u dump the state to its log",
                "  d destroy (SIGTERM)     k destroy (SIGKILL)",
                "  K exit: destroy every process, then terminate the Actor",
                "",
                "A ProcessManager runs --safe by default, and denies every one",
                "of those, dump included.  This page says so rather than",
                "appearing to act.  Start it with --unsafe to use them.",
                "",
                "The definition, held in a Category of a HyperSpace:",
                "  n  name the HyperSpace and the Category path",
                "  s  start the selected Entry, as a process",
                "  t  stop the process of the selected Entry",
                "  e  enable or disable the selected Entry",
                "  J  the definition as the JSON that a ProcessManager reads",
                "",
                "An Entry is a process when its storage URL begins with",
                '"process:", and what follows is one definition entry, as',
                "JSON.  Its lifecycle manager URL names the ProcessManager.",
                "Editing the Category does not restart anything, and a",
                "ProcessManager still reads its JSON file when it starts.",
                "",
                "This page: L log level  H this help",
                "Esc Backspace q back  x quit the Dashboard",
            ]
        )


class ProcessManagerFrame(ServiceFrame):
    """The Dashboard page: the process table, the state, the log"""

    def __init__(self, screen, dashboard):
        super().__init__(screen, dashboard, name="process_manager_frame")

        self.page = ProcessManagerPage()
        self.topic_path = None
        self.service_text = ""
        self.proxy = None

        # The definition: a Category of another Service, so it has its own
        # proxy and its own request.  The ProcessManager does not know of it
        # yet, which is why a person names it
        self.definition_topic = None  # the HyperSpace that holds it
        self.definition_path = ""  # the Category path within it
        self.definition_proxy = None
        self.definition_tree = CategoryTree()
        self.request = ListRequest()
        self._diagnostic = ""

        # The state table gets its rows first, so that "last_error" and the
        # metrics are visible on an 80x24 terminal.  The posture and the count
        # of denials are in the title bar as well, because they are what an
        # operator came to see
        state_height = min(len(STATE_KEYS) + 3, max(5, screen.height // 3))
        process_height = max(3, screen.height - state_height - 15)

        # The definition on the left, what is running on the right, so that
        # an Entry and its process are read across one row
        self.definition_widget = MultiColumnListBox(
            process_height,
            ["<18", "<4", "<10", "<0"],
            options=[],
            titles=["Definition", "On", "State", "Command"],
            on_select=self._on_select_definition,
        )
        self.process_widget = MultiColumnListBox(
            process_height, ["<10", "<8", "<0"], options=[], titles=["uid", "pid", "command"]
        )
        columns = Layout([30, 1, 24])
        self.add_layout(columns)
        columns.add_widget(self.definition_widget, 0)
        columns.add_widget(VerticalDivider(), 1)
        columns.add_widget(self.process_widget, 2)

        layout = Layout([1])
        self.add_layout(layout)
        layout.add_widget(Divider())

        self.state_widget = MultiColumnListBox(state_height, ["<22", "<0"], options=[], titles=["Variable", "Value"])
        layout = Layout([1])
        self.add_layout(layout)
        layout.add_widget(self.state_widget)

        self.legend = Label("", height=2)  # the keys need two lines
        layout = Layout([1])
        self.add_layout(layout)
        layout.add_widget(self.legend)

        self.log_ui = LogUI(self)
        self.fix()  # Prepare asciimatics_Frame for use

    # The Service ------------------------------------------------------ #

    def _service_frame_start(self, service, service_ec_consumer):
        topic_path = service[0]
        if topic_path == self.topic_path:
            return  # idempotent
        self.topic_path = topic_path
        self.service_text = self._service_title.value
        self.proxy = aiko.get_service_proxy(f"{topic_path}/in", ProcessManager)
        self.request.start()
        self.log_ui._service_frame_start(service, service_ec_consumer)

    def _service_frame_stop(self, service):
        if self.topic_path is None:
            return
        self.request.stop()
        self.log_ui._service_frame_stop(service)
        self.topic_path = None
        self.proxy = None

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

    # Keys ------------------------------------------------------------- #

    def process_event(self, event):
        if isinstance(event, KeyboardEvent) and self.topic_path:
            action = self.page.action(event.key_code)
            if action is not None:
                self._act(action)
                return None
        return super().process_event(event)

    def _act(self, action):  # noqa: C901
        kind = action[0]
        if kind == "log_level":
            self.scene.add_effect(LogLevelPopupMenu(self._screen, self.state_widget, self.topic_path))
            return
        if kind == "help":
            self._popup(self.page.help_text(), ["OK"])
            return

        if kind == "definition":
            self._definition_form()
            return
        if kind == "json":
            self._popup(self.page.definition_text(self._definition_nodes()), ["OK"])
            return
        if kind == "enabled":
            self._toggle_enabled()  # the Category, not this Actor
            return

        may_send, why = self.page.may_send(self._cache(), self.page.function_of(kind))
        if not may_send:
            self._popup(why, ["OK"])
            return
        if kind == "create":
            self._create()
        elif kind == "destroy":
            self._destroy(kill=action[1])
        elif kind == "dump":
            if self._connected():
                self.proxy.dump()
        elif kind == "exit":
            self._confirm_exit()
        elif kind == "start":
            self._start()
        elif kind == "stop":
            self._stop()

    def _popup(self, text, buttons, on_close=None):
        self.scene.add_effect(PopUpDialog(self._screen, text, buttons, on_close=on_close, theme="nice"))

    def _selected_uid(self):
        row = self.process_widget.value
        if row is None or row >= len(self.process_widget.options):
            return None
        return self.process_widget.options[row][0][0]

    def _create(self):
        """Ask for a command line, then send (create COMMAND ARGUMENTS)"""

        text = Text("Command:", "command")
        text.value = ""  # a Text with no value raises on its draw

        def _on_close(button_index):
            words = text.value.split()
            if button_index == 1 and words and self._connected():
                self.proxy.create(words[0], words[1:])

        popup = PopUpDialog(
            self._screen, "Create a process" + " " * 36, ["Cancel", "Create"], on_close=_on_close, theme="nice"
        )
        layout = Layout([1])
        popup.add_layout(layout)
        layout.add_widget(text)
        popup.fix()
        self.scene.add_effect(popup)

    def _destroy(self, kill):
        uid = self._selected_uid()
        if uid is None:
            return self._popup("Select a process first.", ["OK"])

        def _on_close(button_index):
            if button_index == 1 and self._connected():
                self.proxy.destroy(uid, kill)

        signal = "SIGKILL" if kill else "SIGTERM"
        self._popup(f"Destroy <{uid}> with {signal}?", ["Cancel", "Destroy"], _on_close)

    def _confirm_exit(self):
        def _on_close(button_index):
            if button_index == 1 and self._connected():
                self.proxy.exit(0)

        self._popup("Destroy every process, then terminate the ProcessManager?", ["Cancel", "Exit"], _on_close)

    # The definition, held in a Category ------------------------------- #

    def _definition_form(self):
        """Name the HyperSpace and the Category path.  The Services that
        could hold one are a closed set, so they are chosen, not typed"""

        options = self.page.hyperspace_options(self._services())
        if not options:
            return self._popup(
                "No HyperSpace or Category Service is running.\n\n"
                "A definition is a Category of a HyperSpace, which has to"
                "\nbe running for this page to read it.  The Dashboard"
                '\nhides Categories until "f" then "c" says to show them.',
                ["OK"],
            )

        def accept(values):
            self.definition_topic = values["topic_path"]
            self.definition_path = values["path"].strip().strip("/")
            self.definition_proxy = aiko.get_service_proxy(f"{self.definition_topic}/in", HyperSpace)
            self.definition_tree.reset(self.definition_path or "/")
            self._definition_request(self.definition_path)

        self._form(
            "The definition Category",
            [
                choice_field("topic_path", "Service", options, self.definition_topic),
                text_field("path", "Path", self.definition_path),
            ],
            "Read",
            accept,
            note="A Category of Entries whose storage URL begins with"
            '\n"process:".  An empty path is the HyperSpace itself.',
        )

    def _form(self, title, fields, button, on_accept, note=""):
        self.scene.add_effect(FormFrame(self._screen, title, fields, button, on_accept, note=note))

    def _absolute(self, path):
        """A tree path is relative to the definition Category, so that the
        tree's root is that Category wherever it is"""

        return entry_path_join(self.definition_path, path) if self.definition_path else path

    def _definition_request(self, path=""):
        """Ask the HyperSpace for one Category, by its own path, and
        remember the relative path that the answer belongs to"""

        if self.definition_proxy is None or not self._connected():
            return
        absolute = self._absolute(path)
        self.request.request(path, lambda topic: self.definition_proxy.list(topic, absolute or None, True, False))

    def _definition_nodes(self):
        return self.definition_tree.rows()

    def _selected_definition(self):
        """(node, Process) for the selected definition row, or (None, …)"""

        path = self.definition_widget.value
        node = self.definition_tree.node(path) if path else None
        if node is None:
            return None, None
        process, _ = process_of_entry(node.entry)
        return node, process

    def _on_select_definition(self):
        node, process = self._selected_definition()
        if node is None:
            return
        if node.kind == CATEGORY:
            node.expanded = not node.expanded
            if node.expanded and not node.loaded:
                self._definition_request(node.path)
            return
        if process is None:
            _, diagnostic = process_of_entry(node.entry)
            return self._popup(f"{node.name}\n\n{diagnostic}\n\nstorage: {node.entry.storage_url}", ["OK"])
        self._popup(
            "\n".join(
                [
                    node.name,
                    "",
                    f"command   {command_line(process)}",
                    f"cwd       {process.cwd or '-'}",
                    f"enabled   {process.enabled}",
                    f"manager   {node.entry.lcm_url}",
                ]
            ),
            ["OK"],
        )

    def _start(self):
        node, process = self._selected_definition()
        if process is None:
            return self._popup("Select a process Entry first.", ["OK"])
        if not process.enabled:
            return self._popup(f'{node.name} is disabled.\n\nPress "e" to enable it, then "s" to start it.', ["OK"])

        def _on_close(button_index):
            if button_index == 1 and self._connected():
                # Positional, as the command line calls it: a remote proxy
                # turns keyword arguments into one dictionary argument
                self.proxy.create(process.command, process.arguments, None, process.cwd)

        self._popup(f"Start {command_line(process)} ?", ["Cancel", "Start"], _on_close)

    def _stop(self):
        node, process = self._selected_definition()
        if process is None:
            return self._popup("Select a process Entry first.", ["OK"])
        live = self.page.live_processes(self._cache())
        found = live.get(command_line(process))
        if found is None:
            return self._popup(f"No process of {node.name} is running.", ["OK"])
        uid = found[0]

        def _on_close(button_index):
            if button_index == 1 and self._connected():
                self.proxy.destroy(uid, False)

        self._popup(f"Stop <{uid}> {command_line(process)} ?", ["Cancel", "Stop"], _on_close)

    def _toggle_enabled(self):
        """Enable or disable an Entry, by updating the Category that holds
        it.  It changes what will run, and never what is running"""

        node, process = self._selected_definition()
        if process is None:
            return self._popup("Select a process Entry first.", ["OK"])
        if self.definition_proxy is None or not self._connected():
            return

        url = process_url(not process.enabled, command_line(process), process.cwd)
        self.definition_proxy.update(self._absolute(node.path), None, None, None, url)
        self._definition_request(entry_path_parent(node.path))
        self._diagnostic = f"{node.name}: {'enabled' if not process.enabled else 'disabled'}"

    # Drawing ---------------------------------------------------------- #

    def _update(self, frame_no):
        super()._update(frame_no)  # may start the Service
        if self.topic_path is None:
            return
        cache = self._cache()

        self._service_title.value = f"{self.service_text}    {self.page.title(cache)}"
        self.process_widget.options = [(row, index) for index, row in enumerate(self.page.process_rows(cache))]
        self.state_widget.options = [
            ((name, value), index) for index, (name, value) in enumerate(self.page.state_rows(cache))
        ]

        answer = self.request.take()
        if answer is not None:
            self._definition_merge(*answer)
        expired = self.request.expired()
        if expired is not None:
            self._diagnostic = f"{expired or self.definition_path}: no answer"

        self.definition_widget.options = [
            (columns, path) for columns, path in self.page.definition_rows(self._definition_nodes(), cache)
        ]
        if self.definition_topic is None:
            self._diagnostic = DEFINITION_ABSENT

        safe = self.page.read_safe(cache)
        if safe is False:
            keys = "keys: c create  d destroy  k kill  u dump  K exit"
        else:
            denied = "  ".join(FUNCTIONS_DENIED_WHEN_SAFE)
            keys = f"keys: (--safe denies {denied})"
        keys += "   n definition  s start  t stop  e enabled  J json  L log level  H help"
        self.legend.text = f"{keys}   {self._diagnostic}" if self._diagnostic else keys
        self.log_ui._update(frame_no)

    def _definition_merge(self, path, records):
        entries, diagnostics = parse_entry_records(records)
        if diagnostics:
            self._diagnostic = f"{path or '/'}: {' '.join(diagnostics)}"
            return
        self._diagnostic = ""
        self.definition_tree.merge(path, entries)


# plugin key: the protocol type of process_manager:0
plugins = {"process_manager": ProcessManagerFrame}

# --------------------------------------------------------------------------- #
