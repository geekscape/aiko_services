#!/usr/bin/env python3
#
# Goals
# ~~~~~
# - Human friendly PipelineDefinition (persistent form)
#   - Consider Jono's define graph by PipelineElement input needs ?
# - Simple Pipeline use-cases
#   - PipelineElements either all in-process or all distributed
# * HighLighter Live RTSP / WebRTC Pipeline (current functionality)
#   * Streaming Pipeline connected to long running ML Pipeline(s)
# * Wrap existing ML Pipeline as new PipelineElement
#   * Run existing production ML Pipeline, e.g EQ, AIMS, Medechat
# * WPS ML Model
# - Josh's ML Training Pipeline (click-to-train)
#   - Lizze's "video sampling" requirements
#
# To Do
# ~~~~~
# - Refactor "Tuple[bool, FrameOutput]" as new data type
#
# - Review "pipeline_2020.py" and "stream.py" to extract the good bits !
#   - Use of "stream.py"
#   - PipelineElement module loading
# * PipelineElements as Services (optional if all PEs in single process)
#   * Within a single processes
#     - Later on, deal with thread-safety, especially with Aiko Services
#   * Across processes using LCM / LCC with Transport MQTT and Ray ?
#     - Pluggable payload format: S-Expressions and/or JSON
#   - Use of Apache Plasma and Lens
# * Provide statistics, e.g time per PipelineElement, messages per second
#   - Scripted load test
# * Drive frames through Pipeline, e.g message queue (data source, flatout ?)
#   - Entities as DataSources and DataTargets
# * "event.py" from older message queue and only use mailboxes
# * Update Parameters on-the-fly ... using ECProducer ?
# - Extended State: Service (ready), Actor (busy), LCM / LCC, Pipeline, ...
#   - StateMachine ?
# - Pipelines as a PipelineElement within a parent Pipeline
#   - With Pipeline, either all in single process or all distributed
#   - Pipeline tree with combination of single process and distributed
# * Fix "component.py" instantiate specified implementation
# - Strong typing: Incorporate ServiceProtocol and Interfaces
# - Consider whether NetworkX should be replaced by specific design
#
# - Similar design approach to AuthenticationManager, StorageManager, etc
#   - Core Service / Actor, Interface do_command()/do_request, CLI/TUI/GUI
# - Similar design approach to StreamTrain, etc
#   - Use of EAVTs, streams and HL Web UI hints (layout and widgets)
#
# Plan 2022-10-04
# ~~~~~~~~~~~~~~~
# - Spike new Pipeline (Actor) with in-process PipelineElements (Actors)
#
# - Spike HL Live Streaming Pipeline --> Long running ML Pipeline
#   - Assume ML Pipeline already started (may change later)
#   - Now, StreamSessionManager uses Tasks (via TaskManager) --> ML Pipeline
#     - Migrate to new Pipeline implementation of ML Pipeline accepting Frames
#     - DataSource: TaskManager (Task --> Frame) --> ML Pipeline
#     - DataSource: VideoFileSource (Frames) --> ML Pipeline
#       - Will be set-up via a Task
#     - DataSource: VideoRTSPSource (Frames) --> ML Pipeline
#       - Will be set-up via a Task
#     - DataSource: VideoWebRTCSource (Frames) --> ML Pipeline
#       - Will be set-up via a Task
#     - DataTarget: In each case, the Pipeline result is provided to a target
#
# - Pipeline (is-a PipelineElement) ...
#   - Pipeline stream_create(data_target, ...)
#   - All PipelineElements in-process
#   - All PipelineElements distributed
#
# - LifeCycle management: creation and deletion
#   - Pipeline leases: All Pipelines are leased ?
#     - Stream Pipelines are definitely leased
#   - Longer running Pipelines, e.g ML Pipelines
#     - Stream Pipeline: VideoRTSPSource exists as long as the camera exists
#   - Session (ephemeral) Streams, e.g WebRTC created by WebRTCSesssionManager
#   - Scaling: Consider how the new Pipelines can be scaled up and down
#
# - Data capture: Each data type can be stored and managed by HL Web

from abc import abstractmethod
import click
from dataclasses import dataclass, asdict
import networkx as nx                 # TODO: Reconsider use of networkx module
from typing import Any, List, Tuple

from aiko_services import *
from aiko_services.utilities import *

__all__ = [
    "Pipeline", "PipelineDefinition",
    "PipelineElement", "PipelineElementDefinition",
    "ServiceDefinition"
]

ACTOR_TYPE = "Pipeline"
PROTOCOL = f"{ServiceProtocol.AIKO}/pipeline:0"

_LOGGER = aiko.logger(__name__)
_VERSION = 0

# --------------------------------------------------------------------------- #

