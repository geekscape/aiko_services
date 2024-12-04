#!/usr/bin/env python3
#
# Manage Pipelines consisting of PipelineElements (Actors or Services)
#
# Usage
# ~~~~~
# DEFINITION=pipeline_definition.json
# aiko_pipeline create  [--name $PIPELINE_NAME] $DEFINITION
# aiko_pipeline destroy $PIPELINE_NAME
#
# aiko_pipeline create $DEFINITION --log_level debug  \
#   --stream_id 1 --frame_data "(argument_name: argument_value ...)"
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
#   - ServiceDefinition: map-out, map-in and name_mapping
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
import copy
from collections import OrderedDict  # All OrderedDict operations are O(1)
from dataclasses import dataclass, asdict
from enum import Enum
import json
import os
import queue
import threading
from threading import Thread
import time
import traceback
from typing import Any, Dict, List, Tuple

from aiko_services.main import *
from aiko_services.main.transport import *
from aiko_services.main.utilities import *

__all__ = [
    "Pipeline", "PipelineElement", "PipelineElementImpl", "PipelineImpl",
    "PROTOCOL_PIPELINE"
]

_VERSION = 0

ACTOR_TYPE_PIPELINE = "pipeline"
ACTOR_TYPE_ELEMENT = "pipeline_element"
PROTOCOL_PIPELINE =  f"{ServiceProtocol.AIKO}/{ACTOR_TYPE_PIPELINE}:{_VERSION}"
PROTOCOL_ELEMENT =  f"{ServiceProtocol.AIKO}/{ACTOR_TYPE_ELEMENT}:{_VERSION}"

_GRACE_TIME = 60  # seconds
_LOGGER = aiko.logger(__name__)

_WINDOWS = False  # Stream windowing protocol for distributed function calls

# --------------------------------------------------------------------------- #

class DeployType(Enum):
    LOCAL = "local"
    REMOTE = "remote"

@dataclass
class PipelineDefinition:
#   comment: str  # Specified in Avro schema and discarded by parser
    version: int
    name: str
    runtime: str
    graph: List[str]
    parameters: Dict  # Optional field, default: {}
    elements: List

@dataclass
class PipelineElementDefinition:
#   comment: str  # Specified in Avro schema and discarded by parser
    name: str     # unique name
    input: Dict[str, str]
    output: Dict[str, str]
    parameters: Dict  # Optional field, default: {}
    deploy: Dict

@dataclass
class PipelineElementDeployLocal:
    class_name: str  # optional field, default: name
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
    module: str  # TODO: Is this really needed ?  Probably not !
    service_filter: RemoteServiceFilter

# --------------------------------------------------------------------------- #

class PipelineGraph(Graph):
    def __init__(self, head_nodes=None):
        super().__init__(head_nodes)

    def add_element(self, element):
        self.add(element)
        element.predecessors = OrderedDict()

    @property
    def element_count(self):
        return len(self._graph)

    @classmethod
    def get_element(cls, node):
        element = node.element

        if element.__class__.__name__ == "ServiceRemoteProxy":
            lifecycle = "ready"  # element.get_lifecycle() ?
            local = False        # element.is_local() ?
            name = node.name
        else:
            lifecycle = element.share["lifecycle"]  # element.get_lifecycle() ?
            local = element.is_local()

            if element.__class__.__name__ == "PipelineRemote":
                name = node.name
            else:
                name = element.__class__.__name__

        return element, name, local, lifecycle

# TODO: Work-in-progress
# - Pass 1: Validate_inputs_by_name_and_type()
#   - Each input NAME and TYPE provided by exactly one parent predecessor
#   - Each input NAME and TYPE provided by exactly one predecessor (recursive)
#
# - Pass 2: Validate_inputs_by_position_and_type()
#   - Each input TYPE provided exactly in order by parent predecessor
#   - Each input TYPE provided by exactly one predecessor (recursive) ?
#
# - Pass 3: Perform mapping first, then ...
#   - Check mapping output --> input: NAME and TYPE must match
#     "graph": ["(A (B D (d0: d1)) (C D))"],
#
# - Provide mapping clues
# - Flexible or Strict (exact match predecessor output --> successor input)
# - Reflect on PipelineElement function signatures to create definition.elements

    def validate_inputs(self, inputs, predecessors, checked=None, strict=False):
        checked = checked if checked else []  # each predecessor checked once
        for predecessor in predecessors.values():
            if predecessor not in checked:
                checked.append(predecessor)
                predecessor_outputs = predecessor.element.definition.output
                for input in inputs:
                    for predecessor_output in predecessor_outputs:
                        if predecessor_output["name"] == input["name"]:
                            input["found"] += 1
                if not strict:
                    inputs, checked = self.validate_inputs(
                                      inputs, predecessor.predecessors, checked)
        return inputs, checked

    def validate_mapping(self, map_in_nodes, element_name, input):
        valid_mappings = []
        if element_name in map_in_nodes:
            map_in_node = map_in_nodes[element_name]
            for predecessor_name, mapping in map_in_node.items():
                if input["name"] in mapping.values():
                    valid_mappings.append((predecessor_name, mapping))
        return valid_mappings

    def validate(self, pipeline_definition, head_node_name, strict=False):
        node_unknown = None
        try:
            nodes = self.get_path(head_node_name)
        except KeyError as key_error:
            node_unknown = key_error
        if node_unknown:
            raise SystemExit(
                f"PipelineDefinition PipelineElement unknown: {node_unknown}")

        for node in nodes:
            element, element_name, _, _ = PipelineGraph.get_element(node)
            element_inputs = element.definition.input
            element_inputs = [{**item, "found": 0} for item in element_inputs]

            if element_name not in self._head_nodes:
                predecessors = node.predecessors
                if len(predecessors) == 0:  # Don't worry about graph head nodes
                    continue
                inputs, _ = self.validate_inputs(
                                element_inputs, predecessors, strict)
                for input in inputs:
                    try_map_in_out = False
                    diagnostic = f"PipelineElement {element_name}: input \"{input['name']}\" not produced by any "
                    if strict and input["found"] != 1:
                        diagnostic += "immediate predecessor PipelineElement"
                        try_map_in_out = True
                    #   print(f"{diagnostic}")  # TODO: Ensure this is right
                    elif input["found"] == 0:
                        diagnostic += "previous PipelineElements"
                        try_map_in_out = True

                    if try_map_in_out:
                        map_in_nodes = pipeline_definition.map_in_nodes
                        if not self.validate_mapping(
                            map_in_nodes, element_name, input):
                            pass
                        #   print(f"{diagnostic}")  # TODO: Ensure this is right

            for successor_name in node.successors:
                successor = self.get_node(successor_name)
                successor.predecessors[element_name] = node

