#!/usr/bin/env python3
#
# Manage Pipelines consisting of PipelineElements (Actors or Services)
#
# Usage
# ~~~~~
# ./pipeline.py create [--name pipeline_name] pipeline_definition
# ./pipeline.py delete pipeline_name
#
# Definition
# ~~~~~~~~~~
# "graph": [
#   "(PE_0 PE_1)",
#   "(PE_0 PE_1 (PE_2 PE_1))",
#   "(PE_0 (PE_1 (PE_3 PE_5)) (PE_2 (PE_4 PE_5)))"
# ],
#
# Important
# ---------
# - Pipeline is-a PipelineElement and a Category (of PipelineElements)
#
# - PipelineDefinition inputs
#   - Program language (Python) data structure is the gold standard
#   - Avro parsed and validated JSON or S-Expressions
#     - Consider using FastAVRO (CPython)
#   - GraphQL
#
# Resources
# ~~~~~~~~~
# - AVRO 1.9.1 specification
#   - https://avro.apache.org/docs/1.9.1/spec.html
#
#   - https://www.perfectlyrandom.org/2019/11/29/handling-avro-files-in-python
#     - https://github.com/linkedin/python-avro-json-serializer
#     - https://marcosschroh.github.io/python-schema-registry-client
#
# To Do
# ~~~~~
# - pipeline_2020.py ...
#   - DataSources and DataTargets support
#   - Replace "message queues" with "mailboxes"
#   - Streams support
#   - StateMachine support
#   - RTSP and WebRTC GStreamer pipeline support for HL Live
#
# - pipeline_2022.py ...
#   - ServiceDefinition: pads (name_mapping)
#   - PipelineElementDefinition(ServiceDefinition): service_level_agreement
#   - PipelineDefinition(PipelineElementDefinition): edges: List[Tuple[PE, PE]]
#
# - For local PipelineElements, better module loading, etc
# - Handle remote PipelineElements
#   - Collect "topic_path", etc into a "service_filter" structure
# - Collect "local" and "remote" into "deployment" configuration structure
# - Validate function inputs and outputs against Pipeline Definition
#
# - Handle list of sub-graphs
# - StateMachine support
#     "graph: [
#       "(PE_0 default:)",
#       "(PE_0 streaming: (PE_1 PE_3) (PE_2 PE_3))"
#     ]

from abc import abstractmethod
import avro.schema
from avro_validator.schema import Schema
import click
from dataclasses import dataclass, asdict
from enum import Enum
import json
import os
import traceback
from typing import Any, Dict, List, Tuple

from aiko_services import *
from aiko_services.utilities import *

__all__ = [
    "Pipeline", "PipelineElement", "PipelineElementImpl", "PipelineImpl"
]

SCHEMA_PATHNAME = "pipeline_definition.avsc"  # Incorporate into source code ?

ACTOR_TYPE_PIPELINE = "pipeline"
ACTOR_TYPE_ELEMENT = "pipeline_element"
PROTOCOL_PIPELINE =  f"{ServiceProtocol.AIKO}/{ACTOR_TYPE_PIPELINE}:0"
PROTOCOL_ELEMENT =  f"{ServiceProtocol.AIKO}/{ACTOR_TYPE_ELEMENT}:0"

_LOGGER = aiko.logger(__name__)
_VERSION = 0

# --------------------------------------------------------------------------- #
# TODO: Move into "utilities/graph.py"
#
# TODO: Use dataclasses and https://pypi.org/project/json for serialisation
#       Avro support for classes built with Pydantic
#       import json;  string = json.dump(...)
#
# graph = Graph()
# node_a = Node("a", None)
# node_b = Node("b", None)
# node_a.add("b")
# graph.add(node_a)
# graph.add(node_b)
# graph.nodes()

from collections import OrderedDict

