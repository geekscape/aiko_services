# To Do
# ~~~~~
# - None, yet.
#
# Notes
# ~~~~~
# gst-launch-1.0 filesrc location=../football_test_1.mp4 ! qtdemux ! avdec_h264 ! videoconvert ! osxvideosink
#
# CUDA_VISIBLE_DEVICES=3 /mnt/code/aiko_services_internal/aiko_services_internal/video/gstreamer/video_example.py -if /app/resources/sample.mp4 -os 192.168.1.154:5000 -r 1280 1280 -f 6/1

import os

from aiko_services.elements.gstreamer import *

__all__ = ["VideoFileReader"]

# -----------------------------------------------------------------------------

class VideoFileReader:
  def __init__(self, input_filename, width, height):
    if not os.path.exists(input_filename):
      raise ValueError("File does not exist: " + input_filename)

    Gst = gst_initialise()

    gst_launch_command = "filesrc location={} ! qtdemux ! {} ! videoconvert ! video/x-raw, format={} ! appsink name=sink".format(input_filename, utilities.get_h264_decoder(), utilities.get_format())
    pipeline = Gst.parse_launch(gst_launch_command)

    sink = pipeline.get_by_name("sink")
    sink_caps = "video/x-raw, format={}, width={}, height={}".format(utilities.get_format(), width, height)
    sink.set_property("caps", Gst.caps_from_string(sink_caps))

    self.video_reader = VideoReader(pipeline, sink)

  def queue_size(self):
    return self.video_reader.queue.qsize()

  def read_frame(self, timeout = None):
    return self.video_reader.read_frame(timeout)
