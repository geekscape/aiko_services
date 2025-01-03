# Requires either ...
# - pip install PyGObject
# ... or ...
# - apt-get install python3-gi

from sys import platform

__all__ = [
    "get_format",
    "get_h264_decoder", "get_h264_encoder", "get_h264_encoder_options",
    "GStreamerError", "gst_initialise", "enable_opencv", "process_video"
]

# --------------------------------------------------------------------------- #

operating_system = "unknown"

if platform == "linux" or platform == "linux2":
  operating_system = "linux"
elif platform == "darwin":
  operating_system = "mac_os_x"

format = "RGB"
h264_decoder = { "linux": "avdec_h264", "mac_os_x": "avdec_h264" }
h264_encoder = { "linux": "x264enc",    "mac_os_x": "vtenc_h264" }

def get_format():
  return format

def get_h264_decoder():
  return h264_decoder[operating_system]

def get_h264_encoder():
  return h264_encoder[operating_system]

def get_h264_encoder_options():
  if operating_system != "linux": return ""

  return "tune=zerolatency speed-preset=ultrafast sliced-threads=true key-int-max=30"

# --------------------------------------------------------------------------- #

import gi

Gst = None
GstBase = None
GObject = None

class GStreamerError(Exception):
  def __init__(self, message):
    self.message = message

def gst_initialise(multiple_return_values=False):
  global Gst, GstBase, GObject

  if not Gst:
    gi.require_version('Gst', '1.0')
    gi.require_version('GstBase', '1.0')
    from gi.repository import Gst, GstBase, GObject
    Gst.init(None)

  if multiple_return_values:
    return Gst, GstBase, GObject
  else:
    return Gst

# --------------------------------------------------------------------------- #

cv2 = None

def enable_opencv():
  global cv2
  cv2 = None

  try:
    cv2 = __import__("cv2")
  except Exception: pass

  return cv2

def process_video(video_reader, video_writer):
  while True:
    frame = video_reader.read_frame(0.01)

    if frame != None:
      if "type" in frame and frame["type"] == "image":
#       print("Frame: ", frame["id"], video_reader.queue_size(), video_writer.queue_size())

        if cv2:
          image = cv2.cvtColor(frame["image"], cv2.COLOR_RGB2BGR)
          cv2.imshow("Video", image)
          if cv2.waitKey(1) & 0xff == ord('q'): break

          frame["image"] = cv2.putText(
            frame["image"], str(frame["id"]), (100, 400),
            cv2.FONT_HERSHEY_SIMPLEX, 2, (255,255,255), 2, cv2.LINE_AA)

      video_writer.write_frame(frame)

# --------------------------------------------------------------------------- #
