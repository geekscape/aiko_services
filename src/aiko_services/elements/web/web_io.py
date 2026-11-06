# Usage
# ~~~~~
# cd src/aiko_services/elements/web
# aiko_pipeline create pipelines/web_pipeline_0.json -s 1
# # then open http://<this-host>:8090 in a browser on the same network
#
# aiko_pipeline create <camera PipelineDefinition> -s 1  \
#   -p VideoShowWeb.port 8091 -p VideoShowWeb.max_fps 2
#
# VideoShowWeb is a pass-through PipelineElement for looking at a camera's
# view from a browser: every frame goes on downstream unchanged, and a web
# server thread shows the latest image as a live MJPEG stream, with the
# shared state of chosen elements (by default the Pipeline's source, so a
# camera's sensor.* values), aiming overlays drawn by the browser (a grid
# of thirds, a center cross, a level line) and a focus assist switch
#
# It costs nothing while nobody watches: process_frame() keeps a reference
# to the latest image.  With a viewer connected, one encoder thread scales
# the latest image to "width" and JPEG-encodes it, at most "max_fps" times
# a second.  The event loop never encodes
#
# parameter: "port"            HTTP port (8090); 0 picks a free one
# parameter: "host"            bind address ("0.0.0.0": every interface)
# parameter: "max_fps"         encoded frames per second at most (4.0)
# parameter: "width"           scaled image width in pixels (960, 0: none)
# parameter: "quality"         JPEG quality, 1 to 100 (80)
# parameter: "title"           page title (default: the Pipeline name)
# parameter: "status_elements" elements whose shared state the page shows,
#                              "(A B)" or "A" (default: the source element)
#
# Web page: "/" the page, "/stream.mjpg" the live view, "/snapshot.jpg" one
# full-size frame, "/status" JSON, "/update?element=E&name=N&value=V" sends
# "(update N V)" to element E, for the names in WRITABLE_KEYS only
#
# Shared state: state (serving | error), url, port, viewers, frames_encoded
#
# The shared state of other elements arrives through ECConsumers, as on
# aiko_dashboard: the element observes, it never reaches into another
# element.  The web server has no authentication: use it on a trusted
# network only
#
# To Do
# ~~~~~
# - Several images per frame: shows the last one

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Tuple
import urllib.parse

import numpy as np

import aiko_services as aiko

__all__ = ["FrameWebServer", "VideoShowWeb"]

DEFAULT_PORT = 8090
DEFAULT_MAX_FPS = 4.0
DEFAULT_WIDTH = 960
DEFAULT_QUALITY = 80
WRITABLE_KEYS = ("focus_assist",)      # what the page may change
PUBLISH_PERIOD_S = 1.0

# --------------------------------------------------------------------------- #
# FrameWebServer: the web part, independent of the framework (unit tested
# without a Pipeline).  offer() is O(1) on the caller's thread; encoding
# happens on the encoder thread, only while a viewer is connected

