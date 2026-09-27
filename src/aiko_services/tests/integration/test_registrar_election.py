# Aiko Services Registrar: the primary election against a real MQTT server
#
# A stale retained "(primary found ...)" (a Registrar and its MQTT server
# stopped together, so the will was never sent) must not block a new
# Registrar: it probes the announced primary, publishes "(primary absent)"
# and becomes the primary.  A second Registrar against a live primary
# probes it and stays secondary.
#
# Needs an MQTT server on AIKO_MQTT_HOST:AIKO_MQTT_PORT (default
# localhost:1883), else every test skips.  Each run uses its own
# AIKO_NAMESPACE, so a live Registrar on the same server is not disturbed.
#
#   AIKO_MQTT_HOST=localhost pytest [-s] integration/test_registrar_election.py

import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid

import pytest

mqtt = pytest.importorskip("paho.mqtt.client")

HOST = os.environ.get("AIKO_MQTT_HOST", "localhost")
PORT = int(os.environ.get("AIKO_MQTT_PORT", "1883"))
ELECTION_TIMEOUT = 8.0        # seconds: probe 3 to 3.5, then the echo
SOURCE = Path(__file__).resolve().parents[3]      # the directory with aiko_services/

class Observer:
    """An MQTT client that records what arrives on the namespace's topics"""

    def __init__(self, namespace):
        self.boot_topic = f"{namespace}/service/registrar"
        self.messages = []                        # (topic, payload, retained)
        self.lock = threading.Lock()
        self.client = mqtt.Client()
        self.client.on_message = self._on_message
        self.client.connect(HOST, PORT, 30)
        self.client.subscribe([(self.boot_topic, 0), (f"{namespace}/+/+/+/probe", 0)])
        self.client.loop_start()

    def _on_message(self, client, userdata, message):
        with self.lock:
            self.messages.append(
                (message.topic, message.payload.decode(errors="replace"), message.retain))

    def boot_payloads(self):
        with self.lock:
            return [payload for topic, payload, _ in self.messages
                    if topic == self.boot_topic and payload]

    def wait_for(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return predicate()

    def publish_retained(self, payload):
        self.client.publish(self.boot_topic, payload, retain=True).wait_for_publish()

    def close(self):
        self.publish_retained("")                 # leave nothing retained
        self.client.loop_stop()
        self.client.disconnect()

def broker_answers():
    client = mqtt.Client()
    try:
        client.connect(HOST, PORT, 5)
        client.disconnect()
        return True
    except OSError:
        return False

pytestmark = pytest.mark.skipif(not broker_answers(),
    reason=f"no MQTT server on {HOST}:{PORT}")

@pytest.fixture
def namespace():
    return f"test_election_{uuid.uuid4().hex[:8]}"

@pytest.fixture
def observer(namespace):
    observer = Observer(namespace)
    yield observer
    observer.close()

@pytest.fixture
def registrars(namespace):
    """Start Registrar processes in the namespace; stopped afterwards"""

    started = []

    def start():
        environment = dict(os.environ, AIKO_NAMESPACE=namespace,
            AIKO_MQTT_HOST=HOST, AIKO_MQTT_PORT=str(PORT),
            PYTHONPATH=os.pathsep.join(filter(None, [str(SOURCE), os.environ.get("PYTHONPATH")])))
        process = subprocess.Popen(
            [sys.executable, "-c", "from aiko_services.main.registrar import main; main()"],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        started.append(process)
        return process

    yield start
    for process in started:
        process.send_signal(signal.SIGTERM)
    for process in started:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

def test_stale_announcement_is_replaced(namespace, observer, registrars):
    stale = f"(primary found {namespace}/deadhost/4242/1 2 0)"
    observer.publish_retained(stale)
    assert observer.wait_for(lambda: stale in observer.boot_payloads(), 5)

    started_at = time.monotonic()
    registrars()
    prefix = f"(primary found {namespace}/"
    assert observer.wait_for(lambda: any(payload.startswith(prefix) and payload != stale
        for payload in observer.boot_payloads()), ELECTION_TIMEOUT), observer.messages
    elapsed = time.monotonic() - started_at
    payloads = observer.boot_payloads()
    absent = payloads.index("(primary absent)")
    new = next(index for index, payload in enumerate(payloads)
               if payload.startswith(prefix) and payload != stale)
    assert payloads[0] == stale and absent < new
    print(f"stale announcement replaced in {elapsed:.1f} s")

def test_second_registrar_stays_secondary(namespace, observer, registrars):
    registrars()
    prefix = f"(primary found {namespace}/"
    assert observer.wait_for(lambda: any(payload.startswith(prefix)
        for payload in observer.boot_payloads()), ELECTION_TIMEOUT), observer.messages
    primary = next(payload for payload in observer.boot_payloads()
                   if payload.startswith(prefix))
    before = len(observer.boot_payloads())

    registrars()
    replied = lambda: any(topic.endswith("/probe") and payload == "(item_count 0)"
                          for topic, payload, _ in observer.messages)
    assert observer.wait_for(replied, ELECTION_TIMEOUT), observer.messages
    time.sleep(1.0)                               # nothing more on the boot topic
    assert observer.boot_payloads()[before:] == []
    assert observer.boot_payloads()[-1] == primary