# --------------------------------------------------------------------------- #
# PipelineElement: service_level_agreement: low_latency, etc

class PipelineElement(Actor):
    Interface.default("PipelineElement",
        "aiko_services.main.pipeline.PipelineElementImpl")

    @abstractmethod
    def create_frame(self, stream, frame_data):
        pass

    @abstractmethod
    def create_frames(
        self, stream, frame_generator, frame_id=FIRST_FRAME_ID, rate=None):
        pass

    @abstractmethod
    def get_parameter(self, name, default=None, use_pipeline=True):
        pass

    @abstractmethod
    def get_stream(self):
        pass

    @classmethod
    def is_local(cls):
        return True

    @abstractmethod
    def my_id(self, all=False):
        pass

# PipelineElement developer must provide a process_frame() implementation

    @abstractmethod
    def process_frame(self, stream, **kwargs) -> Tuple[StreamEvent, dict]:
        """
        Returns "status" indicating success or failure of processing the frame
        """
        pass

    @abstractmethod
    def start_stream(self, stream, stream_id):
        pass

    @abstractmethod
    def stop_stream(self, stream, stream_id):
        pass

class PipelineElementImpl(PipelineElement):
    def __init__(self, context):
        self.definition = context.get_definition()
        self.pipeline = context.get_pipeline()
        self.is_pipeline = (self.pipeline == None)
        if context.protocol == "*":
            context.set_protocol(
                PROTOCOL_PIPELINE if self.is_pipeline else PROTOCOL_ELEMENT)
        context.get_implementation("Actor").__init__(self, context)

    #  "log_level" parameter overrides "AIKO_LOG_LEVEL" environment variable
        log_level, found = self.get_parameter(
            "log_level", self_share_priority=False)
        if found:
            self.logger.setLevel(str(log_level).upper())

        self.share["source_file"] = f"v{_VERSION}⇒ {__file__}"
        self.share.update(self.definition.parameters)
    # TODO: Fix Aiko Dashboard / EC_Producer incorrectly updates this approach
    #   self.share["parameters"] = self.definition.parameters  # TODO

    def create_frame(self, stream, frame_data, frame_id=None):
        if stream.stream_id not in self.pipeline.DEBUG:     # DEBUG: 2024-12-02
            self.pipeline.DEBUG[stream.stream_id] = {}
        self.pipeline.DEBUG[stream.stream_id]["create_frame"] = {
            "time": local_iso_now(), "latest_frame_id": frame_id}

        frame_id = frame_id if frame_id else stream.frame_id
        stream_copy = Stream(stream.stream_id, frame_id,
            stream.parameters, stream.queue_response,
            stream.state, stream.topic_response)
        self.pipeline.create_frame(stream_copy, frame_data)

# Optional "frame_generator" starts during "create_stream() --> start_stream()"

    def create_frames(
        self, stream, frame_generator, frame_id=FIRST_FRAME_ID, rate=None):

        thread_args = (stream, frame_generator, int(frame_id), rate)
        Thread(target=self._create_frames_generator,
            args=thread_args, daemon=True).start()

# TODO: For "rate" measure time since last frame to be more accurate
# FIX:  For "rate" check "rate=0" (fills mailbox) versus "rate=None" ?

    def _create_frames_generator(self, stream, frame_generator, frame_id, rate):
        try:
            self.pipeline._enable_thread_local(
                "_create_frames_generator", stream.stream_id, frame_id)
            stream, frame_id = self.get_stream()

            while stream.state == StreamState.RUN:
                try:
                    stream_event, frame_data = frame_generator(stream, frame_id)
                except Exception as exception:
                    self.logger.error(
                        "Exception in pipeline_element._create_frames() --> "  \
                        "frame_generator()")
                    stream_event = StreamEvent.ERROR
                    frame_data = {"diagnostic": traceback.format_exc()}

                stream.state = self.pipeline._process_stream_event(
                    self.name, stream_event, frame_data)

                if stream.state == StreamState.RUN and frame_data:
                    if isinstance(frame_data, dict):
                        frame_data = [frame_data]
                    if isinstance(frame_data, list):
                        for a_frame_data in frame_data:
                            self.create_frame(stream, a_frame_data, frame_id)
                            frame_id += 1
                    else:
                        self.logger.warning(
                            "Frame generator must return either "
                            "{frame_data} or [{frame_data}]")
                else:
                    frame_id += 1

                if stream.state in [StreamState.DROP_FRAME, StreamState.RUN]:
                    stream.state = StreamState.RUN
                    if rate:
                        time.sleep(1.0 / rate)
                    self.pipeline.thread_local.frame_id = frame_id
        finally:
            self.pipeline._disable_thread_local("_create_frames_generator")

    # TODO: During process_frame(), stream parameters should be updated
    #       in self.share[], just like PipelineDefinition parameters.
    #       Note: Consider the performance implications when doing this !

    def get_parameter(self,
        name, default=None, use_pipeline=True, self_share_priority=True):

        value = None
        found = False

        element_parameter_name = f"{self.definition.name}.{name}"
        stream_parameters = self._get_stream_parameters()

        if element_parameter_name in stream_parameters:
            value = stream_parameters[element_parameter_name]
            found = True
        elif name in self.definition.parameters:
            if self_share_priority and name in self.share:
                value = self.share[name]
            else:
                value = self.definition.parameters[name]
            found = True

    # TODO: Should also allow Pipeline parameters to be updated

        if not found and use_pipeline and not self.is_pipeline:
            if name in stream_parameters:
                value = stream_parameters[name]
                found = True
            elif name in self.pipeline.definition.parameters:
                if self_share_priority and name in self.pipeline.share:
                    value = self.pipeline.share[name]
                else:
                    value = self.pipeline.definition.parameters[name]
                found = True

        if not found and default is not None:
            value = default  # Note: "found" is deliberately left as False
        return value, found

    def get_stream(self):
        return self.pipeline.get_stream()

    def _get_stream_parameters(self):
        parameters = {}
        try:
            stream, _ = self.get_stream()
            if stream:
                parameters = stream.parameters
        except AttributeError:
            pass
        return parameters

    def my_id(self, all=False):
        name = self.name if all else ""
        stream, frame_id = self.get_stream()
        return f"{name}<{stream.stream_id}:{frame_id}>"

    def start_stream(self, stream, stream_id):
        return StreamEvent.OKAY, None

    def stop_stream(self, stream, stream_id):
        return StreamEvent.OKAY, None

