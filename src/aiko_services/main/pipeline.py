#!/usr/bin/env python3
#
# Manage Pipelines consisting of PipelineElements (Actors or Services)
#
# Usage: aiko_pipeline create
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~
# DEFINITION=pipeline_definition.json
# aiko_pipeline create  [--name $PIPELINE_NAME] $DEFINITION
# aiko_pipeline destroy $PIPELINE_NAME
#
# aiko_pipeline create $DEFINITION --log_level debug  \
#   --stream_id 1 --frame_data "(argument_name: argument_value ...)"
#
# aiko_pipeline create ../examples/pipeline/pipeline_local.json
#   --hooks all -fd "(b: 0)"                   # Create Frame, enable all Hooks
#
# Usage: aiko_pipeline destroy $PIPELINE_NAME
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Usage: aiko_pipeline list [--watch]
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Usage: aiko_pipeline update $PIPELINE_NAME
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Update is applied to an existing Pipeline with the specified Pipeline name
# Stream Response best with "-sr -s N -r"  # Else can't change topic_response
#                              ---
#   Update and create Stream and/or Frame
#   -------------------------------------
# aiko_pipeline create ../examples/pipeline/pipeline_local.json -ll debug
#
# aiko_pipeline update p_local -fd "(b: 0)"           # Create Frame
# aiko_pipeline update p_local -fd "(b: 0)" -sr       # Create Frame, Response
# aiko_pipeline update p_local -p PE_1.pe_1_inc 2 -fd "(b: 0)"  # Set parameter
# aiko_pipeline update p_local -s 1                   # Create Stream
# aiko_pipeline update p_local -s 2 -gt 3             # Create Stream grace time
# aiko_pipeline update p_local -s 3 -fd "(b: 0)"      # Create Stream and Frame
# aiko_pipeline update p_local -s 3 -fd "(b: 0)" -r   # Create Stream reset
# aiko_pipeline update p_local -s 4 -fd "(b: 0)" -sr  # Stream, Frame, Response
#
# aiko_pipeline update p_local -ll debug              # Pipeline log level
# aiko_pipeline update p_local -ll debug_all          # Also PipelineElements
#
#   Update DataSource value
#   -----------------------
# cd ../elements/media
# aiko_pipeline create pipelines/text_pipeline_0.json -ll debug
#
# aiko_pipeline update p_text_0 -s 1  \
#            -p TextReadFile.data_sources "(file://data_in/in_00.txt)"
# aiko_pipeline update p_text_0 -s 2  \
#            -p TextReadFile.data_sources "(file://data_in/in_01.txt)"
#
#   Update and use specific Graph Path
#   ----------------------------------
# aiko_pipeline create ../examples/pipeline/pipeline_paths.json -ll debug
#
# aiko_pipeline update p_paths -fd "(in_a: hello)"
# aiko_pipeline update p_paths -s 1 -fd "(in_a: hello)" -gp PE_IN_1
#
# PipelineDefinition
# ~~~~~~~~~~~~~~~~~~
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
# Low-level use of MQTT messages as remote function calls
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
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
# * BUG: "PipelineImpl.create_frame(..., graph_path=None)" doesn't use the
#     "graph_path" parameter at all !
#
# * Fix: Define Pipeline outputs explicitly, not just implicitly via PE outputs
#
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
# * Ensure all shared updates occur via "events" (handlers, messages and timers)
#   managed by the event loop and executed solely by the event loop thread.
#
# - Collect "local" and "remote" into "deployment" configuration structure
#
# - Support remote "aiko_pipeline update PIPELINE_NAME --hooks HOOKS_TYPE"
#   - Including "pipeline.remove_hook_handler()", i.e hooks="none"
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
import click
import copy
from collections import OrderedDict  # All OrderedDict operations are O(1)
from dataclasses import dataclass, asdict
import datetime
from enum import Enum
import json
import os
import psutil
import queue
import threading
from threading import Thread
import time
import traceback
from typing import Any, Dict, List, Tuple

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = [
    "Pipeline", "PipelineElement", "PipelineElementImpl",
    "PipelineElementLoop",
    "PipelineImpl",
    "PIPELINE_HOOK_PROCESS_ELEMENT", "PIPELINE_HOOK_PROCESS_ELEMENT_POST",
    "PIPELINE_HOOK_PROCESS_FRAME", "PROTOCOL_PIPELINE"
]

_VERSION = 0

ACTOR_TYPE_PIPELINE = "pipeline"
ACTOR_TYPE_ELEMENT = "pipeline_element"
PROTOCOL_PIPELINE =  f"{SERVICE_PROTOCOL_AIKO}/{ACTOR_TYPE_PIPELINE}:{_VERSION}"
PROTOCOL_ELEMENT =  f"{SERVICE_PROTOCOL_AIKO}/{ACTOR_TYPE_ELEMENT}:{_VERSION}"

