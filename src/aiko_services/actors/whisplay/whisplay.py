#!/usr/bin/env python3
#
# Aiko Services: the WhisPlay Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Replaces the vendor WhisPlay demonstration that /etc/rc.local used to
# start.  It shows the camera on the panel, and a long button press performs
# the "action", which is a clean shutdown by default.
#
# Shared variables ...
#   action      "power_off"  what a long button press does
#   rate        "3.0"        frames each second
#   resolution  "240x180"    what is read from the camera
#
# Threads, which is the part to read first (P11, ADR-027) ...
# - State is mutated only on the event-loop thread.  The worker thread and
#   the button thread never touch self.share
# - The worker and the button post work with _post_message()
# - Settings go the other way, into the worker, through a Queue.  There are
#   no locks, and no shared mutable data
#
# The panel is driven directly, in colour.  The "display:0" protocol is one
# bit at 128x64 and has no image command, so a camera frame cannot go
# through it.  Epic 4 absorbs this Actor's panel when display:0 gains a real
# depth.
#
# To Do
# ~~~~~
# * A short press and a double press, for the menu and the demonstration
# * Take any video source through a DataSource, not only this camera
# * The RGB LEDs, as their own Actor

from abc import abstractmethod
import os
import queue
import socket
import subprocess
import time
from threading import Thread

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname, parse

from aiko_services.actors.whisplay.button import LONG_PRESS_SECONDS
from aiko_services.actors.whisplay.camera import CameraNotFound
from aiko_services.actors.whisplay.frame import compose, parse_resolution

__all__ = [
    "ACTIONS", "PROTOCOL", "SETTINGS", "WIRE_COMMANDS", "WhisPlay",
    "WhisPlayImpl"
]

PROTOCOL = f"{aiko.SERVICE_PROTOCOL_AIKO}/whisplay:0"
PROTOCOL_TYPE = "whisplay"

ACTIONS = ("power_off", "none")        # What a long press may do
SETTINGS = ("action", "rate", "resolution")
RATE_LOW, RATE_HIGH = 0.1, 30.0
REOPEN_PERIOD = 10.0                   # Seconds, before trying a device again
_THREAD_NAME = "whisplay"

class WhisPlay(aiko.Actor):
    """Shows the camera on the WhisPlay panel, and performs an action on a
    long button press.  There are no wire commands of its own: the settings
    are changed as shared variables, with (update NAME VALUE) on the control
    topic.  That is deliberate, because "action" decides whether a press
    halts the host, and nothing on the bus should reach that directly"""

    PROTOCOL = PROTOCOL

    aiko.Interface.default(
        "WhisPlay", "aiko_services.actors.whisplay.whisplay.WhisPlayImpl")

# P12, ADR-023: deny by default.  This Actor adds no wire command of its own
WIRE_COMMANDS = frozenset({"set_log_level", "stop"})

class WhisPlayImpl(WhisPlay):
    def __init__(self, context, panel=None, camera=None, button=None,
        action="power_off", rate="3.0", resolution="240x180", rotate=0,
        worker=True):

        context.call_init(self, "Actor", context)

        self._panel, self._camera, self._button = panel, camera, button
        self._rotate = int(rotate)
        self._queue = queue.Queue()        # settings, into the worker thread
        self._stopping = False

        self.share.update({
            "source_file": f"v{aiko.__version__}⇒ {__file__}",
            "action": action,
            "rate": rate,
            "resolution": resolution,
            "device": getattr(self._panel, "device", "none"),
            "frames": "0",
            "last_error": "-",
        })
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        if self._button:
            self._button.add_handler(self._button_handler)
            self._button.open()

        # worker=False composes the Actor without its thread, which is how
        # the tests exercise the handlers.  Nothing else sets it
        self._thread = None
        if worker:
            self._thread = Thread(
                target=self._run, daemon=True, name=_THREAD_NAME)
            self._thread.start()

# Dispatch: deny by default (P12) ------------------------------------------ #

    def _topic_in_handler(self, _aiko, topic, payload_in):
        command, parameters = None, None
        try:
            command, parameters = parse(payload_in)
        except Exception:                                # noqa: BLE001
            return self._reject("parse_error", payload_in)
        if command not in WIRE_COMMANDS or not isinstance(parameters, list):
            return self._reject("unknown_command", command)
        self._post_message(aiko.ActorTopic.IN, command, parameters)

    def _reject(self, reason, detail):
        self.logger.warning(f"Refused: {reason}: {detail}")
        self.ec_producer.update("last_error", f"{reason}")