# --------------------------------------------------------------------------- #

class Pipeline(PipelineElement):
    Interface.default("Pipeline", "aiko_services.main.pipeline.PipelineImpl")

    @abstractmethod
    def create_stream(self, stream_id, graph_path=None,
        parameters=None, grace_time=_GRACE_TIME,
        queue_response=None, topic_response=None):
        pass

    @abstractmethod
    def destroy_stream(self, stream_id, graceful=False):
        pass

    @abstractmethod
    def parse_pipeline_definition(cls, pipeline_definition_pathname):
        pass

    @abstractmethod
    def process_frame_response(
        self, stream, frame_data) -> Tuple[StreamEvent, dict]:
        pass

    @abstractmethod
    def set_parameter(self, stream_id, name, value):
        pass

    @abstractmethod
    def set_parameters(self, stream_id, parameters):
        pass

class PipelineImpl(Pipeline):
    DEPLOY_TYPE_LOOKUP = {
        DeployType.LOCAL.value: PipelineElementDeployLocal,
        DeployType.REMOTE.value: PipelineElementDeployRemote
    }
    DEPLOY_TYPE_LOCAL_NAME = PipelineElementDeployLocal.__name__
    DEPLOY_TYPE_REMOTE_NAME = PipelineElementDeployRemote.__name__

    def __init__(self, context):
        self.DEBUG = {}                                     # DEBUG: 2024-12-02

        self.actor = context.get_implementation("Actor")  # _WINDOWS
        context.get_implementation("PipelineElement").__init__(self, context)
        print(f"MQTT topic: {self.topic_in}")

        self.share["definition_pathname"] = context.definition_pathname
        self.share["lifecycle"] = "waiting"
        self.share["graph_path"] = context.graph_path
        self.remote_pipelines = {}  # Service name --> PipelineRemote instance
        self.services_cache = None

        self.stream_leases = {}
        self.thread_local = threading.local()  # See _enable_thread_local()

    #  "log_level" parameter overrides "AIKO_LOG_LEVEL" environment variable
        log_level, found = self.get_parameter(
            "log_level", self_share_priority=False)
        if found:
            self.logger.setLevel(str(log_level).upper())

        self.pipeline_graph = self._create_pipeline_graph(context.definition)
        self.share["element_count"] = self.pipeline_graph.element_count
        self.share["streams"] = 0
        self.share["streams_frames"] = 0
        self.share["sliding_windows"] = _WINDOWS
        self._update_lifecycle_state()

    # TODO: Better visualization of the Pipeline / PipelineElements details
        if False:
            print(f"Pipeline graph path ...")
            graph_path = self.pipeline_graph.get_path(self.share["graph_path"])
            for node in graph_path:
                print(f"    PipelineElement: {node.name}")

        event.add_timer_handler(self._status_update_timer, 3.0)

    # Exists only for_WINDOWS option
    def ec_producer_change_handler(self, command, item_name, item_value):
        global _WINDOWS
        self.actor.ec_producer_change_handler(
            self, command, item_name, item_value)
        if item_name == "sliding_windows":
            try:
                _WINDOWS = item_value.lower() == "true"
            except ValueError:
                pass

    def _update_lifecycle_state(self):
        pe_lifecycles = []
        graph_path = self.pipeline_graph.get_path(self.share["graph_path"])
        for node in graph_path:
            _, _, _, lifecycle = PipelineGraph.get_element(node)
            pe_lifecycles.append(lifecycle == "ready")
        lifecycle = "ready" if all(pe_lifecycles) else "waiting"
        self.ec_producer.update("lifecycle", lifecycle)

    def _status_update_timer(self):
        streams_frames = 0
        for stream_lease in self.stream_leases.values():
            streams_frames += len(stream_lease.stream.frames)

        self.ec_producer.update("streams", len(self.stream_leases))
        self.ec_producer.update("streams_frames", streams_frames)

    def _add_node_properties(self, node_name, properties, predecessor_name):
        definition = self.definition

        if node_name not in definition.map_in_nodes:
            definition.map_in_nodes[node_name] = {}
        definition.map_in_nodes[node_name][predecessor_name] = properties

        if predecessor_name not in definition.map_out_nodes:
            definition.map_out_nodes[predecessor_name] = {}
        definition.map_out_nodes[predecessor_name][node_name] = properties

