# To Do
# ~~~~~
# - Replace "Gst.parse_launch()" with hand-built pipeline !

import sys
from threading import Thread

if sys.version_info >= (3,0):
  from queue import Queue, Empty
else:
  from Queue import Queue, Empty

from aiko_services.elements.gstreamer import *

__all__ = ["VideoFileWriter"]

# -----------------------------------------------------------------------------

class VideoFileWriter:
  def __init__(self, filename, width, height, framerate):
    self.Gst = gst_initialise()
    self.queue = Queue(maxsize=30)

# vtenc_h264: 1280x768, 512x288, 256x144
    gst_launch_command = "appsrc name=source ! videoconvert ! videoscale ! videorate ! video/x-raw,width=1280,height=768,framerate=25/1 ! {} ! splitmuxsink location={}"
#   location={}_%03d.mp4
#   max-files=10
#   max-size-bytes=1024000
#   max-size-time=1000000  # 1 second

#   gst_launch_command = "appsrc name=source ! {} ! mp4mux ! filesink location={}"
#   gst_launch_command = "appsrc name=source ! jpegenc ! avimux ! filesink location={}"
#   gst_launch_command = "appsrc name=source ! {} ! decodebin ! mpegtsmux ! filesink location={}"

    pipeline = self.Gst.parse_launch(gst_launch_command.format(utilities.get_h264_encoder(), filename))

    appsrc = pipeline.get_child_by_name("source")
    src_caps = "video/x-raw,format={},width={},height={},framerate={}".format(utilities.get_format(), width, height, framerate)
    appsrc.props.caps = self.Gst.caps_from_string(src_caps)

    appsrc.props.stream_type  = 0  # GST_APP_STREAM_TYPE_STREAM
    appsrc.props.is_live      = True
    appsrc.props.do_timestamp = True
    appsrc.props.format       = self.Gst.Format.TIME

    pipeline.set_state(self.Gst.State.PLAYING)

    def _run():
      while True:
        frame = self.queue.get()
        if "type" in frame and frame["type"] == "EOS":
          appsrc.emit('end-of-stream')
        else:
#         print("VFW frame: ", frame["id"], self.queue.qsize())
          data = frame["image"].tobytes()
          buffer = self.Gst.Buffer.new_allocate(None, len(data), None)
          buffer.fill(0, data)
          appsrc.emit('push-buffer', buffer)

    self._t = Thread(target=_run, args=())
    self._t.daemon = True
    self._t.start()

  def queue_size(self):
    return self.queue.qsize()

  def write_frame(self, frame):
    self.queue.put(frame)
