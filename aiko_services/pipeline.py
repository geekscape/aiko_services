#!/usr/bin/env python3
#
# Manage Pipelines consisting of PipelineElements (Actors or Services)
#
# Usage
# ~~~~~
#
# To Do
# ~~~~~
# - CLI create(): Should run Pipeline in the background (detached)
# - CLI delete(): Implement
#
# - PipelineDefinition design and implementation
# - LifeCycleManager / Client implementations ...
#   - Pipeline implementation: PipelineElements are all within same process
#   - Pipeline implementation: PipelineElements are all distributed
# - Visual representation and editing
#
# - Incorporate pipeline_2022.py
# - Incorporate pipeline_2020.py
#   - aiko_services/examples/pipeline/*, RTSP and WebRTC pipelines
#   - StateMachine (rewrite)
# - Pipeline / PipelineElement properties --> Stream (leased)
#   - Update Pipeline / PipelineElement properties on-the-fly
#   - Tasks (over GraphQL or MQTT) --> Session (leased)
# - Session limits: frame count (maybe just 1) and lease time
# - Integrate GStreamer plug-ins as PipelineElements
# - Media data transports, e.g in-band MQTT and out-of-band RTSP / WebRTC

import click

from aiko_services import *

__all__ = [
]

ACTOR_TYPE = "Pipeline"
PROTOCOL = f"{ServiceProtocol.AIKO}/pipeline:0"

_LOGGER = aiko.logger(__name__)
_VERSION = 0

# --------------------------------------------------------------------------- #
# TODO: Graph.add(): [node] ?
# TODO: Node.add(): [dependency] ?
# TODO: Should dependencies be more than just a name (string) ?
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
    def __init__(self, name, dependencies=None):
        self._name = name
        self._dependencies = dependencies if dependencies else {}

    @property
    def dependencies(self):
        dependencies = []
        for dependency in self._dependencies:
            dependencies.append(dependency)
        return dependencies

    @property
    def name(self):
        return self._name

    def __repr__(self):
        return f"{self.name}: {self._dependencies}"

    def add(self, dependency):
        if dependency in self._dependencies:
            raise KeyError(f"Node already contains dependency: {dependency}")
        self._dependencies[dependency] = dependency

    def remove(self, dependency):
        if dependency in self._dependencies:
            del self._dependencies[dependency]

# --------------------------------------------------------------------------- #

class Pipeline(Actor):
    Interface.implementations["Pipeline"] = "__main__.PipelineImpl"

class PipelineImpl(Pipeline):
    def __init__(self, implementations, name, protocol, tags, transport):

        implementations["Actor"].__init__(self,
            implementations, name, protocol, tags, transport)

        self.state = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒{__file__}"
        }
        self.ec_producer = ECProducer(self, self.state)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    #   self.add_message_handler(self._topic_all_handler, "#")  # for testing
        self.add_message_handler(self._topic_in_handler, self.topic_in)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def _topic_in_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
# TODO: Apply proxy automatically for Actor and not manually here
        self._post_message(actor.Topic.IN, command, parameters)

# --------------------------------------------------------------------------- #

@click.group()
def main():
    pass

@main.command(help="Create Pipeline")
@click.argument("definition_pathname", nargs=1, type=str, required=True)
@click.option("--name", "-n", type=str, default=ACTOR_TYPE, required=False)
def create(definition_pathname, name):
    init_args = actor_args(name, PROTOCOL)
    pipeline = compose_instance(PipelineImpl, init_args)
    pipeline.run()

@main.command(help="Delete Pipeline")
@click.argument("name", nargs=1, type=str, required=True)
def delete(name):
    raise SystemExit("Error: pipeline.py delete: Unimplemented")

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