# Pipeline current "stream" and "frame_id" are thread-local variables
# Valid for create_stream(), process_frame() and destroy_stream() on main thread
# Valid for PipelineElement._create_frames_generator() thread
#
# Always use ...
#     try:
#         self._enable_thread_local("function_name", stream_id, frame_id)
#         stream, frame_id = self.get_stream()
#     finally:
#         self._disable_thread_local("function_name")

    def _enable_thread_local(self, function_name, stream_id, frame_id=None):
        stream = getattr(self.thread_local, "stream", None)
        assert not stream, "self.thread_local.stream must not be assigned"
        self.thread_local.stream = self.stream_leases[stream_id].stream
        if frame_id:
            self.thread_local.frame_id = frame_id
        else:
            self.thread_local.frame_id = self.thread_local.stream.frame_id
    #   self.logger.warning(f"Enable:  {function_name}: {self.my_id()}")  # useful

    def _disable_thread_local(self, function_name):
        stream = self.thread_local.stream
        assert stream, "self.thread_local.stream must be assigned"
    #   self.logger.warning(f"Disable: {function_name}: {self.my_id()}")  # useful
        self.thread_local.stream = None
        self.thread_local.frame_id = None

    def create_frame(self, stream_dict, frame_data):
        if isinstance(stream_dict, Stream):
            stream_dict = stream_dict.as_dict()
        self._post_message(
            ActorTopic.IN, "process_frame", [stream_dict, frame_data])

    @classmethod
    def create_pipeline(cls, definition_pathname, pipeline_definition,
        name, graph_path, stream_id, parameters, frame_id, frame_data,
        grace_time, queue_response=None, stream_reset=False):

        name = name if name else pipeline_definition.name

        init_args = pipeline_args(name,
            protocol=PROTOCOL_PIPELINE,
            definition=pipeline_definition,
            definition_pathname=definition_pathname,
            graph_path=graph_path
        )
        pipeline = compose_instance(PipelineImpl, init_args)

        stream_dict = {"frame_id": int(frame_id), "parameters": {}}

        if stream_id is not None:
            stream_dict["stream_id"] = stream_id
            if stream_reset:
                pipeline.destroy_stream(stream_id)

            pipeline.create_stream(stream_id, graph_path=None,
                parameters=dict(parameters), grace_time=grace_time,
                queue_response=queue_response, topic_response=None)
        else:
            pipeline.set_parameters(None, parameters)

        if frame_data is not None:
            function_name, arguments = parse(f"(process_frame {frame_data})")
            if len(arguments):
                pipeline.create_frame(stream_dict, arguments[0])
            else:
                raise SystemExit(
                    f"Error: Frame data must be provided")

        return pipeline

    def _create_pipeline_graph(self, definition):
        header = f"Error: Creating Pipeline: {definition.name}"

        if len(definition.elements) == 0:
            self._error_pipeline(header,
                "PipelineDefinition: Doesn't define any PipelineElements")

        definition.map_in_nodes = {}
        definition.map_out_nodes = {}
        node_heads, node_successors = Graph.traverse(
            definition.graph, self._add_node_properties)
        pipeline_graph = PipelineGraph(node_heads)
    #   self.parameters = definition.parameters  # TODO: Use it or lose it !

        for pipeline_element_definition in definition.elements:
            element_instance = None
            element_name = pipeline_element_definition.name
            if element_name not in node_successors:
                print(f'Warning: Skipping PipelineElement {element_name}: '
                      f'Not used within the "graph" definition')
                continue
            deploy_definition = pipeline_element_definition.deploy
            deploy_type_name = type(deploy_definition).__name__

            if deploy_type_name == PipelineImpl.DEPLOY_TYPE_LOCAL_NAME:
                class_name = pipeline_element_definition.deploy.class_name
                element_class = self._load_element_class(
                    deploy_definition.module, class_name, header)

            # TODO: Is element_name is correct for remote case
            if deploy_type_name == PipelineImpl.DEPLOY_TYPE_REMOTE_NAME:
                element_class = PipelineRemote

            if not element_class:
                self._error_pipeline(header,
                    f"PipelineDefinition: PipelineElement type unknown: "
                    f"{deploy_type_name}")

            init_args = pipeline_element_args(element_name,
                definition=pipeline_element_definition, pipeline=self)
            element_instance = compose_instance(element_class, init_args)
            element_instance.parameters = pipeline_element_definition.parameters

            if element_class == PipelineRemote:
                service_name = deploy_definition.service_filter["name"]
                if service_name not in self.remote_pipelines:
                    topic_path = None  # uniquely identifies remote Pipeline
                    self.remote_pipelines[service_name] = (
                        element_name, element_instance, topic_path)
                else:
                    self._error_pipeline(header,
                        f"PipelineDefinition: PipelineElement {element_name}: "
                        f"re-uses remote service_filter name: {service_name}")
                if not self.services_cache:
                    self.services_cache = services_cache_create_singleton(self)
                service_filter = ServiceFilter.with_topic_path(
                    **deploy_definition.service_filter)
                self.services_cache.add_handler(
                    self._pipeline_element_change_handler, service_filter)

            element = Node(
                element_name, element_instance, node_successors[element_name])
            pipeline_graph.add_element(element)

        pipeline_graph.validate(definition, self.share["graph_path"])
        return pipeline_graph

