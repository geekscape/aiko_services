# Usage
# ~~~~~
# - gst-launch-1.0 videotestsrc ! video/x-raw,width=852,height=480,framerate=\(fraction\)24/1 ! x264enc pass=pass1 threads=0 bitrate=900 tune=zerolatency ! flvmux name=mux ! rtmpsink location="rtmp://highlighter.antmedia.io/WebRTCAppEE/759246100812675440813771"
#
# To Do
# ~~~~~
# - Replace "Gst.parse_launch()" with hand-built pipeline !

import sys
import time
from threading import Thread

if sys.version_info >= (3,0):
  from queue import Queue, Empty
else:
  from Queue import Queue, Empty

from aiko_services.elements.gstreamer import *

__all__ = ["VideoStreamWriter"]

# -----------------------------------------------------------------------------

data = None

class VideoStreamWriter:
  def __init__(self, hostname, port, width, height, framerate, rtmp_url=None):
    self.Gst = gst_initialise()
    self.queue = Queue(maxsize=30)

    if rtmp_url:
      gst_launch_command = 'appsrc name=source ! videoconvert ! x264enc bitrate=1000 me=4 subme=10 ref=2 tune=zerolatency ! video/x-h264 ! h264parse ! video/x-h264 ! queue ! flvmux name=muxer streamable=true ! rtmpsink location="{}" sync=false'.format(rtmp_url)
    else:
      gst_launch_command = "appsrc name=source ! videoconvert ! {} {} ! rtph264pay config-interval=5 pt=96 ! udpsink host={} port={}".format(utilities.get_h264_encoder(), utilities.get_h264_encoder_options(), hostname, port)

    pipeline = self.Gst.parse_launch(gst_launch_command)
    appsrc = pipeline.get_child_by_name("source")
    src_caps = "video/x-raw,format={},width={},height={},framerate={}".format(utilities.get_format(), width, height, framerate)
    appsrc.props.caps = self.Gst.caps_from_string(src_caps)

    appsrc.props.stream_type  = 0  # GST_APP_STREAM_TYPE_STREAM
    appsrc.props.is_live      = True
    appsrc.props.do_timestamp = True
    appsrc.props.format       = self.Gst.Format.TIME

    pipeline.set_state(self.Gst.State.PLAYING)

    def _run_consume_queue():
      global data

      while True:
        frame = self.queue.get()
        if "type" in frame and frame["type"] == "EOS":
          appsrc.emit('end-of-stream')
        else:
#         print("VSW frame: ", frame["id"], self.queue.qsize())
          data = frame["image"].tobytes()
          buffer = self.Gst.Buffer.new_allocate(None, len(data), None)
          buffer.fill(0, data)
          appsrc.emit('push-buffer', buffer)

    self._t1 = Thread(target=_run_consume_queue, args=())
    self._t1.daemon = True
    self._t1.start()

    def _run_constant_framerate():
      global data

      while True:
        time.sleep(0.04)
        if data:
          buffer = self.Gst.Buffer.new_allocate(None, len(data), None)
          buffer.fill(0, data)
          appsrc.emit('push-buffer', buffer)

#   self._t2 = Thread(target=_run_constant_framerate, args=())
#   self._t2.daemon = True
#   self._t2.start()

  def queue_size(self):
    return self.queue.qsize()

  def write_frame(self, frame):
    self.queue.put(frame)
