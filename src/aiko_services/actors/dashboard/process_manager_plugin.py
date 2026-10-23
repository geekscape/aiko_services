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
    Label, Layout, MultiColumnListBox, PopUpDialog, Text,
)

import aiko_services as aiko
from aiko_services.main.connection import ConnectionState
from aiko_services.actors.dashboard import (
    LogLevelPopupMenu, LogUI, ServiceFrame,
)
from aiko_services.main.process_manager import (
    ProcessManager, SAFE_FUNCTIONS, parse_process_share,
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
    "L": ("log_level",),
    "H": ("help",),
}

# The functions this page sends, and the shared-state key that reports
# whether the Actor is in safe mode
FUNCTIONS_DENIED_WHEN_SAFE = tuple(
    sorted({"create", "destroy", "dump", "exit"} - set(SAFE_FUNCTIONS)))

STATE_KEYS = (
    "safe", "watchdog", "definition_pathname", "lifecycle", "log_level",
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
                "It is an Actor from before --safe existed.")
        return False, (
            f"This ProcessManager runs --safe, so it denies ({function} ...)"
            " from the message bus.\n\n"
            "Each of "
            + ", ".join(FUNCTIONS_DENIED_WHEN_SAFE)
            + " needs an Actor started with:\n"
            "    aiko_process run --unsafe\n\n"
            "The command line and the definition file are not affected,"
            " because neither goes through the bus.")

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

        rows = [(name, str(cache[name]))
            for name in STATE_KEYS if name in cache]
        metrics = cache.get("metrics")
        if isinstance(metrics, dict):
            rows += [(f"metrics.{name}", str(metrics[name]))
                for name in sorted(metrics)]
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

    @staticmethod
    def help_text():
        return "\n".join([
            "The ProcessManager's functions, sent on its in topic:",
            "  c create a process      u dump the state to its log",
            "  d destroy (SIGTERM)     k destroy (SIGKILL)",
            "  K exit: destroy every process, then terminate the Actor",
            "",
            "A ProcessManager runs --safe by default, and denies every one",
            "of those, dump included.  This page says so rather than",
            "appearing to act.  Start it with --unsafe to use them.",
            "",
            "This page: L log level  H this help",
            "Esc Backspace q back  x quit the Dashboard",
        ])

class ProcessManagerFrame(ServiceFrame):
    """The Dashboard page: the process table, the state, the log"""

    def __init__(self, screen, dashboard):
        super().__init__(screen, dashboard, name="process_manager_frame")

        self.page = ProcessManagerPage()
        self.topic_path = None
        self.service_text = ""
        self.proxy = None

    # The state table gets its rows first, so that "last_error" and the
    # metrics are visible on an 80x24 terminal.  The posture and the count
    # of denials are in the title bar as well, because they are what an
    # operator came to see
        state_height = min(len(STATE_KEYS) + 3, max(5, screen.height // 3))
        process_height = max(3, screen.height - state_height - 13)

        self.process_widget = MultiColumnListBox(process_height,
            ["<10", "<8", "<0"], options=[],
            titles=["uid", "pid", "command"])
        layout = Layout([1])
        self.add_layout(layout)
        layout.add_widget(self.process_widget)

        self.state_widget = MultiColumnListBox(state_height,
            ["<22", "<0"], options=[], titles=["Variable", "Value"])
        layout = Layout([1])
        self.add_layout(layout)
        layout.add_widget(self.state_widget)

        self.legend = Label("", height=1)
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
        self.topic_path = topic_path
        self.service_text = self._service_title.value
        self.proxy = aiko.get_service_proxy(
            f"{topic_path}/in", ProcessManager)
        self.log_ui._service_frame_start(service, service_ec_consumer)

    def _service_frame_stop(self, service):
        if self.topic_path is None:
            return
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

    # Keys ------------------------------------------------------------- #

    def process_event(self, event):
        if isinstance(event, KeyboardEvent) and self.topic_path:
            action = self.page.action(event.key_code)
            if action is not None:
                self._act(action)
                return None
        return super().process_event(event)

    def _act(self, action):
        kind = action[0]
        if kind == "log_level":
            self.scene.add_effect(LogLevelPopupMenu(
                self._screen, self.state_widget, self.topic_path))
            return
        if kind == "help":
            self._popup(self.page.help_text(), ["OK"])
            return

        may_send, why = self.page.may_send(self._cache(), kind)
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

    def _popup(self, text, buttons, on_close=None):
        self.scene.add_effect(PopUpDialog(
            self._screen, text, buttons, on_close=on_close, theme="nice"))

    def _selected_uid(self):
        row = self.process_widget.value
        if row is None or row >= len(self.process_widget.options):
            return None
        return self.process_widget.options[row][0][0]

    def _create(self):
        """Ask for a command line, then send (create COMMAND ARGUMENTS)"""

        text = Text("Command:", "command")

        def _on_close(button_index):
            words = text.value.split()
            if button_index == 1 and words and self._connected():
                self.proxy.create(words[0], words[1:])

        popup = PopUpDialog(self._screen,
            "Create a process" + " " * 36, ["Cancel", "Create"],
            on_close=_on_close, theme="nice")
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
        self._popup(f"Destroy <{uid}> with {signal}?",
            ["Cancel", "Destroy"], _on_close)

    def _confirm_exit(self):
        def _on_close(button_index):
            if button_index == 1 and self._connected():
                self.proxy.exit(0)

        self._popup(
            "Destroy every process, then terminate the ProcessManager?",
            ["Cancel", "Exit"], _on_close)

    # Drawing ---------------------------------------------------------- #

    def _update(self, frame_no):
        super()._update(frame_no)                 # may start the Service
        if self.topic_path is None:
            return
        cache = self._cache()

        self._service_title.value =  \
            f"{self.service_text}    {self.page.title(cache)}"
        self.process_widget.options = [(row, index)
            for index, row in enumerate(self.page.process_rows(cache))]
        self.state_widget.options = [((name, value), index)
            for index, (name, value) in enumerate(self.page.state_rows(cache))]

        safe = self.page.read_safe(cache)
        if safe is False:
            self.legend.text = "keys: c create  d destroy  k kill  " \
                               "u dump  K exit  L log level  H help"
        else:
            denied = "  ".join(FUNCTIONS_DENIED_WHEN_SAFE)
            self.legend.text = f"keys: L log level  H help   " \
                               f"(--safe denies {denied})"
        self.log_ui._update(frame_no)

# plugin key: the protocol type of process_manager:0
plugins = {"process_manager": ProcessManagerFrame}

# --------------------------------------------------------------------------- #
