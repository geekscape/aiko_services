# To Do
# ~~~~~
# - Split into "image.py" and "video.py"

import cv2

from aiko_services.stream import StreamElement

__all__ = ["ImageShow", "VideoReadFile"]

class ImageShow(StreamElement):
    def stream_frame_handler(self, swag):
        self.logger.debug(f"stream_frame_handler(): frame_id: {self.frame_id}")
        image = swag[self.predecessor]["image"]
        title = self.parameters["window_title"]
        cv2.imshow(title, image)
        if self.frame_id == 0:
            cv2.moveWindow(title, self.parameters["window_x"], self.parameters["window_y"])
        if cv2.waitKey(1) & 0xFF == ord("q"):
            return False, None
        return True, None

    def stream_stop_handler(self, swag):
        self.logger.debug("stream_stop()")
        cv2.destroyAllWindows()
        return True, None

class VideoReadFile(StreamElement):
    def stream_start_handler(self, swag):
        self.logger.debug("stream_start_handler()")
        video_filename = self.parameters["video_pathname"]
        self.video_capture = cv2.VideoCapture(video_filename)
        if (self.video_capture.isOpened() == False): 
            self.logger.error(f"Couldn't open video file: {video_filename}")
            return False, None
        return True, None

    def stream_frame_handler(self, swag):
        if self.video_capture.isOpened():
            success, image = self.video_capture.read()
            if success == True:
                self.logger.debug(f"stream_frame_handler(): frame_id: {self.frame_id}")
                if self.frame_id % 10 == 0:
                    print(f"Frame Id: {self.frame_id}", end="\r")
                return True, {"image": image}
            else:
                self.video_capture.release()
                self.logger.debug(f"Video end of file")
        return False, None

class ImageAnnotate1(StreamElement):
    def stream_frame_handler(self, swag):
        self.logger.debug(f"stream_frame_handler(): frame_id: {self.frame_id}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageAnnotate2(StreamElement):
    def stream_frame_handler(self, swag):
        self.logger.debug(f"stream_frame_handler(): frame_id: {self.frame_id}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageOverlay(StreamElement):
    def stream_frame_handler(self, swag):
        self.logger.debug(f"stream_frame_handler(): frame_id: {self.frame_id}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}
