#!/usr/bin/env python3
#
# Manage Pipelines consisting of PipelineElements (Actors or Services)
#
# Usage
# ~~~~~
# DEFINITION=pipeline_definition.json
# aiko_pipeline create [--name $PIPELINE_NAME] $DEFINITION
# aiko_pipeline delete $PIPELINE_NAME
#
# AIKO_LOG_LEVEL=DEBUG AIKO_LOG_MQTT=false aiko_pipeline create $DEFINITION
#
# NAMESPACE=AIKO
# HOST=localhost
# PID=`ps ax | grep aiko_pipeline | grep -v grep | tr -s " " | cut -d" " -f1-2`
# SID=1
# TOPIC=$NAMESPACE/$HOST/$PID/$SID/in
#
# mosquitto_pub -h $HOST -t $TOPIC -m "(create_stream 1)"
# mosquitto_pub -h $HOST -t $TOPIC -m "(process_frame (stream_id: 1) (a: 0))"
# mosquitto_pub -h $HOST -t $TOPIC -m "(destroy_stream 1)"
#
# Definition
# ~~~~~~~~~~
# "graph": [
#   "(PE_0 PE_1)",
#   "(PE_0 PE_1 (PE_2 PE_1))",
#   "(PE_0 (PE_1 (PE_3 PE_5)) (PE_2 (PE_4 PE_5)))"
# ]
#
# PipelineElement function argument name mapping example ...
# - PE_1 outputs "a" and PE_2 outputs "b"
# - Whilst PE_3 expects inputs "x" and "y"
#
# "graph": [
#   "(PE_0 (PE_1 PE_3 (a: x)) (PE_2 PE_3 (b: y)))"
# ]
#
# Important
# ---------
# - Pipeline is-a PipelineElement and a Category (of PipelineElements)
#
# - Pipeline Definition Avro schema is hard-coded into this source file ...
#   - To ensure that the Avro schema matches the source code implementation
#   - Avoid having to refer to a critical file somewhere in the filesystem
#
# - PipelineDefinition inputs
#   - Program language (Python) data structure is the gold standard
#   - Avro parsed and validated JSON or S-Expressions
#     - Consider using FastAvro (CPython)
#   - GraphQL
#
# Resources
# ~~~~~~~~~
# - Avro 1.9.1 specification
#   - https://avro.apache.org/docs/1.9.1/spec.html
#
#   - https://www.perfectlyrandom.org/2019/11/29/handling-avro-files-in-python
#     - https://github.com/linkedin/python-avro-json-serializer
#     - https://marcosschroh.github.io/python-schema-registry-client
#
# To Do
# ~~~~~
# * CLI: pipeline.py show <service_filter>
# * CLI: pipeline.py get <service_filter> <parameter_name>  # or wildcard "*"
# * CLI: pipeline.py set <service_filter> <parameter_name> <parameter_value>
#
# * Should "stream_start()" and "stream_stop()" should return success/failure ?
#   - Yes and the "swag" should be just like "process_frame()"
#
# * Handle list of sub-graphs for multiple sources of different data types
#   - With StateMachine support for dynamic Graph routing / traversal
#       "graph: [
#         "(PE_0 default:)",
#         "(PE_0 streaming: (PE_1 PE_3) (PE_2 PE_3))"
#       ]
#
# - Collect "local" and "remote" into "deployment" configuration structure
#
# - Validate function inputs and outputs against Pipeline Definition
#
# - Pipeline CLI option to be the LifeCycleManager and recursively create both
#   local and *remote* Pipeline / PipelineElements
#
# - pipeline_2022.py ...
#   - ServiceDefinition: fan-out, fan-in and name_mapping
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

_GRACE_TIME = 60
_LOGGER = aiko.logger(__name__)
_VERSION = 0

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
# Pipeline:        fan-out, fan-in and name_mapping ?
# PipelineElement: service_level_agreement: low_latency, etc

@dataclass
class FrameContext:
    stream_id: int
    frame_id: int

