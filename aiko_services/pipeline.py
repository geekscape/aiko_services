#!/usr/bin/env python3
#
# Manage Pipelines consisting of PipelineElements (Actors or Services)
#
# Usage
# ~~~~~
# ./pipeline.py create pipeline_definition [--name pipeline_name]
# ./pipeline.py delete pipeline_name
#
# Important
# ---------
# - Pipeline is-a Category
# - Pipeline is-a LifeCycleManager, PipelineElement is-a LifeCycleClient
#
# - Pipeline Definition inputs
#   - Python data structure (gold standard)
#   - HL Web GraphQL
#   - Avro (validated) / YAML / JSON ?
#   *** FastAVRO (CPython)
#   *** https://www.perfectlyrandom.org/2019/11/29/handling-avro-files-in-python
#   - https://github.com/linkedin/python-avro-json-serializer
#   - https://marcosschroh.github.io/python-schema-registry-client
#
# Resources
# ~~~~~~~~~
# - AVRO 1.9.1 specification
#   - https://avro.apache.org/docs/1.9.1/spec.html
#
# To Do
# ~~~~~
# - CLI create(): Should run Pipeline in the background (detached)
#   - See hl_all/infrastructure/websockets/authentication_manager.py
# - CLI delete(): Implement
#
# - PipelineDefinition design and implementation
# - LifeCycleManager / Client implementations ...
#   - Pipeline implementation: PipelineElements are all within same process
#   - Pipeline implementation: PipelineElements are all distributed
# - Visual representation and editing
#
# - Incorporate ~/play/avro: PipelineDefinition and Remote function calls
# - Incorporate pipeline_2022.py
# - Incorporate pipeline_2020.py
#   - aiko_services/examples/pipeline/*, RTSP and WebRTC pipelines
#   - StateMachine (rewrite)
# - Pipeline / PipelineElement properties --> Stream (leased)
#   - Update Pipeline / PipelineElement properties on-the-fly
#   - Tasks (over GraphQL or MQTT) --> Session (leased)
# - Session limits: frame count (maybe just 1) and lease time
# - Integrate GStreamer plug-ins as PipelineElements
# - Media data transports, e.g in-band MQTT and out-of-band RTSP / WebRTC

import avro.schema
from avro_validator.schema import Schema
import click
from dataclasses import dataclass
from enum import Enum
import json
import os
# import queue
from typing import Dict, List

from aiko_services import *
# from aiko_services.utilities import *

__all__ = [
]

PIPELINE_DEFINITION_PATHNAME = "pipeline_definition.avsc"

ACTOR_TYPE = "pipeline"
PROTOCOL = f"{ServiceProtocol.AIKO}/{ACTOR_TYPE}:0"

_LOGGER = aiko.logger(__name__)
_VERSION = 0

# --------------------------------------------------------------------------- #
# TODO: Use dataclasses and https://pypi.org/project/json for serialisation
#       Avro support for classes built with Pydantic
#       import json;  string = json.dump(...)
# TODO: Graph.add(): [nodes] ?
# TODO: Node.add(): [dependencies] ?
# TODO: Should dependencies be more than just "element.output" (string) ?
# TODO: Declare stream head nodes ... which accept frames ?

class Graph:
    def __init__(self):
        self._graph = {}

    def __repr__(self):
        return str(self.nodes(as_strings=True))

    def add(self, node):
        if node.name in self._graph:
            raise KeyError(f"Graph already contains node: {node}")
        self._graph[node.name] = node

    def nodes(self, as_strings=False):
        nodes = []
        for node in self._graph.values():
            nodes.append(str(node) if as_strings else node)
        return nodes

    def remove(self, node):
        if node.name in self._graph:
            del self._graph[node.name]

    def resolve(self):
        pass

class Node:
    def __init__(self, name, element, dependencies=None):
        self._name = name
        self._element = element
        self._dependencies = dependencies if dependencies else {}

    @property
    def dependencies(self):
        dependencies = []
        for dependency in self._dependencies:
            dependencies.append(dependency)
        return dependencies

    @property
    def element(self):
        return self._element

    @property
    def name(self):
        return self._name

    def __repr__(self):
        return f"{self._name}: {self._dependencies}"

    def add(self, dependency):
        if dependency in self._dependencies:
            raise KeyError(f"Node already contains dependency: {dependency}")
        self._dependencies[dependency] = dependency

    def remove(self, dependency):
        if dependency in self._dependencies:
            del self._dependencies[dependency]

g = Graph()
na = Node("a", None)
nb = Node("b", None)
na.add("da")
nb.add("db")
g.add(na)
g.add(nb)

# --------------------------------------------------------------------------- #
# TODO: Incorporate "pipeline_definition.avsc"

SCHEMA = avro.schema.parse(json.dumps({
    "namespace"    : "example.avro",
    "name"         : "User",
    "type"         : "record",
    "fields"       : [
         {"name": "name"            , "type": "string"},
         {"name": "favorite_number" , "type": ["int", "null"]},
         {"name": "favorite_color"  , "type": ["string", "null"]}
    ]
}))

# --------------------------------------------------------------------------- #

class PipelineType(Enum):
    LOCAL = "local"
    REMOTE = "remote"

@dataclass
class PipelineElementDefinitionLocal:
    name: str
    module: str
    input: Dict[str, str]
    output: Dict[str, str]

@dataclass
class PipelineElementDefinitionRemote:
    topic_path: str
    name: str
    owner: str
    protocol: str
    transport: str
    tags: str
    input: Dict[str, str]
    output: Dict[str, str]

@dataclass
class PipelineDefinition:
    version: int
    name: str
    runtime: str
    parameters: Dict
    pipeline: [Dict]
    pipeline_graph: List[str]