class FrameWebServer:
    def __init__(self, port=DEFAULT_PORT, host="0.0.0.0", title="Camera",
        max_fps=DEFAULT_MAX_FPS, width=DEFAULT_WIDTH,
        quality=DEFAULT_QUALITY, status_provider=None, update_handler=None,
        logger=None):

        self.port = int(port)
        self.host = host
        self.title = title
        self.max_fps = float(max_fps)
        self.width = int(width)
        self.quality = int(quality)
        self.status_provider = status_provider or (lambda: {})
        self.update_handler = update_handler
        self.logger = logger
        self.frames_offered = 0
        self.frames_encoded = 0
        self.viewers = 0
        self._condition = threading.Condition()
        self._latest = None
        self._image_seq = 0
        self._encoded_image_seq = 0
        self._jpeg = None
        self._jpeg_seq = 0
        self._stopped = False
        self._server = None
        self._threads = []

    def start(self):
        """Binds and serves; returns the port (the chosen one for port 0)"""

        server = ThreadingHTTPServer((self.host, self.port), _Handler)
        server.daemon_threads = True
        server.frame_web_server = self
        self._server = server
        self.port = server.server_address[1]
        self._stopped = False
        for target, name in ((server.serve_forever, "web_server"),
                             (self._encode_loop, "web_encoder")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)
        return self.port

    def stop(self):
        with self._condition:
            self._stopped = True
            self._condition.notify_all()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._threads = []

    def offer(self, image):
        """Any thread: keep a reference to the latest image, nothing more"""

        with self._condition:
            self._latest = image
            self._image_seq += 1
            self.frames_offered += 1
            if self.viewers:
                self._condition.notify_all()

    def stats(self):
        with self._condition:
            return {"port": self.port, "viewers": self.viewers,
                    "frames_offered": self.frames_offered,
                    "frames_encoded": self.frames_encoded,
                    "max_fps": self.max_fps, "width": self.width}

    def encode(self, image, width=None):
        """uint8 RGB (or gray) image --> JPEG bytes, scaled to width"""

        import cv2                      # lazy: imports without OpenCV
        image = np.asarray(image)
        width = self.width if width is None else width
        height, image_width = image.shape[:2]
        if width and image_width > width:
            scaled_height = max(1, int(round(height * width / image_width)))
            interpolation = cv2.INTER_AREA  \
                if image_width >= 2 * width else cv2.INTER_LINEAR
            image = cv2.resize(image, (width, scaled_height),
                               interpolation=interpolation)
        if image.ndim == 3 and image.shape[2] == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        ok, buffer = cv2.imencode(
            ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        return buffer.tobytes() if ok else None

    def _encode_loop(self):
        next_due = 0.0
        while True:
            delay = next_due - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            with self._condition:
                while not self._stopped and (self.viewers == 0
                        or self._image_seq == self._encoded_image_seq):
                    self._condition.wait(timeout=1.0)
                if self._stopped:
                    return
                image, image_seq = self._latest, self._image_seq
            try:
                jpeg = self.encode(image)
            except Exception as exception:
                self._log("warning", f"encode failed: {exception}")
                jpeg = None
            next_due = time.monotonic() + 1.0 / max(self.max_fps, 0.1)
            with self._condition:
                self._encoded_image_seq = image_seq
                if jpeg:
                    self._jpeg = jpeg
                    self._jpeg_seq += 1
                    self.frames_encoded += 1
                    self._condition.notify_all()

    def _log(self, level, message):
        if self.logger:
            getattr(self.logger, level)(f"VideoShowWeb: {message}")

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):    # no line per request
        pass

    def do_GET(self):
        web = self.server.frame_web_server
        url = urllib.parse.urlparse(self.path)
        try:
            if url.path == "/":
                self._send(200, "text/html; charset=utf-8",
                           _page(web.title).encode("utf-8"))
            elif url.path == "/stream.mjpg":
                self._stream(web)
            elif url.path == "/snapshot.jpg":
                with web._condition:
                    image = web._latest
                jpeg = web.encode(image, width=0)  \
                    if image is not None else None
                if jpeg:
                    self._send(200, "image/jpeg", jpeg)
                else:
                    self._send(503, "text/plain", b"no frame yet")
            elif url.path == "/status":
                status = {"viewer": web.stats(), **web.status_provider()}
                self._send(200, "application/json",
                           json.dumps(status).encode("utf-8"))
            elif url.path == "/update":
                self._update(web, urllib.parse.parse_qs(url.query))
            else:
                self.send_error(404)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _update(self, web, query):
        element = query.get("element", [""])[0]
        name = query.get("name", [""])[0]
        value = query.get("value", [""])[0]
        if name not in WRITABLE_KEYS or not web.update_handler  \
            or not element or not value or " " in value:
            self._send(403, "text/plain", b"not writable")
            return
        web.update_handler(element, name, value)
        self._send(204, "text/plain", b"")

    def _stream(self, web):
        self.send_response(200)
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with web._condition:
            web.viewers += 1
            last = web._jpeg_seq
            web._condition.notify_all()
        try:
            while True:
                with web._condition:
                    while web._jpeg_seq == last and not web._stopped:
                        web._condition.wait(timeout=5.0)
                    if web._stopped:
                        return
                    jpeg, last = web._jpeg, web._jpeg_seq
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                    + jpeg + b"\r\n")
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with web._condition:
                web.viewers -= 1

def _page(title):
    return _PAGE.replace("__TITLE__", _escape(title))