class Graph:
    def __init__(self, head_nodes=None):
        self._graph = OrderedDict()
        self._head_nodes = head_nodes if head_nodes else OrderedDict()

    def __iter__(self):
        nodes = OrderedDict()

        def traverse(node):
            if node in nodes:
                del nodes[node]
            nodes[node] = None
            for successor in node.successors:
                traverse(self._graph[successor])

        if self._head_nodes:
            node = self._graph[next(iter(self._head_nodes))]
            traverse(node)

        return iter(nodes)

    def __repr__(self):
        return str(self.nodes(as_strings=True))

    def add(self, node):
        if node.name in self._graph:
            raise KeyError(f"Graph already contains node: {node}")
        self._graph[node.name] = node

    def nodes(self, as_strings=False):
        nodes = []
        for node in self._graph.values():
            nodes.append(node.name if as_strings else node)
        return nodes

    def remove(self, node):
        if node.name in self._graph:
            del self._graph[node.name]

    @classmethod
    def traverse(cls, graph_definition):
        node_heads = OrderedDict()
        node_successors = OrderedDict()

        def add_successor(node, successor):
            if not node in node_successors:
                node_successors[node] = OrderedDict()
            if successor:
                node_successors[node][successor] = successor

        def traverse_successors(node, successors):
            for successor in successors:
                if isinstance(successor, list):
                    add_successor(node, successor[0])
                    traverse_successors(successor[0], successor[1:])
                else:
                    add_successor(node, successor)
                    add_successor(successor, None)

        for subgraph_definition in graph_definition:
            node, successors = parse(subgraph_definition)
            node_heads[node] = node
            traverse_successors(node, successors)

        return node_heads, node_successors

class Node:
    def __init__(self, name, element, successors=None):
        self._name = name
        self._element = element
        self._successors = successors if successors else OrderedDict()

    def add(self, successor):
        self._successors.add(successor)

    @property
    def element(self):
        return self._element

    @property
    def name(self):
        return self._name

    def remove(self, successor):
        self._successors.discard(successor)

    @property
    def successors(self):
        return self._successors

    def __repr__(self):
        return f"{self._name}: {list(self._successors)}"

# --------------------------------------------------------------------------- #
# TODO: "pipeline_definition.avsc" incorporate into source code ?

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
# TODO: @dataclass: Pipeline:        Graph of PipelineElements, name_mapping ?
# TODO: @dataclass: PipelineElement: service_level_agreement: low_latency

class DeployType(Enum):
    LOCAL = "local"
    REMOTE = "remote"

@dataclass
class PipelineDefinition:
    version: int
    name: str
    runtime: str
    graph: List[str]
    parameters: Dict
    elements: List

@dataclass
class PipelineElementDefinition:
    name: str
    input: Dict[str, str]
    output: Dict[str, str]
    deploy: Dict

@dataclass
class PipelineElementDeployLocal:
    module: str

@dataclass
class RemoteServiceFilter:
    topic_path: str
    name: str
    owner: str
    protocol: str
    transport: str
    tags: str

@dataclass
class PipelineElementDeployRemote:
    service_filter: RemoteServiceFilter

class PipelineGraph(Graph):

    def __init__(self, head_nodes=None):
        super().__init__(head_nodes)

    def add_element(self, element):
        self.add(element)

    @property
    def element_count(self):
        return len(self._graph)

# --------------------------------------------------------------------------- #

@dataclass
class FrameContext:
    stream_id: int
    frame_id: int

class PipelineElement(Actor):
    Interface.implementations["PipelineElement"] =  \
        "__main__.PipelineElementImpl"

    @abstractmethod
    def process_frame(self, context, **kwargs) -> Tuple[bool, Any]:
        """
        Returns a tuple of (success, output) where "success" indicates
        success or failure of processing the frame
        """
        pass

    @abstractmethod
    def start_stream(self, context, parameters):
        pass

    @abstractmethod
    def stop_stream(self, context):
        pass

class PipelineElementImpl(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport, definition):
        self.definition = definition

        if protocol == None:
            protocol = PROTOCOL_ELEMENT

        implementations["Actor"].__init__(self,
            implementations, name, protocol, tags, transport)

    #   print(f"### {self.__class__.__name__}.__init__() invoked")

        self.state["source_file"] = f"v{_VERSION}⇒{__file__}"

    def get_logger(self):
        return _LOGGER

    def start_stream(self, context, parameters):
        pass

    def stop_stream(self, context):
        pass