# TODO: Consider refactoring Stream into "stream.py" ?

    def create_stream(self, stream_id, graph_path=None,
        parameters=None, grace_time=_GRACE_TIME,
        queue_response=None, topic_response=None):

        if queue_response and topic_response:
            self.logger.error(
                f"Create stream: use either queue_response or topic_response")
            return False

    # TODO: Proper solution for overall handling of remote Pipeline proxy
    # TODO: Implement limit on delayed post message
        if self.share["lifecycle"] != "ready":
            arguments = [stream_id, graph_path,
                parameters, grace_time, queue_response, topic_response]
            self._post_message(
                ActorTopic.IN, "create_stream", arguments, delay=3.0)
            self.logger.warning(
                f"Create stream: {stream_id}: invoked when remote "
                 "Pipeline hasn't been discovered ... will retry")
            return False

        stream_id = str(stream_id)
        if stream_id in self.stream_leases:
            self.logger.error(f"Create stream: {stream_id} already exists")
            return False

        graph_path = graph_path if graph_path else self.share["graph_path"]
        if graph_path:
            if graph_path not in self.pipeline_graph._head_nodes:
                self.logger.error(
                    f"Create stream: Unknown Pipeline Graph Path: {graph_path}")
                return False

        if stream_id not in self.DEBUG:                     # DEBUG: 2024-12-02
            self.DEBUG[stream_id] = {}
        self.DEBUG[stream_id]["create_stream"] = {
            "time": local_iso_now(), "stream_id": stream_id}

        self.logger.debug(f"Create stream: {self.name}<{stream_id}>")
        stream_lease = Lease(int(grace_time), stream_id,
            lease_expired_handler=self.destroy_stream)
        stream_lease.stream = Stream(
            stream_id=stream_id,
            graph_path=graph_path,
            parameters=parameters if parameters else {},
            queue_response=queue_response,
            topic_response=topic_response)
        self.stream_leases[stream_id] = stream_lease

        try:
            self._enable_thread_local("create_stream", stream_id)
            stream, _ = self.get_stream()

            graph_path = self.pipeline_graph.get_path(self.share["graph_path"])
            for node in graph_path:
                element, element_name, local, _ =  \
                    PipelineGraph.get_element(node)
                if local:  ## Local element ##
                    try:
                        stream_event, diagnostic = element.start_stream(
                            stream, stream_id)
                    except Exception as exception:
                        self.logger.error("Exception in "  \
                          "pipeline.create_stream() --> start_stream()")
                        stream_event = StreamEvent.ERROR
                        diagnostic = {"diagnostic": traceback.format_exc()}

                    stream_state = self._process_stream_event(
                        element_name, stream_event, diagnostic)
                else:  ## Remote element ##
                    # TODO: Consider using "topic_response=self.topic_control"
                    if _WINDOWS:
                        element.create_stream(
                            stream_id, Graph.path_remote(stream.graph_path),
                            parameters, grace_time, None, self.topic_in)
        finally:
            self._disable_thread_local("create_stream")
        return True

    def destroy_stream(self, stream_id, graceful=False, use_thread_local=True):
        stream_id = str(stream_id)

    # TODO: Proper solution for handling of remote Pipeline proxy
    # TODO: Implement limit on delayed post message

    ## Remote elements ##
        if self.share["lifecycle"] == "ready":
            graph_path = self.pipeline_graph.get_path(self.share["graph_path"])
            for node in graph_path:
                element, _, local, _ = PipelineGraph.get_element(node)
                if not local:
                    element.destroy_stream(stream_id, True)

        else:
            if _WINDOWS:
                arguments = [stream_id, graceful, use_thread_local]
                self._post_message(
                    ActorTopic.IN, "destroy_stream", arguments, delay=3.0)
                self.logger.warning(
                    f"Destroy stream: {stream_id}: invoked when remote "
                     "Pipeline hasn't been discovered ... will retry")
                return False

    ## Local elements ##
        if stream_id not in self.stream_leases:
            return False

        try:
            if use_thread_local:
                self._enable_thread_local("destroy_stream", stream_id)
            stream, _ = self.get_stream()

            if graceful and len(stream.frames):
                arguments = [stream_id, graceful, use_thread_local]
                self._post_message(
                    ActorTopic.IN, "destroy_stream", arguments, delay=3.0)
                return False

            self.logger.debug(f"Destroy stream: {self.name}<{stream_id}>")

            if stream_id in self.DEBUG:                     # DEBUG: 2024-12-02
                del self.DEBUG[stream_id]

            graph_path = self.pipeline_graph.get_path(self.share["graph_path"])
            for node in graph_path:
                element, element_name, local, _ =  \
                    PipelineGraph.get_element(node)
                if local:  ## Local element ##
                    try:
                        stream_event, diagnostic = element.stop_stream(
                            stream, stream_id)
                    except Exception as exception:
                        self.logger.error("Exception in "  \
                          "pipeline.destroy_stream() --> stop_stream()")
                        stream_event = StreamEvent.ERROR
                        diagnostic = {"diagnostic": traceback.format_exc()}

                    stream_state = self._process_stream_event(element_name,
                        stream_event, diagnostic, in_destroy_stream=True)
        finally:
            if use_thread_local:
                self._disable_thread_local("destroy_stream")

        stream_lease = self.stream_leases[stream_id]
        del self.stream_leases[stream_id]
        return True

    def _error_pipeline(self, header, diagnostic):
        PipelineImpl._exit(header, diagnostic)

    @classmethod
    def _exit(cls, header, diagnostic):
        complete_diagnostic = f"{header}\n{diagnostic}"
        _LOGGER.error(complete_diagnostic)
        raise SystemExit(-1)

    def get_stream(self):   # See _enable_thread_local()
        stream = self.thread_local.stream
        assert stream, "self.thread_local.stream must be assigned"
        return stream, self.thread_local.frame_id

    def _load_element_class(self,
        module_descriptor, element_name, header):

        diagnostic = None
        stack_traceback = ""
        try:
            module = load_module(module_descriptor)
            element_class = getattr(module, element_name)
        except FileNotFoundError:
            diagnostic = "found"
        except Exception:
            diagnostic = "loaded"
            stack_traceback = "\n" + str(traceback.format_exc())
        if diagnostic:
            self._error_pipeline(header,
                f"PipelineDefinition: PipelineElement {element_name}: "
                f"Module {module_descriptor} could not be {diagnostic}"
                f"{stack_traceback}")
        return element_class

    @classmethod
    def parse_pipeline_definition(cls, pipeline_definition_pathname):
        CLASS_NAME_FIELD = "class_name"
        COMMENT_FIELD = "#"
        PARAMETERS_FIELD = "parameters"
        header = f"Error: Parsing PipelineDefinition: {pipeline_definition_pathname}"
        try:
            pipeline_definition_dict = json.load(
                open(pipeline_definition_pathname, "r"))
            PIPELINE_DEFINITION_SCHEMA.validate(pipeline_definition_dict)
        except ValueError as value_error:
            PipelineImpl._exit(header, value_error)

        if COMMENT_FIELD in pipeline_definition_dict:  # discard
            del pipeline_definition_dict[COMMENT_FIELD]
        if PARAMETERS_FIELD not in pipeline_definition_dict:  # optional
            pipeline_definition_dict[PARAMETERS_FIELD] = {}

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
            if COMMENT_FIELD in element_fields:  # discard
                del element_fields[COMMENT_FIELD]
            if PARAMETERS_FIELD not in element_fields:  # optional
                element_fields[PARAMETERS_FIELD] = {}

            try:
                element_definition = PipelineElementDefinition(**element_fields)
            except TypeError as type_error:
                PipelineImpl._exit(header,
                    f"PipelineDefinition: PipelineElement {type_error}")

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
                    f"PipelineDefinition: PipelineElement "
                    f"{element_definition.name}: "
                    f"Unknown Pipeline deploy type: {deploy_type}")

            element_deploy_fields = element_definition.deploy[deploy_type]

            if deploy_type == DeployType.LOCAL.value:
                if CLASS_NAME_FIELD not in element_deploy_fields:  # optional
                    element_deploy_fields[CLASS_NAME_FIELD] =  \
                        element_definition.name

            element_definition.deploy =  \
                pipeline_element_deploy_type(**element_deploy_fields)

            element_definitions.append(element_definition)

        pipeline_definition.elements = element_definitions

        _LOGGER.info(
            f"PipelineDefinition parsed: {pipeline_definition_pathname}")
        return(pipeline_definition)

    def _pipeline_element_change_handler(self, command, service_details):
        if command in ["add", "remove"]:
            topic_path = f"{service_details[0]}/in"
            service_name = service_details[1]
            element_name, element_instance, element_topic_path =  \
                self.remote_pipelines[service_name]
            node = self.pipeline_graph.get_node(element_name)
            element_definition = node.element.definition
            topic_path_match = False

            if command == "add":     # use discovered remote proxy
                topic_path_match = True
                element_instance.set_remote_absent(False)
                new_element_instance = get_actor_mqtt(
                    topic_path, PipelineRemote)
                new_element_instance.definition = element_definition

            if command == "remove":  # use original PipelineRemote instance
                if topic_path == element_topic_path:
                    topic_path_match = True
                    topic_path = None
                    element_instance.set_remote_absent(True)
                    new_element_instance = element_instance

            if topic_path_match:
                self.logger.debug(f"PipelineElement remote {element_name}: "
                                  f"{command}: {service_details[0:2]}")

                self.remote_pipelines[service_name] = (
                    element_name, element_instance, topic_path)
                node._element = new_element_instance
                self._update_lifecycle_state()

    def process_frame(
        self, stream_dict, frame_data) -> Tuple[StreamEvent, dict]:

        if self.share["lifecycle"] != "ready":
            arguments = [stream_dict, frame_data]
            self._post_message(
                ActorTopic.IN, "process_frame", arguments, delay=3.0)
            stream_id = stream_dict.get("stream_id", "*")
            self.logger.warning(
                f"Process frame: {stream_id}: invoked when remote "
                 "Pipeline hasn't been discovered ... will retry")
            return False

        return self._process_frame_common(stream_dict, frame_data, True)

    def process_frame_response(
        self, stream_dict, frame_data) -> Tuple[StreamEvent, dict]:

        return self._process_frame_common(stream_dict, frame_data, False)

    def _process_frame_common(self, stream_dict, frame_data_in, new_frame)  \
        -> Tuple[StreamEvent, dict]:

        frame_complete = True
        graph, stream =  \
            self._process_initialize(stream_dict, frame_data_in, new_frame)
        if graph is None:
            return False

        try:
            self._enable_thread_local("process_frame", stream.stream_id)
            stream, _ = self.get_stream()
            try:                                            # DEBUG: 2024-12-02
                frame = stream.frames[stream.frame_id]
            except KeyError:                                # DEBUG: 2024-12-02
                self.logger.error(
                    f"Stream <{stream.stream_id}>: "
                    f"Frame id: <{stream.frame_id}> not found\n"
                     "### Is a background thread in a PipelineElement "
                     'changing "stream.frame_id" ?\n'
                    f"### Purging Stream <{stream.stream_id}> in-flight frames")
                details = self.DEBUG[stream.stream_id]["create_stream"]
                self.logger.warning(f'##     {details["time"]}: create_stream(): stream_id: {details["stream_id"]}')

                details = self.DEBUG[stream.stream_id]["frames_lru"]
                self.logger.warning(f'##     Recent process frame_id(s): {details.get_list()}')

                self.logger.warning(f"##     Cached frame_id(s): {list(stream.frames.keys())}")

                details = self.DEBUG[stream.stream_id]["create_frame"]
                self.logger.warning(f'##     {details["time"]}: create_frame(): Last generated frame_id: {details["latest_frame_id"]}')

                stream.frames.clear()  # radically prevent memory leaks
                return False
            metrics = self._process_metrics_initialize(frame)

            definition_pathname = self.share["definition_pathname"]
            element_name = None
            frame_data_out = {} if new_frame else frame_data_in

            for node in graph:
                if stream.state in [StreamState.DROP_FRAME, StreamState.ERROR]:
                    break
                # TODO: Is element_name is correct for all error diagnostics
                element, element_name, local, _ =  \
                    PipelineGraph.get_element(node)
                header = f'Error: Invoking Pipeline "{definition_pathname}": ' \
                         f'PipelineElement "{element_name}": process_frame()'

                inputs = self._process_map_in(
                    header, element, element_name, frame.swag)

                stream_event = StreamEvent.OKAY
                try:
                    if local:  ## Local element ##
                        start_time = time.time()

                        try:
                            stream_event, frame_data_out =  \
                                element.process_frame(stream, **inputs)
                        except Exception as exception:
                            self.logger.error(
                                "Exception in pipeline.process_frame() --> "  \
                                "frame_generator()")
                            stream_event = StreamEvent.ERROR
                            frame_data_out = {
                                "diagnostic": traceback.format_exc()}

                        stream.state = self._process_stream_event(
                            element_name, stream_event, frame_data_out)
                    #   TODO: Test "stream.state" before continuing
                        self._process_map_out(element_name, frame_data_out)
                        self._process_metrics_capture(  # TODO: Move up ?
                            metrics, element.name, start_time)
                        frame.swag.update(frame_data_out)
                    else:  ## Remote element ##
                        if self.share["lifecycle"] != "ready":
                            diagnostic = {
                                "diagnostic": "process_frame() invoked when "
                                     "remote Pipeline hasn't been discovered"
                            }
                            stream.state = self._process_stream_event(
                                element_name, StreamEvent.ERROR, diagnostic)
                        else:
                            frame_complete = False
                            frame_data_out = {}
                            frame.paused_pe_name = node.name
                            remote_stream = {
                                "stream_id": stream.stream_id,
                                "frame_id": stream.frame_id
                            }
                            element.process_frame(remote_stream, **inputs)
                            # process_frame_response() --> continue graph
                        break
                except Exception as exception:
                    self._error_pipeline(header, traceback.format_exc())

            if frame_complete:
                stream_info = {
                    "stream_id": stream.stream_id,
                    "frame_id": stream.frame_id,
                    "state": stream.state}
                if stream.queue_response:
                    stream.queue_response.put((stream_info, frame_data_out))
                elif stream.topic_response:
                    actor = get_actor_mqtt(stream.topic_response, Pipeline)
                    actor.process_frame_response(stream_info, frame_data_out)
                else:
                    payload = generate(
                        "process_frame", (stream_info, frame_data_out))
                    aiko.message.publish(self.topic_out, payload)

        finally:
        # If not _WINDOWS, then always remove the cached Stream Frame
            if not _WINDOWS and stream.frame_id in stream.frames:
                del stream.frames[stream.frame_id]
            if frame_complete and stream.frame_id in stream.frames:
                del stream.frames[stream.frame_id]
            self._disable_thread_local("process_frame")
        return True

    def _process_initialize(self, stream_dict, frame_data_in, new_frame):
        frame = None
        graph = None
        stream = Stream()
        header = f"Process frame <{stream.stream_id}:{stream.frame_id}>:"
        if not stream.update(stream_dict):
            self.logger.warning(f"{header} stream_dict must be a dictionary")
            return None, None

        if frame_data_in == []:
            frame_data_in = {}
        if not isinstance(frame_data_in, dict):
            self.logger.warning(f"{header} frame data must be a dictionary")
            return None, None

    # If not _WINDOWS, then always automatically create a new Stream
        stream_id = stream.stream_id
        new_stream_id = DEFAULT_STREAM_ID if _WINDOWS else stream_id
        if stream_id == new_stream_id:
            if new_stream_id not in self.stream_leases:
                status = self.create_stream(
                    new_stream_id, graph_path=stream.graph_path,
                    parameters=stream.parameters)
                if status == False:
                    return None, None

        frame_id = stream.frame_id
        header = f"Process frame <{stream_id}:{frame_id}>:"
        if stream_id not in self.stream_leases:
            self.logger.warning(f"{header} stream not found")
        else:
            stream_lease = self.stream_leases[stream_id]
            stream_lease.extend()
            stream_lease.stream.update(
                {"frame_id": frame_id, "state": stream.state})
            stream = stream_lease.stream

    # If not _WINDOWS, then always automatically create a new Frame
            if new_frame:
                if _WINDOWS and frame_id in stream.frames:
                    self.logger.warning(f"{header} new frame id already exists")
                else:
                    if stream_id not in self.DEBUG:         # DEBUG: 2024-12-02
                        self.DEBUG[stream_id] = {}
                    if "frames_lru" not in self.DEBUG[stream_id]:
                        self.DEBUG[stream_id]["frames_lru"] = LRUCache(size=8)
                    self.DEBUG[stream_id]["frames_lru"].put(frame_id,
                        {"time": local_iso_now(), "frame_id": frame_id}
                    )

                    stream.frames[frame_id] = Frame()
                    frame = stream.frames[frame_id]
                    graph = self.pipeline_graph.get_path(stream.graph_path)
    # If not _WINDOWS, then don't support "process_frame_response()"
            elif not _WINDOWS:
                return None, None
            elif frame_id in stream.frames:
                frame = stream.frames[frame_id]
                graph = self.pipeline_graph.iterate_after(
                    frame.paused_pe_name, stream.graph_path)
            else:
                self.logger.warning(f"{header} paused frame id doesn't exist")

        if frame:
            frame.swag.update(frame_data_in)  # SWAG: Stuff We All Get 😅
        return graph, stream

