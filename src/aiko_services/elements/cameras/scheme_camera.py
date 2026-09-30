# DataSchemeCamera: the DataScheme base class shared by the camera schemes
# (scheme_depthai.py, scheme_gigev.py).  It owns the device, the parameter
# coercion, the warm-up, the frame generator and the shared state; a
# subclass names its scheme and camera class and adds its own parameters
#
# URL grammar of every camera scheme ...
# - "(<scheme>://)"           the first camera found (discovery)
# - "(<scheme>://<address>)"  one camera; the address form is the SDK's
# The URL carries no options: everything else is a PipelineElement
# parameter, so it can be given at the command line with "-p"
#
# parameter: "resolution"      "WxH" (default "1920x1080"), "native" / "full"
# parameter: "frame_rate"      frames per second, 8.0 default, "25/1" form
#                              accepted ("fps" is a deprecated alias)
# parameter: "rate"            delivery throttle (create_frames), default
#                              none: the camera paces the Stream
# parameter: "resize_mode"     crop | letterbox | stretch (scaled output)
# parameter: "settle"          frames discarded while the camera converges
#                              after start, a count or "3s"; the default
#                              is the subclass's
# parameter: "capture_timeout" seconds per capture (1.0); ten consecutive
#                              timeouts end the Stream
# parameter: "log_frames"      true: one debug log line per frame
# parameter: "focus_assist"    true: publish sensor.sharpness once a second,
#                              for turning a manual focus ring to the peak
# parameter: "data_batch_size" only 1 is supported
#
# Shared state (observe via aiko_dashboard) ...
#   state            opening | settling | streaming | stopped | error
#   device_id, address, sdk_version
#   settled          waiting | <n>_frames | timeout_<n>_frames | off
#   frames           frames delivered         measured_fps  over 2 s
#   frames_dropped   captured but not delivered: the Pipeline fell behind
#   capture_timeouts last_frame_utc           last_error  <token>@UTC
#   sensor.*         what the device reports: resolution (delivered WxH),
#                    exposure_us, gain, iso_sensitivity, lens_position,
#                    color_temperature_k, auto_status and white_balance
#                    (a camera's own auto features), temperature_c and
#                    packets_dropped (once a second), and sharpness with
#                    focus_assist
#   Configuration keys carry the parameter names and valid parameter
#   values: resolution, frame_rate, settle, resize_mode, capture_timeout,
#   log_frames, focus_assist and the subclass's own.  The framework reads
#   a share item in preference to the element parameter of the same name,
#   so these are the live values: a dashboard "(update ...)" of a writable
#   key takes effect at once, and every configuration key applies to the
#   next Stream
#
# Threads: create_sources() / destroy_sources() and the share handler run
# on the event-loop thread and publish directly.  A capture thread per
# Stream owns the camera: warm-up steps, captures, settle, timeouts, the
# focus and status readouts.  It queues delivered frames on a short host
# queue (FRAME_QUEUE_SIZE, the oldest dropped and counted in
# frames_dropped).  frame_generator() runs on the frame generator thread
# and only takes a ready frame, so the Stream lock is held for
# microseconds: a camera wait inside the generator would hold that lock
# for most of each frame period, each frame's process_frame() would wait
# for it, the frame mailbox would never empty, and the event loop would
# never reach its MQTT messages (dashboard share requests and updates).
# Neither the capture thread nor frame_generator() touches share: they
# record into a pending dictionary that an event-loop timer publishes once
# a second.
# A process abort (KeyboardInterrupt in the event loop) exits without
# destroying the Streams, and a generator thread blocked inside the SDK
# when the interpreter finalizes aborts the process (C++ terminate), so
# an atexit hook closes the camera first
#
# To Do
# ~~~~~
# - "data_batch_size" > 1
# - Device-clock timestamps

import atexit
from collections import deque
import threading
import time

import aiko_services as aiko
from aiko_services.elements.cameras import camera

__all__ = ["DataSchemeCamera"]

