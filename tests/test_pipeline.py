import pytest as pt
import os
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from aiko_services.pipeline import (
    Pipeline
)

HERE = Path(__file__).parent
TEST_DATA = HERE / "data"

ENV_PATTERN = "AIKO_TEST_PNG_PATTERN"
os.environ[ENV_PATTERN] = "*.png"

TMP_DIR = Path(tempfile.mkdtemp())
TEST_HEIGHT = 5
TEST_WIDTH = 10

pipeline_00 = [
    {
      "name": "ImageGlobDirectories",
      "module": "aiko_services.elements.image_io",
      "successors": [
        "ImageResize",
      ],
      "parameters": {
        "directories": [f"{TEST_DATA}"],
        "patterns": [f"${ENV_PATTERN}"]
      }
    },
    {
      "name": "ImageResize",
      "module": "aiko_services.elements.image_io",
      "successors": [
        "ImageWriteFile"
      ],
      "parameters": {
          "new_width": TEST_WIDTH,
          "new_height": TEST_HEIGHT,
          "image": f"$ImageGlobDirectories.image"
      }
    },
    {
      "name": "ImageWriteFile",
      "module": "aiko_services.elements.image_io",
      "parameters": {
          "image_pathname": str(TMP_DIR / "test_{:03d}.png"),
          "image": f"$ImageResize.image"
      }
    }
]

def test_pipeline():
    pipeline = Pipeline(pipeline_00)
    pipeline.run()
    image_paths = list(TMP_DIR.glob("*.png"))
    assert len(image_paths) == 1, f"{TMP_DIR}"
    actual_image = np.asarray(Image.open(image_paths[0]), dtype=np.uint8)
    expected_image = np.zeros((TEST_HEIGHT, TEST_WIDTH), dtype=np.uint8)
    np.testing.assert_array_equal(actual_image, expected_image)
