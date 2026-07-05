---
title: Graph utility
description: A lightweight directed graph — Nodes with ordered successors —
  plus an S-expression graph-definition parser, the foundation of Pipeline
  dataflow graphs
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/graph.py
related: [design_overview, parser]
version: "0.6"
last_updated: 2026-07-05
---

# Graph utility

## Overview

The graph utility provides `Graph` and `Node`: an insertion-ordered
directed graph with deterministic traversal, plus a class method that
parses S-expression graph definitions (via the
[Parser](parser.md) utility). It exists chiefly to power Pipeline
definitions — `PipelineGraph` in `pipeline.py` subclasses `Graph`, and
every `"graph": ["(A B C)"]` line in a Pipeline definition file goes
through `Graph.traverse()`.

**Why you'd use it**: turn a declarative dataflow description into an
execution order:

```python
from aiko_services.main.utilities import Graph, Node

heads, successors = Graph.traverse(["(a (b d) (c d))"])
# heads:      {"a": "a"}
# successors: a → {b, c},  b → {d},  c → {d},  d → {}
```

## For application developers

### Command-line usage

There is no CLI; the module is exercised by `aiko_pipeline` whenever a
Pipeline definition's `graph` field is parsed.

### Public API

```python
class Node:
    Node(name, element=None, successors=None)
    add(successor_name) / remove(successor_name)
    name / element / successors        # properties

class Graph:
    Graph(head_nodes=None)
    add(node) / remove(node) / get_node(name) / nodes(as_strings=False)
    get_path(head_node_name=None)      # iterator in execution order
    iterate_after(node_name, head_node_name=None)
    __iter__                           # same as get_path()
    Graph.traverse(graph_definition, node_properties_callback=None)
    Graph.path_local(graph_path) / Graph.path_remote(graph_path)
```

Building a graph by hand:

```python
graph = Graph()
node_a = Node("a")        # optionally Node("a", data_a)
node_b = Node("b")
node_a.add("b")           # successors are referenced by name
graph.add(node_a)
graph.add(node_b)
```

Successor edges may carry a properties dictionary, reported through a
callback — this is how Pipeline definitions map output names to input
names between PipelineElements:

```python
def node_properties_callback(node_name, properties, predecessor_name):
    print(node_name, properties, predecessor_name)

heads, successors = Graph.traverse(
    ["(a (b d (key_0: value_0)) (c d (key_1: value_1)))"],
    node_properties_callback)
# --> "d" {"key_0": "value_0"} "b"
# --> "d" {"key_1": "value_1"} "c"
```

Real call sites in `src/aiko_services/main/pipeline.py`:

```python
node_heads, node_successors = Graph.traverse(
    graph_definition, self.node_properties_callback)   # parse definition
pipeline_graph = PipelineGraph(node_heads)             # subclass of Graph
...
element = Node(name, element_instance, successors)     # one per element
```

`iterate_after()` returns the nodes downstream of a given node — used by
the Pipeline to resume a paused stream and to jump back for loops.
`path_local()` / `path_remote()` split a `"local:remote"` graph-path
string, selecting which sub-path runs in this process versus a remote
Pipeline.

## For framework developers (internals)

### Design

```
   Graph
   ┌─────────────────────────────────────────┐
   │ _graph:      {"a": Node, "b": Node, …}  │  OrderedDict, O(1) ops
   │ _head_nodes: {"a": …}                   │  traversal entry points
   └─────────────────────────────────────────┘
   Node
   ┌─────────────────────────────────────────┐
   │ name, element (payload), successors     │  successors: ordered set
   └─────────────────────────────────────────┘
```

`get_path()` computes execution order by depth-first descent with a
"delete then re-append" trick on an OrderedDict: when a node is reached
again by a later branch it moves to the *end*, guaranteeing every node
appears after all of its predecessors (a topological order for DAGs).
Nodes are decoupled from edges — successors are stored as names and
resolved through the Graph, so a Node can be defined before its
successors exist.

### Implementation notes

- `Graph.add()` raises `KeyError` on a duplicate name; `remove()` is a
  silent no-op for unknown nodes — asymmetric by design of current use.
- There is **no cycle detection**: a cyclic definition sends `get_path()`
  into infinite recursion. Pipeline loops are handled above this layer.
- `traverse()` distinguishes a dict appearing as a *successor* (edge
  properties → callback) from a dict appearing as a *node* (ignored).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Graph` | Own the name→Node map and head nodes; produce execution order; parse graph definitions (`traverse`); split local/remote graph paths | `Node`; [Parser](parser.md) (`parse()`); `PipelineGraph` (subclass in `pipeline.py`) |
| `Node` | Carry a name, an optional payload (`element`) and an ordered set of successor names | `Graph` (resolves successor names) |

## Current limitations and roadmap

From the source `To Do` list:

- Optimise `Graph.__iter__()` with an execution-order cache, invalidated
  on changes (currently recomputed every iteration)
- Serialisation via dataclasses and JSON; consider Avro / Pydantic
- No direct unit tests; covered indirectly by
  `src/aiko_services/tests/unit/test_pipeline_graph.py` through Pipeline
  creation
- No cycle detection (see Implementation notes)

## Related concepts

- [Parser](parser.md) — parses the S-expression graph definitions
- [Design overview](../design_overview.md) — where Pipelines fit in
  Aiko Services
