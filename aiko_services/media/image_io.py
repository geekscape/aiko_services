# To Do
# ~~~~~
# - None, yet !

from aiko_services.stream import StreamElement

import numpy as np
from pathlib import Path
from PIL import Image

__all__ = ["ImageAnnotate1", "ImageAnnotate2", "ImageOverlay", "ImageReadFile", "ImageWriteFile"]


class ImageAnnotate1(StreamElement):
    def stream_frame_handler(self, swag):
        self.logger.debug(f"stream_frame_handler(): frame_count: {self.frame_count}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageAnnotate2(StreamElement):
    def stream_frame_handler(self, swag):
        self.logger.debug(f"stream_frame_handler(): frame_count: {self.frame_count}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageOverlay(StreamElement):
    def stream_frame_handler(self, swag):
        self.logger.debug(f"stream_frame_handler(): frame_count: {self.frame_count}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageReadFile(StreamElement):
    def stream_start_handler(self, swag):
        self.logger.debug("stream_start_handler()")
        self.image_pathname = self.parameters["image_pathname"]
        image_directory = Path(self.image_pathname).parent
        if not image_directory.exists:
            self.logger.error(f"Couldn't find directory: {image_directory}")
            return False, None
        return True, None

    def stream_frame_handler(self, swag):
        image_path = self.image_pathname.format(self.frame_count)
        try:
            image = np.asarray(Image.open(image_path), dtype=np.uint8)
        except Exception:
            self.logger.debug(f"End of images")
            return False, None

        self.logger.debug(f"stream_frame_handler(): frame_count: {self.frame_count}")
        if self.frame_count % 10 == 0:
            print(f"Frame Id: {self.frame_count}", end="\r")
        return True, {"image": image}

class ImageWriteFile(StreamElement):
    def stream_start_handler(self, swag):
        self.image_pathname = self.parameters["image_pathname"]
# TODO: Error handling
        Path(self.image_pathname).parent.mkdir(exist_ok=True, parents=True)
        return True, None

    def stream_frame_handler(self, swag):
        self.logger.debug(f"stream_frame_handler(): frame_count: {self.frame_count}")
        image = swag[self.predecessor]["image"]
        pil_image = Image.fromarray(image)
# TODO: Error handling
        pil_image.save(self.image_pathname.format(self.frame_count))
        return True, None