# --------------------------------------------------------------------------- #

class Pipeline(PipelineElement):
    Interface.implementations["Pipeline"] = "__main__.PipelineImpl"

class PipelineImpl(Pipeline):
    DEPLOY_TYPE_LOOKUP = {
        DeployType.LOCAL.value: PipelineElementDeployLocal,
        DeployType.REMOTE.value: PipelineElementDeployRemote
    }
    DEPLOY_TYPE_LOCAL_NAME = PipelineElementDeployLocal.__name__
    DEPLOY_TYPE_REMOTE_NAME = PipelineElementDeployRemote.__name__

    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, definition_pathname=""):

        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport, definition)

        self.pipeline_graph = self._create_pipeline(definition)
        self.state["definition_pathname"] = definition_pathname
        self.state["element_count"] = self.pipeline_graph.element_count

    #   print(f"PIPELINE: {self.pipeline_graph.nodes()}")
    #   for node in self.pipeline_graph:
    #       print(f"NODE: {node.name}")

    def _create_pipeline(self, definition):
        pipeline_error = f"Error: Creating Pipeline: {definition.name}"

        if len(definition.elements) == 0:
            message = "PipelineDefinition: Doesn't define any PipelineElements"
            PipelineImpl._system_exit(pipeline_error, message)

        node_heads, node_successors = Graph.traverse(definition.graph)
        pipeline_graph = PipelineGraph(node_heads)

        for pipeline_element_definition in definition.elements:
            element_instance = None
            element_name = pipeline_element_definition.name
            deploy_definition = pipeline_element_definition.deploy
            deploy_type_name = type(deploy_definition).__name__

            if deploy_type_name == PipelineImpl.DEPLOY_TYPE_LOCAL_NAME:
                diagnostic = None
                module_descriptor = deploy_definition.module
                try:
                    module = load_module(module_descriptor)
                    element_class = getattr(module, element_name)
                except FileNotFoundError:
                    diagnostic = "found"
                except Exception:
                    diagnostic = "loaded"
                if diagnostic:
                    message = f"PipelineDefinition: PipelineElement {element_name}: Module {module_descriptor} could not be {diagnostic}"
                    PipelineImpl._system_exit(pipeline_error, message)

                init_args = {
                    **actor_args(element_name.lower()),
                    "definition": pipeline_element_definition,
                }
                element_instance = compose_instance(element_class, init_args)

            if deploy_type_name == PipelineImpl.DEPLOY_TYPE_REMOTE_NAME:
                service_filter = ServiceFilter.with_topic_path(
                    **deploy_definition.service_filter)

            if not element_instance:
                message = f"PipelineDefinition: PipelineElement type unknown: {deploy_type_name}"
                PipelineImpl._system_exit(pipeline_error, message)

            element = Node(
                element_name, element_instance, node_successors[element_name])
            pipeline_graph.add_element(element)

        return pipeline_graph

    @classmethod
    def parse_pipeline_definition(cls, pipeline_definition_pathname):
        schema_error =  \
            f"Error: Parsing PipelineDefinition schema: {SCHEMA_PATHNAME}"
        json_error =  \
            f"Error: Parsing PipelineDefinition JSON: {pipeline_definition_pathname}"

        try:
            schema = Schema(SCHEMA_PATHNAME).parse()
        except ValueError as value_error:
            PipelineImpl._system_exit(schema_error, value_error)

        try:
            pipeline_definition_dict = json.load(
                open(pipeline_definition_pathname, "r"))
            schema.validate(pipeline_definition_dict)
        except ValueError as value_error:
            PipelineImpl._system_exit(json_error, value_error)

        pipeline_definition = PipelineDefinition(**pipeline_definition_dict)

        if pipeline_definition.version != 0:
            message = f"PipelineDefinition: Version must be 0, but is {pipeline_definition.version}"
            PipelineImpl._system_exit(json_error, message)

        if pipeline_definition.runtime != "python":
            message = f'PipelineDefinition: Runtime must be "python", but is "{pipeline_definition.runtime}"'
            PipelineImpl._system_exit(json_error, message)

        element_definitions = []
        for element_fields in pipeline_definition.elements:
            element_definition = PipelineElementDefinition(**element_fields)

            if len(element_definition.deploy.keys()) != 1:
                message = f"PipelineDefinition: PipelineElement {element_definition.name} must be either local or remote"
                PipelineImpl._system_exit(json_error, message)
            deploy_type = list(element_definition.deploy.keys())[0]

            if deploy_type in PipelineImpl.DEPLOY_TYPE_LOOKUP:
                pipeline_element_deploy_type =  \
                    PipelineImpl.DEPLOY_TYPE_LOOKUP[deploy_type]
            else:
                message = f"Unknown Pipeline deploy type: {deploy_type}"
                PipelineImpl._system_exit(json_error, message)
            deploy = pipeline_element_deploy_type(
                **element_definition.deploy[deploy_type])
            element_definition.deploy = deploy

            element_definitions.append(element_definition)

        pipeline_definition.elements = element_definitions

        nodes = {}
        for sub_graph in pipeline_definition.graph:
            node_head, node_successors = parse(sub_graph)

        message = f"PipelineDefinition parsed: {pipeline_definition_pathname}"
        _LOGGER.info(message)
        return(pipeline_definition)

    @classmethod
    def _system_exit(cls, summary_message, detail_message):
        diagnostic_message = f"{summary_message}\n{detail_message}"
        _LOGGER.error(diagnostic_message)
        raise SystemExit(diagnostic_message)

    def process_frame(self, context, swag) -> Tuple[bool, None]:
        _LOGGER.debug(f"Invoking Pipeline: context: {context}, swag: {swag}")
        definition_pathname = self.state["definition_pathname"]

        for node in self.pipeline_graph:
            element = node.element
            element_name = element.__class__.__name__
            diagnostic = f'Error: Invoking Pipeline "{definition_pathname}": PipelineElement "{element_name}": process_frame()'

            inputs = {}
            input_names = [input["name"] for input in element.definition.input]
            for input_name in input_names:
                try:
                    inputs[input_name] = swag[input_name]
                except KeyError as key_error:
                    MESSAGE = f'Function parameter "{input_name}" not found'
                    PipelineImpl._system_exit(diagnostic, MESSAGE)

            try:
                okay, frame_output = element.process_frame(context, **inputs)
            except Exception as exception:
                PipelineImpl._system_exit(diagnostic, traceback.format_exc())

            swag = {**swag, **frame_output}  # TODO: How can this fail ?
        return True, swag

    def start_stream(self, context, parameters):
        pass

    def stop_stream(self, context):
        pass

