# Usage
# ~~~~~
# export AIKO_LOG_LEVEL=DEBUG; export AIKO_LOG_MQTT=false
#
# aiko_pipeline create pipeline_image_0.json --stream_id 1    \
#   -sp ImageReadFile.data_batch_size 8  2>&1 | cut -c34-
#
# aiko_pipeline create pipeline_image_0.json --stream_id 1    \
#   -sp ImageReadFile.data_sources file://data_in/in_{}.jpeg
#
# aiko_pipeline create pipeline_image_0.json --stream_id 1    \
#   -sp ImageReadFile.data_sources file://data_in/in_00.jpeg  \
#   -sp ImageResize.resolution 320:240                        \
#   -sp ImageWriteFile.data_targets file://data_out/out_00.jpeg
#
# aiko_pipeline create pipeline_image_0.json
#     -fd "(data_sources: data_in/in_00.jpeg)"
#
# To Do
# ~~~~~
# - Refactor optional module import into common function (see video_io.py)
# - Refactor "utility.py:contains_all()"
# - Refactor "utility.py" "data_sources" parsing
# - Refactor "utility.py" path glob generator
#
# - Consider what causes Stream to be closed, e.g single frame processed ?
#   - When all [data_sources] produced and not the default stream ?
#
# - Add Stream "parameter" for optional output Image numpy format
#
# - Document "DataSource" and "DataTarget" ...
#   - ImageReadFile:  start_stream() --> create_frames() --> process_frame()
#                     Therefore pass parameters as required
#   - ImageWriteFile: Mustn't use create_frame()
#                     Therefore get parameters in process_frame()
#
# - ImageReadFile should accept a list of DataSources type ...
#   - URL: "file://" and media_type: "jpeg", "png", etc
#
# - PE_Metrics: Determine what to metrics to capture, e.g frame rates ?

import os
from pathlib import Path
from PIL import Image
from typing import Tuple

import aiko_services as aiko
from aiko_services.main.utilities import parse

_LOGGER = aiko.get_logger(__name__)

_NUMPY_IMPORTED = False
try:
    import numpy as np
    _NUMPY_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "image_io.py: Couldn't import numpy module"
    print(f"WARNING: {diagnostic}")
    _LOGGER.warning(diagnostic)

__all__ = ["ImageOverlay", "ImageReadFile", "ImageResize", "ImageWriteFile"]

def contains_all(source: str, match: chr):  # TODO: Refactor utility code
    return False not in [character in source for character in match]

def file_glob_difference(file_glob, filename):
    difference = None
    tokens = file_glob.split("*")
    token_start = tokens[0]
    token_end = tokens[1] if len(tokens) > 1 else ""
    if filename.startswith(token_start) and filename.endswith(token_end):
        difference = filename[len(token_start):len(filename)-len(token_end)]
    return difference

# --------------------------------------------------------------------------- #
# ToDo: Display lines, mask, polygons, rectangles, text
# ToDo: Display Metrics
# ToDo: Display pose stick figures

class ImageOverlay(aiko.PipelineElement):
    pass

# --------------------------------------------------------------------------- #
# Check
# ~~~~~
# - Return Pipeline result back to HL Serving Task
#
# - aiko_pipeline argument options for AIKO_LOG_LEVEL / AIKO_LOG_MQTT
#   - AIKO_LOG_MQTT --> AIKO_LOG=mqtt,console,...
#
# - Try to remove the need to write PE.__init__(...) in every PE
#
# * PE.set_parameter(): parameters --> self.share[] ?
#
# * aiko_pipeline create -s 1 -sp data_sources --> load stream parameter data
#   - Overriding the PipelineDefinition
#   - Same for HL Serving Tasks and HL Live
#
# * If DataSource has "stream_required" ...
#   - Each DataSource developer shouldn't have to do this
#
# * Consider process_frame() updating stream parameters --> self.share[]
#   - See timer driven "main/pipeline.py:_update_lifecycle_state()"
#
# * For "PipelineElement.create_frames()" ...
#   - Implement frame window, which has a maximum size to minimise frames
#   - Implement frame "push back" so subsequent PEs can manage frame flow
#
# - Check HL Serving Task and HL Live
#   - process_datasources(stream_id, parameters, [data_sources])
#     - data_sources: URL and MediaType
#
# - Read/Write, to/from File, to/from Stream
#
# - URLs
#   - file://, http://, mqtt://, hl:// (pre-signed URL), s3://
#   - web_camera://, rtsp://, webrt://
#   - youtube:// uploaded video or live stream
#   * Haplomic: Shared memory, e.g shm://
#
# - MediaTypes
#   - image/raw|jpeg|png, video/h.264, audio/*, text/raw, pointcloud/2d|3d
#   * Laboratory camera: image/raw

# --------------------------------------------------------------------------- #
# ImageReadFile is a DataSource which supports ...
# - Individual image file
# - Directory of image files with an optional filename filter
# - TODO: Archive (tgz, zip) of image files with an optional filename filter
#
# Supports both Streams and direct process_frame() calls