# TODO: Refactor metrics into "utilities/metrics.py:class Metrics" ?

    def _process_metrics_initialize(self, frame):
        metrics = frame.metrics
        if metrics == {}:
            metrics["pipeline_elements"] = {}
            metrics["time_pipeline_start"] = time.time()
        return metrics

    def _process_metrics_capture(self, metrics, element_name, start_time):
        time_element = time.time() - start_time
        metrics["pipeline_elements"][f"time_{element_name}"] = time_element

        time_pipeline = time.time() - metrics["time_pipeline_start"]
        metrics["time_pipeline"] = time_pipeline  # Total time, so far !

    def _process_map_in(self, header, element, element_name, swag):
        map_in_names = {}
        if element_name in self.definition.map_in_nodes:
            map_in_elements = self.definition.map_in_nodes[element_name]
            for in_element, in_map in map_in_elements.items():
                from_name, to_name = next(iter(in_map.items()))
                map_in_names[to_name] = f"{element_name}.{to_name}"

        inputs = {}
        input_names = [input["name"] for input in element.definition.input]

        for input_name in input_names:
            try:
                if input_name in map_in_names:
                    inputs[input_name] = swag[map_in_names[input_name]]
                else:
                    inputs[input_name] = swag[input_name]
            except KeyError as key_error:
                self._error_pipeline(header,
                    f'Function parameter "{input_name}" not found')
        return inputs

    def _process_map_out(self, element_name, frame_data_out):
        if element_name in self.definition.map_out_nodes:
            map_out_node = self.definition.map_out_nodes[element_name]
            for out_element, out_map in map_out_node.items():
                from_name, to_name = next(iter(out_map.items()))
                to_name = f"{out_element}.{to_name}"
                frame_data_out[to_name] = frame_data_out.pop(from_name)

