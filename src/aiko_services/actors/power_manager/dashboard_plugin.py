# Usage
# ~~~~~
# aiko_dashboard -p aiko_services.actors.power_manager.dashboard_plugin
#
# Select the "power_manager" Service and press Enter, or S.
#
# Design
# ~~~~~~
# Phase 4 of the power management plan.  The Dashboard's generic variable
# list already shows every one of this Actor's seventy shared items, in
# producer order, as "name value".  That is a dump and not a page: the
# three numbers an operator acts on are somewhere in it.
#
# Three parts, which is the shape of actors/display/dashboard_plugin.py:
#
# - PowerManagerPage is pure.  A replica of the shared state goes in, and
#   rows come out.  It has no asciimatics and no network, so it carries
#   the tests
# - PowerManagerFrame is the shell: layouts, widgets, keys
# - the log section is LogUI, unchanged, which every other page uses
#
# The page reads the Dashboard's own ECConsumer and never makes a second
# one: two consumers of one producer each hold a lease.  It polls that
# replica in _update() rather than adding a handler, which also avoids
# the fact that _service_frame_stop() is not called on quit, on a crash
# or on a resize.
#
# The posture
# ~~~~~~~~~~~
# This Actor runs "--safe" by default and denies (set_threshold ...),
# which stops a host.  The page follows the ProcessManager's page: it
# reads the posture out of the replica, says which it is, and explains
# the denial with the command that lifts it.  Read-only against a safe
# host, read-write against an unsafe one.
#
# To Do
# ~~~~~
# - The chart view: a live window, panning and zoom (increment 4b)
# - The Recorder, so log records survive a page visit (increment 4c)
# - History from the Actor's own log, for a chart that opens full
#   (increment 4d, and it is a new read plane: the lead decides)
# - [Save], once it is decided where a changed threshold is persisted

from asciimatics.widgets import Label, Layout, MultiColumnListBox, Widget

import aiko_services as aiko
from aiko_services.ide.tui.dashboard import (
    LogUI, ServiceFrame, display_value,
)
from aiko_services.main.connection import ConnectionState

from aiko_services.actors.power_manager.power_manager import (
    PowerManager, THRESHOLDS,
)

__all__ = ["ChartWidget", "PowerManagerFrame", "PowerManagerPage", "plugins"]

# The views, in the order "v" cycles them
SUMMARY, DETAIL, INFORMATION = "summary", "detail", "information"
VIEWS = (SUMMARY, DETAIL, INFORMATION)

# What the bottom section shows, which "w" switches
RECORDS, TELEMETRY = "records", "telemetry"
SOURCES = (RECORDS, TELEMETRY)

# The keys this page claims.  Everything here is outside the set the
# Dashboard reserves ("?", Tab, Enter, x, X, D, L, S, l, c, f, s, C, K),
# and the first three are proposed for every page, so that a person who
# learns them here does not learn them again elsewhere
KEYS = {
    "v": ("view", 1),
    "V": ("view", -1),
    "I": ("information",),
    "H": ("help",),
    "w": ("source",),
}

TELEMETRY_FIELDS = (
    "sampled_utc", "supply.volts", "supply.amps", "battery.volts",
    "battery.amps", "battery.pack_celsius", "cpu.celsius", "docked",
    "mode", "policy_reason",
)

# The thresholds, grouped as they are governed.  A person editing the
# voltages wants all of them at once, because the rule between them is
# a ladder: five dialogs to change one ladder is five chances to leave it
# inconsistent
# "hold_time_s", "remount_grace_s" and "hold_release_delay_s" are absent,
# because they are module constants in button.py, quiesce.py and render.py
# rather than entries in THRESHOLDS.  §3.3 of the plan says no threshold is
# a constant in the code, and three of them still are.  This page can only
# edit what the Actor can be asked to change
GROUPS = (
    ("voltages", ("battery_volts_floor", "battery_volts_low",
        "quiesce_volts", "battery_volts_charged")),
    ("graces and deadlines", ("powered_down_grace_s",
        "powered_down_application_grace_s", "powered_up_grace_s",
        "undocked_maximum_s", "dock_dwell_s", "battery_dwell_s")),
    ("supply", ("supply_amps_maximum", "supply_amps_fraction",
        "supply_headroom_volts", "supply_warning_dwell_s")),
    ("up-time", ("powered_up_maximum_s", "powered_up_requests_maximum")),
    ("working", ("working_dwell_s", "working_loss_s",
        "working_reporters_maximum")),
    ("temperature", ("battery_pack_celsius_maximum",)),
)

