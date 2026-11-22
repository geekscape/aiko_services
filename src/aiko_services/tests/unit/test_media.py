# Usage
# ~~~~~
# pytest [-s] unit/test_media.py
# pytest [-s] unit/test_media.py::test_VideoSample

from typing import Tuple

from PIL import Image

import aiko_services as aiko
from aiko_services.tests.unit import do_create_pipeline

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test", "runtime": "python",
  "graph": ["(GenerateImages VideoSample)"],
  "elements": [
    { "name":   "GenerateImages",
      "parameters": {"data_sources": "(file://__TEMP_FILE__)"},
      "input":  [],
      "output": [{"name": "images", "type": "[image]"}],
      "deploy": {
        "local": {"module": "aiko_services.tests.unit.test_media"}
      }
    },
    { "name":   "VideoSample",
      "input":  [{"name": "images", "type": "[image]"}],
      "output": [{"name": "images", "type": "[image]"}],
      "parameters": {"sample_rate": 0},
      "deploy": {
        "local": {"module": "aiko_services.elements.media.video_io"}
      }
    }
  ]
}
"""


class GenerateImages(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        self.image = Image.new("RGB", (320, 240), "black")
        context.set_protocol("generate_images:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        aiko.process.terminate()
        return aiko.StreamEvent.OKAY, {"images": [self.image]}


def test_VideoSample(capsys, tmp_path):
    # NOTE(nic): This is here because I couldn't figure out how to avoid setting the `data_sources` parameter,
    #  nor could I figure out how to set it to a null input.  Throw this down the stairs if a better way exists.
    d = tmp_path / "video.mp4"
    d.touch()
    do_create_pipeline(PIPELINE_DEFINITION.replace("__TEMP_FILE__", str(d)))
    assert "ZeroDivisionError" not in capsys.readouterr().out
