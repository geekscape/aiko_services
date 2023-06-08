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
# - Pipeline CLI option to be the LifeCycleManager and recursively create both
#   local and *remote* Pipeline / PipelineElements
#
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
#   - Improve Service/ActorDiscovery to implement dynamic Service/ActorProxy
#     - Until Service/Actor is discovered, then dynamic Proxy is a default
#     - When Service/Actor is discovered, then dynamic Proxy is updated
#     - When Service/Actor vanishes, then dynamic Proxy returns to default
#     - Provide "absent" / "ready" status
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
from aiko_services.transport import *
from aiko_services.utilities import *

__all__ = [
    "Pipeline", "PipelineElement", "PipelineElementImpl", "PipelineImpl"
]

ACTOR_TYPE_PIPELINE = "pipeline"
ACTOR_TYPE_ELEMENT = "pipeline_element"
PROTOCOL_PIPELINE =  f"{ServiceProtocol.AIKO}/{ACTOR_TYPE_PIPELINE}:0"
PROTOCOL_ELEMENT =  f"{ServiceProtocol.AIKO}/{ACTOR_TYPE_ELEMENT}:0"

_LOGGER = aiko.logger(__name__)
_VERSION = 0

# --------------------------------------------------------------------------- #
# TODO: Incorporate "pipeline_definition.avsc" into this source code ?

SCHEMA_PATHNAME = "pipeline_definition.avsc"

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
    module: str
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
# Pipeline:        name_mapping ?
# PipelineElement: service_level_agreement: low_latency, etc

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

        self.state["source_file"] = f"v{_VERSION}⇒{__file__}"

    def get_logger(self):
        return _LOGGER

    def start_stream(self, context, parameters):
        pass

    def stop_stream(self, context):
        pass

class PipelineElementRemoteAbsent(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport, definition):

        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport, definition)

        self.state["lifecycle"] = "absent"

    def process_frame(self, context, **kwargs) -> Tuple[bool, dict]:
        _LOGGER.error(f"PipelineElement.process_frame(): {self.definition.name}: invoked when remote Pipeline Actor hasn't been discovered")
        return False, {}