# Every word this Actor can publish, and what it means.  A page that
# shows a token an operator has to look up somewhere else has not
# finished the job, so a test asserts that nothing is missing from here
INFORMATION_TEXT = (
    ("policy", "What this Actor does with its own decision"),
    ("  advisory", "It decides, publishes and logs, and acts on nothing"),
    ("  hold", "It keeps this host powered"),
    ("  shutdown_pending", "A shutdown was decided and could not be done"),
    ("  shutting_down", "A shutdown is under way"),
    ("", ""),
    ("policy_reason", "Why the decision is what it is"),
    ("  button_held", "A person held the soft power button"),
    ("  battery_floor", "The battery pack is at the voltage it must "
        "not go below"),
    ("  battery_low", "The battery pack is low, so an orderly shutdown "
        "starts"),
    ("  battery_pack_temperature", "The battery pack is too warm.  The "
        "battery pack, never the processor"),
    ("  no_hold_property", "This host cannot hold its own power"),
    ("  docked", "The supply is present, so there is nothing to decide"),
    ("  undocked_timeout", "The backstop on an undocked hold expired"),
    ("  powered_down_grace", "The deployment's own deadline expired"),
    ("  powered_up_held", "A client holds a powered-up Lease"),
    ("  powered_up_idle", "No client holds one"),
    ("  powered_up_grace", "The wait after the last Lease was released"),
    ("  hook_missing", "The shutdown hook is not installed, so a "
        "shutdown would not release the hold"),
    ("  application_grace", "The wait before a writer is told to stop"),
    ("", ""),
    ("mode", "What an application is being asked to do"),
    ("  normal", "Write as usual"),
    ("  conserve", "The supply is gone.  Finish, and expect to stop"),
    ("  quiesce", "Stop writing now.  The file systems go read-only"),
    ("", ""),
    ("mode_reason", "Why the mode is what it is"),
    ("  policy", "The policy decided to stop this host"),
    ("  docked", "The supply is present"),
    ("  battery", "The battery pack reached the quiesce voltage"),
    ("  hook_missing", "The shutdown hook is not installed"),
    ("  held", "Quiesce never returns to normal without a dock"),
    ("  application_grace", "The wait before a writer is told to stop"),
    ("  undocked", "The supply is gone"),
    ("", ""),
    ("supply_warning", "The supply is too small for the load it carries"),
    ("  supply_current", "The supply is drawing near its rated current"),
    ("  supply_headroom", "The supply sits too close to the battery "
        "pack to charge it, and the battery pack is not charged"),
    ("", ""),
    ("writing_ok", "Whether an application should write to the file "
        "systems"),
    ("working.lost", "Every reporter has been silent for "
        "working_loss_s"),
    ("enforce", "Whether a measured threshold may stop this host.  "
        "Advisory means it may not"),
    ("safe", "The posture.  Safe denies every function that stops a "
        "host, including set_threshold"),
    ("hold_state", "Whether the power hold is on"),
    ("hook", "Whether the shutdown hook is installed"),
    ("", ""),
    ("A threshold", "is not persisted.  The command line wins at the "
        "next restart"),
    ("The log file", "rolls on the UTC day, so today's file keeps "
        "yesterday's name until UTC midnight"),
    ("The log section", "shows this process's records, so Services "
        "sharing a process share the stream"),
)

# --------------------------------------------------------------------------- #

def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _age(seconds):
    """A duration a person reads, from seconds"""

    value = _number(seconds)
    if value is None:
        return "-"
    value = int(value)
    if value < 60:
        return f"{value} s"
    if value < 3600:
        return f"{value // 60} m {value % 60:02d} s"
    return f"{value // 3600} h {(value % 3600) // 60:02d} m"