# FIX: _create_frame_generator(): StreamEvent.ERROR -->
#          self.destroy_stream(get_stream_id(), graceful=False)  # immediately !

# TODO: Check local cases "stream_state.RUN | STOP | ERROR" ...
# TODO: - _create_frame_generator()
# TODO: - create_stream()
# TODO: - _process_frame_common()
# TODO: - destroy_stream()

# TODO: Check remote cases "stream_state.RUN | STOP | ERROR" ...
# TODO: - _create_frame_generator()
# TODO: - create_stream()
# TODO: - _process_frame_common()
# TODO: - destroy_stream()

    def _process_stream_event(self, element_name, stream_event, diagnostic,
        in_destroy_stream=False):

        def get_diagnostic(diagnostic):
            event_name = StreamEventName[stream_event]
            if "diagnostic" in diagnostic:
                diagnostic = diagnostic["diagnostic"]
            else:
                diagnostic = "No diagnostic provided"
            return f"{element_name.upper()}: {event_name} "  \
                   f"stream {self.my_id()} {diagnostic}"

        def get_stream_id():
            stream, _ = self.get_stream()
            return stream.stream_id

        stream_state = StreamState.RUN

        if stream_event == StreamEvent.DROP_FRAME:
            stream_state = StreamState.DROP_FRAME

        if stream_event == StreamEvent.STOP:
            stream_state = StreamState.STOP
            self.logger.debug(get_diagnostic(diagnostic))
            if not in_destroy_stream:  # avoid destroy_stream() recursion
                self._post_message(    # gracefully after frames processed
                    ActorTopic.IN, "destroy_stream", [get_stream_id(), True])

        elif stream_event == StreamEvent.ERROR:
            stream_state = StreamState.ERROR
            self.logger.error(get_diagnostic(diagnostic))
            if not in_destroy_stream:  # avoid destroy_stream() recursion
                self.destroy_stream(get_stream_id(), use_thread_local=False)

        return stream_state

    def set_parameter(self, stream_id, name, value):
        if stream_id is None:
            names = name.split(".")  # PipelineElementName.ParameterName
            if len(names) == 1:      # Pipeline parameter
                self.share[names[0]] = value
            else:                    # PipelineElement parameter
                try:
                    node = self.pipeline_graph.get_node(names[0])
                    node.element.share[names[1]] = value
                except KeyError:
                    pass
        elif stream_id in self.stream_leases:
            stream_lease = self.stream_leases[stream_id]
            parameters = stream_lease.stream.parameters
            parameters[name] = value

    def set_parameters(self, stream_id, parameters):
        for parameter in parameters:
            self.set_parameter(stream_id, parameter[0], parameter[1])

