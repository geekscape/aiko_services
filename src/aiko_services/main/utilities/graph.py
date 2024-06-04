# Usage
# ~~~~~
# from aiko_services.main.utilities import *
# graph = Graph()
# node_a = Node("a", None)
# node_b = Node("b", None)
# node_a.add("b")
# graph.add(node_a)
# graph.add(node_b)
# graph.nodes()
#
# heads, successors = graph.traverse(["(a (b d) (c d))"])
#
# Nodes may optionally have a dictionary of properties
#
# def node_properties_callback(node_name, properties, predecessor_name):
#   print(node_name, properties, predecessor_name)
#
# heads, successors = graph.traverse([
#   "(a (b d (key_0: value_0)) (c d (key_1: value_1)))"],
#   node_properties_callback)
#
# --> "D"  {"key_0": "value_0"}  "B"
# --> "D"  {"key_1": "value_1"}  "C"
#
# To Do
# ~~~~~
# - For serialization, use dataclasses and JSON
#   - Consider Avro support for classes built with Pydantic
#       import json;  string = json.dump(...)

from collections import OrderedDict  # All OrderedDict operations are O(1)

from .parser import parse

__all__ = ["Graph", "Node"]

# --------------------------------------------------------------------------- #

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
                if successor is None:
                    breakpoint()
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

    def get_node(self, node_name):
        return self._graph[node_name]

    def nodes(self, as_strings=False):
        nodes = []
        for node in self._graph.values():
            nodes.append(node.name if as_strings else node)
        return nodes

    def remove(self, node):
        if node.name in self._graph:
            del self._graph[node.name]

    @classmethod
    def traverse(cls, graph_definition, node_properties_callback=None):
        node_heads = OrderedDict()
        node_successors = OrderedDict()

# if "node" is a dictionary of properties, then ignore it ... because ...
# if "successor" is a dictionary of properties, then optionally invoke callback

        def add_successor(node, successor):
            if not isinstance(node, dict):
                if not node in node_successors:
                    node_successors[node] = OrderedDict()
                if isinstance(successor, str):
                    node_successors[node][successor] = successor
                elif successor and isinstance(successor, dict):
                    if node_properties_callback:
                        successor_name = list(node_successors[node].keys())[-1]
                        properties = successor
                        predecessor_name = node
                        node_properties_callback(
                            successor_name, properties, predecessor_name)

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
            add_successor(node, None)
            traverse_successors(node, successors)

        return node_heads, node_successors

class Node:
    def __init__(self, name, element, successors=None):
        self._name = name
        self._element = element
        self._successors = successors if successors else OrderedDict()

    def add(self, successor):
        if successor not in self._successors:
            self._successors[successor] = successor

    @property
    def element(self):
        return self._element

    @property
    def name(self):
        return self._name

    def remove(self, successor):
        if successor in self._successors:
            del self._successors[successor]

    @property
    def successors(self):
        return self._successors

    def __repr__(self):
        return f"{self._name}: {list(self._successors)}"

# --------------------------------------------------------------------------- #
