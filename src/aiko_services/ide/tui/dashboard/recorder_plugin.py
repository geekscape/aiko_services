#!/usr/bin/env python3
#
# Aiko Services: the Recorder's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# What a Recorder holds: the topics it records, the newest log record of
# each one, the filters it listens on, and how much it has let go.
#
# Registered through "plugins.py", the Dashboard's default "--plugin"
# module, so this page needs no flag.  The key is the protocol type.
#
# Design
# ~~~~~~
# asciimatics has no screen double, so the decisions live in RecorderPage,
# which is pure, and the Frame below is the thin part.  That is the
# division the Display Actor's page and the ProcessManager's page use.
#
# State comes from the Dashboard's own ECConsumer, never from a second
# consumer of this page's own: two consumers of one producer would each
# hold a lease, and the Dashboard already has one.
#
# A "lru_cache.<topic>" item holds either the newest record, as a string,
# or every record the ring buffer holds, as a list.  The Recorder decides
# which, and this page reads both, so it needs no change when that
# question is settled.
#
# Unlike the ProcessManager's page, every function this page sends is one
# the Recorder allows in each posture, so there is no posture to explain.
#
# To Do
# ~~~~~
# - Follow one topic live, in its own pane
# - Edit a size here, as the Display Actor's page edits a setting

from asciimatics.event import KeyboardEvent
from asciimatics.widgets import (
    Label, Layout, MultiColumnListBox, PopUpDialog, Text,
)

import aiko_services as aiko
from aiko_services.main.connection import ConnectionState
from aiko_services.ide.tui.dashboard import (
    LogLevelPopupMenu, LogUI, ServiceFrame,
)
from aiko_services.main.recorder import Recorder

__all__ = ["RecorderFrame", "RecorderPage", "plugins"]

KEYS = {
    "r": ("record_start",),
    "R": ("record_stop",),
    "L": ("log_level",),
    "H": ("help",),
}

STATE_KEYS = (
    "filters", "lru_cache_size", "ring_buffer_size", "records_period",
    "lifecycle", "log_level",
)

RECORD_WIDTH = 96          # a log record is long; the table shows the start

class RecorderPage:
    """The page's decisions, with no screen and no network"""

    def action(self, key_code):
        """What a key asks for, or None when this page does not take it"""

        if key_code < 0 or key_code > 0x10FFFF:
            return None
        return KEYS.get(chr(key_code))

    @staticmethod
    def records(cache, topic):
        """Every record the shared state holds for one topic, oldest
        first.  The item is a string when the Recorder publishes only the
        newest record, and a list when it publishes the whole ring"""

        topics = cache.get("lru_cache")
        if not isinstance(topics, dict) or topic not in topics:
            return []
        item = topics[topic]
        if isinstance(item, (list, tuple)):
            return [str(record) for record in item]
        return [str(item)]

    @staticmethod
    def topic_rows(cache):
        """[(topic, held, newest)] for each recorded topic, by topic"""

        topics = cache.get("lru_cache")
        if not isinstance(topics, dict):
            return []
        rows = []
        for topic in sorted(topics):
            records = RecorderPage.records(cache, topic)
            newest = records[-1] if records else ""
            rows.append((topic, str(len(records)), newest[:RECORD_WIDTH]))
        return rows

    @staticmethod
    def filters(cache):
        """Each filter the Recorder listens on"""

        item = cache.get("filters")
        if isinstance(item, (list, tuple)):
            return [str(value) for value in item]
        return [str(item)] if item else []

    @staticmethod
    def state_rows(cache):
        """[(name, value)]: what this Recorder is, then its metrics"""

        rows = []
        for name in STATE_KEYS:
            if name not in cache:
                continue
            value = cache[name]
            if isinstance(value, (list, tuple)):
                value = " ".join(str(item) for item in value) or "-"
            rows.append((name, str(value)))
        metrics = cache.get("metrics")
        if isinstance(metrics, dict):
            rows += [(f"metrics.{name}", str(metrics[name]))
                for name in sorted(metrics)]
        return rows

    @staticmethod
    def title(cache):
        """What the page says beside the Service: how much it holds, and
        how much it has let go"""

        metrics = cache.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        topics = len(RecorderPage.topic_rows(cache))
        return (f"topics: {topics}   records: {metrics.get('records', 0)}"
                f"   evicted: {metrics.get('evicted', 0)}")

    @staticmethod
    def help_text():
        return "\n".join([
            "The Recorder's functions, sent on its in topic:",
            "  r record_start: record the topics matching a filter",
            "  R record_stop:  stop a filter, and forget what it recorded",
            "",
            "A Recorder holds one ring buffer for each topic, inside an",
            "LRU cache of topics, so the topic that has gone longest",
            "without a record is the one it lets go of.  Both sizes are",
            "shared variables, and small ones show the edge cases sooner:",
            "  aiko_recorder -l 2 -r 2",
            "",
            "This page: Enter the records of the selected topic",
            "  L log level  H this help",
            "Esc Backspace q back  x quit the Dashboard",
        ])