class PipelineElementRemoteFound(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport, definition):

        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport, definition)

        self.state["lifecycle"] = "ready"

    def process_frame(self, context, **kwargs) -> Tuple[bool, dict]:
        _LOGGER.info(f"PipelineElementRemoteFound.process_frame(): invoked after remote Pipeline Actor discovered")
        return True, {}

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

        self.remote_pipelines = {}  # Service name --> PipelineElement name
        self.services_cache = None
        self.pipeline_graph = self._create_pipeline(definition)
        self.state["definition_pathname"] = definition_pathname
        self.state["element_count"] = self.pipeline_graph.element_count

    # TODO: Better visualization of the Pipeline / PipelineElements details
    #   print(f"PIPELINE: {self.pipeline_graph.nodes()}")
    #   for node in self.pipeline_graph:
    #       print(f"NODE: {node.name}")

    def _error(self, summary_message, detail_message):
        PipelineImpl._exit(summary_message, detail_message)

    @classmethod
    def _exit(cls, summary_message, detail_message):
        diagnostic_message = f"{summary_message}\n{detail_message}"
        _LOGGER.error(diagnostic_message)
        raise SystemExit(diagnostic_message)

    def _create_pipeline(self, definition):
        pipeline_error = f"Error: Creating Pipeline: {definition.name}"

        if len(definition.elements) == 0:
            message = "PipelineDefinition: Doesn't define any PipelineElements"
            self._error(pipeline_error, message)

        node_heads, node_successors = Graph.traverse(definition.graph)
        pipeline_graph = PipelineGraph(node_heads)

        for pipeline_element_definition in definition.elements:
            element_instance = None
            element_name = pipeline_element_definition.name
            deploy_definition = pipeline_element_definition.deploy
            deploy_type_name = type(deploy_definition).__name__

            if deploy_type_name == PipelineImpl.DEPLOY_TYPE_LOCAL_NAME:
                element_class = self._load_element_class(
                    deploy_definition.module, element_name, pipeline_error)

            # TODO: Make sure element_name is correct for remote case

            if deploy_type_name == PipelineImpl.DEPLOY_TYPE_REMOTE_NAME:
                element_class = PipelineElementRemoteAbsent
                service_name = deploy_definition.service_filter["name"]
                if service_name not in self.remote_pipelines:
                    self.remote_pipelines[service_name] = element_name
                else:
                    message = f"PipelineDefinition: PipelineElement {element_name}: re-uses the remote service_filter name: {service_name}"
                    self._error(pipeline_error, message)
                if not self.services_cache:
                    self.services_cache = services_cache_create_singleton(self)
                service_filter = ServiceFilter.with_topic_path(
                    **deploy_definition.service_filter)
                self.services_cache.add_handler(
                    self._pipeline_element_change_handler, service_filter)

            if not element_class:
                message = f"PipelineDefinition: PipelineElement type unknown: {deploy_type_name}"
                self._error(pipeline_error, message)

            init_args = {
                **actor_args(element_name.lower()),
                "definition": pipeline_element_definition,
            }
            element_instance = compose_instance(element_class, init_args)

            element = Node(
                element_name, element_instance, node_successors[element_name])
            pipeline_graph.add_element(element)

        return pipeline_graph

    def _load_element_class(self,
        module_descriptor, element_name, pipeline_error):

        diagnostic = None
        try:
            module = load_module(module_descriptor)
            element_class = getattr(module, element_name)
        except FileNotFoundError:
            diagnostic = "found"
        except Exception:
            diagnostic = "loaded"
        if diagnostic:
            message = f"PipelineDefinition: PipelineElement {element_name}: Module {module_descriptor} could not be {diagnostic}"
            self._error(pipeline_error, message)
        return element_class

    @classmethod
    def parse_pipeline_definition(cls, pipeline_definition_pathname):
        schema_error =  \
            f"Error: Parsing PipelineDefinition schema: {SCHEMA_PATHNAME}"
        json_error =  \
            f"Error: Parsing PipelineDefinition JSON: {pipeline_definition_pathname}"

        try:
            schema = Schema(SCHEMA_PATHNAME).parse()
        except ValueError as value_error:
            PipelineImpl._exit(schema_error, value_error)

        try:
            pipeline_definition_dict = json.load(
                open(pipeline_definition_pathname, "r"))
            schema.validate(pipeline_definition_dict)
        except ValueError as value_error:
            PipelineImpl._exit(json_error, value_error)

        pipeline_definition = PipelineDefinition(**pipeline_definition_dict)

        if pipeline_definition.version != 0:
            message = f"PipelineDefinition: Version must be 0, but is {pipeline_definition.version}"
            PipelineImpl._exit(json_error, message)

        if pipeline_definition.runtime != "python":
            message = f'PipelineDefinition: Runtime must be "python", but is "{pipeline_definition.runtime}"'
            PipelineImpl._exit(json_error, message)

        element_definitions = []
        for element_fields in pipeline_definition.elements:
            element_definition = PipelineElementDefinition(**element_fields)

            if len(element_definition.deploy.keys()) != 1:
                message = f"PipelineDefinition: PipelineElement {element_definition.name} must be either local or remote"
                PipelineImpl._exit(json_error, message)
            deploy_type = list(element_definition.deploy.keys())[0]

            if deploy_type in PipelineImpl.DEPLOY_TYPE_LOOKUP:
                pipeline_element_deploy_type =  \
                    PipelineImpl.DEPLOY_TYPE_LOOKUP[deploy_type]
            else:
                message = f"Unknown Pipeline deploy type: {deploy_type}"
                PipelineImpl._exit(json_error, message)
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

    def _pipeline_element_change_handler(self, command, service_details):
        if command in ["add", "remove"]:
            print(f"Pipeline change: ({command}: {service_details[0:2]} ...)")
            topic_path = f"{service_details[0]}/in"
            service_name = service_details[1]
            element_name = self.remote_pipelines[service_name]
            node = self.pipeline_graph.get_node(element_name)
            element_definition = node.element.definition

            if command == "add":
                pipeline_error = f"Error: Updating Pipeline: {element_definition.name}"
            # TODO: Don't create another PipelineElement Service !
                element_class = self._load_element_class(
                    element_definition.deploy.module, element_name,
                    pipeline_error)

            if command == "remove":
                element_class = PipelineElementRemoteAbsent

            init_args = {
                **actor_args(element_name.lower()),
                "definition": element_definition,
            }
            element_instance = compose_instance(element_class, init_args)
            if command == "add":
                element_instance = get_actor_mqtt(topic_path, PipelineElementRemoteFound)
                element_instance.definition = element_definition
            node._element = element_instance
            print(f"Pipeline update: --> {element_name} proxy")

    def process_frame(self, context, swag) -> Tuple[bool, None]:
        _LOGGER.debug(f"Invoking Pipeline: context: {context}, swag: {swag}")
        definition_pathname = self.state["definition_pathname"]

        for node in self.pipeline_graph:
            element = node.element
            # TODO: Make sure element_name is correct for remote case
            element_name = element.__class__.__name__
            diagnostic = f'Error: Invoking Pipeline "{definition_pathname}": PipelineElement "{element_name}": process_frame()'

            inputs = {}
            input_names = [input["name"] for input in element.definition.input]
            for input_name in input_names:
                try:
                    inputs[input_name] = swag[input_name]
                except KeyError as key_error:
                    MESSAGE = f'Function parameter "{input_name}" not found'
                    self._error(diagnostic, MESSAGE)

            frame_output = {}
            try:
                if element_name != "ServiceRemoteProxy":
                    okay, frame_output = element.process_frame(
                        context, **inputs)
                    # TODO: Check if PipelineElement failed, i.e "okay" status
                else:
                    element.process_frame(context, **inputs)
                    # TODO: Pipeline stream needs to "pause" waiting for result
            except Exception as exception:
                self._error(diagnostic, traceback.format_exc())

            swag = {**swag, **frame_output}  # TODO: Consider all failure modes

        # TODO: May need to return the result to a parent Pipeline
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
@click.option("--name", "-n", type=str, default=None, required=False,
    help="Pipeline Actor name")
def create(definition_pathname, name):
    if not os.path.exists(SCHEMA_PATHNAME):
        raise SystemExit(
            f"Error: PipelineDefinition schema not found: {SCHEMA_PATHNAME}")

    if not os.path.exists(definition_pathname):
        raise SystemExit(
            f"Error: PipelineDefinition not found: {definition_pathname}")

    pipeline_definition = PipelineImpl.parse_pipeline_definition(
        definition_pathname)
    name = name if name else pipeline_definition.name

    init_args = actor_args(name, PROTOCOL_PIPELINE)
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
