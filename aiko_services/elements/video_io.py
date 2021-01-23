# To Do
# ~~~~~
# - Implement ...
#     video_capture = cv2.VideoCapture(video_pathname)
#     width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
#     height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
#     length = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
#     frame_rate = int(video_capture.get(cv2.CAP_PROP_FPS))
try:
    import cv2
except ModuleNotFoundError:
    raise ModuleNotFoundError(
        (
            "opencv-python package not installed. "
            'Install aiko_services with --extras "opencv" '
            "or install opencv-python manually to use this "
            "module."
        )
    )

from pathlib import Path
import numpy as np

from aiko_services.stream import StreamElement

__all__ = ["VideoReadFile", "VideoShow", "VideoWriteFile"]


class VideoReadFile(StreamElement):
    expected_parameters = ("video_pathname",)
    expected_inputs = ()
    expected_outputs = "images"

    def stream_start_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
        self.video_capture = cv2.VideoCapture(self.video_pathname)
        if self.video_capture.isOpened() == False:
            self.logger.error(f"Couldn't open video file: {self.video_pathname}")
            return False, None

        self.state_action = None
        if self.pipeline_state_machine and "state_action" in self.parameters:
            self.state_action = self.parameters["state_action"]
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        # ToDo: implement bathch size
        if self.video_capture.isOpened():
            success, image_bgr = self.video_capture.read()
            if success == True:
                self.logger.debug(
                    f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
                )
                image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                image_rgb = np.expand_dims(image_rgb, axis=0)
                if frame_id % 10 == 0:
                    print(f"Frame Id: {frame_id}", end="\r")

                if self.state_action:
                    if frame_id == self.state_action[0]:
                        self.pipeline_state_machine.transition(
                            self.state_action[1], None
                        )
                return True, {"images": image_rgb}
            else:
                self.logger.debug("End of video")
        return False, None

    def stream_stop_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_stop_handler(): stream_id: {stream_id}")
        self.video_capture.release()
        self.video_capture = None
        return True, None


class VideoShow(StreamElement):
    expected_parameters = ()
    expected_inputs = ()
    expected_outputs = ()

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        title = self.window_title
        image_rgb = inputs.image
        image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2RGB)
        cv2.imshow(title, image_bgr)
        if frame_id == 0:
            window_x = self.window_location[0]
            window_y = self.window_location[1]
            cv2.moveWindow(title, window_x, window_y)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            return False, None
        return True, {"image": image_rgb}

    def stream_stop_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_stop_handler(): stream_id: {stream_id}")
        cv2.destroyAllWindows()
        return True, None


class VideoWriteFile(StreamElement):
    expected_parameters = (
        ("video_format", "MP4V"),
        "video_frame_rate",
        ("video_pathname", "video_output.mp4"),
    )
    expected_inputs = ("images",)
    expected_outputs = ()

    def stream_start_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
        self.image_shape = None
        self.video_writer = None
        return True, None

    def _init_video_writer(self, video_pathname, video_format, frame_rate, image_shape):
        video_directory = Path(video_pathname).parent
        video_directory.mkdir(exist_ok=True, parents=True)
        return cv2.VideoWriter(
            video_pathname,
            cv2.VideoWriter_fourcc(*video_format),
            frame_rate,
            image_shape,
        )

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        image_shape = inputs.images.shape
        if len(image_shape) == 4:
            if image_shape[0] == 1:
                image_rgb = inputs.images
            else:
                self.logger.error(
                    "VideoWriteFile cannot support more than one image at a time. Got : image of shape '{image_shape}'"
                )
                return False, None
        else:
            image_rgb = inputs.images

        image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2RGB)

        if self.video_writer is None:
            if self.image_shape is None:
                self.image_shape = (image_rgb.shape[1], image_rgb.shape[0])
            self.video_writer = self._init_video_writer(
                self.video_pathname,
                self.video_format,
                self.video_frame_rate,
                self.image_shape,
            )

        self.video_writer.write(image_bgr)
        return True, {"image": image_rgb}

    def stream_stop_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_stop_handler(): stream_id: {stream_id}")
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        return True, None
