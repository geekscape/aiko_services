# Usage
# ~~~~~
# from aiko_services.utilities import *
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
                if isinstance(successor, list):
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