PIPELINE_HOOK_PROCESS_ELEMENT = "pipeline.process_element:"
_PIPELINE_HOOK_PROCESS_ELEMENT = PIPELINE_HOOK_PROCESS_ELEMENT+"0"
PIPELINE_HOOK_PROCESS_ELEMENT_POST = "pipeline.process_element_post:"
_PIPELINE_HOOK_PROCESS_ELEMENT_POST = PIPELINE_HOOK_PROCESS_ELEMENT_POST+"0"
PIPELINE_HOOK_PROCESS_FRAME = "pipeline.process_frame:"
_PIPELINE_HOOK_PROCESS_FRAME = PIPELINE_HOOK_PROCESS_FRAME+"0"
PIPELINE_HOOK_PROCESS_FRAME_COMPLETE = "pipeline.process_frame_complete:"
_PIPELINE_HOOK_PROCESS_FRAME_COMPLETE = PIPELINE_HOOK_PROCESS_FRAME_COMPLETE+"0"
PIPELINE_HOOK_DESTROY_STREAM = "pipeline.destroy_stream:"
_PIPELINE_HOOK_DESTROY_STREAM = PIPELINE_HOOK_DESTROY_STREAM+"0"

_GRACE_TIME = 60  # seconds
_LOGGER = aiko.logger(__name__)
_METRICS_MEMORY_ENABLE = False
_STREAM_STATE_WORKING = [
    StreamState.DROP_FRAME, StreamState.NO_FRAME, StreamState.RUN
]

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
                    #   self.logger.debug(f"{diagnostic}")  # TODO: Verify
                    elif input["found"] == 0:
                        diagnostic += "previous PipelineElements"
                        try_map_in_out = True

                    if try_map_in_out:
                        map_in_nodes = pipeline_definition.map_in_nodes
                        if not self.validate_mapping(
                            map_in_nodes, element_name, input):
                            pass
                        #   self.logger.debug(f"{diagnostic}")  # TODO: Verify
            for successor_name in node.successors:
                successor = self.get_node(successor_name)
                successor.predecessors[element_name] = node

# --------------------------------------------------------------------------- #
# PipelineElement: service_level_agreement: low_latency, etc

class PipelineElement(Actor):
    Interface.default("PipelineElement",
        "aiko_services.main.pipeline.PipelineElementImpl")

    @abstractmethod
    def create_frame(self, stream, frame_data, frame_id=None, graph_path=None):
        pass

    @abstractmethod
    def create_frames(
        self, stream, frame_generator, frame_id=FIRST_FRAME_ID, rate=None):
        pass

    @abstractmethod
    def get_parameter(self, name,
        default=None, required=False, use_pipeline=True):
        pass

    @abstractmethod
    def get_stream(self):
        pass

    @abstractmethod
    def get_variables(self):
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
        context.call_init(self, "Actor", context)

    #  "log_level" parameter overrides "AIKO_LOG_LEVEL" environment variable
        log_level, found = self.get_parameter(
            "log_level", self_share_priority=False)
        if found:
            self.logger.setLevel(log_level_real(log_level))

        self.share["source_file"] = f"v{_VERSION}⇒ {__file__}"
        self.share.update(self.definition.parameters)
    # TODO: Fix Aiko Dashboard / EC_Producer incorrectly updates this approach
    #   self.share["parameters"] = self.definition.parameters  # TODO

    def create_frame(self, stream, frame_data, frame_id=None, graph_path=None):
        if stream.stream_id not in self.pipeline.DEBUG:     # DEBUG: 2024-12-02
            self.pipeline.DEBUG[stream.stream_id] = {}
        self.pipeline.DEBUG[stream.stream_id]["create_frame"] = {
            "time": local_iso_now(), "latest_frame_id": frame_id}

        frame_id = frame_id if frame_id else stream.frame_id
        graph_path = graph_path if graph_path else stream.graph_path
        stream_copy = Stream(
            stream_id=stream.stream_id,
            frame_id=frame_id,
            graph_path=graph_path,
            parameters=stream.parameters,
            queue_response=stream.queue_response,
            state=stream.state,
            topic_response=stream.topic_response)
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
                "_create_frames_generator()", stream.stream_id, frame_id)
            stream, frame_id = self.get_stream()

            mailbox_name = f"{self.pipeline.name}/1/in"
            mailbox_queue = None
            period_counter = 0
            start_time = time.monotonic()

            while stream.state == StreamState.RUN:
            # TODO: 2024-12-11: Throttle "frame_generator" when "rate" is None
            # TODO: Create "event.py:get_mailbox_queue()", "size" and "throttle"
                if not rate or rate == 0:
                    if mailbox_queue:
                        if mailbox_queue.qsize() >= 32:
                            time.sleep(0.02)  # 50 Hz check
                            continue
            # TODO: Find cases when Pipeline "in" mailbox doesn't exist yet
                    elif mailbox_name in event.mailboxes:
                        mailbox_queue = event.mailboxes[mailbox_name].queue

                stream.lock.acquire("_create_frames_generator()")
                try:
                    stream_event, frame_data = frame_generator(stream, frame_id)
                except Exception as exception:
                    self.logger.error(
                        "Exception in pipeline_element._create_frames() --> "  \
                        "frame_generator()")
                    stream_event = StreamEvent.ERROR
                    frame_data = {"diagnostic": traceback.format_exc()}

                stream.set_state(self.pipeline._process_stream_event(
                    self.name, stream, stream_event, frame_data))
                if stream.state == StreamState.ERROR:
                    break

                if stream.state == StreamState.RUN and frame_data:
                    graph_path, _ = self.get_parameter("_graph_path_", None)
                    if isinstance(frame_data, dict):
                        frame_data = [frame_data]
                    if isinstance(frame_data, list):
                        for a_frame_data in frame_data:
                            self.create_frame(
                                stream, a_frame_data, frame_id, graph_path)
                            frame_id += 1
                            self.pipeline.thread_local.frame_id = frame_id
                    else:
                        self.logger.warning(
                            "Frame generator must return either "
                            "{frame_data} or [{frame_data}]")

                if stream.state in _STREAM_STATE_WORKING:
                    stream.set_state(StreamState.RUN)
                stream.lock.release()

                if rate and stream.state == StreamState.RUN:
                # TODO: When "rate" parameter updates, then fix "period_time"
                    period_counter += 1
                    period_time = period_counter * (1.0 / rate)
                    duration = period_time + start_time - time.monotonic()
                    if duration > 0:
                        time.sleep(duration)
                elif stream_event == StreamEvent.NO_FRAME:
                    time.sleep(0.02)  # Avoid frame_generator() busy CPU loop
        except Exception as exception:
            self.logger.error("PipelineImpl._create_frames_generator(): "  \
                             f"{traceback.format_exc()}")
        finally:
            self.pipeline._disable_thread_local("_create_frames_generator()")

    # TODO: During process_frame(), stream parameters should be updated
    #       in self.share[], just like PipelineDefinition parameters.
    #       Note: Consider the performance implications when doing this !

    def get_parameter(self, name,
        default=None, required=False, use_pipeline=True,
        self_share_priority=True):

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

        if required and not found:
            raise KeyError(f'Must provide "{name}" parameter')
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

    def get_variables(self, stream):
        return self.pipeline.definition.parameters |  \
               self.pipeline.share                 |  \
               self.definition.parameters          |  \
               self.share                          |  \
               self._get_stream_parameters()       |  \
               stream.frames[stream.frame_id].swag

    def my_id(self, all=False):
        name = self.name if all else ""
        stream, frame_id = self.get_stream()
        return f"{name}<{stream.stream_id}:{frame_id}>"

    def start_stream(self, stream, stream_id):
        return StreamEvent.OKAY, None

    def stop_stream(self, stream, stream_id):
        return StreamEvent.OKAY, None

