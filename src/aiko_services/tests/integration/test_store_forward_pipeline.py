# Usage
# ~~~~~
# pytest [-s] integration/test_store_forward_pipeline.py
#
# End to end in one process, real sockets on 127.0.0.1, no MQTT broker:
# a synthetic video Pipeline writes MP4 segments into an outbox, an
# edge-role SegmentStoreForward Actor watching that outbox uploads them
# over HTTP, and a StoreForwardMessageHTTPServer (the server host's
# message layer, driven directly) receives them into its inbox.  Needs
# Flask and OpenCV
#
# To Do
# ~~~~~
# - Add the server-role Actor too, once two Actors of the same Interface
#   in one process is a tested configuration

import hashlib
import os
import threading
import time

import pytest
pytest.importorskip("flask",
    reason="StoreForward HTTP server needs flask: pip install flask")
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")

import aiko_services as aiko
from aiko_services.main.store_forward import PROTOCOL, SegmentStoreForwardImpl
from aiko_services.main.store_forward.store_forward_http import (
    StoreForwardMessageHTTPClient, StoreForwardMessageHTTPServer
)
from aiko_services.tests.unit import do_compose_pipeline

SEGMENTS = 3
WATCHDOG_S = 40.0

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test_store_forward_e2e", "runtime": "python",
  "graph": ["(SyntheticVideoRead CaptureLimit VideoWriteStoreForward)"],
  "parameters": {"_create_stream_": "1", "frame_rate": 5.0},
  "elements": [
    { "name":   "SyntheticVideoRead",
      "parameters": {
        "data_sources": "(synth://video/plain?width=64&height=48)",
        "rate": 5.0
      },
      "input":  [{"name": "images", "type": "[image]"}],
      "output": [{"name": "images", "type": "[image]"}],
      "deploy": {
        "local": {"module": "aiko_services.elements.media.synthetic_io"}}
    },
    { "name":   "CaptureLimit", "input": [], "output": [],
      "parameters": {"frame_count": 7},
      "deploy": {
        "local": {"module": "aiko_services.elements.control.elements"}}
    },
    { "name":   "VideoWriteStoreForward",
      "parameters": {
        "data_targets":    "(store_forward://OUTBOX)",
        "segment_frames":  3,
        "segment_seconds": 0
      },
      "input":  [{"name": "images", "type": "[image]"}], "output": [],
      "deploy": {
        "local": {"module": "aiko_services.elements.media.store_forward_io"}}
    }
  ]
}
"""

class _ServerRecorder:
    def __init__(self):
        self.received = []
        self.lock = threading.Lock()

    def on_command(self, payload):
        return "accepted"

    def on_event(self, segment_id, event, detail):
        if event == "received_ok":
            with self.lock:
                self.received.append(segment_id)

def _sha256(path):
    with open(path, "rb") as file:
        return hashlib.sha256(file.read()).hexdigest()

def test_pipeline_segments_arrive_at_server(tmp_path):
    server_in, server_out = tmp_path / "server_in", tmp_path / "server_out"
    edge_in, edge_out = tmp_path / "edge_in", tmp_path / "edge_out"
    for directory in (server_in, server_out, edge_in, edge_out):
        directory.mkdir()

    recorder = _ServerRecorder()
    server = StoreForwardMessageHTTPServer(str(server_in), str(server_out),
        bind="127.0.0.1", port_range=(0, 0), advertise_host="127.0.0.1",
        chunk_size=4096)
    endpoint = server.start(recorder.on_command, recorder.on_event)

    client = StoreForwardMessageHTTPClient(endpoint, str(edge_in),
        str(edge_out), poll_period=0.2, chunk_size=4096)
    parameters = {"message": client, "inbox": str(edge_in),
                  "outbox": str(edge_out), "outbox_period": 0.2}
    init_args = aiko.actor_args("store_forward_test_edge",
        parameters=parameters, protocol=PROTOCOL, tags=["role=edge"])
    actor = aiko.compose_instance(SegmentStoreForwardImpl, init_args)

    results = {"ok": False, "watchdog": False}
    started = time.monotonic()

    def check():
        arrived = len([name for name in os.listdir(server_in)
                       if not name.startswith(".")])
        if arrived >= SEGMENTS:
            results["ok"] = True
        elif time.monotonic() - started > WATCHDOG_S:
            results["watchdog"] = True
        if results["ok"] or results["watchdog"]:
            aiko.event.remove_timer_handler(check)
            aiko.process.terminate()

    definition = PIPELINE_DEFINITION.replace("OUTBOX", str(edge_out))
    pipeline = do_compose_pipeline(definition, frame_data=None)
    aiko.event.add_timer_handler(check, 0.5)
    try:
        pipeline.run(mqtt_connection_required=False)
    finally:
        aiko.event.remove_timer_handler(actor._outbox_scan)
        client.stop()
        server.stop()

    assert not results["watchdog"], f"only {recorder.received} arrived"
    assert sorted(recorder.received) == sorted(actor.share["store_forwards"])
    arrived = sorted(name for name in os.listdir(server_in)
                     if not name.startswith("."))
    sent = sorted(os.listdir(edge_out / ".sent"))
    assert len(arrived) == SEGMENTS and arrived == sent, (arrived, sent)
    for name in arrived:
        assert _sha256(server_in / name) == _sha256(edge_out / ".sent" / name)
    assert actor.share["metrics"]["sent_bytes"] ==  \
        str(sum(os.path.getsize(server_in / name) for name in arrived))