class RecorderFrame(ServiceFrame):
    """The Dashboard page: the topics, the state, the log"""

    def __init__(self, screen, dashboard):
        super().__init__(screen, dashboard, name="recorder_frame")

        self.page = RecorderPage()
        self.topic_path = None
        self.service_text = ""
        self.proxy = None

        state_height = min(len(STATE_KEYS) + 4, max(5, screen.height // 3))
        topic_height = max(3, screen.height - state_height - 13)

        self.topic_widget = MultiColumnListBox(topic_height,
            ["<34", "<6", "<0"], options=[],
            titles=["Topic", "Held", "Newest record"],
            on_select=self._show_records)
        layout = Layout([1])
        self.add_layout(layout)
        layout.add_widget(self.topic_widget)

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
        self.proxy = aiko.get_service_proxy(f"{topic_path}/in", Recorder)
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
                self._act(action[0])
                return None
        return super().process_event(event)

    def _act(self, kind):
        if kind == "log_level":
            self.scene.add_effect(LogLevelPopupMenu(
                self._screen, self.state_widget, self.topic_path))
        elif kind == "help":
            self._popup(self.page.help_text(), ["OK"])
        elif kind == "record_start":
            self._filter_dialog("Record the topics matching", "Record",
                lambda filter: self.proxy.record_start(filter))
        elif kind == "record_stop":
            filters = self.page.filters(self._cache())
            self._filter_dialog("Stop recording", "Stop",
                lambda filter: self.proxy.record_stop(filter),
                filters[0] if filters else "")

    def _popup(self, text, buttons, on_close=None):
        self.scene.add_effect(PopUpDialog(
            self._screen, text, buttons, on_close=on_close, theme="nice"))

    def _filter_dialog(self, prompt, button, send, value=""):
        text = Text("Filter:", "filter")
        text.value = value

        def _on_close(button_index):
            if button_index == 1 and text.value and self._connected():
                send(text.value)

        popup = PopUpDialog(self._screen, prompt + " " * 30,
            ["Cancel", button], on_close=_on_close, theme="nice")
        layout = Layout([1])
        popup.add_layout(layout)
        layout.add_widget(text)
        popup.fix()
        self.scene.add_effect(popup)

    def _show_records(self):
        """Enter on a topic: every record the shared state holds for it"""

        row = self.topic_widget.value
        if row is None or row >= len(self.topic_widget.options):
            return
        topic = self.topic_widget.options[row][0][0]
        records = self.page.records(self._cache(), topic)
        if not records:
            return self._popup(f"No records for {topic}", ["OK"])
        text = "\n".join(record[:RECORD_WIDTH] for record in records[-16:])
        self._popup(f"{topic}\n\n{text}", ["OK"])

    # Drawing ---------------------------------------------------------- #

    def _update(self, frame_no):
        super()._update(frame_no)                 # may start the Service
        if self.topic_path is None:
            return
        cache = self._cache()

        self._service_title.value =  \
            f"{self.service_text}    {self.page.title(cache)}"
        self.topic_widget.options = [(row, index)
            for index, row in enumerate(self.page.topic_rows(cache))]
        self.state_widget.options = [((name, value), index)
            for index, (name, value) in enumerate(self.page.state_rows(cache))]
        self.legend.text = "keys: r record_start  R record_stop  " \
                           "Enter the records  L log level  H help"
        self.log_ui._update(frame_no)

# plugin key: the protocol type of recorder:0
plugins = {"recorder": RecorderFrame}

# --------------------------------------------------------------------------- #
