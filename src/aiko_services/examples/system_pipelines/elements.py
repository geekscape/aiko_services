#!/usr/bin/env python3
#
# Demonstrates a combined main Pipeline (overall data flow reading
# from a web camera)), using a remote Pipeline containing a YOLOE
# detection PipelineElement.
#
# Usage
# ~~~~~
# aiko_process run 0_process_manager.json
# aiko_dashboard
#
# Notes
# ~~~~~
# image = (np.random.rand(480, 640, 3) * 255).astype(np.uint8)
# base64_data = numpy_array_to_base64(image)
# image_copy = base64_to_numpy_array(base64_data)

import base64
import io
import numpy as np
from typing import Optional, Tuple
import zlib

import aiko_services as aiko

# --------------------------------------------------------------------------- #

def base64_to_numpy_array(b64: str, *, dtype: Optional[np.dtype] = None,
    shape: Optional[tuple[int, ...]] = None, validate: bool = True,
    ) -> np.ndarray:

    if not isinstance(b64, str):
        raise TypeError(f"b64 must be a str, got {type(b64)!r}")

    try:
        compressed = base64.b64decode(b64.encode("utf-8"), validate=validate)
    except TypeError:
        compressed = base64.b64decode(b64.encode("utf-8"))

    raw = zlib.decompress(compressed)

    buf = io.BytesIO(raw)
    arr = np.load(buf, allow_pickle=False)

    if dtype is not None and arr.dtype != np.dtype(dtype):
        raise ValueError(
            f"dtype mismatch: expected {np.dtype(dtype)}, got {arr.dtype}")

    if shape is not None and tuple(arr.shape) != tuple(shape):
        raise ValueError(
            f"shape mismatch: expected {tuple(shape)}, got {tuple(arr.shape)}")
    return arr

def numpy_array_to_base64(arr: np.ndarray, *, compress_level: int = 6,) -> str:
    if not isinstance(arr, np.ndarray):
        raise TypeError(f"arr must be a numpy.ndarray, got {type(arr)!r}")

    if not (0 <= compress_level <= 9):
        raise ValueError("compress_level must be in [0..9]")

    # Ensure predictable serialization performance
    if not arr.flags["C_CONTIGUOUS"]:
        arr = np.ascontiguousarray(arr)

    buf = io.BytesIO()
    np.save(buf, arr, allow_pickle=False)
    raw = buf.getvalue()

    compressed = zlib.compress(raw, level=compress_level)
    b64 = base64.b64encode(compressed).decode("utf-8")
    return b64

# --------------------------------------------------------------------------- #

class Base64ToImages(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("base64_to_images:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, base64_data)  \
        -> Tuple[aiko.StreamEvent, dict]:

        self.logger.debug(f"{self.my_id()}: base64 --> images")
        image = base64_to_numpy_array(base64_data)
        return aiko.StreamEvent.OKAY, {"images": [image]}

class ImagesToBase64(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("images_to_base64:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.debug(f"{self.my_id()}: images --> base64")
        base64_data = numpy_array_to_base64(images[0])
        return aiko.StreamEvent.OKAY, {"base64_data": base64_data}

# --------------------------------------------------------------------------- #