class PipelineElement(Actor):
    Interface.implementations["PipelineElement"] =  \
        "aiko_services.pipeline.PipelineElementImpl"

    @abstractmethod
    def process_frame(self, context, **kwargs) -> Tuple[bool, Any]:
        """
        Returns a tuple of (success, output) where "success" indicates
        success or failure of processing the frame
        """
        pass

    @abstractmethod
    def start_stream(self, context, stream_id):
        pass

    @abstractmethod
    def stop_stream(self, context, stream_id):
        pass

class PipelineElementImpl(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        self.definition = definition
        self.pipeline = pipeline
        if protocol == None:
            protocol = PROTOCOL_ELEMENT

        implementations["Actor"].__init__(self,
            implementations, name, protocol, tags, transport)

        self.state["source_file"] = f"v{_VERSION}⇒{__file__}"

    def get_logger(self):
        return _LOGGER

    def _id(self, context):
        return f"{self.name}<{context['stream_id']}:{context['frame_id']}>"

    def start_stream(self, context, stream_id):
        pass

    def stop_stream(self, context, stream_id):
        pass

class PipelineElementRemote(PipelineElement):
    pass

class PipelineElementRemoteAbsent(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

        self.state["lifecycle"] = "absent"

    def process_frame(self, context, **kwargs) -> Tuple[bool, dict]:
        _LOGGER.error( "PipelineElement.process_frame(): "
                      f"{self.definition.name}: invoked when "
                       "remote Pipeline Actor hasn't been discovered")
        return True, {}

class PipelineElementRemoteFound(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

        self.state["lifecycle"] = "ready"

    def process_frame(self, context, **kwargs) -> Tuple[bool, dict]:
        _LOGGER.info("PipelineElementRemoteFound.process_frame(): "
                     "invoked after remote Pipeline Actor discovered")
        return True, {}

# --------------------------------------------------------------------------- #

class Pipeline(PipelineElement):
    Interface.implementations["Pipeline"] =  \
        "aiko_services.pipeline.PipelineImpl"

    @abstractmethod
    def create_frame(self, context, swag):
        pass

    @abstractmethod
    def create_stream(self, stream_id, parameters=None, grace_time=_GRACE_TIME):
        pass

    @abstractmethod
    def destroy_stream(self, stream_id):
        pass

class PipelineImpl(Pipeline):
    DEPLOY_TYPE_LOOKUP = {
        DeployType.LOCAL.value: PipelineElementDeployLocal,
        DeployType.REMOTE.value: PipelineElementDeployRemote
    }
    DEPLOY_TYPE_LOCAL_NAME = PipelineElementDeployLocal.__name__
    DEPLOY_TYPE_REMOTE_NAME = PipelineElementDeployRemote.__name__

    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline, definition_pathname=""):

        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, self)
        print(f"MQTT topic: {self.topic_in}")

        self.state["lifecycle"] = "start"
        self.remote_pipelines = {}  # Service name --> PipelineElement name
        self.services_cache = None
        self.state["definition_pathname"] = definition_pathname
        self.stream_leases = {}

        self.pipeline_graph = self._create_pipeline(definition)
        self.state["element_count"] = self.pipeline_graph.element_count
        self.state["lifecycle"] = "ready"

    # TODO: Better visualization of the Pipeline / PipelineElements details
    #   print(f"PIPELINE: {self.pipeline_graph.nodes()}")
    #   for node in self.pipeline_graph:
    #       print(f"NODE: {node.name}")

    def _error(self, header, diagnostic):
        PipelineImpl._exit(header, diagnostic)

    @classmethod
    def _exit(cls, header, diagnostic):
        complete_diagnostic = f"{header}\n{diagnostic}"
        _LOGGER.error(complete_diagnostic)
        raise SystemExit(complete_diagnostic)

    def create_frame(self, context, swag):
        self._post_message("in", "process_frame", [context, swag])

    def _create_pipeline(self, definition):
        header = f"Error: Creating Pipeline: {definition.name}"

        if len(definition.elements) == 0:
            self._error(header,
                "PipelineDefinition: Doesn't define any PipelineElements")

        node_heads, node_successors = Graph.traverse(definition.graph)
        pipeline_graph = PipelineGraph(node_heads)

        for pipeline_element_definition in definition.elements:
            element_instance = None
            element_name = pipeline_element_definition.name
            deploy_definition = pipeline_element_definition.deploy
            deploy_type_name = type(deploy_definition).__name__

            if deploy_type_name == PipelineImpl.DEPLOY_TYPE_LOCAL_NAME:
                element_class = self._load_element_class(
                    deploy_definition.module, element_name, header)

            # TODO: Make sure element_name is correct for remote case

            if deploy_type_name == PipelineImpl.DEPLOY_TYPE_REMOTE_NAME:
                element_class = PipelineElementRemoteAbsent
                service_name = deploy_definition.service_filter["name"]
                if service_name not in self.remote_pipelines:
                    self.remote_pipelines[service_name] = element_name
                else:
                    self._error(header,
                        f"PipelineDefinition: PipelineElement {element_name}: "
                        f"re-uses remote service_filter name: {service_name}")
                if not self.services_cache:
                    self.services_cache = services_cache_create_singleton(self)
                service_filter = ServiceFilter.with_topic_path(
                    **deploy_definition.service_filter)
                self.services_cache.add_handler(
                    self._pipeline_element_change_handler, service_filter)

            if not element_class:
                self._error(header,
                    f"PipelineDefinition: PipelineElement type unknown: "
                    f"{deploy_type_name}")

            init_args = {
                **actor_args(element_name.lower()),
                "definition": pipeline_element_definition,
                "pipeline": self
            }
            element_instance = compose_instance(element_class, init_args)

            element = Node(
                element_name, element_instance, node_successors[element_name])
            pipeline_graph.add_element(element)

        return pipeline_graph

    def _load_element_class(self,
        module_descriptor, element_name, header):

        diagnostic = None
        try:
            module = load_module(module_descriptor)
            element_class = getattr(module, element_name)
        except FileNotFoundError:
            diagnostic = "found"
        except Exception:
            diagnostic = "loaded"
        if diagnostic:
            self._error(header,
                f"PipelineDefinition: PipelineElement {element_name}: "
                f"Module {module_descriptor} could not be {diagnostic}")
        return element_class

    @classmethod
    def parse_pipeline_definition(cls, pipeline_definition_pathname):
        header = f"Error: Parsing PipelineDefinition: {pipeline_definition_pathname}"
        try:
            pipeline_definition_dict = json.load(
                open(pipeline_definition_pathname, "r"))
            PIPELINE_DEFINITION_SCHEMA.validate(pipeline_definition_dict)
        except ValueError as value_error:
            PipelineImpl._exit(header, value_error)

        try:
            pipeline_definition = PipelineDefinition(**pipeline_definition_dict)
        except TypeError as type_error:
            PipelineImpl._exit(header, type_error)

        if pipeline_definition.version != PIPELINE_DEFINITION_VERSION:
            PipelineImpl._exit(header,
                f"PipelineDefinition: Version must be 0, "
                f"but is {pipeline_definition.version}")

        if pipeline_definition.runtime != "python":
            PipelineImpl._exit(header,
                f'PipelineDefinition: Runtime must be "python", '
                f'but is "{pipeline_definition.runtime}"')

        element_definitions = []
        for element_fields in pipeline_definition.elements:
            element_definition = PipelineElementDefinition(**element_fields)

            if len(element_definition.deploy.keys()) != 1:
                PipelineImpl._exit(header,
                    f"PipelineDefinition: PipelineElement "
                    f"{element_definition.name} must be either local or remote")
            deploy_type = list(element_definition.deploy.keys())[0]

            if deploy_type in PipelineImpl.DEPLOY_TYPE_LOOKUP:
                pipeline_element_deploy_type =  \
                    PipelineImpl.DEPLOY_TYPE_LOOKUP[deploy_type]
            else:
                PipelineImpl._exit(header,
                    f"Unknown Pipeline deploy type: {deploy_type}")

            deploy = pipeline_element_deploy_type(
                **element_definition.deploy[deploy_type])
            element_definition.deploy = deploy

            element_definitions.append(element_definition)

        pipeline_definition.elements = element_definitions

        nodes = {}
        for sub_graph in pipeline_definition.graph:
            node_head, node_successors = parse(sub_graph)

        _LOGGER.info(
            f"PipelineDefinition parsed: {pipeline_definition_pathname}")
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
                header = f"Error: Updating Pipeline: {element_definition.name}"
            # TODO: Don't create another PipelineElement Service !
                element_class = self._load_element_class(
                    element_definition.deploy.module, element_name, header)

            if command == "remove":
                element_class = PipelineElementRemoteAbsent

            init_args = {
                **actor_args(element_name.lower()),
                "definition": element_definition,
                "pipeline": self
            }
            element_instance = compose_instance(element_class, init_args)
            if command == "add":
                element_instance = get_actor_mqtt(
                    topic_path, PipelineElementRemoteFound)
                element_instance.definition = element_definition
            node._element = element_instance
            print(f"Pipeline update: --> {element_name} proxy")

    def process_frame(self, context, swag) -> Tuple[bool, None]:
        if "stream_id" not in context:    # Default stream_id
            context["stream_id"] = 0
        if "frame_id" not in context:     # Default frame_id
            context["frame_id"] = 0
        swag = swag if len(swag) else {}  # Default swag

        # Use existing stream content and update with process_frame(context)
        if context["stream_id"] in self.stream_leases:
            stream_lease = self.stream_leases[context["stream_id"]]
            stream_lease.extend()
            stream_lease.context.update(context)
            context = stream_lease.context

     #  _LOGGER.debug(f"Process frame: {self._id(context)}, swag: {swag}")

        definition_pathname = self.state["definition_pathname"]

        for node in self.pipeline_graph:
            element = node.element
            # TODO: Make sure element_name is correct for remote case
            element_name = element.__class__.__name__
            header = f'Error: Invoking Pipeline "{definition_pathname}": ' \
                     f'PipelineElement "{element_name}": process_frame()'

            inputs = {}
            input_names = [input["name"] for input in element.definition.input]
            for input_name in input_names:
                try:
                    inputs[input_name] = swag[input_name]
                except KeyError as key_error:
                    self._error(header,
                        f'Function parameter "{input_name}" not found')

            frame_output = {}
            okay = True
            try:
                if element_name != "ServiceRemoteProxy":
                    okay, frame_output = element.process_frame(
                        context, **inputs)
                else:
                    element.process_frame(context, **inputs)
                    # TODO: Pipeline stream needs to "pause" waiting for result
            except Exception as exception:
                self._error(header, traceback.format_exc())

            if not okay:
                for stream_id in self.stream_leases.copy():
                    self.destroy_stream(stream_id)
                PipelineImpl._exit(
                    f'PipelineElement "{element_name}": process_frame(): False',
                    "Pipeline stopped")

            swag = {**swag, **frame_output}  # TODO: Consider all failure modes

        # TODO: May need to return the result to a parent Pipeline
        return True, swag

    def create_stream(self, stream_id, parameters=None, grace_time=_GRACE_TIME):
        if self.state["lifecycle"] != "ready":
            self._post_message(
                "in", "create_stream", [stream_id, parameters, grace_time])
            return

        if stream_id in self.stream_leases:
            _LOGGER.error(f"Pipeline create stream: {stream_id} already exists")
        else:
            stream_lease = Lease(int(grace_time), stream_id,
                lease_expired_handler=self.destroy_stream)
            stream_lease.context = {
                "frame_id": 0,
                "parameters": parameters if parameters else {},
                "stream_id": stream_id
            }
            self.stream_leases[stream_id] = stream_lease

            for node in self.pipeline_graph:
                node.element.start_stream(stream_lease.context, stream_id)

    def destroy_stream(self, stream_id):
        if stream_id in self.stream_leases:
            stream_lease = self.stream_leases[stream_id]
            del self.stream_leases[stream_id]
            context = stream_lease.context
            frame_id = context["frame_id"]
            _LOGGER.info(f"Pipeline destroy stream: {self._id(context)}")

            for node in self.pipeline_graph:
                node.element.stop_stream(context, stream_id)

# --------------------------------------------------------------------------- #

try:
    PIPELINE_DEFINITION_VERSION = 0
    PIPELINE_DEFINITION_SCHEMA = avro.schema.parse("""
{
  "namespace": "aiko_services",
  "name":      "pipeline_definition",
  "type":      "record",
  "fields": [
    { "name": "version", "type": "int", "default": 0 },
    { "name": "name",    "type": "string" },
    { "name": "runtime", "type": {
        "name": "type",
        "type": "enum",
        "symbols": ["go", "python"]
      }
    },

    { "name": "graph", "type": {
        "type": "array", "items": "string"
      }
    },

    { "name": "parameters", "type": {
        "type": "map", "values": ["boolean", "int", "null", "string"]
      }
    },

    { "name": "elements", "type": [
        { "type": "array",
          "items": {
            "name": "element",
            "type": "record",
            "fields": [
              { "name": "name",   "type": "string" },
              { "name": "input",  "type": {
                  "type": "array", "items": {
                    "name": "input",
                    "type": "record",
                    "fields": [
                      { "name": "type", "type": "string" },
                      { "name": "name", "type": "string" }
                    ]
                  }
                }
              },
              { "name": "output", "type": {
                  "type": "array", "items": {
                    "name": "output",
                    "type": "record",
                    "fields": [
                      { "name": "type", "type": "string" },
                      { "name": "name", "type": "string" }
                    ]
                  }
                }
              },
              { "name": "deploy", "type": {
                  "name": "deploy_fields",
                  "type": "record",
                  "fields": [
                    { "name": "local", "type": [
                        "null",
                        { "name": "local_fields",
                          "type": "record",
                          "fields": [
                            { "name": "module", "type": "string" }
                          ]
                        }
                      ]
                    },
                    { "name": "remote", "type": [
                        "null",
                        { "name": "remote_fields",
                          "type": "record",
                          "fields": [
                            { "name": "module", "type": "string" },
                            { "name": "service_filter", "type": [
                                { "name": "service_filter",
                                  "type": "record",
                                  "fields": [
                                    { "name": "topic_path",
                                        "type": "string", "default": "*" },
                                    { "name": "name",
                                        "type": "string", "default": "*" },
                                    { "name": "owner",
                                        "type": "string", "default": "*" },
                                    { "name": "protocol",
                                        "type": "string", "default": "*" },
                                    { "name": "transport",
                                        "type": "string", "default": "*" },
                                    { "name": "tags",
                                        "type": "string", "default": "*" }
                                  ]
                                }
                              ]
                            }
                          ]
                        }
                      ]
                    }
                  ]
                }
              }
            ]
          }
        }
      ]
    }
  ]
}
    """)
except avro.errors.SchemaParseException as schema_parse_exception:
    PipelineImpl._exit(
        "Error: Parsing aiko_services/pipeline.py: PIPELINE_DEFINITION_SCHEMA",
        schema_parse_exception)

# --------------------------------------------------------------------------- #

@click.group()
def main():
    """Create and delete Pipelines"""
    pass

@main.command(help="Create Pipeline defined by PipelineDefinition pathname")
@click.option("--name", "-n", type=str, default=None, required=False,
    help="Pipeline Actor name")
@click.argument("definition_pathname", nargs=1, type=str)
def create(definition_pathname, name):
    if not os.path.exists(definition_pathname):
        raise SystemExit(
            f"Error: PipelineDefinition not found: {definition_pathname}")

    pipeline_definition = PipelineImpl.parse_pipeline_definition(
        definition_pathname)
    name = name if name else pipeline_definition.name

    init_args = actor_args(name, PROTOCOL_PIPELINE)
    init_args["definition"] = pipeline_definition
    init_args["pipeline"] = None
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
