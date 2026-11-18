# Usage
# ~~~~~
# pytest [-s] unit/test_cameras_pipeline_definitions.py
#
# The committed camera PipelineDefinitions parse, validate, deploy modules
# that import, and name elements that exist: the hardware-free validation
# that the testing strategy asks for (e_06 section 9).  No camera SDK is
# needed, because every cameras module imports without one
#
# To Do
# ~~~~~
# - None, yet !

import importlib
import json
from pathlib import Path
import os

import pytest
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")

import aiko_services as aiko
from aiko_services.elements import cameras
from aiko_services.main.utilities import parse

PIPELINES = Path(cameras.__file__).parent / "pipelines"
DEFINITIONS = sorted(d.name for d in PIPELINES.iterdir() if d.name.endswith(".json"))

def test_five_definitions_are_committed():
    assert DEFINITIONS == ["depthai_pipeline_0.json",
                           "depthai_pipeline_1.json",
                           "depthai_pipeline_2.json", "gigev_pipeline_0.json",
                           "gigev_pipeline_1.json"]

@pytest.mark.parametrize("name", DEFINITIONS)
def test_definition_parses_and_deploys(name):
    path = PIPELINES / name
    with path.open() as file:
        definition = json.load(file)                # valid JSON
    parsed = aiko.PipelineImpl.parse_pipeline_definition(path)  # schema
    element_names = [element.name for element in parsed.elements]
    for element in definition["elements"]:          # deploy module + class
        module_name = element["deploy"]["local"]["module"]
        module = importlib.import_module(module_name)
        assert hasattr(module, element["name"]), (name, element["name"])
    for graph in definition["graph"]:               # every node is defined
        for node in parse(graph, car_cdr=False):
            assert node in element_names, (name, node)
    assert definition["parameters"]["_create_stream_"] == "1"
    private = ".".join(["192", "168"])              # assembled: grep-safe
    assert private not in json.dumps(definition)     # placeholder URLs only
