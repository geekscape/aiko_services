# To Do
# ~~~~~
# - None, yet.
#
# Notes
# ~~~~~
# gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! autovideosink
#
# To Do
# ~~~~~
# - Support Mac OS X camera sources

import os

from aiko_services.elements.gstreamer import *

__all__ = ["VideoCameraReader"]

# -----------------------------------------------------------------------------

class VideoCameraReader:
  def __init__(self, input_devicepath, width, height):
    if not os.path.exists(input_devicepath):
      raise ValueError("Device does not exist: " + input_devicepath)

    Gst = gst_initialise()

    gst_launch_command = "v4l2src device={} ! videoflip video-direction=horiz ! videoconvert ! videorate ! appsink name=sink".format(input_devicepath)
    pipeline = Gst.parse_launch(gst_launch_command)

    sink = pipeline.get_by_name("sink")
    sink_caps = "video/x-raw, format={}, width={}, height={}, framerate={}".format(utilities.get_format(), width, height, "10/1")
    sink.set_property("caps", Gst.caps_from_string(sink_caps))

    self.video_reader = VideoReader(pipeline, sink)

  def queue_size(self):
    return self.video_reader.queue.qsize()

  def read_frame(self, timeout = None):
    return self.video_reader.read_frame(timeout)
