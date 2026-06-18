#!/usr/bin/env python3
"""LocateAnything object detector for aiko_services pipelines.

Adapted from ``examples/yolo/yolo.py`` (``YoloDetector``).

Setup (from the aiko_services repo root)::

    pip install -e ".[locate_anything]"

``locateanything_worker`` is not on PyPI. Add Embodied to ``PYTHONPATH``::

    export PYTHONPATH=$PYTHONPATH:path/to/eagle/Embodied

Run the example pipeline (from this directory)::

    aiko_pipeline create locate_anything_pipeline_0.json -s 1

    AIKO_LOG_LEVEL=DEBUG aiko_pipeline create locate_anything_pipeline_0.json -s 1

    aiko_pipeline create locate_anything_pipeline_0.json -s 1 \\
      -sp VideoReadWebcam.path /dev/video2  # Linux
"""

import re
import sys
from pathlib import Path
from typing import Tuple

import aiko_services as aiko
from aiko_services.elements.media import convert_image_to_pil
from aiko_services.main.utilities import parse

__all__ = [ "LocateAnythingDetector" ]

_STUBS_DIR = Path(__file__).resolve().parent / "stubs"
if _STUBS_DIR.is_dir():
    stubs_path = str(_STUBS_DIR)
    if stubs_path not in sys.path:
        sys.path.insert(0, stubs_path)
    import decord  # noqa: F401  # satisfy transformers import check

_LOCATE_ANYTHING_MODEL_PATHNAME = "nvidia/LocateAnything-3B"

# --------------------------------------------------------------------------- #
# Default categories for robotdog detection
# tennis_ball, kong_ball, rubber_ball, dog_biscuit
# blue_cup, red_cup, orange_cone
# stop_sign, sign
# octopus, red_ball, green_ball, building
# pine_tree, oak_tree, xgomini2

_ROBOTDOG_CATEGORIES = [
    "tennis_ball", "kong_ball", "rubber_ball", "dog_biscuit",
    "blue_cup", "red_cup", "orange_cone",
    "stop_sign", "sign",
    "octopus", "red_ball", "green_ball", "building",
    "pine_tree", "oak_tree", "xgomini2",
]

import torch
from locateanything_worker import LocateAnythingWorker


class LocateAnythingDetector(aiko.PipelineElement):
    
    _REF_BOX_PATTERN = re.compile(
        r"<ref>([^<]+)</ref>((?:<box>.*?</box>)+)")
    _BOX_PATTERN = re.compile(
        r"<box>\s*<\s*(\d+)\s*>\s*"
        r"<\s*(\d+)\s*>\s*"
        r"<\s*(\d+)\s*>\s*"
        r"<\s*(\d+)\s*>\s*</box>")

    def __init__(self, context):
        context.set_protocol("object_detector:0")
        context.call_init(self, "PipelineElement", context)

    def start_stream(self, stream, stream_id):
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.device = "cuda" if torch.cuda.is_available() else self.device

        locate_anything_model_pathname, _ = self.get_parameter(
            "model", default=_LOCATE_ANYTHING_MODEL_PATHNAME)

        self.worker = LocateAnythingWorker(
            locate_anything_model_pathname, device=self.device)

        names, _ = self.get_parameter("names", default="()")
        names = parse(names, car_cdr=False)
        if isinstance(names, list) and len(names) and names[0] != "":
            self.categories = names
        else:
            self.categories = list(_ROBOTDOG_CATEGORIES)
            self.logger.warning(
                'Parameter "names" must be a list; using default categories')
        return aiko.StreamEvent.OKAY, {}

    def _parse_detections(self, answer: str, image_width: int, image_height: int):
        """Parse <ref>category</ref><box>... detection output into overlay entries."""
        detections = []
        for category, boxes_str in self._REF_BOX_PATTERN.findall(answer):
            for x1, y1, x2, y2 in self._BOX_PATTERN.findall(boxes_str):
                x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
                x_min = int(min(x1, x2) / 1000 * image_width)
                y_min = int(min(y1, y2) / 1000 * image_height)
                x_max = int(max(x1, x2) / 1000 * image_width)
                y_max = int(max(y1, y2) / 1000 * image_height)
                detections.append((
                    category,
                    x_min,
                    y_min,
                    max(0, x_max - x_min),
                    max(0, y_max - y_min),
                ))
        return detections

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        overlay = {"objects": [], "rectangles": []}
        objects = overlay["objects"]
        rectangles = overlay["rectangles"]

        image_id = 0
        for image in images:
            pil_image = convert_image_to_pil(image)
            image_width, image_height = pil_image.size

            result = self.worker.detect(
                pil_image, self.categories, verbose=False)
            box_id = 0
            for name, x, y, w, h in self._parse_detections(
                    result["answer"], image_width, image_height):
                confidence = 1.0
                objects.append({"name": name, "confidence": confidence})
                rectangles.append({"x": x, "y": y, "w": w, "h": h})

                #   print(f"{name}: c: {confidence:0.2f}: "  \
                #         f"i{image_id}: d{detection_id}: b{box_id}")
                box_id += 1
            image_id += 1

        return aiko.StreamEvent.OKAY, {"overlay": overlay}

# --------------------------------------------------------------------------- #
