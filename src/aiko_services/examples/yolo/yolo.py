#!/usr/bin/env python3
#
# pip install tensorrt
# RT_PATH=$HOME/venvs/venv_3.12.7/lib/python3.12/site-packages/tensorrt_libs
# export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$RT_PATH
#
# aiko_pipeline create yolo_pipeline_0.json -s 1  # aiko_dashboard --> logging
#
# AIKO_LOG_LEVEL=DEBUG aiko_pipeline create yolo_pipeline_0.json -s 1
#
# aiko_pipeline create yolo_pipeline_0.json -s 1  \
#   -sp VideoReadWebcam.path /dev/video2
#
# To Do
# ~~~~~
# - Implement multiple simultaneous YOLO model checkpoints, referenced by name
#
# - Provide more flexible search for "_YOLO_MODEL_PATHNAME" ?
#
# - Detector:    Inference rate (ignore frames ?)
# - Performance: Using GPU efficiently ?
# - YoloDetector
#   - Performance ... use GPU efficiently ?
#   - Ultralytics issues with OpenCV.imshow() --> Python AV package ?!?

import os
from typing import Tuple

import aiko_services as aiko

__all__ = [ "YoloDetector" ]

_YOLO_MODEL_PATHNAME = "yolov8n_robotdog.pt"

# --------------------------------------------------------------------------- #
# New classes trained for "yolov8n_robotdog.pt" ...
# 20: tennis_ball, 21: kong_ball, 22: rubber_ball, 23: dog_biscuit
# 26: blue_cup,    27: red_cup,   28: orange_cone
# 30: stop_sign,   31: sign
# 33: octopus,     34: red_ball,  35: green_ball,  61: building
# 77: pine_tree,   78: oak_tree,  79: xgomini2

_ROBOTDOG_CLASSES = [
    20, 21, 22, 23, 26, 27, 28, 30, 31, 33, 34, 35, 61, 77, 78, 79 ]

import torch
from ultralytics import YOLO

class YoloDetector(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("object_detector:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.device = "cuda" if torch.cuda.is_available() else self.device
        self.yolo_model = YOLO(_YOLO_MODEL_PATHNAME)
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        overlay = {"objects": [], "rectangles": []}
        objects = overlay["objects"]
        rectangles = overlay["rectangles"]

        image_id = 0
        for image in images:
            detections = self.yolo_model(
                image, device=self.device, verbose=False)
            detection_id = 0
            for detection in detections:
                box_id = 0
                for box in detection.boxes:
                    class_id = int(box.cls[0].item())
                    if class_id in _ROBOTDOG_CLASSES:
                        name = detection.names[class_id]
                        confidence = round(box.conf[0].item(), 2)
                        x = int(box.xyxy[0][0].item())
                        y = int(box.xyxy[0][1].item())
                        w = int(box.xywh[0][2].item())
                        h = int(box.xywh[0][3].item())

                        objects.append({"name": name, "confidence": confidence})
                        rectangles.append({"x": x, "y": y, "w": w, "h": h})

                    #   print(f"{name}: c: {confidence:0.2f}: "  \
                    #         f"i{image_id}: d{detection_id}: b{box_id}")
                        box_id += 1
                detection_id += 1
            image_id += 1

        return aiko.StreamEvent.OKAY, {"overlay": overlay}

# --------------------------------------------------------------------------- #