# --------------------------------------------------------------------------- #

class PipelineElementLoop(PipelineElement):
    Interface.default("PipelineElementLoop",
        "aiko_services.main.pipeline.PipelineElementImpl")

# --------------------------------------------------------------------------- #

class Pipeline(PipelineElement):
    Interface.default("Pipeline", "aiko_services.main.pipeline.PipelineImpl")

    @abstractmethod
    def create_stream(self, stream_id, graph_path=None,
        parameters=None, grace_time=_GRACE_TIME,
        queue_response=None, topic_response=None):
        pass

    @abstractmethod
    def destroy_stream(self, stream_id, graceful=False, use_thread_local=True, diagnostic={}, with_lock=False):
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

        self.pipeline_graph = None
        self.actor = context.get_implementation("Actor")    # _WINDOWS
        context.call_init(self, "PipelineElement", context)
        self.logger.info(f"MQTT topic: {self.topic_in}")

        self.share["definition_pathname"] = context.definition_pathname
        self.share["lifecycle"] = "waiting"
        self.share["graph_path"] = context.graph_path
        self.remote_pipelines = {}  # Service name --> PipelineRemote instance

        self.stream_leases = {}
        self.thread_local = threading.local()  # See _enable_thread_local()

    # TODO: Duplicated in PipelineElementImpl.__init__() remove ?
    #  "log_level" parameter overrides "AIKO_LOG_LEVEL" environment variable
        log_level, found = self.get_parameter(
            "log_level", self_share_priority=False)
        if found:
            self.logger.setLevel(log_level_real(log_level))

        self.add_hook(_PIPELINE_HOOK_PROCESS_ELEMENT)
        self.add_hook(_PIPELINE_HOOK_PROCESS_ELEMENT_POST)
        self.add_hook(_PIPELINE_HOOK_PROCESS_FRAME)
        self.add_hook(_PIPELINE_HOOK_PROCESS_FRAME_COMPLETE)
        self.add_hook(_PIPELINE_HOOK_DESTROY_STREAM)

        self.pipeline_graph = self._create_pipeline_graph(context.definition)
        self.share["element_count"] = self.pipeline_graph.element_count
        self.share["streams"] = 0
        self.share["streams_frames"] = 0

        global _WINDOWS
        _WINDOWS, _ = self.get_parameter("sliding_windows", _WINDOWS)
        self.share["sliding_windows"] = _WINDOWS

        self._update_lifecycle_state()

    # TODO: Better visualization of the Pipeline / PipelineElements details
        if False:
            self.logger.info(f"Pipeline graph path ...")
            graph_path = self.pipeline_graph.get_path(self.share["graph_path"])
            for node in graph_path:
                self.logger.info(f"    PipelineElement: {node.name}")

        event.add_timer_handler(self._status_update_timer, 3.0)

    def ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            if log_level_all(item_value):               # update all elements ?
                log_level = log_level_real(item_value)  # clean-up log_level :)
                if self.pipeline_graph:
                    for node in self.pipeline_graph:
                        element, _, _, _ = PipelineGraph.get_element(node)
                        element.ec_producer.update(item_name, log_level)

        self.actor.ec_producer_change_handler(
            self, command, item_name, item_value)

        if item_name == "sliding_windows":
            try:
                global _WINDOWS
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

        definition.edge_definitions[node_name] = properties