class PipelineRemote(PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)
        self.set_remote_absent(True)

    def create_stream(self, stream_id, graph_path=None,
        parameters=None, grace_time=_GRACE_TIME,
        queue_response=None, topic_response=None):

        if self.absent:
            self.log_error("create_stream")
        return not self.absent

    def destroy_stream(self, stream_id, graceful=False):
        if self.absent:
            self.log_error("destroy_stream")
        return not self.absent

    @classmethod
    def is_local(cls):
        return False

    def log_error(self, function_name):
        self.logger.error(f"PipelineElement.{function_name}(): "
                          f"{self.definition.name}: invoked when "
                           "remote Pipeline hasn't been discovered")

    def process_frame(self, stream, **kwargs) -> Tuple[StreamEvent, dict]:
        if self.absent:
            self.log_error("process_frame")
        return not self.absent

    def set_remote_absent(self, absent):
        self.absent = absent
        self.share["lifecycle"] = "absent" if self.absent else "ready"

# --------------------------------------------------------------------------- #

try:
    PIPELINE_DEFINITION_VERSION = 0
    PIPELINE_DEFINITION_SCHEMA = avro.schema.parse("""
{
  "namespace": "aiko_services",
  "name":      "pipeline_definition",
  "type":      "record",
  "fields": [
    { "name": "comment", "type": "string" },
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
              { "name": "comment", "type": "string" },
              { "name": "name",    "type": "string" },
              { "name": "input",   "type": {
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
                            { "name": "class_name", "type": "string" },
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
    """Create and destroy Pipelines"""
    pass

@main.command(help="Create Pipeline defined by PipelineDefinition pathname")
@click.argument("definition_pathname", nargs=1, type=str)
@click.option("--name", "-n", type=str,
    default=None, required=False,
    help="Pipeline name")
@click.option("--graph_path", "-gp", type=str,
    default=None, required=False,
    help="Pipeline Graph Path, use Head_PipelineElement_name")
@click.option("--parameters", "-p", type=click.Tuple((str, str)),
    default=None, multiple=True, required=False,
    help="Define Stream parameters")
@click.option("--stream_reset", "-r", is_flag=True,
    help="Reset the remote Stream by invoking destroy_stream() first")
@click.option("--stream_id", "-s", type=str,
    default=None, required=False,
    help='Create Stream with identifier with optional process_id "name_{}"')
@click.option("--stream_parameters", "-sp", type=click.Tuple((str, str)),
    default=None, multiple=True, required=False,
    help="Define Stream parameters")
@click.option("--grace_time", "-gt", type=int,
    default=_GRACE_TIME, required=False,
    help="Stream receive frame time-out duration")
@click.option("--show_response", "-sr", is_flag=True,
    help="Show pipeline output response (output)")
@click.option("--frame_id", "-fi", type=int,
    default=0, required=False,
    help="Process Frame with identifier")
@click.option("--frame_data", "-fd", type=str,
    default=None, required=False,
    help="Process Frame with data")
@click.option("--log_level", "-ll", type=str,
    default="INFO", required=False,
    help="error, warning, info, debug")
@click.option("--log_mqtt", "-lm", type=str,
    default="all", required=False,
    help="all, false (console), true (mqtt)")
@click.option("--windows", "-w", is_flag=True,
    help="Enable experimental distributed Streams sliding window protocol")
@click.option("--exit_message", is_flag=True,
    help="Display exit warning message")

def create(definition_pathname, graph_path, name, parameters, stream_id,
    stream_parameters,  # DEPRECATED
    frame_id, frame_data, grace_time, show_response,
    log_level, log_mqtt, stream_reset, windows, exit_message):

    global _WINDOWS
    if windows:
        _WINDOWS = True

    if stream_id:
        stream_id = stream_id.replace("{}", get_pid())  # sort-of unique id

    if stream_parameters:
        parameters = stream_parameters
        _LOGGER.warning('"--stream_parameters" replaced by "--parameters"')

    os.environ["AIKO_LOG_LEVEL"] = log_level.upper()
    os.environ["AIKO_LOG_MQTT"] = log_mqtt

    if not os.path.exists(definition_pathname):
        raise SystemExit(
            f"Error: PipelineDefinition not found: {definition_pathname}")

    pipeline_definition = PipelineImpl.parse_pipeline_definition(
        definition_pathname)

    def pipeline_response_handler(queue_pipeline_response):
        while True:
            response = queue_pipeline_response.get()
            id = f'<{response[0]["stream_id"]}:{response[0]["frame_id"]}>'
            frame_data = response[1]
            _LOGGER.info(f"Output: {id} {frame_data}")

    queue_pipeline_response = None
    if show_response:
        queue_pipeline_response = queue.Queue()
        Thread(target=pipeline_response_handler,
            args=(queue_pipeline_response,), daemon=True).start()

    pipeline = PipelineImpl.create_pipeline(
        definition_pathname, pipeline_definition,
        name, graph_path, stream_id, parameters, frame_id, frame_data,
        grace_time, queue_response=queue_pipeline_response,
        stream_reset=stream_reset)

    pipeline.run(mqtt_connection_required=False)
    if exit_message:
        _LOGGER.warning("Pipeline process exit")

@main.command(help="Destroy Pipeline")
@click.argument("name", nargs=1, type=str, required=True)

def destroy(name):
# TODO: D.R.Y: Refactor based on "storage.py" and put this in the right place !
    def actor_discovery_handler(command, service_details):
        if command == "add":
            event.remove_timer_handler(waiting_timer)
            topic_path = f"{service_details[0]}/in"
            actor = get_actor_mqtt(topic_path, Pipeline)
            actor.stop()
            print(f'Destroyed Pipeline "{name}"')
            aiko.process.terminate()

    def waiting_timer():
        event.remove_timer_handler(waiting_timer)
        print(f'Waiting to discover Pipeline "{name}"')

    actor_discovery = ActorDiscovery(aiko.process)
    service_filter = ServiceFilter("*", name, "*", "*", "*", "*")
    actor_discovery.add_handler(actor_discovery_handler, service_filter)
    event.add_timer_handler(waiting_timer, 0.5)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
