# Notes
# ~~~~~
# - Pipeline Graph ...
#   - Information flow, dependencies (strong and weak), categories
#   - https://en.wikipedia.org/wiki/Graph_(abstract_data_type)#Operations
#     - https://en.wikipedia.org/wiki/Adjacency_list
#   - https://en.wikipedia.org/wiki/Graph_traversal
#
# To Do
# ~~~~~
# - In-memory data structure <-- convert --> Persistent storage
# - Why is pipeline_handler() only running at half the specified time ?
# - Why don't timer events occur when pipeline is running flatout ?
# - Add Pipeline.state ...
#   - When pipeline stopped ... event.remove_timer_handler(timer_test)

import networkx as nx
from queue import Queue
import time
import json
import yaml

import aiko_services.event as event
from aiko_services.stream import StreamElementState, StreamQueueElement, StreamElement
from aiko_services.utilities import get_logger, load_module, load_modules

__all__ = ["Pipeline", "load_pipeline_definition"]

_LOGGER = get_logger(__name__)

class Pipeline():
    def __init__(self, pipeline_definition, frame_rate = 0, state_machine = None, stream_id = "nil"):
        self.frame_rate = frame_rate
        self.state_machine = state_machine
        self.stream_id = stream_id
        self.frame_id = -1  # first time through is for stream_start_handler()

        self.graph = nx.DiGraph(version=0)
        nodes = self.graph.nodes
        for node in pipeline_definition:
            node_name = node["name"]
            if node_name in nodes and "module" in self.get_node(node_name):
                raise ValueError(f"Duplicate pipeline element: {node_name}")

            if "successors" not in node:
                node["successors"] = {"default": []}
            if isinstance(node["successors"], list):
                node["successors"] = {"default": node["successors"]}
            if not isinstance(node["successors"], dict):
                raise ValueError(f"Pipeline element successor must be list or dict: {node_name}")

            if "module" in node:
                self.graph.add_node(node_name, module=node["module"], successors=node["successors"])
            else:
                raise ValueError(f"Pipeline element must declare a 'module': {node_name}")

            if "successors" in node:
                for successors in node["successors"].values():
                    for successor in successors:
                        self.graph.add_edge(node_name, successor)

            if "parameters" not in node:
                node["parameters"] = {}
            self.get_node(node_name)["parameters"] = node["parameters"]

        for node_name in self.get_node_names():
          for successor in self.get_node_successors(node_name, based_on_state=False):
              if "module" not in self.get_node(successor):
                  raise ValueError(f"Pipeline element successor not defined: {node_name} --> {successor}")

        _LOGGER.debug(f"Pipeline definition: {self}")

    def get_head_node(self):
        head_node = None
        if self.graph.number_of_nodes():
            head_node = self.get_node(self.get_head_node_name())
        return head_node

    def get_head_node_name(self):
        head_node_name = None
        if self.graph.number_of_nodes():
            head_node_name = self.get_node_names()[0]
        return head_node_name

    def get_module_pathnames(self):
        module_pathnames = []
        for node in list(self.graph.nodes.data()):
            module_pathname = node[1].get("module", None)
            module_pathnames.append(module_pathname)
        return module_pathnames

    def get_node(self, node_name):
        return self.graph.nodes[node_name]

    def get_nodes(self):
        return list(self.graph.nodes.data())

    def get_node_names(self):
        return list(self.graph.nodes)

    def get_node_parameters(self, node_name):
        return self.get_node(node_name)["parameters"]

    def get_node_predecessors(self, node_name):
        return list(self.graph.predecessors(node_name))

    def get_node_successors(self, node_name, based_on_state=True):
        if based_on_state and self.state_machine:
            state = self.state_machine.get_state()
            node_successors = self.get_node(node_name)["successors"]
            if state not in node_successors:
                state = "default"
            successors = node_successors[state]
        else:
            successors = list(self.graph.successors(node_name))
        return successors

    def load_node_modules(self):
        module_pathnames = self.get_module_pathnames()
        modules = load_modules(module_pathnames)

        node_names_modules = dict(zip(self.get_node_names(), modules))
        for node_name, module in node_names_modules.items():
            if module:
                node = self.get_node(node_name)
                node_parameters = node.get("parameters", {})
                node_predecessors = self.get_node_predecessors(node_name)
                class_ = getattr(module, node_name)
                node["instance"] = class_(node_name, node_parameters, node_predecessors, self.state_machine)

    def pipeline_handler(self, queue_item = None, queue_item_type = "none"):
