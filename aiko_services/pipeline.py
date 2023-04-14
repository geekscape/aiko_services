#!/usr/bin/env python3
#
# Manage Pipelines consisting of PipelineElements (Actors or Services)
#
# Usage
# ~~~~~
# ./pipeline.py create [--name pipeline_name] pipeline_definition
# ./pipeline.py delete pipeline_name
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
#   - https://www.perfectlyrandom.org/2019/11/29/handling-avro-files-in-python
#     - https://github.com/linkedin/python-avro-json-serializer
#     - https://marcosschroh.github.io/python-schema-registry-client
#
# Resources
# ~~~~~~~~~
# - AVRO 1.9.1 specification
#   - https://avro.apache.org/docs/1.9.1/spec.html
#
# To Do
# ~~~~~
# - Incorporate ~/play/avro: PipelineDefinition and Remote function calls
# - Incorporate pipeline_2022.py
# - Incorporate pipeline_2020.py
#   - aiko_services/examples/pipeline/*, RTSP and WebRTC pipelines
#   - StateMachine (rewrite)
#
# - CLI create(): Should run Pipeline in the background (detached)
#   - See hl_all/infrastructure/websockets/authentication_manager.py
# - CLI delete(): Implement
#
# - Visual representation and editing
#
# - Pipeline / PipelineElement properties --> Stream (leased)
#   - Update Pipeline / PipelineElement properties on-the-fly
#   - Tasks (over GraphQL or MQTT) --> Session (leased)
# - Session limits: frame count (maybe just 1) and lease time
# - Integrate GStreamer plug-ins as PipelineElements
# - Media data transports, e.g in-band MQTT and out-of-band RTSP / WebRTC
#
# To Do: 2020
# ~~~~~~~~~~~
# - Pipeline Graph ...
#   - Information flow, dependencies (strong and weak), categories
#   - https://en.wikipedia.org/wiki/Graph_(abstract_data_type)#Operations
#     - https://en.wikipedia.org/wiki/Adjacency_list
#   - https://en.wikipedia.org/wiki/Graph_traversal
#
# * Replace queue handler with mailboxes
# - In-memory data structure <-- convert --> Persistent storage
# - Why is pipeline_handler() only running at half the specified time ?
# - Why don't timer events occur when pipeline is running flatout ?
# - Add Pipeline.state ...
#   - When pipeline stopped ... event.remove_timer_handler(timer_test)

from abc import abstractmethod
import avro.schema
from avro_validator.schema import Schema
import click
from dataclasses import dataclass
from enum import Enum
import json
import os
# import queue
from typing import Any, Dict, List, Tuple

from aiko_services import *
# from aiko_services.utilities import *

__all__ = [
    "Pipeline", "PipelineElement", "PipelineElementImpl", "PipelineImpl"
]

SCHEMA_PATHNAME = "pipeline_definition.avsc"

ACTOR_TYPE_PIPELINE = "pipeline"
ACTOR_TYPE_ELEMENT = "pipeline_element"
PROTOCOL_PIPELINE =  f"{ServiceProtocol.AIKO}/{ACTOR_TYPE_PIPELINE}:0"
PROTOCOL_ELEMENT =  f"{ServiceProtocol.AIKO}/{ACTOR_TYPE_ELEMENT}:0"

_LOGGER = aiko.logger(__name__)
_VERSION = 0

# --------------------------------------------------------------------------- #
# graph = Graph()
# node_a = Node("a", None)
# node_b = Node("b", None)
# node_a.add("b")
# graph.add(node_a)
# graph.add(node_b)
# graph.nodes()
#
# TODO: Move into "utilities/graph.py"
#
# TODO: Use dataclasses and https://pypi.org/project/json for serialisation
#       Avro support for classes built with Pydantic
#       import json;  string = json.dump(...)

from collections import OrderedDict

class Graph:
    def __init__(self, head_nodes=None):
        self._graph = OrderedDict()
        self._head_nodes = head_nodes if head_nodes else OrderedDict()

    def __iter__(self):
        nodes = OrderedDict()

        def traverse(node):
            for successor in node.successors:
                nodes[self._graph[successor]] = None
            for successor in node.successors:
                traverse(self._graph[successor])

        if self._head_nodes:
            node = self._graph[list(self._head_nodes)[0]]
            nodes[node] = None
            traverse(node)
        return iter(nodes)

    def __repr__(self):
        return str(self.nodes(as_strings=True))

    def add(self, node):
        if node.name in self._graph:
            raise KeyError(f"Graph already contains node: {node}")
        self._graph[node.name] = node

    def nodes(self, indicate_head_nodes=False, as_strings=False):
        nodes = []
        for node in self._graph.values():
            output = node.name if as_strings else node
            if indicate_head_nodes and node.name in self._head_nodes:
                output = f"*{output}"
            output = nodes.append(output)
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
                if type(successor) == list:
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
# TODO: @dataclass: Pipeline:        Graph of PipelineElements, name_mapping ?
# TODO: @dataclass: PipelineElement: service_level_agreement: low_latency

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
    graph: List[str]
    parameters: Dict
    pipeline: [Dict]