# Pipeline current "stream" and "frame_id" are thread-local variables
# Valid for create_stream(), process_frame() and destroy_stream() on main thread
# Valid for PipelineElement._create_frames_generator() thread
#
# Always use ...
#     try:
#         self._enable_thread_local("function_name()", stream_id, frame_id)
#         stream, frame_id = self.get_stream()
#     finally:
#         self._disable_thread_local("function_name()")

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

    def create_frame(self, stream, frame_data, frame_id=None, graph_path=None):
        if isinstance(stream, Stream):
            stream = stream.as_dict()
        self._post_message(
            ActorTopic.IN, "process_frame", [stream, frame_data])

    @classmethod
    def create_pipeline(cls, definition_pathname, pipeline_definition,
        name, graph_path, stream_id, parameters, frame_id, frame_data,
        grace_time, queue_response=None,
        log_level=None, stream_reset=False, hooks="none", windows=False):

        global _WINDOWS
        _WINDOWS = windows

        name = name if name else pipeline_definition.name

        init_args = pipeline_args(name,
            protocol=PROTOCOL_PIPELINE,
            definition=pipeline_definition,
            definition_pathname=definition_pathname,
            graph_path=graph_path
        )
        pipeline = compose_instance(PipelineImpl, init_args)

        PipelineImpl.update_pipeline(pipeline, graph_path, stream_id,
            parameters, frame_id, frame_data, grace_time,
            queue_response, None, log_level, stream_reset, hooks)

        return pipeline

    def _create_pipeline_graph(self, definition):
        header = f"Error: Creating Pipeline: {definition.name}"

        if len(definition.elements) == 0:
            self._error_pipeline(header,
                "PipelineDefinition: Doesn't define any PipelineElements")

        definition.map_in_nodes = {}
        definition.map_out_nodes = {}
        definition.edge_definitions = {}
        node_heads, node_successors = Graph.traverse(
            definition.graph, self._add_node_properties)
        pipeline_graph = PipelineGraph(node_heads)
    #   self.parameters = definition.parameters  # TODO: Use it or lose it !

        for pipeline_element_definition in definition.elements:
            element_instance = None
            element_name = pipeline_element_definition.name
            if element_name not in node_successors:
                self.logger.warning(f'Skipping PipelineElement {element_name}: '
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

                service_filter = ServiceFilter.with_topic_path(
                    **deploy_definition.service_filter)

                do_discovery(PipelineElement, service_filter,
                    lambda service_details, service:
                        self._change_remote_element_handler(
                            True, service_details),
                    lambda service_details:
                        self._change_remote_element_handler(
                            False, service_details))

            element = Node(
                element_name, element_instance, node_successors[element_name])
            pipeline_graph.add_element(element)

        pipeline_graph.validate(definition, self.share["graph_path"])
        return pipeline_graph

    def _change_remote_element_handler(self, discovered, service_details):
        topic_path = f"{service_details[0]}/in"
        service_name = service_details[1]
        element_name, element_instance, element_topic_path =  \
            self.remote_pipelines[service_name]
        node = self.pipeline_graph.get_node(element_name)
        element_definition = node.element.definition
        topic_path_match = False

        if discovered:  # use discovered remote proxy
            topic_path_match = True
            element_instance.set_remote_absent(False)
            new_element_instance = get_service_proxy(
                topic_path, PipelineRemote)
            new_element_instance.definition = element_definition

        else:           # use original PipelineRemote instance
            if topic_path == element_topic_path:
                topic_path_match = True
                topic_path = None
                element_instance.set_remote_absent(True)
                new_element_instance = element_instance

        if topic_path_match:
            self.logger.debug(f"PipelineElement remote {element_name}: "
                f"{'add' if discovered else 'remove'}: {service_details[0:2]}")
            self.remote_pipelines[service_name] = (
                element_name, element_instance, topic_path)
            node._element = new_element_instance
            self._update_lifecycle_state()

# TODO: Consider refactoring Stream into "stream.py" ?

    def create_stream(self, stream_id, graph_path=None,
        parameters=None, grace_time=_GRACE_TIME,
        queue_response=None, topic_response=None):

        if queue_response and topic_response:
            self.logger.error(
                "Create stream: use either queue_response or topic_response")
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

        self.logger.debug(f"Create stream: <{stream_id}>")
        grace_time = parse_number(grace_time, _GRACE_TIME)
        stream_lease = Lease(grace_time, stream_id,
            lease_expired_handler=self.destroy_stream)
        stream_lease.stream = Stream(
            stream_id=stream_id,
            graph_path=graph_path,
            parameters=parameters if parameters else {},
            queue_response=queue_response,
            topic_response=topic_response)
        self.stream_leases[stream_id] = stream_lease

        try:
            self._enable_thread_local("create_stream()", stream_id)
            stream, _ = self.get_stream()
            stream.lock.acquire("create_stream()")

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

                    stream.set_state(self._process_stream_event(
                        element_name, stream, stream_event, diagnostic))
                    if stream.state == StreamState.ERROR:
                        break
                else:  ## Remote element ##
                    # TODO: Consider using "topic_response=self.topic_control"
                    if _WINDOWS:
                        element.create_stream(
                            stream_id, Graph.path_remote(stream.graph_path),
                            parameters, grace_time, None, self.topic_in)
        finally:
            if stream.lock.in_use():
                stream.lock.release()
            self._disable_thread_local("create_stream()")
        return True

    def destroy_stream(self, stream_id,
                       graceful=False,
                       use_thread_local=True,
                       diagnostic={},
                       with_lock=False):
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
                self._enable_thread_local("destroy_stream()", stream_id)
            stream, _ = self.get_stream()
            if not with_lock:
                stream.lock.acquire("destroy_stream()")

            if graceful and len(stream.frames):
                arguments = [stream_id, graceful, use_thread_local, diagnostic]
                self._post_message(
                    ActorTopic.IN, "destroy_stream", arguments, delay=3.0)
                return False

            self.logger.debug(f"Destroy stream: <{stream_id}>")

            if stream_id in self.DEBUG:                     # DEBUG: 2024-12-02
                del self.DEBUG[stream_id]

            destroy_stream_state = stream.state

            graph_path = self.pipeline_graph.get_path(self.share["graph_path"])
            for node in graph_path:
                element, element_name, local, _ =  \
                    PipelineGraph.get_element(node)
                if local:  ## Local element ##
                    try:
                        stream_event, stop_stream_data = element.stop_stream(
                            stream, stream_id)
                        if stream_event == StreamEvent.ERROR:
                            diagnostic = stop_stream_data
                    except Exception as exception:
                        self.logger.error("Exception in "  \
                          "pipeline.destroy_stream() --> stop_stream()")
                        stream_event = StreamEvent.ERROR
                        diagnostic = {"diagnostic": traceback.format_exc()}

                    stream.set_state(self._process_stream_event(
                        element_name, stream, stream_event, diagnostic,
                        in_destroy_stream=True))
                    if stream.state == StreamState.ERROR:
                        destroy_stream_state = StreamState.ERROR
                    elif destroy_stream_state == StreamState.ERROR:
                        stream.state = StreamState.ERROR

            # Notify listeners that the stream has stopped
            if stream.state >= StreamState.RUN:
                stream.state = StreamState.STOP
            self.run_hook(_PIPELINE_HOOK_DESTROY_STREAM,
                lambda: {"stream": stream,
                         "diagnostic": diagnostic})
            stream_info = {
                "stream_id": stream.stream_id,
                "frame_id": stream.frame_id,
                "state": stream.state}
            if stream.queue_response:
                stream.queue_response.put((stream_info, diagnostic))
            if stream.topic_response:
                actor = get_actor_mqtt(stream.topic_response, Pipeline)
                actor.process_frame_response(stream_info, diagnostic)
        finally:
            stream.lock.release()
            if use_thread_local:
                self._disable_thread_local("destroy_stream()")

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
            PipelineDefinitionSchema.validate(pipeline_definition_dict)
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

        if pipeline_definition.version != PipelineDefinitionSchema.version:
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
        self.run_hook(_PIPELINE_HOOK_PROCESS_FRAME, lambda: {
            "graph": graph, "stream": stream,
            "frame_data_in": frame_data_in, "new_frame": new_frame})
        if graph is None:
            return False

        try:
            self._enable_thread_local("process_frame()", stream.stream_id)
            stream, _ = self.get_stream()
            stream.lock.acquire("process_frame()")
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

            graph_node_list = list(graph)
            while len(graph_node_list):
                node = graph_node_list.pop(0)

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
                        self._process_metrics_start(metrics)
                        self.run_hook(_PIPELINE_HOOK_PROCESS_ELEMENT, lambda: {
                            "element_name": element_name,
                            "element": element,
                            "stream": stream,
                            "inputs": inputs})
                        try:
                            stream_event, frame_data_out =  \
                                element.process_frame(stream, **inputs)

                            if isinstance(element, PipelineElementLoop):
                                if stream_event is not StreamEvent.LOOP_END:
                                    stream.variables["loop_node"] = node
                                    stream.variables["loop_graph"] =  \
                                        graph_node_list.copy()
                                else:
                                    loop_boundary = stream.variables.get("loop_boundary", None)
                                    if loop_boundary:
                                        loop_end_name = loop_boundary.split(":")[0]
                                        graph_node_list = list(
                                            self.pipeline_graph.iterate_after(loop_end_name, stream.graph_path))
                        except Exception as exception:
                            self.logger.error(
                                "Exception in pipeline.process_frame() --> "  \
                                "frame_generator()")
                            stream_event = StreamEvent.ERROR
                            frame_data_out = {
                                "diagnostic": traceback.format_exc()}

                        self.run_hook(_PIPELINE_HOOK_PROCESS_ELEMENT_POST,
                            lambda: {
                                "element_name": element_name,
                                "element": element,
                                "stream": stream, "stream_event": stream_event,
                                "frame_data_out": frame_data_out})
                        stream.set_state(self._process_stream_event(
                            element_name, stream, stream_event,
                            frame_data_out))
                        if stream.state == StreamState.ERROR:
                            break
                    #   TODO: Test "stream.state" before continuing
                        self._process_map_out(element, element_name, frame_data_out)
                        self._process_metrics_capture(  # TODO: Move up ?
                            metrics, element.name)
                        frame.swag.update(frame_data_out)
                    else:  ## Remote element ##
                        if self.share["lifecycle"] != "ready":
                            diagnostic = {
                                "diagnostic": "process_frame() invoked when "
                                     "remote Pipeline hasn't been discovered"
                            }
                            stream.set_state(self._process_stream_event(
                                element_name, stream, StreamEvent.ERROR,
                                diagnostic))
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

                loop_node = stream.variables.get("loop_node", None)
                if loop_node:
                    loop_boundary = stream.variables.get("loop_boundary", None)
                    if loop_boundary:
                        loop_end_name = loop_boundary.split(":")[0].lower()
                        if element.name == loop_end_name:
                            loop_graph = stream.variables.get("loop_graph")
                            loop_graph.insert(0, loop_node)
                            graph_node_list = loop_graph

            if frame_complete:
                stream_info = {
                    "stream_id": stream.stream_id,
                    "frame_id": stream.frame_id,
                    "state": stream.state}
                self.run_hook(_PIPELINE_HOOK_PROCESS_FRAME_COMPLETE,
                    lambda: {
                        "stream": stream,
                        "frame_data_out": frame_data_out})
                if stream.queue_response:
                    stream.queue_response.put((stream_info, frame_data_out))
                elif stream.topic_response:
                    actor = get_service_proxy(stream.topic_response, Pipeline)
                    actor.process_frame_response(stream_info, frame_data_out)
                else:
                    try:
                        payload = generate(
                            "process_frame", (stream_info, frame_data_out))
                        aiko.message.publish(self.topic_out, payload)
                    except Exception as exception:
                        diagnostic = "Couldn't generate() \"frame_data\" output"
                        self._error_pipeline(
                            header, f"{diagnostic}\n{traceback.format_exc()}")

        finally:
        # If not _WINDOWS, then always remove the cached Stream Frame
            if not _WINDOWS and stream.frame_id in stream.frames:
                del stream.frames[stream.frame_id]
            if frame_complete and stream.frame_id in stream.frames:
                del stream.frames[stream.frame_id]
            if stream.lock.in_use():
                stream.lock.release()
            self._disable_thread_local("process_frame()")
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
                self.logger.warning(f"_process_initialize called for non-existent stream {stream_id}")
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
                    graph_path = stream.graph_path
                    if "graph_path" in stream_dict:  # create_frame() overrides
                        graph_path = stream_dict["graph_path"]
                    graph = self.pipeline_graph.get_path(graph_path)
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

# For each frame
    def _process_metrics_initialize(self, frame):
        metrics = frame.metrics
        if metrics == {}:
            metrics["frame"] = {}  # frame start metrics
            metrics["elements"] = {}
            metrics["pipeline_start_time"] = time.monotonic()
            if _METRICS_MEMORY_ENABLE:
                memory_rss = psutil.Process().memory_info().rss
                metrics["pipeline_start_memory"] = memory_rss
        return metrics

# For each PipelineElement
    def _process_metrics_start(self, metrics):
        metrics["start"] = {}  # PipelineElement start metrics
        metrics["start"]["time"] = time.monotonic()
        if _METRICS_MEMORY_ENABLE:
            memory_rss = psutil.Process().memory_info().rss
            metrics["start"]["memory"] = memory_rss

# For each PipelineElement
    def _process_metrics_capture(self, metrics, element_name):
        time_element = time.monotonic() - metrics["start"]["time"]
        metrics["elements"][f"{element_name}_time"] = time_element
        pipeline_time = time.monotonic() - metrics["pipeline_start_time"]
        metrics["pipeline_time"] = pipeline_time  # Total so far !
        if _METRICS_MEMORY_ENABLE:
            memory_rss = psutil.Process().memory_info().rss
            memory_element =  memory_rss - metrics["start"]["memory"]
            metrics["elements"][f"{element_name}_memory"] = memory_element
            pipeline_memory = memory_rss - metrics["pipeline_start_memory"]
            metrics["pipeline_memory"] = pipeline_memory  # Total so far !

    def _process_map_in(self, header, element, element_name, swag):
        #map_in_names = {}
        #if element_name in self.definition.map_in_nodes:
        #    map_in_elements = self.definition.map_in_nodes[element_name]
        #    for in_element, in_map in map_in_elements.items():
        #        from_name, to_name = next(iter(in_map.items()))
        #        map_in_names[to_name] = f"{element_name}.{to_name}"
        #print(f"map_in_names: {map_in_names}")

        #inputs = {}
        #input_names = [input["name"] for input in element.definition.input]

        #for input_name in input_names:
        #    try:
        #        if input_name in map_in_names:
        #            inputs[input_name] = swag[map_in_names[input_name]]
        #        else:
        #            inputs[input_name] = swag[input_name]
        #    except KeyError as key_error:
        #        self._error_pipeline(header,
        #            f'Function parameter "{input_name}" not found')

        inputs = {}
        for input in element.definition.input:
            if input["name"] in swag:
                inputs[input["name"]] = swag[input["name"]]

        edge_definitions = self.definition.edge_definitions.get(element_name, {})
        for predecessor_output, input_name in edge_definitions.items():
            if predecessor_output in swag:
                inputs[input_name] = swag[predecessor_output]

        return inputs

    def _process_map_out(self, element, element_name, frame_data_out):
        for output in element.definition.output:
            output_name = output["name"]
            qualified_output_name = f"{element_name}.{output_name}"
            if output_name in frame_data_out:
                frame_data_out[qualified_output_name] = frame_data_out[output_name]
        #if element_name in self.definition.map_out_nodes:
        #    map_out_node = self.definition.map_out_nodes[element_name]
        #    for out_element, out_map in map_out_node.items():
        #        from_name, to_name = next(iter(out_map.items()))
        #        to_name = f"{out_element}.{to_name}"
        #        frame_data_out[to_name] = frame_data_out.pop(from_name)

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

    def _process_stream_event(self,
        element_name, stream, stream_event, diagnostic,
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

        if stream_event == StreamEvent.NO_FRAME:
            stream_state = StreamState.NO_FRAME

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
                #if stream.lock._in_use:
                #    stream.lock.release()
                stream.state = StreamState.ERROR
                self.destroy_stream(get_stream_id(), use_thread_local=False, diagnostic=diagnostic, with_lock=stream.lock._in_use)

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

    @classmethod
    def update_pipeline(cls, pipeline, graph_path, stream_id,
        parameters, frame_id, frame_data, grace_time,
        queue_response=None, topic_response=None,
        log_level=None, stream_reset=False, hooks="none"):

    # TODO: Support update of remote "pipeline", issue with named arguments ?
    # TODO: Support "pipeline.remove_hook_handler()", i.e hooks="none"
        hooks = hooks.split(",")
        if any(hook in ["all", "am"] for hook in hooks):
            pipeline.add_hook_handler(ACTOR_HOOK_MESSAGE_CALL+"0",
                DEFAULT_HOOK, {"show": ["topic", "message"]})
        if any(hook in ["all", "pe"] for hook in hooks):
            pipeline.add_hook_handler(_PIPELINE_HOOK_PROCESS_ELEMENT,
                DEFAULT_HOOK, {"show": ["element_name"]})
        if any(hook in ["all", "pep"] for hook in hooks):
            pipeline.add_hook_handler(_PIPELINE_HOOK_PROCESS_ELEMENT_POST,
                DEFAULT_HOOK, {"show": ["element_name"]})
        if any(hook in ["all", "pf"] for hook in hooks):
            pipeline.add_hook_handler(_PIPELINE_HOOK_PROCESS_FRAME,
                DEFAULT_HOOK, {"show": ["stream.stream_id", "frame_data_in"]})

        if log_level:
            pipeline.set_log_level(log_level)

        stream_dict = {"frame_id": int(frame_id), "parameters": {}}

        if stream_id is not None:
            stream_dict["stream_id"] = stream_id
            if stream_reset:
                pipeline.destroy_stream(stream_id)

            pipeline.create_stream(stream_id, graph_path,
                dict(parameters), grace_time, queue_response, topic_response)
        else:
            pipeline.set_parameters(None, parameters)

        if frame_data is not None:
            function_name, arguments = parse(f"(process_frame {frame_data})")
            if len(arguments):
                if queue_response:
                    stream_dict["queue_response"] = queue_response
                if topic_response:
                    stream_dict["topic_response"] = topic_response
                pipeline.create_frame(stream_dict, arguments[0])
            else:
                raise SystemExit(
                    f"Error: Frame data must be provided")

class PipelineRemote(PipelineElement):
    def __init__(self, context):
        context.call_init(self, "PipelineElement", context)
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
# Deliberately define schema in-line, rather than in a separate file

PIPELINE_DEFINITION_SCHEMA = """
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
"""

class PipelineDefinitionSchema:
    avro_schema = None
    version = 0

    def validate(pipeline_definition_dict):
        if not PipelineDefinitionSchema.avro_schema:
            try:
                PipelineDefinitionSchema.avro_schema = avro.schema.parse(
                    PIPELINE_DEFINITION_SCHEMA)
            except avro.errors.SchemaParseException as schema_parse_exception:
                PipelineImpl._exit(
                    "Error: Parsing aiko_services/pipeline.py: "
                    "PipelineDefinitionSchema",
                    schema_parse_exception)

        return PipelineDefinitionSchema.avro_schema.validate(
                    pipeline_definition_dict)

# --------------------------------------------------------------------------- #

@click.group()

def main():
    """Create, list, update and destroy Pipelines"""
    pass

def do_show_response(topic_response=None):  # default is to use a queue_response
    queue_response = None

    def show_response(stream_dict, frame_data):
        id = f'<{stream_dict["stream_id"]}:{stream_dict["frame_id"]}>'
        _LOGGER.info(f"Output: {id} {frame_data}")

    def queue_response_handler(queue_response):
        while True:
            response = queue_response.get()
            show_response(response[0], response[1])

    def topic_response_handler(_aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        if command == "process_frame_response":
            show_response(parameters[0], parameters[1])
            aiko.process.terminate()

    if topic_response:
        aiko.process.add_message_handler(topic_response_handler, topic_response)
    else:
        queue_response = queue.Queue()
        Thread(target=queue_response_handler,
                 args=(queue_response,), daemon=True).start()

    return queue_response

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
    help="Define parameters")
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
    default=None, required=False,
    help='error, warning, info, debug plus "_all"')
@click.option("--log_mqtt", "-lm", type=str,
    default="all", required=False,
    help="all, false (console), true (mqtt)")
@click.option("--hooks", "-h", type=str,
    default="none", required=False,
    help="Some combination of am,pe,pep,pf,all,none")
@click.option("--windows", "-w", is_flag=True,
    help="Enable experimental distributed Streams sliding window protocol")
@click.option("--exit_message", is_flag=True,
    help="Display exit warning message")

def create(definition_pathname, graph_path, name, parameters, stream_id,
    stream_parameters,  # DEPRECATED
    frame_id, frame_data, grace_time, show_response,
    log_level, log_mqtt, stream_reset, hooks, windows, exit_message):

    if stream_id:
        stream_id = stream_id.replace("{}", get_pid())  # sort-of unique id

    if stream_parameters:
        parameters = stream_parameters
        _LOGGER.warning('"--stream_parameters" replaced by "--parameters"')

    os.environ["AIKO_LOG_MQTT"] = log_mqtt

    if not os.path.exists(definition_pathname):
        raise SystemExit(
            f"Error: PipelineDefinition not found: {definition_pathname}")

    pipeline_definition = PipelineImpl.parse_pipeline_definition(
        definition_pathname)

    queue_pipeline_response = do_show_response() if show_response else None

    pipeline = PipelineImpl.create_pipeline(
        definition_pathname, pipeline_definition,
        name, graph_path, stream_id, parameters, frame_id, frame_data,
        grace_time, queue_response=queue_pipeline_response,
        log_level=log_level, stream_reset=stream_reset, hooks=hooks,
        windows=windows)

    pipeline.run(mqtt_connection_required=False)
    if exit_message:
        _LOGGER.warning("Pipeline process exit")

@main.command(help="Destroy running Pipeline")
@click.argument("name", nargs=1, type=str, required=True)

def destroy(name):
    do_command(Pipeline, ServiceFilter("*", name, "*", "*", "*", "*"),
        lambda pipeline: pipeline.stop(), terminate=True)
    aiko.process.run()
    _LOGGER.info(f'Destroyed Pipeline "{name}"')

@main.command(name="list", help="List running Pipelines")
@click.option("--watch", "-w", is_flag=True,
    help="Show on-going Pipeline create and destroy actions")

def list_command(watch):  # Don't overwrite the Python "list" class
    service_filter = ServiceFilter("*", "*", PROTOCOL_PIPELINE, "*", "*", "*")

    def show_service(command, service_details):
        topic_path = service_details[0]
        name = service_details[1]
    #   protocol = service_details[2][service_details[2].rfind("/") + 1:]
    #   transport = service_details[3]
        owner = service_details[4]
    #   tags = service_details[5]
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"{now} {command:6s} {topic_path} {name} {owner}")

    def service_discovery_handler(command, service_details):
        if not watch and command == "sync":
            services = services_cache.get_services()
            services = services.filter_services(service_filter)
            for service_details in services:
                show_service("add", service_details)
            aiko.process.terminate()

        if watch and command != "sync":
            show_service(command, service_details)

    services_cache = services_cache_create_singleton(aiko.process, True, 0)
    services_cache.add_handler(service_discovery_handler, service_filter)