class ImageReadFile(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        data_sources, found = self.get_parameter("data_sources")
        if not found:
            diagnostic = 'Must provide "data_sources" parameter'
            return aiko.StreamEvent.ERROR, diagnostic
        data_source, data_sources = parse(data_sources)  # TODO: Improve parse()
        data_sources.insert(0, data_source)

        paths = []
        for data_source in data_sources:
            tokens = data_source.split("://")  # URL "file://path" or "path"
            if len(tokens) == 1:
                path = tokens[0]
            else:
                if tokens[0] != "file":
                    diagnostic = 'DataSource scheme must be "file://"'
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
                path = tokens[1]

            file_glob = "*"
            if contains_all(path, "{}"):
                file_glob = os.path.basename(path).replace("{}", "*")
                path = os.path.dirname(path)

            path = Path(path)
            if not path.exists():
                diagnostic = f'path "{path}" does not exist'
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

            if path.is_file():
                paths.append((path, None))
            elif path.is_dir():
                paths_sorted = sorted(path.glob(file_glob))
                file_ids = []
                for path in paths_sorted:
                    file_id = None
                    if file_glob != "*":
                        file_id = file_glob_difference(file_glob, path.name)
                    file_ids.append(file_id)
                paths.extend(zip(paths_sorted, file_ids))
            else:
                diagnostic = f'"{path}" must be a file or a directory'
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        if len(paths) == 1:
            self.create_frame(stream, {"paths": [path]})
        else:
            stream.variables["source_paths_generator"] = iter(paths)
            rate, _ = self.get_parameter("rate", default=None)
            rate = float(rate) if rate else None
            self.create_frames(stream, self.frame_generator, rate=rate)

        return aiko.StreamEvent.OKAY, None

    def frame_generator(self, stream, frame_id):
        data_batch_size, _ = self.get_parameter("data_batch_size", default=1)
        data_batch_size = int(data_batch_size)
        paths = []
        try:
            while (data_batch_size > 0):
                data_batch_size -= 1
                path, file_id = next(stream.variables["source_paths_generator"])
                path = Path(path)
                if not path.is_file():
                    diagnostic = f'path "{path}" must be a file'
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
                paths.append(path)
        except StopIteration:
            pass

        if len(paths):
            return aiko.StreamEvent.OKAY, {"paths": paths}
        else:
            return aiko.StreamEvent.STOP, "All paths generated"

    def process_frame(self, stream, paths) -> Tuple[aiko.StreamEvent, dict]:
        images = []
        for path in paths:
            try:
                image = Image.open(path)
                images.append(image)
                self.logger.debug(
                    f"{self.my_id()}: path: {path} {image.size}")
            except Exception as exception:
                diagnostic = f"Error loading image: {exception}"
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
# ToDo: Add logic for using different backends (opencv,...) or
#           different input types (np.ndarray, ...)
#
# ToDo: cv2.resize(image, dimensions, interpolation=cv2.INTER_CUBIC) ?

class ImageResize(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        resolution, _ = self.get_parameter("resolution")
        width, height = resolution.split("x")
        self.logger.debug(f"{self.my_id()}: resolution: {width}x{height}")

        images_resized = []
        for image in images:
            images_resized.append(image.resize((int(width), int(height))))
        return aiko.StreamEvent.OKAY, {"images": images_resized}

# --------------------------------------------------------------------------- #
# ImageWriteFile is a DataTarget that writes images to files
#
# parameter: "data_targets" is the write file path, format variable: "frame_id"
#
# Supports both Streams and direct process_frame() calls
#
# Test
# ~~~~
# export AIKO_LOG_LEVEL=DEBUG; export AIKO_LOG_MQTT=false
#
# aiko_pipeline create pipeline_image_io_0.json -s 1  \
#     -sp ImageWriteFile.path "file://data_out/out_{:02d}.jpeg"

class ImageWriteFile(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        data_targets, found = self.get_parameter("data_targets")
        if not found:
            diagnostic = 'Must provide file "data_targets" parameter'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        tokens = data_targets.split("://")  # URL "file://path" or "path"
        if len(tokens) == 1:
            path = tokens[0]
        else:
            if tokens[0] != "file":
                diagnostic = 'DataSource scheme must be "file://"'
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
            path = tokens[1]

        stream.variables["file_id"] = 0
        stream.variables["target_path"] = path
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        for image in images:
            path = stream.variables["target_path"]
            if contains_all(path, "{}"):
                path = path.format(stream.variables["file_id"])
                stream.variables["file_id"] += 1
            self.logger.debug(f"{self.my_id()}: path: {path}")

            if not isinstance(image, Image.Image):
                if isinstance(image, np.ndarray):  # TODO: Check NUMPY_IMPORTED
                    pass                           # TODO: numpy conversion
                else:
                    diagnostic = "UNKNOWN IMAGE TYPE"  # FIX ME !
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

            try:
                image.save(path)
            except Exception as exception:
                diagnostic = f"Error saving image: {exception}"
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