def _escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
 :root { --bg:#0f172a; --panel:#1e293b; --text:#e2e8f0; --muted:#94a3b8;
         --accent:#38bdf8; --warn:#fbbf24; --line:#475569; }
 body { margin:0; background:var(--bg); color:var(--text);
        font:14px/1.4 system-ui, sans-serif; }
 header { padding:10px 16px; display:flex; gap:16px; align-items:center;
          flex-wrap:wrap; }
 h1 { font-size:17px; margin:0; }
 label, button { color:var(--text); }
 button { background:var(--panel); border:1px solid var(--line);
          border-radius:6px; padding:6px 12px; cursor:pointer; }
 button.on { background:#0369a1; border-color:var(--accent); }
 main { display:flex; gap:16px; padding:0 16px 16px; flex-wrap:wrap; }
 .view { position:relative; flex:1 1 640px; max-width:1280px;
         background:#000; border:1px solid var(--line); }
 .view img { display:block; width:100%; height:auto; }
 .view svg { position:absolute; inset:0; width:100%; height:100%;
             pointer-events:none; }
 .view svg line { vector-effect:non-scaling-stroke; }
 aside { flex:0 1 360px; background:var(--panel); border-radius:8px;
         padding:10px 12px; overflow:auto; max-height:85vh; }
 table { border-collapse:collapse; width:100%; }
 td { padding:2px 6px; vertical-align:top; word-break:break-all; }
 td:first-child { color:var(--muted); white-space:nowrap; }
 h2 { font-size:14px; margin:10px 0 4px; color:var(--accent); }
 .note { color:var(--muted); font-size:12px; }
</style></head>
<body>
<header>
 <h1>__TITLE__</h1>
 <label><input type="checkbox" id="grid" checked> thirds</label>
 <label><input type="checkbox" id="cross" checked> center</label>
 <label><input type="checkbox" id="level"> level</label>
 <button id="focus" type="button">focus assist</button>
 <a href="/snapshot.jpg" style="color:var(--accent)">snapshot</a>
 <span class="note" id="viewer"></span>
</header>
<main>
 <div class="view">
  <img src="/stream.mjpg" alt="live camera view">
  <svg viewBox="0 0 100 100" preserveAspectRatio="none">
   <g id="g_grid" stroke="#ffffff" stroke-opacity="0.6">
    <line x1="33.33" y1="0" x2="33.33" y2="100"/>
    <line x1="66.67" y1="0" x2="66.67" y2="100"/>
    <line x1="0" y1="33.33" x2="100" y2="33.33"/>
    <line x1="0" y1="66.67" x2="100" y2="66.67"/>
   </g>
   <g id="g_cross" stroke="#f43f5e" stroke-width="2">
    <line x1="47" y1="50" x2="53" y2="50"/>
    <line x1="50" y1="46" x2="50" y2="54"/>
   </g>
   <g id="g_level" stroke="#fbbf24" stroke-width="1.5" display="none">
    <line x1="0" y1="50" x2="100" y2="50"/>
   </g>
  </svg>
 </div>
 <aside id="status"><span class="note">waiting for status ...</span></aside>
</main>
<script>
const FIRST = ["state", "device_id", "sensor.resolution", "frame_rate",
  "measured_fps", "frames", "frames_dropped", "exposure_mode",
  "sensor.exposure_us", "sensor.gain", "sensor.auto_status",
  "sensor.white_balance", "sensor.temperature_c", "sensor.packets_dropped",
  "sensor.sharpness", "focus_assist", "settled", "capture_timeouts",
  "last_error", "segments_written", "segment"];
let source = null, focusOn = false;
for (const id of ["grid", "cross", "level"]) {
  document.getElementById(id).addEventListener("change", e =>
    document.getElementById("g_" + id).setAttribute("display",
      e.target.checked ? "inline" : "none"));
}
document.getElementById("focus").addEventListener("click", () => {
  if (!source) return;
  fetch("/update?element=" + encodeURIComponent(source) +
        "&name=focus_assist&value=" + (!focusOn));
});
function table(values) {
  const rows = document.createElement("table");
  const keys = Object.keys(values).filter(k => k !== "#");  // comments
  const ordered = FIRST.filter(k => k in values)
    .concat(keys.filter(k => !FIRST.includes(k)).sort());
  for (const key of ordered) {
    const row = rows.insertRow();
    row.insertCell().textContent = key;
    row.insertCell().textContent = values[key];
  }
  return rows;
}
async function poll() {
  try {
    const status = await (await fetch("/status")).json();
    const panel = document.getElementById("status");
    panel.replaceChildren();
    source = status.source || null;
    for (const [name, values] of Object.entries(status.elements || {})) {
      const heading = document.createElement("h2");
      heading.textContent = name;
      panel.append(heading, table(values));
      if (name === source) focusOn = values.focus_assist === "true";
    }
    document.getElementById("focus").classList.toggle("on", focusOn);
    const v = status.viewer || {};
    document.getElementById("viewer").textContent =
      `${v.viewers ?? 0} viewer(s), ${v.frames_encoded ?? 0} frames sent, ` +
      `at most ${v.max_fps} fps`;
  } catch (error) { /* the Pipeline may be restarting */ }
}
poll();
setInterval(poll, 1000);
</script>
</body></html>
"""

# --------------------------------------------------------------------------- #

class VideoShowWeb(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("video_show_web:0")
        context.call_init(self, "PipelineElement", context)
        self.web = None
        self._followed = {}            # element name --> topic_control
        self._consumers = []
        self._status = {}              # element name --> {item: value}
        self._status_lock = threading.Lock()
        self._source = None            # the element the focus switch drives
        self._timer_armed = False

    def start_stream(self, stream, stream_id):
        if self.web is None:
            self._start_web()
        self._follow_elements()
        if not self._timer_armed:
            aiko.add_timer_handler(self._publish_handler, PUBLISH_PERIOD_S)
            self._timer_armed = True
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        if self.web and images:
            self.web.offer(images[-1])
        return aiko.StreamEvent.OKAY, {"images": images}

    def stop_stream(self, stream, stream_id):
        if self._timer_armed:
            aiko.remove_timer_handler(self._publish_handler)
            self._timer_armed = False
        for consumer in self._consumers:
            try:
                consumer.terminate()
            except Exception:
                pass
        self._consumers = []
        self._followed = {}
        if self.web:
            self.web.stop()
            self.web = None
        self._publish("state", "stopped")
        return aiko.StreamEvent.OKAY, {}

    # The web server ------------------------------------------------------- #

    def _start_web(self):
        get = self.get_parameter
        try:
            title = get("title", None)[0] or getattr(
                self.pipeline, "name", "camera")
            self.web = FrameWebServer(
                port=int(get("port", DEFAULT_PORT)[0]),
                host=str(get("host", "0.0.0.0")[0]),
                title=str(title),
                max_fps=float(get("max_fps", DEFAULT_MAX_FPS)[0]),
                width=int(get("width", DEFAULT_WIDTH)[0]),
                quality=int(get("quality", DEFAULT_QUALITY)[0]),
                status_provider=self._status_snapshot,
                update_handler=self._send_update, logger=self.logger)
            port = self.web.start()
        except Exception as exception:  # never break the Pipeline
            self.web = None
            self._publish("state", "error")
            self.logger.warning(f"VideoShowWeb: no web server: {exception}")
            return
        url = f"http://{_host_address()}:{port}"
        self._publish("state", "serving")
        self._publish("port", port)
        self._publish("url", url)
        self.logger.info(f"VideoShowWeb: open {url} "
                         f"(or http://{socket.gethostname()}.local:{port})")

    # Other elements' shared state, as on aiko_dashboard ------------------- #

    def _follow_elements(self):
        """Never fails the Stream: the view is optional"""

        if self._followed:
            return
        try:
            self._follow(self.pipeline.pipeline_graph)
        except Exception as exception:
            self.logger.warning(f"VideoShowWeb: no shared state: {exception}")

    def _follow(self, graph):
        path = list(graph.get_path(self.pipeline.share["graph_path"]))
        names = _names(self.get_parameter("status_elements", None)[0])
        if not names:
            names = [path[0].name] if path else []
        self._source = names[0] if names else None
        for index, name in enumerate(names):
            try:
                element = graph.get_node(name).element
                if element is self:
                    continue
                topic_control = f"{element.topic_path}/control"
                consumer = aiko.compose_instance(aiko.ECConsumerImpl,
                    aiko.ec_consumer_args(self, index, {}, topic_control))
                consumer.add_handler(self._consumer_handler(name))
            except Exception as exception:
                self.logger.warning(
                    f"VideoShowWeb: cannot follow {name}: {exception}")
                continue
            self._followed[name] = topic_control
            self._consumers.append(consumer)

    def _consumer_handler(self, name):
        def handler(client_id, command, item_name, item_value):
            if not item_name:
                return
            with self._status_lock:
                values = self._status.setdefault(name, {})
                if command in ("add", "update"):
                    values[item_name] = item_value
                elif command == "remove":
                    values.pop(item_name, None)
        return handler

    def _status_snapshot(self):
        with self._status_lock:
            elements = {name: dict(values)
                        for name, values in self._status.items()}
        return {"source": self._source, "elements": elements}

    def _send_update(self, element_name, item_name, item_value):
        """Web server thread: the same message aiko_dashboard sends"""

        topic_control = self._followed.get(element_name)
        if topic_control:
            aiko.process.message.publish(
                topic_control, f"(update {item_name} {item_value})")

    # This element's own shared state -------------------------------------- #

    def _publish_handler(self):
        if self.web:
            stats = self.web.stats()
            for key in ("viewers", "frames_encoded"):
                self._publish(key, stats[key])

    def _publish(self, key, value):
        value = str(value)
        if self.ec_producer.get(key) != value:
            self.ec_producer.update(key, value)

def _names(value):
    if value is None:
        return []
    text = str(value).strip().strip("()")
    return [name for name in text.replace(",", " ").split() if name]

def _host_address():
    """This host's address on the network with the default route"""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))    # no packet is sent
            return probe.getsockname()[0]
    except OSError:
        return socket.gethostname()
