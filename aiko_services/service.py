# Distributed component that can be discovered and processes messages
#
# Notes
# ~~~~~
# topic_path = TopicPath(
#     "namespace",
#     "host",
#     "process_id",
#     "service_id")
#
# service_fields = ServiceFields(
#     "topic_path",
#     ServiceProtocol(ServiceProtocol.AIKO, "test", "0"),
#     "transport",
#     "owner",
#     "tags",
#     "name")
#
# service_fields.topic_path = topic_path
#
# To Do
# ~~~~~
# - Refactor framework.py:ServiceField into this source file
#
# - Define ServiceProtocol: framework.py, registrar.py, service.py (and more ?)
#   - All Services define their own static ServiceProtocol
#
# - Document ServiceFields, ServiceTags and TopicPath
#   - Document: Namespace, Protocol, Transport and Tags
#
# - ServiceFields
#   - Parser and generator (for presentation)
#   - Validation for each setter
#       @name.setter
#       def name(self, value):
#           self._name = value
#
# - ServiceTags
#   - Parser and generator (for presentation)
#   - Validation for each setter
#
# - TopicPath
#   - Parser and generator (for presentation)
#   - Validation for each setter
#
# - Default topic_in_handler(): "message --> function call"
#   - Also provide remote proxy for "function call --> message"
# - Add Component.name --> Service.name --> Actor.name
# - Consolidate Sevices Eventual Consistency and Registrar "ServiceCache"
# - Move ServiceImpl2 to tutorials or examples
#
# - Consider basing share.py:SilverFilter functionality extending from
#   ServiceFields

from abc import abstractmethod

__all__ = [
    "ServiceFields", "ServiceProtocol", "ServiceTags", "TopicPath",
    "Service", "ServiceImpl", "ServiceImpl2"
]

class ServiceProtocol:
    AIKO = "github.com/geekscape/aiko_services/protocol"

    def __init__(self, url_prefix, name, version):
        self._url_prefix = url_prefix
        self._name = name
        self._version = version

    def __repr__(self):
        return f"{self._url_prefix}/{self._name}:{self._version}"

    @property
    def url_prefix(self):
        return self._url_prefix

    @url_prefix.setter
    def url_prefix(self, value):
        self._url_prefix = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, value):
        self._version = value

# ServiceProtocol needs to be defined before importing "framework.py" :(
from aiko_services import *

class ServiceFields:
    def __init__(self, topic_path, protocol, transport, owner, tags, name=None):
        self._topic_path = topic_path
        self._protocol = protocol
        self._transport = transport
        self._owner = owner
        self._tags = tags
        self._name = name

    def __repr__(self):
        return f"{self._topic_path}, {self._protocol}, "  \
               f"{self._transport}, {self._owner}, "      \
               f"{self._tags}, {self._name}"

    @property
    def topic_path(self):
        return self._topic_path

    @topic_path.setter
    def topic_path(self, value):
        self._topic_path = value

    @property
    def protocol(self):
        return self._protocol

    @protocol.setter
    def protocol(self, value):
        self._protocol = value

    @property
    def transport(self):
        return self._transport

    @transport.setter
    def transport(self, value):
        self._transport = value

    @property
    def owner(self):
        return self._owner

    @owner.setter
    def owner(self, value):
        self._owner = value

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, value):
        self._tags = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

class ServiceTags:  # TODO Dictionary of keyword / value pairs
    pass

class TopicPath:
    def __init__(self, namespace, hostname, process_id=0, service_id=0):
        self._namespace = namespace
        self._hostname = hostname
        self._process_id = process_id
        self._service_id = service_id

    def __repr__(self):
        return f"{self._namespace}/{self._hostname}/"  \
               f"{self._process_id}/{self._service_id}"

    @property
    def namespace(self):
        return self._namespace

    @namespace.setter
    def namespace(self, value):
        self._namespace = value

    @property
    def hostname(self):
        return self._hostname

    @hostname.setter
    def hostname(self, value):
        self._hostname = value

    @property
    def process_id(self):
        return self._process_id

    @process_id.setter
    def process_id(self, value):
        self._process_id = value

    @property
    def service_id(self):
        return self._service_id

    @service_id.setter
    def service_id(self, value):
        self._service_id = value

class Service(ServiceProtocolInterface):
    Interface.implementations["Service"] = "aiko_services.service.ServiceImpl"

#   @abstractmethod
#   def service_0(self):
#       pass

class ServiceImpl(Service):
    def __init__(self, implementations):
        pass

#   def service_0(self):
#       print("ServiceImpl.service_0()")

class ServiceImpl2(Service):  # TODO: Move into "../examples/"
    def __init__(self, service_parameter_1):
        print(f"ServiceImpl2.__init__({service_parameter_1})")

    def service_0(self):
        print("ServiceImpl2.service_0()")