@dataclass
class PipelineDefinitionLocal(PipelineDefinition):
    pipeline: List[PipelineElementDefinitionLocal]

@dataclass
class PipelineDefinitionRemote(PipelineDefinition):
    pipeline: List[PipelineElementDefinitionRemote]

# PipelineGraph supports multiple different PipelineElement types.
# However, current PipelineEngines are either "local" or "remote", not both

class PipelineGraph(Graph):

    def __init__(self, head_nodes=None):
        super().__init__(head_nodes)
        self._type_set = set()  # of PipelineType

    def add_element(self, element, element_type_name):
        self._type_set.add(element_type_name)
        self.add(element)

    @property
    def element_count(self):
        return len(self._graph)

    @property
    def type_set(self):
        return self._type_set

# --------------------------------------------------------------------------- #

@dataclass
class FrameContext:
    stream_id: int
    frame_id: int

class PipelineElement(Actor):
    Interface.implementations["PipelineElement"] =  \
        "__main__.PipelineElementImpl"

    @abstractmethod
    def start_stream(self, context, parameters):
        pass

    @abstractmethod
    def stop_stream(self, context):
        pass

    @abstractmethod
    def process_frame(self, context, **kwargs) -> Tuple[bool, Any]:
        """
        Returns a tuple of (success, output) where "success" indicates
        success or failure of processing the frame
        """
        pass

class PipelineElementImpl(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport):
        if protocol == None:
            protocol = PROTOCOL_ELEMENT

        implementations["Actor"].__init__(self,
            implementations, name, protocol, tags, transport)

    #   print(f"### {self.__class__.__name__}.__init__() invoked")

    def start_stream(self, context, parameters):
        pass

    def stop_stream(self, context):
        pass

# --------------------------------------------------------------------------- #
# TODO: Move to own Python source file

class PE_0(PipelineElement):
    @dataclass
    class FrameOutput: a: int; b: str

    def __init__(self,
        implementations, name, protocol, tags, transport):

        protocol = "pe_0:0"  # data_source:0
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport)

    def process_frame(self, context) -> Tuple[bool, FrameOutput]:
        return True, PE_0.FrameOutput(a=stream_id, b=str(frame_id))

class PE_1(PipelineElement):
    @dataclass
    class FrameOutput: a: int; b: str

    def __init__(self,
        implementations, name, protocol, tags, transport):

        protocol = "pe_1:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport)

    def process_frame(self, context) -> Tuple[bool, FrameOutput]:
        return True, PE_1.FrameOutput(a=stream_id, b=str(frame_id))

class PE_2(PipelineElement):
    @dataclass
    class FrameOutput: a: int; b: str

    def __init__(self,
        implementations, name, protocol, tags, transport):

        protocol = "pe_2:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport)

    def process_frame(self, context) -> Tuple[bool, FrameOutput]:
        return True, PE_2.FrameOutput(a=stream_id, b=str(frame_id))

class PE_3(PipelineElement):
    @dataclass
    class FrameOutput: a: int; b: str

    def __init__(self,
        implementations, name, protocol, tags, transport):

        protocol = "pe_3:0"  # data_target:0
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport)

    def process_frame(self, context) -> Tuple[bool, FrameOutput]:
        return True, PE_3.FrameOutput(a=stream_id, b=str(frame_id))

class PE_4(PipelineElement):
    @dataclass
    class FrameOutput: a: int; b: str

    def __init__(self,
        implementations, name, protocol, tags, transport):

        protocol = "pe_4:0"  # data_source:0
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport)

    def process_frame(self, context) -> Tuple[bool, FrameOutput]:
        return True, PE_4.FrameOutput(a=stream_id, b=str(frame_id))

# --------------------------------------------------------------------------- #

class Pipeline(PipelineElement):
    Interface.implementations["Pipeline"] = "__main__.PipelineImpl"

#   @abstractmethod
#   def test(self, value):
#       pass

class PipelineImpl(Pipeline):
    PE_DEFINITION_LOOKUP = {
        PipelineType.LOCAL.value: PipelineElementDefinitionLocal,
        PipelineType.REMOTE.value: PipelineElementDefinitionRemote
    }
    PE_DEFINITION_LOCAL_NAME = PipelineElementDefinitionLocal.__name__
    PE_DEFINITION_REMOTE_NAME = PipelineElementDefinitionRemote.__name__

    def __init__(self,
        implementations, name, protocol, tags, transport,
        pipeline_definition, definition_pathname=""):

        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport)

        self.pipeline_definition = pipeline_definition
        self.pipeline_graph = self._create_pipeline(pipeline_definition)
        print(f"Pipeline graph: {self.pipeline_graph.nodes(True)}")

        self.state = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒{__file__}",
            "definition_pathname": definition_pathname,
            "element_count": self.pipeline_graph.element_count
        }
        self.ec_producer = ECProducer(self, self.state)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self.add_message_handler(self._topic_in_handler, self.topic_in)
        #   binary=True)

