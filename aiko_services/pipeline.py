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

import aiko_services.event as event
from aiko_services.stream import StreamElementState
from aiko_services.utilities import load_modules

__all__ = ["Pipeline"]

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

        self.load_node_modules()
        self.pipeline_start()

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

    def pipeline_handler(self, queue_item = None, queue_item_type = None):
        head_node_name = self.get_head_node_name()
        if head_node_name:
            if not self.pipeline_process(head_node_name, False):
                self.pipeline_process(head_node_name, True)
                self.pipeline_stop()
            self.frame_id += 1
        else:
            self.pipeline_stop()

    def pipeline_process(self, node_name, stream_stop_flag):
        process_queue = Queue(maxsize=self.graph.number_of_nodes())
        process_queue.put(ProcessFrame(node_name), block=False)
        processed_nodes = set()  # Only process each node once per frame
        okay = True

        while process_queue.qsize():
            process_frame = process_queue.get()
            node_name = process_frame.pipeline_node_name

            if node_name not in processed_nodes:
                node = self.get_node(node_name)
                if stream_stop_flag:
                    node["instance"].update_stream_state(stream_stop_flag)
                okay, output = node["instance"].handler(self.stream_id, self.frame_id, process_frame.swag)
                if not okay:
                    break
                process_frame.swag[node_name] = output
                processed_nodes.add(node_name)
                based_on_state = node["instance"].get_stream_state() == StreamElementState.RUN
                for successor_name in self.get_node_successors(node_name, based_on_state=based_on_state):
                    process_queue.put(ProcessFrame(successor_name), block=False)
                node["instance"].update_stream_state(stream_stop_flag)
        return okay

    def pipeline_start(self):
        if self.frame_rate:
            event.add_timer_handler(self.pipeline_handler, self.frame_rate, True)
        else:
            event.add_flatout_handler(self.pipeline_handler)

    def pipeline_stop(self):
        if self.frame_rate:
            event.remove_timer_handler(self.pipeline_handler)
        else:
            event.remove_flatout_handler(self.pipeline_handler)

    def update_node_parameter(self, node_name, parameter_name, parameter_value):
        node_parameters = self.get_node_parameters(node_name)
        if parameter_name in node_parameters:
            node_parameters[parameter_name] = parameter_value
        else:
            raise KeyError(f"Pipeline element {node_name}: Unknown parameter name: {parameter_name}")

    def __str__(self):
        return str(self.get_nodes())

class ProcessFrame():
    def __init__(self, pipeline_node_name, swag = {}):
        self.pipeline_node_name = pipeline_node_name
        self.swag = swag