PUBLISH_PERIOD_S = 1.0
FRAME_QUEUE_SIZE = 2                   # captured, not yet delivered
METADATA_KEYS = ("exposure_us", "gain", "iso_sensitivity", "lens_position",
                 "color_temperature_k", "auto_status", "white_balance")

# --------------------------------------------------------------------------- #
# One DataScheme instance per Stream (see DataSource.start_stream())

class DataSchemeCamera(aiko.DataScheme):
    scheme = "camera"                  # subclass: the URL scheme name
    camera_name = "camera"             # subclass: for log and diagnostics
    default_settle = "0"               # subclass: warm-up frames
    CAPTURE_THREAD = True              # False: frame_generator() captures
                                       # (step by step unit tests)

    def __init__(self, pipeline_element):
        super().__init__(pipeline_element)
        self.camera = None
        self.stopped = False
        self.settle = None
        self.warm_up_steps = None      # iterator of (done, {key: value})
        self.timeouts = 0
        self.frames = 0
        self.capture_timeout = camera.CAPTURE_TIMEOUT_S
        self.log_frames = False
        self.focus_assist = False
        self._focus_due = 0.0          # monotonic time of the next sharpness
        self._status_due = 0.0         # ... and of the next camera status()
        self.rate_meter = camera.RateMeter()
        self._pending = {}
        self._pending_lock = threading.Lock()
        self._publishing = False       # ECProducer re-enters the handlers
        self._timer_armed = False
        self._handler_armed = False
        self._atexit_armed = False
        self._frames = deque(maxlen=FRAME_QUEUE_SIZE)
        self._frames_lock = threading.Lock()
        self.frames_dropped = 0
        self._stop_reason = None       # set by a capture step: ends Stream
        self._pace_s = None            # software trigger: 1 / frame_rate
        self._capture_thread = None

    # Subclass hooks ------------------------------------------------------- #

    def _camera_class(self, settings):
        """The device class; raises RuntimeError when none is usable"""

        raise NotImplementedError

    def _open_camera(self, camera_class, address, settings):
        instance = camera_class(address=address,
            resolution=settings["resolution"],
            frame_rate=settings["frame_rate"],
            resize_mode=settings["resize_mode"],
            trigger=settings.get("trigger", "off"),
            aux_stream=settings.get("aux_stream", True),
            logger=self.pipeline_element.logger)
        instance.open()
        return instance

    def _extra_settings(self, settings):
        """Subclass parameters, added to settings; raises ValueError"""

        pass

    def _start_warm_up(self, settings):
        """After open(): the settle object fed with every frame's metadata
        and, optionally, self.warm_up_steps (run before any capture)"""

        self.settle = camera.CountdownSettle(settings["settle"])

    def _apply_update(self, item_name, item_value):
        """Subclass writable keys; raises ValueError on a bad value"""

        pass

    # Parameters ------------------------------------------------------------ #

    def _camera_settings(self):
        get = self.pipeline_element.get_parameter
        resolution = camera.parse_resolution(
            get("resolution", camera.DEFAULT_RESOLUTION)[0])
        frame_rate_value, found = get("frame_rate", None)
        if not found:
            frame_rate_value, found = get("fps", None)
            if found:
                self.pipeline_element.logger.warning(
                    '"fps" is deprecated, use "frame_rate"')
        frame_rate = camera.parse_frame_rate(frame_rate_value)  \
            if found else camera.DEFAULT_FRAME_RATE
        settle = camera.parse_settle(
            get("settle", self.default_settle)[0], frame_rate)
        resize_mode = camera.parse_resize_mode(get("resize_mode", "crop")[0])
        rate_value, _ = get("rate", None)
        rate = None if rate_value in (None, "", "None", "none", 0, "0")  \
            else camera.parse_frame_rate(rate_value, "rate")
        self.capture_timeout = float(get(
            "capture_timeout", camera.CAPTURE_TIMEOUT_S)[0])
        if self.capture_timeout <= 0:
            raise ValueError("capture_timeout must be positive")
        batch = int(get("data_batch_size", 1)[0])
        if batch != 1:
            raise ValueError(f"data_batch_size {batch}: only 1 is supported")
        self.log_frames = camera.parse_bool(
            get("log_frames", False)[0], "log_frames")
        self.focus_assist = camera.parse_bool(
            get("focus_assist", False)[0], "focus_assist")
        settings = {"resolution": resolution, "frame_rate": frame_rate,
                    "settle": settle, "resize_mode": resize_mode,
                    "rate": rate}
        self._extra_settings(settings)
        return settings

    # DataScheme interface (event-loop thread) ------------------------------ #

    def create_sources(self,
        stream, data_sources, frame_generator=None, use_create_frame=False):

        pipeline_element = self.pipeline_element
        url = data_sources[0]
        if "?" in url:
            return self._error(f'{self.scheme}:// takes no URL options, use '
                               f'PipelineElement parameters: "{url}"')
        address = aiko.DataScheme.parse_url_path(url) or None

        try:
            settings = self._camera_settings()
        except ValueError as value_error:
            return self._error(f"{self.scheme}:// parameter: {value_error}")
        try:
            camera_class = self._camera_class(settings)
        except RuntimeError as runtime_error:
            return self._error(str(runtime_error))

        self._publish("state", "opening")
        self._publish("address", address or "-")
        try:
            self.camera = self._open_camera(camera_class, address, settings)
        except Exception as exception:
            self.camera = None
            return self._error(f"Couldn't open {self.camera_name} "
                               f"{address or '(any)'}: {exception}")

        self.stopped = False
        self.timeouts = 0
        self.frames = 0
        self.warm_up_steps = None
        self._start_warm_up(settings)
        requested = settings["resolution"]
        delivered = self.camera.resolution()
        self._publish("device_id", self.camera.device_id() or "-")
        self._publish("sdk_version", camera_class.sdk_version())
        self._publish("resolution", "native" if requested is None
                      else f"{requested[0]}x{requested[1]}")
        if delivered:
            self._publish("sensor.resolution",
                          f"{delivered[0]}x{delivered[1]}")
        self._publish("frame_rate", settings["frame_rate"])
        self._publish("resize_mode", settings["resize_mode"])
        self._publish("settle", settings["settle"])
        self._publish("capture_timeout", self.capture_timeout)
        self._publish("log_frames", str(self.log_frames).lower())
        self._publish("focus_assist", str(self.focus_assist).lower())
        settling = not self.settle.done or self.warm_up_steps is not None
        self._publish("settled", "waiting" if settling else "off")
        self._publish("state", "settling" if settling else "streaming")
        self._publish("frames", 0)
        self._publish("capture_timeouts", 0)
        pipeline_element.logger.info(
            f"create_sources(): {self.camera_name} "
            f"{self.share.get('device_id')} "
            f"{self.share.get('resolution')} "
            f"at {settings['frame_rate']} fps, settle <= "
            f"{settings['settle']} frames")

        atexit.register(self._close_at_exit)
        self._atexit_armed = True
        aiko.add_timer_handler(self._publish_handler, PUBLISH_PERIOD_S)
        self._timer_armed = True
        pipeline_element.ec_producer.add_handler(
            self._ec_producer_change_handler)
        self._handler_armed = True
        self._frames.clear()
        self.frames_dropped = 0
        self._stop_reason = None
        self._pace_s = 1.0 / settings["frame_rate"]  \
            if settings.get("trigger") == "software" else None
        self._publish("frames_dropped", 0)
        if self.CAPTURE_THREAD:
            self._capture_thread = threading.Thread(
                target=self._capture_loop, daemon=True,
                name=f"{self.scheme}_capture")
            self._capture_thread.start()
        pipeline_element.create_frames(stream,
            frame_generator or self.frame_generator, rate=settings["rate"])
        return aiko.StreamEvent.OKAY, {}

    def destroy_sources(self, stream):
        self.stopped = True             # frame_generator() returns STOP next
        self._join_capture_thread()     # before the camera closes
        if self._atexit_armed:
            atexit.unregister(self._close_at_exit)
            self._atexit_armed = False
        if self._timer_armed:
            aiko.remove_timer_handler(self._publish_handler)
            self._timer_armed = False
        if self._handler_armed:
            self.pipeline_element.ec_producer.remove_handler(
                self._ec_producer_change_handler)
            self._handler_armed = False
        if self.camera:
            try:
                self.camera.close()
            except Exception as exception:
                self.pipeline_element.logger.warning(
                    f"{self.camera_name} close: {exception}")
            self.camera = None
        self._publish_handler()         # flush what the generator recorded
        self._publish("state", "stopped")

    def _close_at_exit(self):
        """Process abort: close the camera so no thread is blocked inside
        the SDK while the interpreter finalizes.  No logging, no share"""

        self.stopped = True
        self._join_capture_thread()
        camera_instance, self.camera = self.camera, None
        if camera_instance:
            try:
                camera_instance.close()
            except Exception:
                pass

    def _join_capture_thread(self):
        """The capture thread ends within one capture: at most the capture
        timeout"""

        thread, self._capture_thread = self._capture_thread, None
        if thread and thread.is_alive()  \
            and thread is not threading.current_thread():
            thread.join(timeout=self.capture_timeout + 1.0)

    # Capture (the capture thread; frame_generator() without it) ---------- #

    def _capture_loop(self):
        """The capture thread: the camera's own pace, or frame_rate for a
        software trigger, until the Stream stops or a step fails"""

        while not self.stopped and self._stop_reason is None:
            started = time.monotonic()
            self._capture_step()
            if self._pace_s:
                remaining = self._pace_s - (time.monotonic() - started)
                if remaining > 0 and not self.stopped:
                    time.sleep(remaining)

    def _capture_step(self):
        """One warm-up step, or one capture that is either discarded while
        the camera settles or queued for delivery.  A failure that must
        end the Stream sets self._stop_reason"""

        if self.warm_up_steps is not None:      # e.g auto-expose, no frames
            try:
                done, values = next(self.warm_up_steps)
            except StopIteration:
                done, values = True, {}
            except Exception as exception:
                self._pend_error(type(exception).__name__)
                self._stop_reason =  \
                    f"{self.camera_name} warm-up failed: {exception}"
                return
            for key, value in values.items():
                self._pend(key, value)
            if done:
                self.warm_up_steps = None
            return

        try:
            image, metadata = self.camera.capture(self.capture_timeout)
        except camera.CaptureTimeout:
            self.timeouts += 1
            self._pend("capture_timeouts", self.timeouts)
            if self.timeouts >= camera.CAPTURE_TIMEOUT_LIMIT:
                self._pend_error("capture_timeout")
                self._stop_reason = f"{self.camera_name}: no frame for "  \
                    f"{self.timeouts * self.capture_timeout:.0f} s"
            return
        except Exception as exception:
            if self.stopped:            # closed while a capture was in flight
                return
            self._pend_error(type(exception).__name__)
            self._stop_reason = f"{self.camera_name} capture failed: "  \
                f"{exception}"
            return
        if self.stopped:
            return
        self.timeouts = 0
        if time.monotonic() >= self._status_due:
            self._status_due = time.monotonic() + PUBLISH_PERIOD_S
            try:
                for key, value in self.camera.status().items():
                    self._pend(f"sensor.{key}", value)
            except Exception as exception:     # best effort: not "error"
                self._pend("last_error", camera.share_token(
                    f"status_{type(exception).__name__}") + "@"
                    + camera.utc_now())
        if self.focus_assist and time.monotonic() >= self._focus_due:
            self._focus_due = time.monotonic() + PUBLISH_PERIOD_S
            self._pend("sensor.sharpness",
                       f"{camera.focus_sharpness(image):.1f}")
        for key in METADATA_KEYS:
            if key in metadata:
                value = metadata[key]
                if isinstance(value, float):
                    value = f"{value:.1f}"
                self._pend(f"sensor.{key}", value)

        if not self.settle.done:
            if self.settle.feed(metadata):
                if self.settle.timed_out:
                    self._pend("settled",
                               f"timeout_{self.settle.frames}_frames")
                    self.pipeline_element.logger.warning(
                        f"{self.camera_name}: not settled after "
                        f"{self.settle.frames} frames, streaming anyway")
                else:
                    self._pend("settled", f"{self.settle.frames}_frames")
                self._pend("state", "streaming")
                delivered = self.camera.resolution()
                if delivered:
                    self._pend("sensor.resolution",
                               f"{delivered[0]}x{delivered[1]}")
            return

        with self._frames_lock:
            if len(self._frames) == self._frames.maxlen:
                self.frames_dropped += 1       # the Pipeline is behind
                self._pend("frames_dropped", self.frames_dropped)
            self._frames.append((image, metadata, time.time()))

    # Frame generator (frame generator thread) ------------------------------ #

    def frame_generator(self, stream, frame_id):
        """Takes a ready frame and returns at once: the framework holds
        the Stream lock around this call"""

        if self.stopped:
            diagnostic = f"{self.camera_name} sources destroyed"
            return aiko.StreamEvent.STOP, {"diagnostic": diagnostic}
        if not self.CAPTURE_THREAD:
            self._capture_step()
        with self._frames_lock:
            item = self._frames.popleft() if self._frames else None
        if item is None:
            if self._stop_reason:
                # STOP, not ERROR: an ERROR here destroys the Stream on the
                # frame generator THREAD, where the _destroy_stream_exit_
                # SystemExit only kills that thread and the process lingers;
                # STOP posts a graceful destroy to the main event thread
                return aiko.StreamEvent.STOP,  \
                    {"diagnostic": self._stop_reason}
            return aiko.StreamEvent.NO_FRAME, {}

        image, metadata, timestamp = item
        self.frames += 1
        self._pend("frames", self.frames)
        self._pend("measured_fps", f"{self.rate_meter.tick():.1f}")
        self._pend("last_frame_utc", camera.utc_now())
        if self.log_frames:
            self.pipeline_element.logger.debug(
                f"frame {frame_id}: {image.shape[1]}x{image.shape[0]} "
                f"{metadata}")
        stream.variables["timestamps"] = [timestamp]
        return aiko.StreamEvent.OKAY, {"images": [image]}

    # Shared state --------------------------------------------------------- #

    def _publish(self, key, value):
        """Event-loop thread only.  ECProducer.update() calls every
        handler, this scheme's included, so the handler ignores updates
        that originate here"""

        self._publishing = True
        try:
            self.pipeline_element.ec_producer.update(key, str(value))
        finally:
            self._publishing = False

    def _pend(self, key, value):
        """Any thread: published by the next _publish_handler()"""

        with self._pending_lock:
            self._pending[key] = str(value)

    def _pend_error(self, cause):
        self._pend("last_error", f"{camera.share_token(cause)}@"
                                 f"{camera.utc_now()}")
        self._pend("state", "error")

    def _publish_handler(self):
        with self._pending_lock:
            pending, self._pending = self._pending, {}
        producer = self.pipeline_element.ec_producer
        for key, value in pending.items():
            if producer.get(key) != value:
                self._publish(key, value)

    def _error(self, diagnostic):
        self._publish("last_error", f"{camera.share_token(diagnostic)}@"
                                    f"{camera.utc_now()}")
        self._publish("state", "error")
        return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if command != "update" or self._publishing:
            return
        try:
            if item_name == "capture_timeout":
                timeout = float(item_value)
                if timeout <= 0:
                    raise ValueError("must be positive")
                self.capture_timeout = timeout
            elif item_name == "log_frames":
                self.log_frames = camera.parse_bool(item_value, item_name)
            elif item_name == "focus_assist":
                self.focus_assist = camera.parse_bool(item_value, item_name)
                self._focus_due = 0.0
                if not self.focus_assist:
                    self._pend("sensor.sharpness", "-")
            else:
                self._apply_update(item_name, item_value)
        except (TypeError, ValueError) as error:
            self.pipeline_element.logger.warning(
                f"share update {item_name}={item_value!r} rejected: {error}")

# --------------------------------------------------------------------------- #
