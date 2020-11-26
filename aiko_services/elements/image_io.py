# To Do
# ~~~~~
# - None, yet !

from aiko_services.stream import StreamElement

import numpy as np
from pathlib import Path
from PIL import Image

__all__ = ["ImageAnnotate1",
           "ImageAnnotate2",
           "ImageGlobDirectories",
           "ImageOverlay",
           "ImageReadFile",
           "ImageResize",
           "ImageWriteFile"]


class ImageAnnotate1(StreamElement):
    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageAnnotate2(StreamElement):
    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageGlobDirectories(StreamElement):
    """Globs for extentions in given directories.

    ie:

    paths = []
    for dir in directories:
        for pat in patterns:
            paths.append(list(dir.glob(pat)))

    json:
    {
      "name": "ImgageGlobDirectories",
      "module": "task_processor.pipeline.file_io",
      "successors": [
        "..."
      ],
      "parameters": {
        "directories": ["dir0", "dir1", ...],
        "patterns": ["patternA", "patternB", ...]
      }
    },

    parameters:
        directories: A list of directories to glob
        patterns: A list of patterns to glob in each directory

    swag:
      image: One image at a time from globbed patterns.
             Directories will be globbed in order they appear.
             np.array(nd.uint8)

    pipeline stop:
      exhausted paths list
      error
    """
    def get_path_generator(self, directories, patterns):
        for directory in directories:
            d = Path(directory)
            if not d.exists():
                raise ValueError("Directory {d} does not exist")

            for pattern in patterns:
                self.logger.info(f"Globbing: {d}/{pattern}")
                for path in d.glob(pattern):
                    yield path

    def stream_start_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")

        try:
            self.path_gen = self.get_path_generator(
                self.parameters["directories"],
                self.parameters["patterns"],
            )
        except Exception as e:
            self.logger.error(f"Error getting path_generator. {e}")
            return False, None

        return True, None

    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}")
        try:
            image_path = next(self.path_gen)
            self.logger.info(f"Path: {image_path}")
            pil_image = Image.open(image_path)
            image = np.asarray(pil_image, dtype=np.uint8)
            out = {"image": image}
            pipeline_status = True
            if frame_id % 10 == 0:
                self.logger.info(f"Frame Id: {frame_id}")
        except ValueError as e:
            pipeline_status = False
            out = None
        except StopIteration as e:
            self.logger.info(f"All paths exhaused, stopping pipeline")
            pipeline_status = False
            out = None
        return pipeline_status, out


class ImageOverlay(StreamElement):
    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}")
        image = swag[self.predecessor]["image"]
        return True, {"image": image}

class ImageReadFile(StreamElement):
    def stream_start_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
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
            self.logger.debug("End of images")
            return False, None

        self.logger.debug(f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}")
        if frame_id % 10 == 0:
            print(f"Frame Id: {frame_id}", end="\r")
        return True, {"image": image}

class ImageResize(StreamElement):
    def stream_start_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
        self.new_height = self.parameters["new_height"]
        self.new_width = self.parameters["new_width"]
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}")
        pil_image = Image.fromarray(swag[self.predecessor]["image"])
        pil_image = pil_image.resize((self.new_width, self.new_height))
        image = np.asarray(pil_image, dtype=np.uint8)
        return True, {"image": image}

class ImageWriteFile(StreamElement):
    def stream_start_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
        self.image_pathname = self.parameters["image_pathname"]
# TODO: Error handling
        Path(self.image_pathname).parent.mkdir(exist_ok=True, parents=True)
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}")
        pil_image = Image.fromarray(swag[self.predecessor]["image"])
# TODO: Error handling: 1) format image, 2) save image
        pil_image.save(self.image_pathname.format(frame_id))
        return True, None

