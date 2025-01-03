# To Do
# ~~~~~
# - Constuctor "Queue maxsize" parameter
# - Ultimately, will start "paused" and will tell video sender to start
# - Should do video_capture.release() ... need to terminate thread first ?
# - Optimization: Option to request image in BGR format to avoid having to
#   convert from RGB to BGR for subsequent OpenCV manipulation.

from aiko_services.elements.gstreamer import *

# Security network camera ...
url_template = "rtsp://USERNAME:PASSWORD@%s:%s"
url_template = "rtsp://admin:silverpond!@%s:%s"

# Periscope HD iOS application (Quality: normal = 640x480 @ 30 FPS)
# url_template = "rtsp://admin:admin@%s:%s/live.sdp"

__all__ = ["VideoStreamReader"]

# -----------------------------------------------------------------------------

class VideoStreamReader:
  def __init__(self, input_hostname, input_port, width, height,
      framerate=None, rtp=False):

    self.Gst = gst_initialise()
    self.source = None
    self.depay = None

    pipeline, sink = self.create_pipeline(input_hostname, input_port, rtp)

    if framerate:  # e.g "30/1", "25/1", "4/1"
      sink_caps = "video/x-raw, format={}, width={}, height={}, framerate={}".format(utilities.get_format(), width, height, framerate)
    else:
      sink_caps = "video/x-raw, format={}, width={}, height={}".format(utilities.get_format(), width, height)
    sink.set_property("caps", self.Gst.caps_from_string(sink_caps))

    self.video_reader = VideoReader(pipeline, sink)

  def on_dynamic_pad(self, dbin, pad):
    if not self.Gst.Element.link(self.source, self.depay):
      pipeline_link_error("source", "depay")
#   pad.link(self.convert.get_pad("source"))

  def create_pipeline(self, input_hostname, input_port, rtp):
    if rtp:
      self.source = self.Gst.ElementFactory.make("udpsrc", None)
      self.source.set_property("port", int(input_port))
      self.source.set_property("caps", self.Gst.caps_from_string(
        "application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264"))
    else:
      url = url_template % (input_hostname, input_port)
      self.source = self.Gst.ElementFactory.make("rtspsrc", None)
      self.source.set_property("location", url)
      self.source.set_property("latency",  10)

    self.depay = self.Gst.ElementFactory.make("rtph264depay", None)
    parser     = self.Gst.ElementFactory.make("h264parse", None)
    decoder    = self.Gst.ElementFactory.make(utilities.get_h264_decoder(), None)
    convert    = self.Gst.ElementFactory.make("videoconvert", None)
    videorate  = self.Gst.ElementFactory.make("videorate", None)
    sink       = self.Gst.ElementFactory.make("appsink", None)
    pipeline   = self.Gst.Pipeline.new("pipeline")

    if not pipeline:
      raise GStreamerError("Failed to create video pipeline")

    pipeline.add(self.source)
    pipeline.add(self.depay)
    pipeline.add(parser)
    pipeline.add(decoder)
    pipeline.add(convert)
    pipeline.add(videorate)
    pipeline.add(sink)

    if rtp:
      self.link_element("source",  self.source, "depay",   self.depay)
    else:
      self.source.connect("pad-added", self.on_dynamic_pad)
    self.link_element("depay",     self.depay,  "parser",    parser)
    self.link_element("parser",    parser,      "decoder",   decoder)
    self.link_element("decoder",   decoder,     "convert",   convert)
    self.link_element("convert",   convert,     "videorate", videorate)
    self.link_element("videorate", videorate,   "sink",      sink)

    return pipeline, sink

  def link_element(self, source_name, source, target_name, target):
    if not self.Gst.Element.link(source, target):
      raise GStreamerError("Couldn't link Pipeline elements: %s to %s" %
        (element1, element2))

  def queue_size(self):
    return self.video_reader.queue.qsize()

  def read_frame(self, timeout = None):
    return self.video_reader.read_frame(timeout)
