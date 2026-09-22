# Usage
# ~~~~~
# pytest [-s] unit/test_image_dewarp.py
#
# Tests of ImageDewarp (elements/cameras/image_dewarp.py): the pure
# calibration loader and matrix scaling, the Dewarper (an identity
# calibration is a pass-through, remap tables are cached per size and
# alpha, a bad file keeps the current calibration) and an in-process
# Pipeline with SyntheticVideoRead.  Skipped when OpenCV is absent
#
# To Do
# ~~~~~
# - None, yet !

import json

import numpy as np
import pytest
pytest.importorskip("cv2", reason="ImageDewarp needs cv2")

from aiko_services.elements.cameras.image_dewarp import (
    Dewarper, load_calibration, scale_camera_matrix
)
from aiko_services.tests.unit import do_create_pipeline
from aiko_services.tests.unit.image_sink import do_results_initialize

def identity_calibration(width, height, image_size=True):
    calibration = {
        "camera_matrix": [[width, 0, (width - 1) / 2],
                          [0, width, (height - 1) / 2], [0, 0, 1]],
        "dist_coeffs": [0, 0, 0, 0, 0]}
    if image_size:
        calibration["image_size"] = [width, height]
    return calibration

def write(path, calibration):
    path.write_text(json.dumps(calibration))
    return str(path)

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test_image_dewarp", "runtime": "python",
  "graph": ["(SyntheticVideoRead ImageDewarp CaptureLimit ImageSink)"],
  "parameters": {"_create_stream_": "1"},
  "elements": [
    { "name":   "SyntheticVideoRead",
      "parameters": {
        "data_sources": "(synth://video/plain?width=64&height=48)",
        "rate": 20.0
      },
      "input":  [{"name": "images", "type": "[image]"}],
      "output": [{"name": "images", "type": "[image]"}],
      "deploy": {
        "local": {"module": "aiko_services.elements.media.synthetic_io"}}
    },
    { "name":   "ImageDewarp",
      "parameters": {"calibration_path": "CALIBRATION", "alpha": 0.0},
      "input":  [{"name": "images", "type": "[image]"}],
      "output": [{"name": "images", "type": "[image]"}],
      "deploy": {
        "local": {"module": "aiko_services.elements.cameras.image_dewarp"}}
    },
    { "name":   "CaptureLimit", "input": [], "output": [],
      "parameters": {"frame_count": 3},
      "deploy": {
        "local": {"module": "aiko_services.elements.control.elements"}}
    },
    { "name":   "ImageSink",
      "input":  [{"name": "images", "type": "[image]"}], "output": [],
      "deploy": {"local": {"module": "aiko_services.tests.unit.image_sink"}}
    }
  ]
}
"""

# --------------------------------------------------------------------------- #

def test_load_calibration(tmp_path):
    path = write(tmp_path / "good.json", identity_calibration(320, 240))
    camera_matrix, dist_coeffs, image_size = load_calibration(path)
    assert camera_matrix.shape == (3, 3) and camera_matrix[0, 0] == 320
    assert dist_coeffs.shape == (1, 5) and image_size == (320, 240)
    calibration = identity_calibration(320, 240, image_size=False)
    calibration["dist_coeffs"] = [0.1, -0.2, 0, 0, 0, 0, 0, 0]  # 8: rational
    assert load_calibration(write(tmp_path / "eight.json",
                                  calibration))[2] is None
    for name, content in (
            ("missing.json", None),
            ("bad.json", "{not json"),
            ("string.json", json.dumps("x")),
            ("no_coeffs.json", json.dumps({"camera_matrix": [[1]]})),
            ("shape.json", json.dumps({"camera_matrix": [[1, 2], [3, 4]],
                                       "dist_coeffs": [0, 0, 0, 0]})),
            ("count.json", json.dumps({"camera_matrix": [[1, 0, 0]] * 3,
                                       "dist_coeffs": [0, 0, 0]})),
            ("size.json", json.dumps({"camera_matrix": [[1, 0, 0]] * 3,
                                      "dist_coeffs": [0, 0, 0, 0],
                                      "image_size": [0, 10]}))):
        path = tmp_path / name
        if content is not None:
            path.write_text(content)
        with pytest.raises(ValueError, match="calibration"):
            load_calibration(path)

def test_scale_camera_matrix():
    matrix = np.array([[1000.0, 0, 500], [0, 900.0, 300], [0, 0, 1]])
    scaled = scale_camera_matrix(matrix, (1000, 600), (500, 300))
    assert scaled.tolist() == [[500, 0, 250], [0, 450, 150], [0, 0, 1]]
    assert matrix[0, 0] == 1000                        # input untouched

def test_dewarper_identity_and_cache(tmp_path):
    dewarper = Dewarper()
    assert not dewarper.loaded
    dewarper.load(write(tmp_path / "identity.json",
                        identity_calibration(320, 240)))
    assert dewarper.loaded and dewarper.image_size == (320, 240)
    rng = np.random.default_rng(1)
    image = rng.integers(0, 256, (240, 320, 3), dtype=np.uint8)
    out = dewarper.apply(image)
    assert out.shape == image.shape and out.dtype == np.uint8
    assert np.abs(out.astype(int) - image.astype(int)).max() <= 1
    assert dewarper.map_count == 1
    dewarper.apply(image)
    assert dewarper.map_count == 1                     # cached
    small = dewarper.apply(image[:120, :160])          # scaled matrix
    assert small.shape == (120, 160, 3) and dewarper.map_count == 2
    dewarper.set_alpha(1.0)
    assert dewarper.map_count == 0                     # rebuilt on demand
    dewarper.apply(image)
    assert dewarper.map_count == 1
    with pytest.raises(ValueError, match="alpha"):
        dewarper.set_alpha(2)

def test_dewarper_bad_reload_keeps_calibration(tmp_path):
    dewarper = Dewarper()
    good = write(tmp_path / "good.json", identity_calibration(64, 48))
    dewarper.load(good)
    with pytest.raises(ValueError):
        dewarper.load(tmp_path / "missing.json")
    assert dewarper.path == good and dewarper.loaded
    assert dewarper.apply(np.zeros((48, 64, 3), np.uint8)).shape == (48, 64, 3)

def test_pipeline_dewarps_frames(tmp_path):
    calibration = write(tmp_path / "identity.json",
                        identity_calibration(64, 48))
    results = do_results_initialize()
    do_create_pipeline(PIPELINE_DEFINITION.replace("CALIBRATION", calibration),
                       frame_data=None)
    assert not results["watchdog"], "Stream did not stop: watchdog fired"
    assert results["stopped"], "ImageSink.stop_stream() was not invoked"
    assert results["frame_ids"] == [0, 1, 2]
    assert results["shapes"] == [(48, 64, 3)] * 3
