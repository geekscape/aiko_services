# Description
# ~~~~~~~~~~~
# Provide Service, Actor, PipelineElement and Pipeline instances with
# extensible data structures for storing common variable fields.
# This reduces the constructor "__init__()" arguments to just one.
# Providing some reasonable protection from breaking application
# code over time ... as the framework changes.
#
# Example
# ~~~~~~~
# In the following example, "actor_args()" creates a "ContextService"
# instance, which is used to populate the constructor "context" argument.
#
#     class Example(Actor):
#         def __init__(self, context):
#             context.get_implementation("Actor").__init__(self, context)
#
#     init_args = actor_args("example")
#     compose_instance(Example, init_args)
#     aiko.process.run()
#
# To Do
# ~~~~~
# - Provide get_parameter() and set_parameter() (using existing code) ?
#
# - Use "__file__" instead of "__name__" and ...
#   - Provide "__file__" --> "__name__" function to avoid "__main__"
#
# - Consider "protocol" revision versus "source code file" version ?
#   - Convenience function for automatically creating source code version ?
#
# - Provide custom __repr__() and __str__() ?
#
# - Provide add_tags() and remove_tags() (using existing code) ?
#   - Tags input is a list, but should tags internally be a dictionary ?

from abc import ABC
from dataclasses import dataclass, field
from typing import Dict, List

__all__ = {
    "Context", "Interface", "ServiceProtocolInterface", "ContextService",
    "ContextPipelineElement", "ContextPipeline"
    "service_args", "actor_args", "pipeline_element_args", "pipeline_args"
}

DEFAULT_PARAMETERS = {}
DEFAULT_PROTOCOL = "*"
DEFAULT_TAGS = []
DEFAULT_TRANSPORT = "mqtt"
DEFAULT_DEFINITION = ""
DEFAULT_DEFINITION_PATHNAME = ""
DEFAULT_STREAM_ID = 0
DEFAULT_FRAME_ID = 0

@dataclass
class Context:
    name: str = "<interface>"
    implementations: Dict[str, str] = field(default_factory=dict)

    def get_implementation(self, implementation_name):
        return self.implementations[implementation_name]

    def get_implementations(self):
        return self.implementations

    def get_name(self) -> str:
        return self.name

    def set_implementation(self, implementation_name, implementation):
        self.implementations[implementation_name] = implementation

    def set_implementations(self, implementations):
        self.implementations = implementations

class Interface(ABC):
    context = Context()

    @classmethod
    def default(cls, implementation_name, implementation):
        cls.context.set_implementation(implementation_name, implementation)

    @classmethod
    def get_implementations(cls):
        return cls.context.get_implementations()

class ServiceProtocolInterface(Interface):
    """Interface marker represents an Aiko Service implementing a protocol"""

# Service and Actor use the same data structure
@dataclass
class ContextService(Context):
    parameters: Dict[str, str] = field(default_factory=dict)
    protocol: str = DEFAULT_PROTOCOL
    tags: List[str] = field(default_factory=list)
    transport: str = DEFAULT_TRANSPORT

    def __post_init__(self):
        if self.name is None or not isinstance(self.name, str):
            raise ValueError(f"Service name must be a string: {self.name}")
        elif not len(self.name):
            raise ValueError(f"Service name must not be an empty string")
        if self.parameters is None:
            self.parameters = DEFAULT_PARAMETERS
        if self.protocol is None:
            self.protocol = DEFAULT_PROTOCOL
        if self.tags is None:
            self.tags = DEFAULT_TAGS
        if self.transport is None:
            self.transport = DEFAULT_TRANSPORT

    def get_parameters(self) -> Dict[str, str]:
        return self.parameters

    def get_protocol(self) -> str:
        return self.protocol

    def get_tags(self) -> List[str]:
        return self.tags

    def get_transport(self) -> str:
        return self.transport

    def set_protocol(self, protocol):
        self.protocol = protocol

@dataclass
class ContextPipelineElement(ContextService):
    definition: str = DEFAULT_DEFINITION
    pipeline: str = None  # TODO: Pipeline reference or None

    def __post_init__(self):
        self.name = self.name.lower()
        super().__post_init__()
        if self.definition is None:
            self.definition = DEFAULT_DEFINITION

    def get_definition(self) -> str:
        return self.definition

    def get_pipeline(self) -> str:
        return self.pipeline

@dataclass
class ContextPipeline(ContextPipelineElement):
    definition_pathname: str = DEFAULT_DEFINITION_PATHNAME
    graph_path: str = None

    def __post_init__(self):
        super().__post_init__()
        if self.definition_pathname is None:
            self.definition_pathname = DEFAULT_DEFINITION_PATHNAME

    def get_definition_pathname(self) -> str:
        return self.definition_pathname

    def get_graph_path(self) -> str:
        return self.graph_path

def service_args(name, implementations=None,
    parameters=None, protocol=None, tags=None, transport=None):

    return {"context":
        ContextService(name, implementations,
            parameters, protocol, tags, transport)}

def actor_args(name, implementations=None,
    parameters=None, protocol=None, tags=None, transport=None):

    return service_args(name, implementations,
        parameters, protocol, tags, transport)

def pipeline_element_args(name, implementations=None,
    parameters=None, protocol=None, tags=None, transport=None,
    definition=None, pipeline=None):

    return {"context":
        ContextPipelineElement(name, implementations,
            parameters, protocol, tags, transport,
            definition, pipeline)}

def pipeline_args(name, implementations=None,
    parameters=None, protocol=None, tags=None, transport=None,
    definition=None, pipeline=None, definition_pathname=None,
    graph_path=None):

    return {"context":
        ContextPipeline(name, implementations,
            parameters, protocol, tags, transport,
            definition, pipeline, definition_pathname, graph_path)}