# TODO: For local PipelineElements, better module loading, etc
# TODO: Handle remote PipelineElements
# TODO: Handle input and output
# TODO: Extract everything out of pipeline_2022.py
# TODO: Extract everything out of pipeline_2020.py

    def _create_pipeline(self, pipeline_definition):
        pipeline_error = f"Error: Creating Pipeline: {pipeline_definition.name}"

        if len(pipeline_definition.pipeline) == 0:
            message = "PipelineDefinition: Doesn't define any PipelineElements"
            PipelineImpl._system_exit(pipeline_error, message)

        node_heads, node_successors = Graph.traverse(pipeline_definition.graph)
        pipeline_graph = PipelineGraph(node_heads)

        for pipeline_element_definition in pipeline_definition.pipeline:
            # Check PipelineElements are all of the same type
            element_type_name = type(pipeline_element_definition).__name__
            if pipeline_graph.type_set:
                if not element_type_name in pipeline_graph.type_set:
                    message = "PipelineDefinition: PipelineElements must be either local or remote"
                    PipelineImpl._system_exit(pipeline_error, message)

            element_name = pipeline_element_definition.name
            element_instance = None

            if element_type_name == PipelineImpl.PE_DEFINITION_LOCAL_NAME:
                element_module = pipeline_element_definition.module
                element_class = getattr(__import__("__main__"), element_name)
                init_args = actor_args(element_name.lower())
                element_instance = compose_instance(element_class, init_args)

            if element_type_name == PipelineImpl.PE_DEFINITION_REMOTE_NAME:
                element_service_filter = ServiceFilter(
                    pipeline_element_definition.topic_path,
                    pipeline_element_definition.name,
                    pipeline_element_definition.owner,
                    pipeline_element_definition.protocol,
                    pipeline_element_definition.transport,
                    pipeline_element_definition.tags)
                element_instance = None

            if not element_instance:
                message = f"PipelineDefinition: PipelineElement type unknown: {element_type_name}"
                PipelineImpl._system_exit(pipeline_error, message)

            element = Node(
                element_name, element_instance, node_successors[element_name])
            pipeline_graph.add_element(element, element_type_name)

        return pipeline_graph

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    @classmethod
    def parse_pipeline_definition(cls, pipeline_definition_pathname):
        schema_error = f"Error: Parsing PipelineDefinition schema: {SCHEMA_PATHNAME}"
        json_error = f"Error: Parsing PipelineDefinition JSON: {pipeline_definition_pathname}"

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

        if len(pipeline_definition.pipeline.keys()) != 1:
            message = "PipelineDefinition: PipelineElements must be either local or remote"
            PipelineImpl._system_exit(json_error, message)
        pipeline_type = list(pipeline_definition.pipeline.keys())[0]

        if pipeline_type in PipelineImpl.PE_DEFINITION_LOOKUP:
            pipeline_element_definition_type =  \
                PipelineImpl.PE_DEFINITION_LOOKUP[pipeline_type]
        else:
            message = f"Unknown Pipeline type: {pipeline_type}"
            PipelineImpl._system_exit(json_error, message)

        pipeline_elements = []
        for pipeline_element in pipeline_definition.pipeline[pipeline_type]:
            pipeline_element = pipeline_element_definition_type(
                    **pipeline_element)
            pipeline_elements.append(pipeline_element)
        pipeline_definition.pipeline = pipeline_elements

# TODO: Handle parameter name-mapping
# TODO: Handle list of sub-graphs
# TODO: StateMachine support
#         "graph: [
#           "(PE_0 default:)",
#           "(PE_0 streaming: (PE_1 PE_3) (PE_2 PE_3))"
#         ]

        nodes = {}
        for sub_graph in pipeline_definition.graph:
            node_head, node_successors = parse(sub_graph)

        message = f"PipelineDefinition parsed: {pipeline_definition_pathname}"
        print(message)
        _LOGGER.info(message)
        return(pipeline_definition)

    @classmethod
    def _system_exit(cls, summary_message, detail_message):
        diagnostic_message = f"{summary_message}\n{detail_message}"
        _LOGGER.error(diagnostic_message)
        raise SystemExit(diagnostic_message)

    def start_stream(self, context, parameters):
        pass

    def stop_stream(self, context):
        pass

    def process_frame(self, context) -> Tuple[bool, None]:
        swag = {}

#   def run(self, run_event_loop=True):
#       print("### PipelineImpl.run()")
#       super().run(run_event_loop)

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
    init_args["pipeline_definition"] = pipeline_definition
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
