# To Do
# ~~~~~
# - Enable GStreamer "appsink" properties to be set via "get_parameter()"
#
# - Create an RTSP DataTarget, which is an RTSP Server producing images
#
# - Support "data_batch_size" resulting in a frame containing multiple images

import queue
from threading import Thread

import aiko_services as aiko
from aiko_services.elements.gstreamer import (
    get_format, get_h264_decoder, gst_initialise, VideoReader)

__all__ = ["DataSchemeRTSP"]

RTSP_LATENCY = 500  # milliseconds, default: 2,000 milliseconds

# --------------------------------------------------------------------------- #
# parameter: "data_sources" provides the RTSP server details (incoming)
# - "data_sources" list should only contain a single entry
# - "(rtsp://hostname:port)"
# - "(rtsp://hostname:port/camera_channel)"
# - "(rtsp://username:password@hostname:port/camera_channel)"

class DataSchemeRTSP(aiko.DataScheme):
    def create_sources(self,
        stream, data_sources, frame_generator, use_create_frame=False):

        gst = gst_initialise()
        pipeline_element = self.pipeline_element
        rtsp_url = data_sources[0]
        self.share["rtsp_url"] = rtsp_url
        pipeline_element.logger.info(f"create_sources(): rtsp_url: {rtsp_url}")

        format, _ = pipeline_element.get_parameter("format", get_format())
        frame_rate, found = pipeline_element.get_parameter("frame_rate")
        if not found:
            diagnostic = 'Must provide "frame_rate" parameter'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        resolution, found = pipeline_element.get_parameter("resolution")
        if not found:
            diagnostic = 'Must provide "resolution" parameter'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        if isinstance(resolution, str):
            width, height = resolution.split("x")
            resolution = (int(width), int(height))

        gst_launch_command = f"rtspsrc location={rtsp_url} latency={RTSP_LATENCY} ! rtph264depay ! h264parse ! {get_h264_decoder()} ! videoconvert ! videorate ! appsink name=sink"
        gst_pipeline = gst.parse_launch(gst_launch_command)
        sink = gst_pipeline.get_by_name("sink")
        sink_caps = f"video/x-raw, format={format}, width={width}, height={height}, framerate={frame_rate}"
        sink.set_property("caps", gst.caps_from_string(sink_caps))
        sink.set_property("drop", True)          # drop buffers, if queue full
        sink.set_property("emit-signals", True)  # enable "new-sample" signal
        sink.set_property("max-buffers", 1)      # buffer queue size
        sink.set_property("sync", False)         # playback fast as possible
        self.video_reader = VideoReader(gst_pipeline, sink)

        self.queue = queue.Queue()
        self.terminate = False

        pipeline_element.create_frames(stream, self.frame_generator, rate=0.0)
        return aiko.StreamEvent.OKAY, {}

    def create_targets(self, stream, data_targets):
        diagnostic = "DataSchemeRTSP does not implement create_targets()"
        return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

    def destroy_sources(self, stream):
        self.terminate = True
        self.video_reader.stop()

    def destroy_targets(self, stream):
        diagnostic = "DataSchemeRTSP does not implement destroy_targets()"
        return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

    def frame_generator(self, stream, frame_id):
        if self.terminate:
            return aiko.StreamEvent.STOP, {"diagnostic": "Terminated"}

        data_batch_size, _ = self.pipeline_element.get_parameter(
            "data_batch_size", default=1)
        data_batch_size = int(data_batch_size)

        frame = self.video_reader.read_frame(0.01)
        images = []
        if frame:
            if "type" in frame and frame["type"] == "image":
                images.append(frame["image"])
                timestamp = -1.0
                if "timestamp" in frame:
                    timestamp = frame["timestamp"]
                    if type(timestamp) is not float:
                        timestamp = -2.0
                stream.variables["timestamps"] = [frame["timestamp"]]

        if images:
            return aiko.StreamEvent.OKAY, {"images": images}
        else:
            return aiko.StreamEvent.NO_FRAME, {}

aiko.DataScheme.add_data_scheme("rtsp", DataSchemeRTSP)

# --------------------------------------------------------------------------- #