# The worker thread: it owns the camera and the panel --------------------- #

    def _run(self):
        """Capture, compose, show.  This thread owns the devices and never
        touches shared state: it posts what it learns (P11)"""

        rate, resolution = self._applied_settings()
        opened = False
        frames = 0
        while not self._stopping:
            started = time.monotonic()
            changed = self._drain_queue()
            if changed:
                rate = changed.get("rate", rate)
                if "resolution" in changed and changed["resolution"] != resolution:
                    resolution = changed["resolution"]
                    opened = False                       # reopen at the new size
            if not opened:
                opened = self._open_devices(resolution)
                if not opened:
                    time.sleep(REOPEN_PERIOD)
                    continue
            try:
                image = self._camera.capture()
                self._panel.show(compose(
                    image, self._lines(frames), rotate=self._rotate))
                frames += 1
                if frames % 10 == 0:
                    self._post_message(
                        aiko.ActorTopic.IN, "_frames", [str(frames)])
            except Exception as exception:               # noqa: BLE001
                self._post_message(
                    aiko.ActorTopic.IN, "_worker_error", [str(exception)])
                opened = False
                time.sleep(REOPEN_PERIOD)
                continue
            delay = (1.0 / rate) - (time.monotonic() - started)
            if delay > 0:
                time.sleep(delay)

    def _applied_settings(self):
        """The settings, read once as the thread starts.  Reading share here
        is safe: nothing has mutated it since __init__, and after this the
        thread only learns through its queue"""

        return self._rate(self.share["rate"]),  \
            parse_resolution(self.share["resolution"])

    def _drain_queue(self):
        changed = {}
        while True:
            try:
                changed.update(self._queue.get_nowait())
            except queue.Empty:
                return changed

    def _open_devices(self, resolution):
        try:
            self._panel.open()
            self._camera.open(resolution)
            return True
        except (CameraNotFound, OSError) as error:
            self._post_message(
                aiko.ActorTopic.IN, "_worker_error", [str(error)])
            return False

    def _lines(self, frames):
        """The text under the picture.  Cheap to build, because it runs on
        every frame"""

        return [
            get_hostname(),
            _address(),
            f"frames {frames}",
            time.strftime("%H:%M:%S"),
        ]

    @staticmethod
    def _rate(value):
        rate = float(value)
        if not RATE_LOW <= rate <= RATE_HIGH:
            raise ValueError(
                f"rate must be {RATE_LOW} to {RATE_HIGH}, not {rate}")
        return rate

# The button thread -------------------------------------------------------- #

    def _button_handler(self, kind, seconds):
        """Runs on the button's thread, so it only posts (P11)"""

        self._post_message(
            aiko.ActorTopic.IN, "_button_press", [kind, f"{seconds:.2f}"])

# Everything below runs on the event-loop thread --------------------------- #

    def _button_press(self, kind, seconds):
        # Not _button: that name is the Button object, set in __init__
        self.logger.debug(f"Button {kind} press, {seconds} s")
        if kind != "long":
            return                       # Short and double presses: Epic 6
        action = self.share["action"]
        self.logger.info(f"Long press: {action}")
        if action == "power_off":
            self._power_off()

    def _power_off(self):
        """Stop Aiko Services cleanly, then halt the host.

        The host halts only.  A PiSugar keeps supplying power to a halted
        Raspberry Pi, so the battery drains until it cuts out.  Cutting the
        PiSugar output needs the I2C write that the power Actor will bring"""

        self._stopping = True
        try:
            self._panel.show(compose(None, ["Shutting down", get_hostname()]))
        except Exception:                                # noqa: BLE001
            pass                         # A failing panel must not stop a halt
        subprocess.Popen(["sudo", "-n", "shutdown", "-h", "now"])
        self.stop()                      # The sanctioned self-stop (ADR-027)

    def _frames(self, frames):
        self.ec_producer.update("frames", frames)

    def _worker_error(self, text):
        self.logger.error(text)
        self.ec_producer.update("last_error", text[:120])

    def _ec_producer_change_handler(self, command, item_name, item_value):
        """A setting changed on the control topic.  Validate here, on the
        event-loop thread, then hand the worker thread a copy (P11)"""

        if command != "update" or item_name not in SETTINGS:
            return
        try:
            if item_name == "rate":
                self._queue.put({"rate": self._rate(item_value)})
            elif item_name == "resolution":
                self._queue.put(
                    {"resolution": parse_resolution(item_value)})
            elif item_name == "action" and item_value not in ACTIONS:
                raise ValueError(
                    f'action must be one of {ACTIONS}, not "{item_value}"')
        except ValueError as error:
            self.logger.warning(f"Refused {item_name}: {error}")
            self.ec_producer.update("last_error", str(error)[:120])

    def stop(self):
        self._stopping = True
        for device in (self._camera, self._panel, self._button):
            try:
                if device:
                    device.close()
            except Exception:                            # noqa: BLE001
                pass
        aiko.process.terminate()

def _address():
    """This host's address on the network, or "-".  No name resolution"""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.2)
            probe.connect(("192.0.2.1", 1))              # TEST-NET-1, no traffic
            return probe.getsockname()[0]
    except OSError:
        return "-"

def service_tags(device):
    """The Service tags, with the panel that was opened"""

    return ["ec=true", f"device={device}"]

# --------------------------------------------------------------------------- #