@dataclass
class PipelineDefinitionLocal(PipelineDefinition):
    pipeline: List[PipelineElementDefinitionLocal]

@dataclass
class PipelineDefinitionRemote(PipelineDefinition):
    pipeline: List[PipelineElementDefinitionRemote]

# TODO: Actor:      PipelineElement
# TODO: @dataclass: ServiceDefinition: type, name, next_elements, parameters
# TODO: @dataclass: PipelineElement:   service_level_agreement: low_latency
# TODO: @dataclass: Pipeline:          elements[], edges[] ?

# --------------------------------------------------------------------------- #

class Pipeline(Actor):
    Interface.implementations["Pipeline"] = "__main__.PipelineImpl"

#   @abstractmethod
#   def test(self, value):
#       pass

class PipelineImpl(Pipeline):
    definition_lookup = {
        PipelineType.LOCAL.value: PipelineElementDefinitionLocal,
        PipelineType.REMOTE.value: PipelineElementDefinitionRemote
    }

    def __init__(self,
        implementations, name, protocol, tags, transport,
        pipeline_definition_pathname):

        implementations["Actor"].__init__(self,
            implementations, name, protocol, tags, transport)

        self.pipeline_definition = self._parse_pipeline_definition(
            pipeline_definition_pathname)

        self.pipeline = self._create_pipeline(self.pipeline_definition)

        self.state = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒{__file__}",
            "definition_pathname": pipeline_definition_pathname
        }
        self.ec_producer = ECProducer(self, self.state)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self.add_message_handler(self._topic_in_handler, self.topic_in)
        #   binary=True)

    def _create_pipeline(self, pipeline_definition):
        breakpoint()
        return None

    def _system_exit(self, summary_message, detail_message):
        diagnostic_message = f"{summary_message}\n{detail_message}"
        _LOGGER.error(diagnostic_message)
        raise SystemExit(diagnostic_message)

    def _parse_pipeline_definition(self, pipeline_definition_pathname):
        schema_error = f"Error: Parsing PipelineDefinition schema: {PIPELINE_DEFINITION_PATHNAME}"
        json_error = f"Error: Parsing PipelineDefinition JSON: {pipeline_definition_pathname}"

        try:
            schema = Schema(PIPELINE_DEFINITION_PATHNAME).parse()
        except ValueError as value_error:
            self._system_exit(schema_error, value_error)

        try:
            pipeline_definition_dict = json.load(
                open(pipeline_definition_pathname, "r"))
            schema.validate(pipeline_definition_dict)
        except ValueError as value_error:
            self._system_exit(json_error, value_error)

        pipeline_definition = PipelineDefinition(**pipeline_definition_dict)

        if pipeline_definition.version != 0:
            message = f"PipelineDefinition version must be 0, but is {pipeline_definition.version}"
            self._system_exit(json_error, message)

        if pipeline_definition.runtime != "python":
            message = f'PipelineDefinition runtime must be "python", but is "{pipeline_definition.runtime}"'
            self._system_exit(json_error, message)

        if len(pipeline_definition.pipeline.keys()) != 1:
            message = "PipelineDefinition PipelineElements can only be local or remote"
            self._system_exit(json_error, message)
        pipeline_type = list(pipeline_definition.pipeline.keys())[0]

        if pipeline_type in PipelineImpl.definition_lookup:
            pipeline_element_definition_type =  \
                PipelineImpl.definition_lookup[pipeline_type]
        else:
            message = f"Unknown Pipeline type: {pipeline_type}"
            self._system_exit(json_error, message)

        pipeline_elements = []
        for pipeline_element in pipeline_definition.pipeline[pipeline_type]:
            pipeline_element = pipeline_element_definition_type(
                    **pipeline_element)
            pipeline_elements.append(pipeline_element)
        pipeline_definition.pipeline = pipeline_elements

        message = f"PipelineDefinition parsed: {pipeline_definition_pathname}"
        print(message)
        _LOGGER.info(message)
        return(pipeline_definition)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def _topic_in_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
# TODO: Apply proxy automatically for Actor and not manually here
        self._post_message(actor.Topic.IN, command, parameters)

# Review ~/play/avro/pipeline_test.py: class PipelineA: implementation
#        ~/play/avro/zz_new_suggestion.py

# import pipeline_definition_test
# pipeline_test = PipelineA(pipeline_definition_test.graph)

# frame_queue = queue.Queue()
# frame = {"input1": {"param1": 1, "param2": 2}}
# frame_queue.put(frame)

# while True:
#   frame = frame_queue.get()
#   result = pipeline_test.run(frame)
#   handle_result(result)  # TODO: Implement

# --------------------------------------------------------------------------- #

@click.group()
def main():
    """Create and delete Pipelines"""
    pass

@main.command(
    help="Create Pipeline where a PIPELINE_DEFINITION is given by a pathname")
@click.argument("pipeline_definition", nargs=1, type=str, required=True)
@click.option("--name", "-n", type=str, default=ACTOR_TYPE, required=False,
    help="Pipeline Actor name")
def create(pipeline_definition, name):
    if not os.path.exists(PIPELINE_DEFINITION_PATHNAME):
        raise SystemExit(
            f"Error: PipelineDefinition schema not found: {PIPELINE_DEFINITION_PATHNAME}")

    if not os.path.exists(pipeline_definition):
        raise SystemExit(
            f"Error: PipelineDefinition not found: {pipeline_definition}")

    init_args = actor_args(name, PROTOCOL)
    init_args["pipeline_definition_pathname"] = pipeline_definition
    pipeline = compose_instance(PipelineImpl, init_args)
    pipeline.run()

@main.command(help="Delete Pipeline")
@click.argument("name", nargs=1, type=str, required=True)
def delete(name):
    raise SystemExit("Error: pipeline.py delete: Unimplemented")

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