class PowerManagerPage:
    """The decisions, with no terminal and no network.

    Everything a test needs is here: which view is showing, what each key
    does, and what rows a replica of the shared state produces"""

    def __init__(self):
        self.view = SUMMARY
        self.source = RECORDS

    def action(self, key_code):
        """What a key does, or None where this page does not claim it"""

        if key_code < 0 or key_code > 0x10FFFF:
            return None            # A function key, which is not a character
        return KEYS.get(chr(key_code))

    def cycle_view(self, step):
        self.view = VIEWS[(VIEWS.index(self.view) + step) % len(VIEWS)]
        return self.view

    def cycle_source(self):
        self.source = SOURCES[
            (SOURCES.index(self.source) + 1) % len(SOURCES)]
        return self.source

    @staticmethod
    def read_safe(cache):
        """The posture, out of a replica.  None where the Actor is older
        than the posture itself.  This is the ProcessManager page's own
        reader, and it is here rather than imported because "main" must
        not depend on "actors" and this page is in "actors" """

        safe = cache.get("safe")
        if safe is None or isinstance(safe, bool):
            return safe
        return str(safe).lower() == "true"

    @classmethod
    def editable(cls, cache):
        """Whether this page may change anything on this Actor"""

        return cls.read_safe(cache) is False

    def legend(self, cache):
        """The footer: where you are, and what the posture allows"""

        posture = self.read_safe(cache)
        if posture is None:
            where = "posture: unknown"
        else:
            where = f"posture: {'safe' if posture else 'UNSAFE'}"
        keys = "v view  I information  w log  H help"
        if posture is not False:
            keys = f"{keys}   (--safe denies Enter: edit)"
        return f"{self.view}   {where}   {keys}"

# The rows ------------------------------------------------------------- #

    @staticmethod
    def _get(cache, *path, default="-"):
        value = cache
        for name in path:
            if not isinstance(value, dict):
                return default
            value = value.get(name)
            if value is None:
                return default
        return value

    def summary_rows(self, cache):
        """The headline: what an operator acts on, and nothing else"""

        get = self._get
        if not cache:
            return [("waiting", "for this Service's shared state")]
        margin = get(cache, "battery", "margin_volts")
        floor = get(cache, "thresholds", "battery_volts_floor")
        warning = get(cache, "supply_warning")
        rows = [
            ("supply", f"{get(cache, 'supply', 'volts')} V   "
                f"{get(cache, 'supply', 'amps')} A   "
                f"{get(cache, 'supply', 'watts')} W"),
            ("battery pack", f"{get(cache, 'battery', 'volts')} V   "
                f"{get(cache, 'battery', 'amps')} A   "
                f"{get(cache, 'battery', 'watts')} W   "
                f"{get(cache, 'battery', 'pack_celsius')} °C"),
            ("  above the floor", f"{margin} V   (floor {floor} V)"),
            ("processor", f"{get(cache, 'cpu', 'celsius')} °C   "
                f"cpu {get(cache, 'cpu', 'percent')} %   "
                f"load {get(cache, 'load', '1m')}   "
                f"memory {get(cache, 'memory', 'percent')} %"),
            ("docked", f"{get(cache, 'docked')}"),
            ("policy", f"{get(cache, 'policy')}   because "
                f"{get(cache, 'policy_reason')}"),
            ("  would / acting", f"{get(cache, 'policy_would')} / "
                f"{get(cache, 'policy_acting')}"),
            ("mode", f"{get(cache, 'mode')}   because "
                f"{get(cache, 'mode_reason')}   "
                f"writing_ok {get(cache, 'writing_ok')}"),
            ("supply warning", "none" if warning == "-" else warning),
            ("undocked since", display_value(
                get(cache, "undocked_since_utc"))),
            ("up-time held", f"{get(cache, 'powered_up', 'held')}   "
                f"{get(cache, 'powered_up', 'reasons')}"),
            ("working", f"{get(cache, 'working', 'last')}   "
                f"{_age(get(cache, 'working', 'age_s'))} ago   "
                f"lost {get(cache, 'working', 'lost')}"),
            ("hold / hook", f"{get(cache, 'hold_state')} / "
                f"{get(cache, 'hook')}"),
            ("sampled", display_value(get(cache, "sampled_utc"))),
            ("metrics", f"samples {get(cache, 'metrics', 'samples')}   "
                f"denied {get(cache, 'metrics', 'denied')}   "
                f"shutdowns {get(cache, 'metrics', 'shutdowns')}   "
                f"warnings {get(cache, 'metrics', 'supply_warnings')}"),
            ("last error", f"{get(cache, 'last_error')}"),
        ]
        return rows

    def detail_rows(self, cache):
        """Everything, under headings, with the editable rows marked"""

        if not cache:
            return [("waiting", "for this Service's shared state")]
        editable = self.editable(cache)
        mark = "  (Enter)" if editable else "  (--safe)"
        rows = [("Service", ""),
            ("  device", f"{self._get(cache, 'device')}"),
            ("  posture", "unsafe" if editable else "safe"),
            ("  log directory", f"{self._get(cache, 'log')}"),
            ("  sample period", f"{self._get(cache, 'sample_period_s')} s"),
        ]
        for heading, names in GROUPS:
            rows.append((f"{heading}{mark}", ""))
            for name in names:
                if name not in THRESHOLDS:
                    continue       # An Actor older than this threshold
                rows.append((f"  {name}",
                    f"{self._get(cache, 'thresholds', name)}"))
        for heading, group in (
            ("readings", ("supply", "battery", "cpu", "memory", "load")),
            ("up-time", ("powered_up",)),
            ("quiesce", ("quiesce",)),
            ("working", ("working",)),
            ("metrics", ("metrics",)),
        ):
            rows.append((heading, ""))
            for name in group:
                values = cache.get(name)
                if not isinstance(values, dict):
                    continue
                for key in sorted(values):
                    rows.append((f"  {name}.{key}", f"{values[key]}"))
        return rows

    @staticmethod
    def information_rows():
        return list(INFORMATION_TEXT)

    def rows(self, cache):
        if self.view == SUMMARY:
            return self.summary_rows(cache)
        if self.view == DETAIL:
            return self.detail_rows(cache)
        return self.information_rows()

    @staticmethod
    def group_of(row_name):
        """The threshold group a detail row belongs to, or None.

        A heading selects its own group, and so does any row under it,
        so an operator never has to find the heading first"""

        name = row_name.strip().removesuffix("(Enter)").removesuffix(
            "(--safe)").strip()
        for heading, names in GROUPS:
            if name == heading or name in names:
                return heading, names
        return None