class PipelineElement(Actor):
    Interface.implementations["PipelineElement"] =  \
        "__main__.PipelineElementImpl"

    @abstractmethod
    def start_stream(self, stream_id, parameters):
        pass

    @abstractmethod
    def stop_stream(self, stream_id, frame_id):
        pass

    @abstractmethod
    def process_frame(self, stream_id, frame_id, **kwargs) -> Tuple[bool, Any]:
        """
        Returns a tuple of (success, output) where "success" indicates
        success or failure of processing the frame
        """
        pass

class PipelineElementImpl(PipelineElement):
    def __init__(self, implementations, name):
        implementations["Actor"].__init__(self, implementations, name)
    #   print(f"# self: {self.__class__.__name__}: PipelineElementImpl.__init__({name}) invoked")

    def start_stream(self, stream_id, parameters):
        pass

    def stop_stream(self, stream_id):
        pass

@dataclass
class ServiceDefinition:
    type: str
    name: str
    pads: dict
    parameters: dict

@dataclass
class PipelineElementDefinition(ServiceDefinition):
    service_level_agreement: str

@dataclass
class PipelineDefinition(PipelineElementDefinition):
    pipeline_elements: List[PipelineElementDefinition]
    edges: List[Tuple[
        Tuple[PipelineElementDefinition, str],
        Tuple[PipelineElementDefinition, str]
    ]]

# --------------------------------------------------------------------------- #
#
#      PE_1
#      /  \
#   PE_2  PE_3
#      \  /
#      PE_4

class PE_1(PipelineElementImpl):
    @dataclass
    class FrameOutput: a: int; b: str

    def __init__(self, implementations, name):
        implementations["PipelineElement"].__init__(self, implementations, name)
    #   print("# PE_1.__init__() invoked")

    def process_frame(self, stream_id, frame_id) -> Tuple[bool, FrameOutput]:
        return True, PE_1.FrameOutput(a=stream_id, b=str(frame_id))

class PE_2(PipelineElementImpl):
    @dataclass
    class FrameOutput: c: int

    def __init__(self, implementations, name):
        implementations["PipelineElement"].__init__(self, implementations, name)
    #   print("# PE_2.__init__() invoked")

    def process_frame(self, stream_id, frame_id, a: int) ->  \
        Tuple[bool, FrameOutput]:
        c = a * 1000
        return True, PE_2.FrameOutput(c)

class PE_3(PipelineElementImpl):
    @dataclass
    class FrameOutput: d: int; e: float

    def __init__(self, implementations, name):
        implementations["PipelineElement"].__init__(self, implementations, name)
    #   print("# PE_3.__init__() invoked")

    def process_frame(self, stream_id, frame_id, b: str) ->  \
        Tuple[bool, FrameOutput]:
        d = len(b)
        e = d / 1000
        return True, PE_3.FrameOutput(d, e)

class PE_4(PipelineElementImpl):
    @dataclass
    class FrameOutput: pass

    def __init__(self, implementations, name):
        implementations["PipelineElement"].__init__(self, implementations, name)
    #   print("# PE_4.__init__() invoked")

    def process_frame(self, stream_id, frame_id, c: int, d: int, e: float) ->  \
        Tuple[bool, FrameOutput]:
        return True, PE_4.FrameOutput()

# --------------------------------------------------------------------------- #

pe_1 = PipelineElementDefinition(
    "PipelineElement", "PE_1", {"output": ["a", "b"]}, {},
    "low_latency"
)

pe_2 = PipelineElementDefinition(
    "PipelineElement", "PE_2", {"input": ["a"], "output": ["c"]}, {},
    "low_latency"
)

pe_3 = PipelineElementDefinition(
    "PipelineElement", "PE_3", {"input": ["b"], "output": ["d", "e"]}, {},
    "low_latency"
)
pe_4 = PipelineElementDefinition(
    "PipelineElement", "PE_4", {"input": ["c", "d", "e"]}, {},
    "low_latency"
)

p_1 = PipelineDefinition(
    "Pipeline", "P_1", {}, {}, "low_latency", [pe_1, pe_2, pe_3, pe_4],
    [   ((pe_1, "a"), (pe_2, "a")),
        ((pe_1, "b"), (pe_3, "b")),
        ((pe_2, "c"), (pe_4, "c")),
        ((pe_3, "d"), (pe_4, "d")),
        ((pe_3, "e"), (pe_4, "e")),
    ]
)

# --------------------------------------------------------------------------- #

class Pipeline(PipelineElement):
    Interface.implementations["Pipeline"] = "__main__.PipelineImpl"

    @abstractmethod
    def test(self, value):
        pass

# TODO: Refactor Service code into PipelineElement

