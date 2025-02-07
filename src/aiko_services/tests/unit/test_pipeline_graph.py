# Usage
# ~~~~~
# pytest [-s] unit/test_pipeline_graph.py
# pytest [-s] unit/test_pipeline_graph.py::test_graph_name_mapping
#
# test_graph_name_mapping()
# -
#   See https://github.com/geekscape/aiko_services/pull/27
#
# To Do
# ~~~~~
# - Test all sorts of Pipeline Graphs

from typing import Tuple

import aiko_services as aiko
from aiko_services.tests.unit import do_create_pipeline

# PIPELINE_DEFINITION = HEADER + GRAPHS[PIPELINE_GRAPH_INDEX] + ELEMENTS
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

PIPELINE_GRAPH_INDEX = 0

HEADER = """{ "version": 0, "name": "p_test", "runtime": "python",
"""

GRAPHS = [
#### GRAPH 0 #### Helpful milestone ####
""" "graph": ["(A B (a_out_0: b_in_0 a_out_1: b_in_1) Terminate)"], """,
#### GRAPH 1 #### Helpful milestone ####
""" "graph": ["(A B (a_out_0: b_in_0 a_out_1: b_in_1) C Terminate)"], """,
#### GRAPH 2 #### Helpful milestone ####
""" "graph": ["(A B (a_out_0: b_in_0 a_out_1: b_in_1) C (a_out_0: c_in_0 b_out_0: c_in_1 a_out_1: c_in_2) Terminate)"], """,
#### GRAPH 3 #### Helpful milestone ####
""" "graph": ["(A B (A.a_out_0: b_in_0 A.a_out_1: b_in_1) Terminate)"], """,
#### GRAPH 4 #### Final test ####
""" "graph": ["(A B (A.a_out_0: b_in_0 A.a_out_1: b_in_1) C (A.a_out_0: c_in_0 B.b_out_0: c_in_1 A.a_out_1: c_in_2) Terminate)"], """
]

ELEMENTS = """
  "elements": [
    { "name":   "A",
      "input":  [],
      "output": [{ "name": "a_out_0", "type": "int" },
                 { "name": "a_out_1", "type": "int" }],
      "deploy": {
        "local": { "module": "aiko_services.tests.unit.test_pipeline_graph" }
      }
    },
    { "name":   "B",
      "input":  [{ "name": "b_in_0", "type": "int" },
                 { "name": "b_in_1", "type": "int" }],
      "output": [{ "name": "b_out_0", "type": "List[int]" }],
      "deploy": {
        "local": { "module": "aiko_services.tests.unit.test_pipeline_graph" }
      }
    },
    { "name":   "C",
      "input":  [{ "name": "c_in_0", "type": "int" },
                 { "name": "c_in_1", "type": "List[int]" },
                 { "name": "c_in_2", "type": "int"}],
      "output": [{ "name": "c_out_0", "type": "List[int]" }],
      "deploy": {
        "local": { "module": "aiko_services.tests.unit.test_pipeline_graph" }
      }
    },
    { "name":   "Terminate", "input":  [], "output": [],
      "deploy": {"local": { "module": "aiko_services.tests.unit.common" }}
    }
  ]
}
"""

class A(aiko.PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream):
        a_out_0 = 0
        a_out_1 = 1
        self.logger.info(
            f"{self.my_id()}: a_out_0: {a_out_0}, a_out_1: {a_out_1}")
    #   result = {"a_out_0": a_out_0, "a_out_1": a_out_1}
        result = {"a_out_0": a_out_0, "a_out_1": a_out_1, "b_in_1": -1}
        return aiko.StreamEvent.OKAY, result

class B(aiko.PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, b_in_0, b_in_1):
        b_out_0 = [b_in_0, b_in_1]
        self.logger.info(f"{self.my_id()}: b_out_0: {b_out_0}")
    #   result = {"b_out_0": b_out_0}
        result = {"b_out_0": b_out_0, "c_in_0": -1, "c_in_1": [-1], "c_in_2": -1}
        return aiko.StreamEvent.OKAY, result

class C(aiko.PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, c_in_0, c_in_1, c_in_2):
        c_out_0 = [c_in_0] + c_in_1 + [c_in_2]
        self.logger.info(f"{self.my_id()}: c_out_0: {c_out_0}")
        return aiko.StreamEvent.OKAY, {"c_out_0": c_out_0}

def test_graph_name_mapping():
    for graph_index in range(len(GRAPHS)):
        print("\n=================================")
        print(f"Test Graph name mapping: Graph[{graph_index}]")
        print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        pipeline_definition = HEADER + GRAPHS[graph_index] + ELEMENTS
        do_create_pipeline(pipeline_definition)
        break