# --------------------------------------------------------------------------- #

@click.group()
def main():
    """Create and delete Pipelines"""
    pass

@main.command(help="Create Pipeline defined by PipelineDefinition pathname")
@click.argument("definition_pathname", nargs=1, type=str)
@click.option("--name", "-n", type=str, default=ACTOR_TYPE_PIPELINE,
    required=False, help="Pipeline Actor name")
def create(definition_pathname, name):
    if not os.path.exists(SCHEMA_PATHNAME):
        raise SystemExit(
            f"Error: PipelineDefinition schema not found: {SCHEMA_PATHNAME}")

    if not os.path.exists(definition_pathname):
        raise SystemExit(
            f"Error: PipelineDefinition not found: {definition_pathname}")

    pipeline_definition = PipelineImpl.parse_pipeline_definition(
        definition_pathname)

    init_args = actor_args(pipeline_definition.name, PROTOCOL_PIPELINE)
    init_args["definition"] = pipeline_definition
    init_args["definition_pathname"] = definition_pathname
    pipeline = compose_instance(PipelineImpl, init_args)
    pipeline.run()

@main.command(help="Delete Pipeline")
@click.argument("name", nargs=1, type=str, required=True)
def delete(name):
    raise SystemExit("Error: pipeline.py delete: Unimplemented")

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
