# To Do
# ~~~~~
# - In "sample_image()" replace "self.image" with an "image_queue"
#   Currently, will drop "images" if get_image() isn't called often enough
#   - Limit the queue length (ring buffer) to prevent excessive memory use
#   - Optionally, offer an "image queue", so that no images are lost
#
# - When pipeline can't be set to "playing state", find out more about the
#   GStreamer problem and report as part of the diagnostic message
#   - Improve command line utilities to catch and report the problem

import numpy as np
import sys
from threading import Thread
import time

if sys.version_info >= (3,0):
  from queue import Queue, Empty
else:
  from Queue import Queue, Empty

from aiko_services.elements.gstreamer import *

__all__ = ["VideoReader"]

# -----------------------------------------------------------------------------

Gst = gst_initialise()

class VideoReader:
  def __init__(self, pipeline, sink):
    self.pipeline  = pipeline
    self.bus       = pipeline.get_bus()
    self.queue     = Queue(maxsize=30)
    self.frame_id  = 1
    self.image     = None
    self.terminate = False
    self.timestamp = 0  # Unix time

#   sink = pipeline.get_by_name("sink")
#   sink.set_property("max-buffers", 2)
#   sink.set_property("drop", True)
#   sink.set_property("sync", False)
    sink.set_property("emit-signals", True)
    sink.connect("new-sample", self.sample_image, sink)

    if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
      raise GStreamerError("Unable to set the pipeline to the playing state")

    def _run():
      while not self.terminate:
        timeout = 1000 * 1000  # nanoseconds
        message = self.bus.timed_pop_filtered(timeout, Gst.MessageType.ANY)

        if self.image is not None:
#         print("NBVR frame: ", self.frame_id, self.queue.qsize())
#         self.image = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
          frame = {
            "type": "image",
            "id": self.frame_id,
            "image": self.image,
            "timestamp": self.timestamp  # Unix time
          }
          self.image = None
          self.timestamp = None
          self.queue.put(frame)
          self.frame_id += 1

        if message:
          if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print("Error received from element %s: %s" % (
              message.src.get_name(), err))
            print("Debugging information: %s" % debug)
            break
          elif message.type == Gst.MessageType.EOS:
            print("GStreamer End-Of-Stream")
            frame = { "type": "EOS" }
            self.queue.put(frame)
            break
          elif message.type == Gst.MessageType.STATE_CHANGED:
            if isinstance(message.src, Gst.Pipeline):
              old_state,new_state,pending_state = message.parse_state_changed()
              print("GStreamer Pipeline state changed from %s to %s" %
                (old_state.value_nick, new_state.value_nick))

    self._t = Thread(target=_run, args=())
    self._t.daemon = True
    self._t.start()

  def gst_to_opencv(self, buffer_data, caps):
#   format = caps.get_structure(0).get_value("format")
    width  = caps.get_structure(0).get_value("width")
    height = caps.get_structure(0).get_value("height")
    image = np.ndarray((height, width, 3), buffer=buffer_data, dtype=np.uint8)
    return image

  def read_frame(self, timeout=None):
    try:
      return self.queue.get(block = timeout is not None, timeout = timeout)
    except Empty:
      return None

  def queue_size(self):
    return self.queue.qsize()

  def sample_image(self, sink, data):
    sample = sink.emit("pull-sample")
    self.timestamp = time.time()  # Unix time
    buffer = sample.get_buffer()

  # Avoid memory leak that is common in many on-line Python examples 😱
  # Use "buffer.map" instead of "buffer.extract_dup(0, buffer_size)" 🤔
    success, buffer_map = buffer.map(Gst.MapFlags.READ)

    if success:
      try:
        caps = sample.get_caps()
    # 120 microseconds: self.gst_to_opencv()
    # 400 microseconds: .copy()
        self.image = self.gst_to_opencv(buffer_map.data, caps).copy()

    # https://gstreamer.freedesktop.org/documentation/gstreamer/...
    #         gstbuffer.html#members
    #   self.decode_timestamp = buffer.dts
    #   self.presentation_timestamp = buffer.pts

      finally:
        buffer.unmap(buffer_map)
    return Gst.FlowReturn.OK

  def stop(self):
    self.terminate = True
