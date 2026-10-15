# Usage
# ~~~~~
# pytest [-s] integration/test_mqtt_reconnect.py
#
# Integration tests for MQTT connection retry, using a real "mosquitto"
# MQTT server that each test starts and stops on a free local port.
# Skipped when the "mosquitto" executable isn't installed.
#
# - A process started before the MQTT server, with
#   mqtt_connection_required=False, connects when the MQTT server starts
#   and connects again after the MQTT server restarts
# - A deliberate set_last_will_and_testament() doesn't cause the previous
#   LWT to be published.  A killed process causes the new LWT to be published
#
# To Do
# ~~~~~
# - None, yet !

import os
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time

import pytest

paho_client = pytest.importorskip("paho.mqtt.client")

_MOSQUITTO_PATHS = ["/opt/homebrew/sbin", "/usr/local/sbin", "/usr/sbin"]
_TIMEOUT = 20.0  # seconds

def _mosquitto_path():
    path = shutil.which("mosquitto")
    if not path:
        for directory in _MOSQUITTO_PATHS:
            candidate = os.path.join(directory, "mosquitto")
            if os.access(candidate, os.X_OK):
                return candidate
    return path

MOSQUITTO = _mosquitto_path()
pytestmark = pytest.mark.skipif(not MOSQUITTO, reason="mosquitto not installed")

def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

def _start_mosquitto(tmp_path, port):
    configuration = tmp_path / "mosquitto.conf"
    configuration.write_text(
        f"listener {port} 127.0.0.1\nallow_anonymous true\n")
    process = subprocess.Popen([MOSQUITTO, "-c", str(configuration)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return process
        except OSError:
            time.sleep(0.05)
    process.kill()
    raise RuntimeError("mosquitto didn't start")

def _stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

_CHILD = textwrap.dedent("""
    import sys
    from aiko_services.main import aiko, event
    from aiko_services.main.message import MessageState

    counter = 0
    def heartbeat():
        global counter
        counter += 1
        aiko.message.publish("test/alive", f"(alive {counter})")
    event.add_timer_handler(heartbeat, 0.2)

    lwt_requested = len(sys.argv) > 1 and sys.argv[1] == "lwt"
    def change_lwt():
        if getattr(aiko.message, "connected", None) == MessageState.CONNECTED:
            event.remove_timer_handler(change_lwt)
            aiko.process.set_last_will_and_testament(
                "test/lwt", "(new will)", False)
            aiko.message.publish("test/lwt_changed", "(changed)")
    if lwt_requested:
        event.add_timer_handler(change_lwt, 0.2)

    print(aiko.topic_lwt, flush=True)
    aiko.process.run(loop_when_no_handlers=True, mqtt_connection_required=False)
""")

class _Watcher:
    def __init__(self, port, topics):
        self.messages = []
        self.lock = threading.Lock()
        self.client = paho_client.Client()
        self.client.on_message = self._on_message
        self.client.on_connect =  \
            lambda client, userdata, flags, rc: [client.subscribe(topic) for topic in topics]
        self.client.connect_async("127.0.0.1", port)
        self.client.loop_start()

    def _on_message(self, client, userdata, message):
        with self.lock:
            self.messages.append((message.topic, message.payload.decode()))

    def wait_for(self, topic, payload_prefix="", timeout=_TIMEOUT, after=0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                for message_topic, payload in self.messages[after:]:
                    if message_topic == topic and payload.startswith(payload_prefix):
                        return True
            time.sleep(0.05)
        return False

    def count(self):
        with self.lock:
            return len(self.messages)

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

def _start_child(tmp_path, port, *arguments):
    script = tmp_path / "child.py"
    script.write_text(_CHILD)
    environment = dict(os.environ,
        AIKO_MQTT_HOST="127.0.0.1", AIKO_MQTT_PORT=str(port),
        AIKO_LOG_MQTT="false")
    child = subprocess.Popen([sys.executable, str(script), *arguments],
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True)
    topic_lwt = child.stdout.readline().strip()
    return child, topic_lwt

def test_connect_after_mqtt_server_starts_and_restarts(tmp_path):
    port = _free_port()
    child = mosquitto = watcher = None
    try:
        child, _ = _start_child(tmp_path, port)  # no MQTT server yet
        time.sleep(1.5)
        assert child.poll() is None, "Process exited without an MQTT server"

        mosquitto = _start_mosquitto(tmp_path, port)
        watcher = _Watcher(port, ["test/alive"])
        assert watcher.wait_for("test/alive"), "No connection after start"

        _stop(mosquitto)
        time.sleep(1.0)
        mosquitto = _start_mosquitto(tmp_path, port)
        after = watcher.count()
        assert watcher.wait_for("test/alive", after=after),  \
            "No connection after MQTT server restart"
    finally:
        if watcher:
            watcher.stop()
        _stop(child)
        _stop(mosquitto)

def test_last_will_and_testament_change(tmp_path):
    port = _free_port()
    child = mosquitto = watcher = None
    try:
        mosquitto = _start_mosquitto(tmp_path, port)
        child, topic_lwt = _start_child(tmp_path, port, "lwt")
        watcher = _Watcher(port, [topic_lwt, "test/lwt", "test/lwt_changed"])
        assert watcher.wait_for("test/lwt_changed"), "LWT wasn't changed"
        time.sleep(1.0)
        assert not watcher.wait_for(topic_lwt, "(absent)", timeout=0.1),  \
            "Previous LWT published by a deliberate disconnection"

        child.send_signal(signal.SIGKILL)
        child.wait(timeout=5)
        assert watcher.wait_for("test/lwt", "(new will)"),  \
            "New LWT not published when the process was killed"
    finally:
        if watcher:
            watcher.stop()
        _stop(child)
        _stop(mosquitto)