#       event_type = f", event: {queue_item_type}"
#       if queue_item_type.startswith("state_"):
#           event_type = f"{event_type}: {queue_item}"
#       _LOGGER.info(f"pipeline_handler(): stream_id: {self.stream_id}{event_type}")

        if queue_item_type.startswith("parameters_"):
            parameters = queue_item
            for name, parameter_value in queue_item.items():
                try:
                    node_name, parameter_name = name.split(":")
                    self.update_node_parameter(node_name, parameter_name, parameter_value)
                except ValueError:
                    _LOGGER.error(f"pipeline_handler(): Invalid parameter name: {name}")
            return

        head_node_name = self.get_head_node_name()
        if head_node_name:
            if not self.pipeline_process(head_node_name, queue_item, queue_item_type):
                self.pipeline_process(head_node_name, queue_item, queue_item_type, stream_stop=True)
                self.pipeline_stop()
            self.frame_id += 1
        else:
            self.pipeline_stop()

    def pipeline_process(self, node_name, queue_item = None, queue_item_type = None, stream_stop = False):
        node = self.get_node(node_name)
        if node["instance"].get_stream_state() == StreamElementState.COMPLETE:
            event_type = f", event: {queue_item_type}"
            if queue_item_type.startswith("state_"):
                event_type = f"{event_type}: {queue_item}"
            _LOGGER.error(f"pipeline_process(): Can't process pipeline: StreamElementState is COMPLETE: stream_id: {self.stream_id}{event_type}")
            return False

        swag = {}
        if queue_item:
            swag["frame"] = {"data": queue_item, "type": queue_item_type}

        process_queue = Queue(maxsize=self.graph.number_of_nodes())
        process_queue.put(node_name, block=False)
        processed_nodes = set()  # Only process each node once per frame
        okay = True

        while process_queue.qsize():
            node_name = process_queue.get()

            if node_name not in processed_nodes:
                node = self.get_node(node_name)
                node_instance = node["instance"]
                if stream_stop:
                    node_instance.update_stream_state(stream_stop)

                try:
                    okay, output = node_instance.handler(self.stream_id, self.frame_id, swag)
                except TypeError as exception:
                    _LOGGER.error(f"pipeline_process(): {node_name} handler state: {node_instance.get_stream_state()} doesn't return (okay, output)")
                    okay = False
                if not okay:
                    break
                swag[node_name] = output
                processed_nodes.add(node_name)
                based_on_state = node_instance.get_stream_state() == StreamElementState.RUN
                for successor_name in self.get_node_successors(node_name, based_on_state=based_on_state):
                    process_queue.put(successor_name, block=False)
                node_instance.update_stream_state(stream_stop)
        return okay

    def get_queue_item_types(self):
        queue_item_types = {
            "frame": f"frame_{self.stream_id}",
            "parameters": f"parameters_{self.stream_id}",
            "state": f"state_{self.stream_id}"
        }
        return queue_item_types

    def pipeline_start(self):
        if self.queue_handler_required():
            queue_item_types = self.get_queue_item_types()
            event.add_queue_handler(self.pipeline_handler, list(queue_item_types.values()))
            event.queue_put("start", queue_item_types["state"])
        elif self.frame_rate:
            event.add_timer_handler(self.pipeline_handler, self.frame_rate, True)
        else:
            event.add_flatout_handler(self.pipeline_handler)

    def pipeline_stop(self):
        if self.queue_handler_required():
            event.remove_queue_handler(self.pipeline_handler, self.get_queue_item_types())
        elif self.frame_rate:
            event.remove_timer_handler(self.pipeline_handler)
        else:
            event.remove_flatout_handler(self.pipeline_handler)

    def queue_handler_required(self):
        head_node_type = type(self.get_head_node()["instance"])
        return issubclass(head_node_type, StreamQueueElement)

    def run(self):
        self.load_node_modules()
        self.pipeline_start()
        event.loop()  # aiko.process()

    def update_node_parameter(self, node_name, parameter_name, parameter_value):
        node_parameters = self.get_node_parameters(node_name)
        if parameter_name in node_parameters:
            node_parameters[parameter_name] = parameter_value
        else:
            raise KeyError(f"Pipeline element {node_name}: Unknown parameter name: {parameter_name}")

    def __str__(self):
        return str(self.get_nodes())

PIPELINE_DEFINITION_NAME = "pipeline_definition"

def load_pipeline_definition(pipeline_pathname, pipeline_name=PIPELINE_DEFINITION_NAME):
    if pipeline_pathname.endswith(".py"):
        mod = load_module(pipeline_pathname)
        pipeline_def =  getattr(mod, pipeline_name)
    elif pipeline_pathname.endswith(".json"):
        with open(pipeline_pathname, "r") as f:
            pipeline_def = json.load(f)[pipeline_name]
    elif pipeline_pathname.endswith(".yaml") or pipeline_pathname.endswith(".yml"):
        with open(pipeline_pathname, "r") as f:
            pipeline_def = yaml.load(f, Loader=yaml.SafeLoader)[pipeline_name]
    else:
        raise ValueError(f"Unsupported pipeline definition format: {pipeline_pathname}")

    return pipeline_def
