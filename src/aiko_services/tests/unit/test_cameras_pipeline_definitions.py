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
import os

import pytest
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")

import aiko_services as aiko
from aiko_services.elements import cameras
from aiko_services.main.utilities import parse

PIPELINES = os.path.join(os.path.dirname(cameras.__file__), "pipelines")
DEFINITIONS = sorted(name for name in os.listdir(PIPELINES)
                     if name.endswith(".json"))

def test_three_definitions_are_committed():
    assert DEFINITIONS == ["depthai_pipeline_0.json",
                           "depthai_pipeline_1.json", "gigev_pipeline_0.json"]

@pytest.mark.parametrize("name", DEFINITIONS)
def test_definition_parses_and_deploys(name):
    path = os.path.join(PIPELINES, name)
    with open(path) as file:
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
