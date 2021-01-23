# To Do
# ~~~~~
# - None, yet !

from aiko_services.stream import StreamElement

import numpy as np
from pathlib import Path
from PIL import Image

__all__ = [
    "ImageAnnotate1",
    "ImageAnnotate2",
    "ImageOverlay",
    "ImageReadFile",
    "ImageResize",
    "ImageWriteFile",
]


class ImageAnnotate1(StreamElement):
    expected_parameters = ()
    expected_inputs = ("image",)
    expected_outputs(
        "image",
    )

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        image = inputs.image
        return True, {"image": image}


class ImageAnnotate2(StreamElement):
    expected_parameters = ()
    expected_inputs = ("image",)
    expected_outputs(
        "image",
    )

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        image = inputs.image
        return True, {"image": image}


class ImageOverlay(StreamElement):
    expected_parameters = ()
    expected_inputs = ("image",)
    expected_outputs(
        "image",
    )

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        image = inputs.image
        return True, {"image": image}


class ImageReadFile(StreamElement):
    expected_parameters = ("image_pathname",)
    expected_inputs = ()
    expected_outputs("images,")

    def stream_start_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
        image_directory = Path(self.image_pathname).parent
        if not image_directory.exists:
            self.logger.error(f"Couldn't find directory: {image_directory}")
            return False, None
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        image_path = self.image_pathname.format(frame_id)
        try:
            pil_image = Image.open(image_path)
            image = np.asarray(pil_image, dtype=np.uint8)
        except Exception:
            self.logger.debug("End of images")
            return False, None

        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        if frame_id % 10 == 0:
            print(f"Frame Id: {frame_id}", end="\r")
        return True, {"image": image}


class ImageResize(StreamElement):
    expected_parameters = (
        "new_height",
        "new_width",
    )
    expected_inputs = ("image",)
    expected_outputs(
        "image",
    )

    def stream_start_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
        self.new_height = self.new_height
        self.new_width = self.new_width
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        pil_image = Image.fromarray(inputs.image)
        pil_image = pil_image.resize((self.new_width, self.new_height))
        image = np.asarray(pil_image, dtype=np.uint8)
        return True, {"image": image}


class ImageWriteFile(StreamElement):
    expected_parameters = ("image_pathname",)
    expected_inputs = ("image",)
    expected_outputs()

    def stream_start_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
        self.image_pathname = self.image_pathname
        # TODO: Error handling
        Path(self.image_pathname).parent.mkdir(exist_ok=True, parents=True)
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        pil_image = Image.fromarray(inputs.image)
        # TODO: Error handling: 1) format image, 2) save image
        pil_image.save(self.image_pathname.format(frame_id))
        return True, None
