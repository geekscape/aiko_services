#!/usr/bin/env python3
#
# Manage Pipelines consisting of PipelineElements (Actors or Services)
#
# Usage
# ~~~~~
# ./pipeline.py create pipeline_definition [--name pipeline_name]
# ./pipeline.py delete pipeline_name
#
# To Do
# ~~~~~
# - CLI create(): Should run Pipeline in the background (detached)
#   - See hl_all/infrastructure/websockets/authentication_manager.py
# - CLI delete(): Implement

# from abc import abstractmethod
# from avro.datafile import DataFileReader
# import avro.io
import avro.schema
from avro_validator.schema import Schema
import click
import json
import os
# import queue
import sys

from aiko_services import *
# from aiko_services.utilities import *

__all__ = [
]

PIPELINE_DEFINITION_PATHNAME = "pipeline_definition.avsc"

ACTOR_TYPE = "pipeline"
PROTOCOL = f"{ServiceProtocol.AIKO}/{ACTOR_TYPE}:0"

_LOGGER = aiko.logger(__name__)
_VERSION = 0

# --------------------------------------------------------------------------- #
# TODO: Use dataclasses and https://pypi.org/project/json for serialisation
#       Avro support for classes built with Pydantic
#       import json;  string = json.dump(...)
# TODO: Graph.add(): [nodes] ?
# TODO: Node.add(): [dependencies] ?
# TODO: Should dependencies be more than just "element.output" (string) ?
# TODO: Declare stream head nodes ... which accept frames ?

class Graph():
    def __init__(self):
        self._graph = {}

    def __repr__(self):
        return str(self.nodes(as_strings=True))

    def add(self, node):
        if node.name in self._graph:
            raise KeyError(f"Graph already contains node: {node}")
        self._graph[node.name] = node

    def nodes(self, as_strings=False):
        nodes = []
        for node in self._graph.values():
            nodes.append(str(node) if as_strings else node)
        return nodes

    def remove(self, node):
        if node.name in self._graph:
            del self._graph[node.name]

    def resolve(self):
        pass

class Node():
    def __init__(self, name, element, dependencies=None):
        self._name = name
        self._element = element
        self._dependencies = dependencies if dependencies else {}

    @property
    def dependencies(self):
        dependencies = []
        for dependency in self._dependencies:
            dependencies.append(dependency)
        return dependencies

    @property
    def element(self):
        return self._element

    @property
    def name(self):
        return self._name

    def __repr__(self):
        return f"{self._name}: {self._dependencies}"

    def add(self, dependency):
        if dependency in self._dependencies:
            raise KeyError(f"Node already contains dependency: {dependency}")
        self._dependencies[dependency] = dependency

    def remove(self, dependency):
        if dependency in self._dependencies:
            del self._dependencies[dependency]

g = Graph()
na = Node("a", None)
nb = Node("b", None)
na.add("da")
nb.add("db")
g.add(na)
g.add(nb)

# --------------------------------------------------------------------------- #
# TODO: Incorporate "pipeline_definition.avsc"

SCHEMA = avro.schema.parse(json.dumps({
    "namespace"    : "example.avro",
    "name"         : "User",
    "type"         : "record",
    "fields"       : [
         {"name": "name"            , "type": "string"},
         {"name": "favorite_number" , "type": ["int", "null"]},
         {"name": "favorite_color"  , "type": ["string", "null"]}
    ]
}))

# --------------------------------------------------------------------------- #

class PipelineType():
    LOCAL = "local"
    REMOTE = "remote"

    types = [LOCAL, REMOTE]

class PipelineDefinition():
    def __init__(self, type=PipelineType.LOCAL):
        self._type = type
        self._elements = {}

    @property
    def type(self):
        return self._type

    def __repr__(self):
        return f"{self._type}"

    def add(self, element):
        if element in self._elements:
            raise KeyError(
                f"PipelineDefinition already contains element: {element}")
        self._elements[element] = element

    def element(self, element):
        if element in self._elements:
            del self._elements[element]

# --------------------------------------------------------------------------- #

class Pipeline(Actor):
    Interface.implementations["Pipeline"] = "__main__.PipelineImpl"

#   @abstractmethod
#   def test(self, value):
#       pass

class PipelineImpl(Pipeline):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        pipeline_definition_pathname):

        implementations["Actor"].__init__(self,
            implementations, name, protocol, tags, transport)

        self._load_pipeline_definition(pipeline_definition_pathname)

        self.state = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒{__file__}",
            "pipeline_definition": pipeline_definition_pathname
        }
        self.ec_producer = ECProducer(self, self.state)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self.add_message_handler(self._topic_in_handler, self.topic_in)
        #   binary=True)

    def _load_pipeline_definition(self, pipeline_definition_pathname):
        try:
            schema = Schema(PIPELINE_DEFINITION_PATHNAME).parse()
        except ValueError as value_error:
            _LOGGER.error(
                f"Error: Parsing Pipeline Definition schema: {PIPELINE_DEFINITION_PATHNAME}")
            _LOGGER.error(value_error)
            sys.exit(1)

        try:
            self.pipeline_definition = json.load(
                open(pipeline_definition_pathname, "r"))
            schema.validate(self.pipeline_definition)
            _LOGGER.info(
                f"Pipeline Definition parsed: {pipeline_definition_pathname}")
        except ValueError as value_error:
            _LOGGER.error(
                f"Error: Parsing Pipeline Definition: {pipeline_definition_pathname}")
            _LOGGER.error(value_error)
            sys.exit(1)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def _topic_in_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
# TODO: Apply proxy automatically for Actor and not manually here
        self._post_message(actor.Topic.IN, command, parameters)

# Review ~/play/avro/pipeline_test.py: class PipelineA: implementation
#        ~/play/avro/zz_new_suggestion.py

# import pipeline_definition_test
# pipeline_test = PipelineA(pipeline_definition_test.graph)

# frame_queue = queue.Queue()
# frame = {"input1": {"param1": 1, "param2": 2}}
# frame_queue.put(frame)

# while True:
#   frame = frame_queue.get()
#   result = pipeline_test.run(frame)
#   handle_result(result)  # TODO: Implement

# --------------------------------------------------------------------------- #

@click.group()
def main():
    """Create and delete Pipelines"""
    pass

@main.command(
    help="Create Pipeline where PIPELINE_DEFINITION is specified by a pathname")
@click.argument("pipeline_definition", nargs=1, type=str, required=True)
@click.option("--name", "-n", type=str, default=ACTOR_TYPE, required=False,
    help="Pipeline Actor name")
def create(pipeline_definition, name):
    if not os.path.exists(PIPELINE_DEFINITION_PATHNAME):
        raise SystemExit(
            f"Error: Pipeline Definition schema not found: {PIPELINE_DEFINITION_PATHNAME}")

    if not os.path.exists(pipeline_definition):
        raise SystemExit(
            f"Error: Pipeline Definition not found: {pipeline_definition}")

    init_args = actor_args(name, PROTOCOL)
    init_args["pipeline_definition_pathname"] = pipeline_definition
    pipeline = compose_instance(PipelineImpl, init_args)
    pipeline.run()

@main.command(help="Delete Pipeline")
@click.argument("name", nargs=1, type=str, required=True)
def delete(name):
    raise SystemExit("Error: pipeline.py delete: Unimplemented")

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
