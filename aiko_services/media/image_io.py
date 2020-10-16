# To Do
# ~~~~~
# - None, yet !

from aiko_services.stream import StreamElement

import numpy as np
from pathlib import Path
from PIL import Image

__all__ = ["ImageAnnotate1", "ImageAnnotate2", "ImageOverlay", "ImageReadFile", "ImageResize", "ImageWriteFile"]


class ImageAnnotate1(StreamElement):
    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): frame_id: {frame_id}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageAnnotate2(StreamElement):
    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): frame_id: {frame_id}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageOverlay(StreamElement):
    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): frame_id: {frame_id}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageReadFile(StreamElement):
    def stream_start_handler(self, stream_id, frame_id, swag):
        self.logger.debug("stream_start_handler()")
        self.image_pathname = self.parameters["image_pathname"]
        image_directory = Path(self.image_pathname).parent
        if not image_directory.exists:
            self.logger.error(f"Couldn't find directory: {image_directory}")
            return False, None
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, swag):
        image_path = self.image_pathname.format(frame_id)
        try:
            pil_image = Image.open(image_path)
            image = np.asarray(pil_image, dtype=np.uint8)
        except Exception:
            self.logger.debug(f"End of images")
            return False, None

        self.logger.debug(f"stream_frame_handler(): frame_id: {frame_id}")
        if frame_id % 10 == 0:
            print(f"Frame Id: {frame_id}", end="\r")
        return True, {"image": image}

class ImageResize(StreamElement):
    def stream_start_handler(self, stream_id, frame_id, swag):
        self.new_height = self.parameters["new_height"]
        self.new_width = self.parameters["new_width"]
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): frame_id: {frame_id}")
        pil_image = Image.fromarray(swag[self.predecessor]["image"])
        pil_image = pil_image.resize((self.new_width, self.new_height))
        image = np.asarray(pil_image, dtype=np.uint8)
        return True, {"image": image}

class ImageWriteFile(StreamElement):
    def stream_start_handler(self, stream_id, frame_id, swag):
        self.image_pathname = self.parameters["image_pathname"]
# TODO: Error handling
        Path(self.image_pathname).parent.mkdir(exist_ok=True, parents=True)
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): frame_id: {frame_id}")
        pil_image = Image.fromarray(swag[self.predecessor]["image"])
# TODO: Error handling: 1) format image, 2) save image
        pil_image.save(self.image_pathname.format(frame_id))
        return True, None