@main.command(help="Update Pipeline: Manage Streams and create Frames")
@click.argument("name", nargs=1, type=str, required=True)
@click.option("--graph_path", "-gp", type=str,
    default=None, required=False,
    help="Pipeline Graph Path, use Head_PipelineElement_name")
@click.option("--parameters", "-p", type=click.Tuple((str, str)),
    default=None, multiple=True, required=False,
    help="Update parameters")
@click.option("--protocol", "-pr", type=str,
    default=PROTOCOL_PIPELINE, required=False,
    help="Discovery protocol, default: pipeline:0")
@click.option("--stream_reset", "-r", is_flag=True,
    help="Reset the remote Stream by invoking destroy_stream() first")
@click.option("--stream_id", "-s", type=str,
    default=None, required=False,
    help="Update Stream with identifier")
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
    default=None, required=False,
    help='error, warning, info, debug plus "_all"')
# TODO: Add "hooks"
# @click.option("--hooks", "-h", type=str,
#   default="none", required=False,
#   help="Some combination of am,pe,pep,pf,all,none")

def update(name, graph_path, parameters, protocol, stream_id,  # TODO: Add hooks
    frame_id, frame_data, grace_time, show_response, log_level, stream_reset):

    if "/" not in protocol:
        protocol = f"{SERVICE_PROTOCOL_AIKO}/{protocol}"

    topic_response = None
    if show_response:        # TODO: Replace "do_command()" with "do_request()"
        topic_response = aiko.topic_in
        do_show_response(topic_response)  # support remote Pipeline response

    def update_command(pipeline):
        PipelineImpl.update_pipeline(pipeline, graph_path, stream_id,
            parameters, frame_id, frame_data, grace_time,
            None, topic_response, log_level, stream_reset, "none")

    do_command(Pipeline,
        ServiceFilter("*", name, protocol, "*", "*", "*"),
        lambda pipeline: update_command(pipeline), terminate=not show_response)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