# --------------------------------------------------------------------------- #

class ChartWidget(Widget):
    """The live chart.  Increment 4b fills this in; it exists now so the
    view cycle and the layout do not change when it does"""

    def __init__(self, page, rows, name=None):
        super().__init__(name, tab_stop=False)
        self.page = page
        self.rows = rows
        self.message = "chart: increment 4b"

    def update(self, frame_no):
        self._frame.canvas.print_at(
            self.message[:self._w], self._x, self._y)

    def reset(self):
        pass

    def process_event(self, event):
        return event

    def required_height(self, offset, width):
        return self.rows

    @property
    def value(self):
        return None

# --------------------------------------------------------------------------- #

class PowerManagerFrame(ServiceFrame):
    """The page: the view, the log section below it, and the keys"""

    def __init__(self, screen, dashboard):
        super().__init__(screen, dashboard, name="power_manager_frame")
        self.page = PowerManagerPage()
        self.topic_path = None
        self.proxy = None

        # Three quarters to the view and one quarter to the log, which is
        # what the lead asked for.  The view is the fixed one and LogUI
        # fills what is left, because LogUI's own layout is the Frame's
        # one filler and a Frame allows only one
        view_height = max(6, (screen.height - 5) * 3 // 4)
        layout = Layout([1])
        self.add_layout(layout)
        self.view_widget = MultiColumnListBox(view_height, ["<22", "<0"],
            options=[], titles=["Name", "Value"],
            on_select=self._on_select_row)
        layout.add_widget(self.view_widget)
        layout = Layout([1])
        self.add_layout(layout)
        self.legend = Label("", height=1)
        layout.add_widget(self.legend)
        self.log_ui = LogUI(self)
        self.fix()

    def _cache(self):
        """The Dashboard's own ECConsumer, never a second one of our own"""

        consumer = self.dashboard.ec_consumer
        return consumer.cache if consumer is not None else {}

    @staticmethod
    def _connected():
        return aiko.process.connection.is_connected(ConnectionState.TRANSPORT)

# The Service ---------------------------------------------------------- #

    def _service_frame_start(self, service, service_ec_consumer):
        topic_path = service[0]
        if topic_path == self.topic_path:
            return                                       # idempotent
        self.topic_path = topic_path
        self.proxy = aiko.get_service_proxy(
            f"{topic_path}/in", PowerManager)
        self.log_ui._service_frame_start(service, service_ec_consumer)

    def _service_frame_stop(self, service):
        if self.topic_path is None:
            return
        self.log_ui._service_frame_stop(service)
        self.topic_path = None
        self.proxy = None

# The keys ------------------------------------------------------------- #

    def process_event(self, event):
        from asciimatics.event import KeyboardEvent

        if isinstance(event, KeyboardEvent):
            action = self.page.action(event.key_code)
            if action is not None:
                self._act(action)
                return None
        self.log_ui.process_event(event)
        return super().process_event(event)

    def _act(self, action):
        from asciimatics.widgets import PopUpDialog

        name = action[0]
        if name == "view":
            self.page.cycle_view(action[1])
        elif name == "information":
            self.page.view = INFORMATION
        elif name == "source":
            self.page.cycle_source()
        elif name == "help":
            self.scene.add_effect(PopUpDialog(
                self._screen, self._help(), ["OK"], theme="nice"))

    @staticmethod
    def _help():
        return (
            " Help   Power manager\n"
            " ----   -------------\n"
            " v V    Next view, previous view\n"
            " I      Information: what every value means\n"
            " w      Log section: records or telemetry\n"
            " Enter  Edit the thresholds under the cursor\n"
            " H ?    This help\n"
            " D      Back to the Dashboard\n"
            " x      Exit\n"
            "\n"
            " A threshold is denied in the safe posture, and it is not\n"
            " persisted: the command line wins at the next restart")

    def _on_select_row(self):
        """Enter on a row: edit the group of thresholds it belongs to"""

        from asciimatics.widgets import PopUpDialog

        cache = self._cache()
        row = self.view_widget.value
        if self.page.view != DETAIL or row is None:
            return
        rows = self.page.rows(cache)
        if row >= len(rows):
            return
        group = self.page.group_of(rows[row][0])
        if group is None:
            return
        if not self.page.editable(cache):
            self.scene.add_effect(PopUpDialog(self._screen,
                " This power manager runs --safe, so it denies\n"
                " (set_threshold ...), which can stop a host.\n\n"
                " To change a threshold, restart it with:\n\n"
                "     aiko_power_manager run --unsafe\n",
                ["OK"], theme="nice"))
            return
        self._edit_group(group, cache)

    def _edit_group(self, group, cache):
        """One form for the whole group, because the rule between the
        thresholds in it is a ladder: editing one at a time is a chance
        to leave it inconsistent at every step"""

        from aiko_services.ide.tui.dashboard import (
            FormFrame, text_field,
        )

        heading, names = group
        fields = []
        for name in names:
            if name not in THRESHOLDS:
                continue
            value = self.page._get(cache, "thresholds", name)
            fields.append(text_field(name, name, f"{value}"))

        def accept(values):
            if not self._connected():
                return
            for name, value in values.items():
                was = self.page._get(cache, "thresholds", name)
                if f"{value}".strip() != f"{was}".strip():
                    self.proxy.set_threshold(name, f"{value}".strip())

        self.scene.add_effect(FormFrame(self._screen,
            f"Thresholds: {heading}", fields, "Accept", accept,
            note='"-" turns a threshold off, where it may be.  '
                 "A change is not persisted: the command line wins at "
                 "the next restart"))

# The draw ------------------------------------------------------------- #

    def _update(self, frame_no):
        super()._update(frame_no)          # It may start the Service
        cache = self._cache()
        rows = self.page.rows(cache)
        self.view_widget.options = [
            (list(row), index) for index, row in enumerate(rows)]
        self.legend.text = self.page.legend(cache)
        self.log_ui._update(frame_no)

plugins = {"power_manager": PowerManagerFrame}

# --------------------------------------------------------------------------- #