class PipelineImpl(Pipeline):
    def __init__(self, implementations, name, pipeline_definition):
        implementations["PipelineElement"].__init__(
            self, implementations, name)
        self.pipeline_definition = pipeline_definition
        aiko.set_protocol(PROTOCOL)  # TODO: Move into service.py

        self.state = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒{__file__}"
        }
        self.ec_producer = ECProducer(self, self.state)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self.add_message_handler(self.topic_in_handler, self.topic_in)

        self._create_pipeline_graph()

    def _create_pipeline_graph(self):
        self.graph = nx.DiGraph()

#       pipeline_elements = [
#           (pe_def.name, {"pipeline_element": getattr(__import__("__main__"), pe_def.name)()})
#           for pe_def in self.pipeline_definition.pipeline_elements
#       ]

        pipeline_elements = []
        for pe_def in self.pipeline_definition.pipeline_elements:
            name = pe_def.name
            pe_class = getattr(__import__("__main__"), name)
            init_args = { "name": name }
        #   print("# _create_pipeline_graph().compose_instance(pe_class, ...)")
            pipeline_element_instance = compose_instance(pe_class, init_args)
            pipeline_element_dict = {
                "pipeline_element": pipeline_element_instance }
            pipeline_element = (name, pipeline_element_dict)
            pipeline_elements.append(pipeline_element)

        self.graph.add_nodes_from(pipeline_elements)

        edges = []
        for edge in self.pipeline_definition.edges:
            node_from = edge[0][0].name
            node_to = edge[1][0].name
            # Add pad conections to nx edge as attributes.
            # Multiple pad connections between the same nodes will be
            # merged in the nx edged attributes dict.
            edge_attributes = {edge[0][1]: edge[1][1]}
            nx_edge = (node_from, node_to, edge_attributes)
            edges.append(nx_edge)

        self.graph.add_edges_from(edges)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if _LOGGER.isEnabledFor(DEBUG):  # Save time
            _LOGGER.debug(f"ECProducer: {command} {item_name} {item_value}")
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def start_stream(self, stream_id, parameters):
        pass

    def stop_stream(self, stream_id):
        pass

    def process_frame(self, stream_id, frame_id) -> Tuple[bool, None]:
        swag = {}
        for node in nx.topological_sort(self.graph):
            nx_node = self.graph.nodes[node]
            pipeline_element = nx_node["pipeline_element"]
            input_pads = pipeline_element.process_frame.__annotations__
            return_type = input_pads.pop("return")
            print(pipeline_element.__class__.__name__)
            print(f"    Input pads: {input_pads}")

            output_pads = {}
            return_class = return_type.__args__[1]
            if return_class != type(None):
                if "__annotations__" in dir(return_class):
                    output_pads = return_class.__annotations__
            print(f"    Output pads: {output_pads}")

            # Use graph to resolve key from swag
            inputs = {
                target_pad_name: swag[source_pad_name]
                for edge in self.graph.in_edges(node)
                for source_pad_name, target_pad_name in
                    self.graph.get_edge_data(*edge).items()
            }

            #inputs = {input_name: swag[input_name]
            #          for input_name in input_pads.keys()}
            okay, frame_output = pipeline_element.process_frame(
                stream_id, frame_id, **inputs)
            if not okay:
            # TODO: Handle PipelineElement failure more gracefully
                raise Exception(f"PipelineElement {pipeline_element.__class__.__name__}: isn't okay")
            if frame_output:
                swag = {**swag, **asdict(frame_output)}
            print(f"\nSwag: {swag}\n")

        return True, None

    def test(self, value):
        _LOGGER.info(f"{self.name}: test({value})")
        payload_out = f"(test {value})"
        aiko.message.publish(aiko.topic_out, payload_out)

    def topic_in_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        if _LOGGER.isEnabledFor(DEBUG):  # Save time
            _LOGGER.debug(
                f"{self.name}: topic_in_handler(): {command}:{parameters}"
            )
# TODO: Apply proxy automatically for Actor and not manually here
        self._post_message(actor.Topic.IN, command, parameters)

# --------------------------------------------------------------------------- #

@click.command("main", help="Pipeline design and implementation development")
@click.argument("pipeline_definition_pathname", nargs=1, default=None, required=False)
def main(pipeline_definition_pathname):
    name = f"{aiko.topic_path}.{ACTOR_TYPE}"  # WIP: Actor name
#   aiko.add_tags([f"key={value}"])
    init_args = {
        "name": name,
        "pipeline_definition": p_1  # TODO: Parse "pipeline_definition_pathname"
    }
#   print("# main().compose_instance(PipelineImpl, ...)")
    pipeline = compose_instance(PipelineImpl, init_args)
    pipeline.process_frame(1000, 2000)
#   pipeline.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
