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
from aiko_services.utilities import load_modules

__all__ = ["Pipeline"]

class Pipeline():
    def __init__(self, pipeline_definition, frame_rate = 0):
        self.frame_rate = frame_rate

        self.graph = nx.DiGraph(version=0)
        nodes = self.graph.nodes
        for node in pipeline_definition:
            node_name = node["name"]
            if node_name in nodes and "source" in self.get_node(node_name):
                raise ValueError(f"Duplicate pipeline element: {node_name}")

            if "source" in node:
                self.graph.add_node(node_name, source=node["source"])
            else:
                raise ValueError(f"Pipeline element missing 'source': {node_name}")

            if "successors" in node:
                for node_successor in node["successors"]:
                    self.graph.add_edge(node_name, node_successor)

            if "parameters" in node:
                self.get_node(node_name)["parameters"] = node["parameters"]

        for node_name in self.get_node_names():
          for successor in self.get_node_successors(node_name):
              if "source" not in self.get_node(successor):
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
            module_pathname = node[1].get("source", None)
            module_pathnames.append(module_pathname)
        return module_pathnames

    def get_node(self, node_name):
        return self.graph.nodes[node_name]

    def get_nodes(self):
        return list(self.graph.nodes.data())

    def get_node_names(self):
        return list(self.graph.nodes)

    def get_node_predecessors(self, node_name):
        return list(self.graph.predecessors(node_name))

    def get_node_successors(self, node_name):
        return list(self.graph.successors(node_name))

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
                node["instance"] = class_(node_name, node_parameters, node_predecessors)

    def pipeline_handler(self):
        head_node_name = self.get_head_node_name()
        if head_node_name:
            if not self.pipeline_process(head_node_name, True):
                self.pipeline_process(head_node_name, False)
                self.pipeline_stop()
        else:
            self.pipeline_stop()

    def pipeline_process(self, node_name, stream_processing):
        process_queue = Queue(maxsize=self.graph.number_of_nodes())
        process_queue.put(ProcessFrame(node_name), block=False)
        processed_nodes = set()  # Only process each node once per frame
        okay = True

        while process_queue.qsize():
            process_frame = process_queue.get()
            node_name = process_frame.pipeline_node_name

            if node_name not in processed_nodes:
                node = self.get_node(node_name)
                if node["instance"].handler:
                    if not stream_processing:
                        node["instance"].update_state(stream_processing)
                    okay, output = node["instance"].handler(process_frame.swag)
                    if not okay:
                        break
                    node["instance"].update_state(stream_processing)
                    process_frame.swag[node_name] = output
                    processed_nodes.add(node_name)
                for successor_name in self.get_node_successors(node_name):
                    process_queue.put(ProcessFrame(successor_name), block=False)
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

    def __str__(self):
        return str(self.get_nodes())

class ProcessFrame():
    def __init__(self, pipeline_node_name, swag = {}):
        self.pipeline_node_name = pipeline_node_name
        self.swag = swag
