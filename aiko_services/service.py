# Description
# ~~~~~~~~~~~
# Distributed Component that can be discovered and processes messages.
# Defines a Service that runs within a Process.
#
# Example
# ~~~~~~~
# from abc import abstractmethod
# from aiko_services import *
#
# class ServiceTest(Service):
#     Interface.implementations["ServiceTest"] = "__main__.ServiceTestImpl"
#
#     @abstractmethod
#     def test(self):
#         pass
#
# class ServiceTestImpl(ServiceTest):
#     def __init__(self,
#         implementations, name, protocol, tags, transport):
#         implementations["Service"].__init__(self,
#             implementations, name, protocol, tags, transport)
#
#     def test(self):
#         print("ServiceTestImpl.test() invoked")
#
# protocol = f"{ServiceProtocol.AIKO}/service_test:0"
# init_args = service_args("service_test", protocol)
# service_test = compose_instance(ServiceTestImpl, init_args)
# service_test.test()
# aiko.process.run()
#
# Notes
# ~~~~~
# topic_path = ServiceTopicPath(
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
# - BUG: Provide filtered Services to "service_change_handler"
#
# - If a Service is created after the Process has found the Registrar,
#   then ensure that the Service is added to the Registrar.
# - If a Service is terminated, ensure that it is removed from the Registrar.
#
# - Default topic_in_handler(): "message --> function call"
#   - Also provide remote proxy for "function call --> message"
#
# - Add Component.name (?) --> Service.name --> Actor.name
#
# - Consolidate Sevices Eventual Consistency and Registrar "ServicesCache"
#
# - Move ServiceImpl2 to tutorials or examples
#
# - Define ServiceProtocol: registrar.py, service.py (and more ?)
#   - All Services define their own static ServiceProtocol
#
# - Document ServiceFields, ServiceTags and ServiceTopicPath
#   - Document: Namespace, Protocol, Transport and Tags
#
# - Consider extending ServiceFields to provide share.py:ServiceFilter
#
# - ServiceFields
#   - Parser and generator (for presentation)
#   - Validation for each setter
#       @name.setter
#       def name(self, value):
#           self._name = value
#
# - ServiceFilter
#   - Generator (for presentation)
#
# - ServiceTags
#   - Parser and generator (for presentation)
#   - Validation for each setter
#
# - ServiceTopicPath
#   - Parser and generator (for presentation)
#   - Validation for each setter

from abc import abstractmethod
import time

from aiko_services import *

__all__ = [
    "ServiceFields", "ServiceFilter", "ServiceProtocol",
    "ServiceTags", "ServiceTopicPath", "Services",
    "Service", "ServiceImpl", "service_args"
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

# class ServiceField:  # TODO: Support integer index plus string name
#   TOPIC = "TOPIC"          # 0
#   PROTOCOL = "PROTOCOL"    # 1
#   TRANSPORT = "TRANSPORT"  # 2
#   OWNER = "OWNER"          # 3
#   TAGS = "TAGS"            # 4

#   fields = [TOPIC, PROTOCOL, TRANSPORT, OWNER, TAGS]

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

class ServiceFilter:
    def __init__(self,
        topic_paths=None, protocol=None, transport=None,
        owner=None, tags=None, name=None):

        self.topic_paths = topic_paths
        self.protocol = protocol
        self.transport = transport
        self.owner = owner
        self.tags = tags
        self.name = name

    def __repr__(self):
        return f"{self.topic_paths}, {self.protocol}, "  \
               f"{self.transport}, {self.owner}, "      \
               f"{self.tags}, {self.name}"


class ServiceTags:  # TODO: Dictionary of keyword / value pairs
    @classmethod
    def get_tag_value(cls, key, tags):
        tags = ServiceTags.parse_tags(tags)
        return tags.get(key)

    @classmethod
    def match_tags(cls, service_tags, match_tags):
        return all([tag in service_tags for tag in match_tags])

    @classmethod
    def parse_tags(cls, tags_list):
        tags = {}
        for tag in tags_list:
            key, value = tag.split("=")
            tags[key] = value
        return tags

class ServiceTopicPath:
    @classmethod
    def parse(cls, topic_path):
        try:
            namespace, hostname, process_id, service_id = topic_path.split("/")
            return ServiceTopicPath(namespace, hostname, process_id, service_id)
        except ValueError:
            return None

    @classmethod
    def topic_paths(cls, topic_path):
        process_topic_path = None
        service_topic_path = ServiceTopicPath.parse(topic_path)
        if service_topic_path:
            process_topic_path = service_topic_path.topic_path_process
        return process_topic_path, str(service_topic_path)


    def __init__(self, namespace, hostname, process_id=0, service_id=0):
        self._namespace = namespace
        self._hostname = hostname
        self._process_id = process_id
        self._service_id = service_id

    def __repr__(self):
        return f"{self.topic_path_process}/{self._service_id}"

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
    def topic_path_process(self):
        return f"{self._namespace}/{self._hostname}/{self._process_id}"

    @property
    def service_id(self):
        return self._service_id

    @service_id.setter
    def service_id(self, value):
        self._service_id = value

# --------------------------------------------------------------------------- #
# services dict: Key: Process topic_path --> Value: Per Processs Services dict

class ServicesIterator:
    def __init__(self, services):
        self._services = services
        self._process_iterator = iter(self._services)
        self.iterate_process()

    def iterate_process(self):
        process_topic_path = self._process_iterator.__next__()
        self._process_services = self._services[process_topic_path]
        self._service_iterator = iter(self._process_services)

    def __next__(self):
        try:
            service_topic_path = self._service_iterator.__next__()
        except StopIteration:
            self.iterate_process()
            service_topic_path = self._service_iterator.__next__()
        return self._process_services[service_topic_path]

class Services:
    def __init__(self):
        self._count = 0
        self._services = {}

    def __iter__(self):
        return ServicesIterator(self._services) if self._services else iter([])

    def __str__(self):
        return "\n".join(self.get_topic_paths())

    def add_service(self, topic_path, service_details):
        process_topic_path, service_topic_path =  \
            ServiceTopicPath.topic_paths(topic_path)
        if process_topic_path:
            if not process_topic_path in self._services:
                self._services[process_topic_path] = {}
            process_services = self._services[process_topic_path]
            if not service_topic_path in process_services:
                process_services[service_topic_path] = service_details
                self._count += 1

    def copy(self):
        clone = Services()
        clone._services = self._services.copy()
        return clone

    @property
    def count(self):
        return self._count

    def filter_services(self, filter):
        results = self.filter_by_topic_paths(filter.topic_paths)
        results = self.filter_by_attributes(filter, services=results)
        return results

# TODO: Make this a more general "filter" that is compatible with
#       "aiko_services/share.py:_filter_compare()" and keep them together
# TODO: Note this code is copied from "aiko_services/registrar.py"
#       The registrar should also use general filters
# services dict: Key: Process topic_path --> Value: Per Processs Services dict

    def filter_by_attributes(self, filter, services=None):
        services = services._services if services else self._services
        results = Services()

        for process_topic_path, process_services in services.items():
            for service_topic, service_details in process_services.items():
            # TODO: Consolidate into consistent ServiceDetails() data structure
                if type(service_details) == dict:
                    protocol = service_details["protocol"]
                    transport = service_details["transport"]
                    owner = service_details["owner"]
                    tags = service_details["tags"]
                else:
                    protocol = service_details[1]
                    transport = service_details[2]
                    owner = service_details[3]
                    tags = service_details[4]
                matches = True
                if filter.protocol != "*":
                    if filter.protocol != protocol:
                        matches = False
                if filter.transport != "*":
                    if filter.transport != transport:
                        matches = False
                if filter.owner != "*":
                    if filter.owner != owner:
                        matches = False
                if filter.tags != "*":
                    if not ServiceTags.match_tags(tags, filter.tags):
                        matches = False
                if matches:
                    results.add_service(service_topic, service_details)
        return results

# TODO: Currently unused
# TODO: Update to use ServiceFields.name, rather than "actor=name" tag
#   def filter_by_name(self, name):
#       services = {}
#       topic_path = ".".join(name.split(".")[:-1])
#       if topic_path in self._services.keys():
#           service = self._services[topic_path]
#           match_tag = f"actor={name}"  # TODO: service.name
#           if ServiceTags.match_tags(service[4], [match_tag]):
#               services[name] = service
#       return services

    def filter_by_topic_paths(self, topic_paths):
        if topic_paths == "*":
            results = self
        else:
            results = Services()
            for topic_path in topic_paths:
                process_topic_path, _ = ServiceTopicPath.topic_paths(topic_path)
                if process_topic_path in self._services:
                    process_services = self._services[process_topic_path]
                    if topic_path in process_services:
                        results.add_service(
                            topic_path, process_services[topic_path])
        return results

    def get_process_services(self, process_topic_path):
        if process_topic_path in self._services:
            return self._services[process_topic_path].keys()
        return []

    def get_service(self, topic_path):
        process_topic_path, service_topic_path =  \
            ServiceTopicPath.topic_paths(topic_path)
        if process_topic_path in self._services:
            process_services = self._services[process_topic_path]
            if service_topic_path in process_services:
                return process_services[service_topic_path]
        return None

    def get_topic_paths(self):
        topic_paths = []
        for _, process_services in self._services.items():
            topic_paths.extend(list(process_services.keys()))
        return topic_paths

    def remove_service(self, topic_path):
        process_topic_path, service_topic_path =  \
            ServiceTopicPath.topic_paths(topic_path)
        if process_topic_path in self._services:
            process_services = self._services[process_topic_path]
            if service_topic_path in process_services:
                del process_services[service_topic_path]
                self._count -= 1
            if len(process_services) == 0:
                del self._services[process_topic_path]

# --------------------------------------------------------------------------- #

class Service(ServiceProtocolInterface):
    Interface.implementations["Service"] = "aiko_services.service.ServiceImpl"

    @abstractmethod
    def add_message_handler(self, message_handler, topic):
        pass

    @abstractmethod
    def remove_message_handler(self, message_handler, topic):
        pass

    @abstractmethod
    def registrar_handler_call(self, action, registrar):
        pass

    @abstractmethod
    def set_registrar_handler(self, registrar_handler):
        pass

    @abstractmethod
    def add_tags(self, tags):
        pass

    @abstractmethod
    def add_tags_string(self, tags_string):
        pass

    @abstractmethod
    def get_tags_string(self):
        pass

# --------------------------------------------------------------------------- #

def service_args(name=None, protocol=None, tags=[], transport="mqtt"):
    return {"name": name,
            "protocol": protocol,
            "tags": tags,
            "transport": transport}

class ServiceImpl(Service):
    def __init__(self,
        implementations, name=None, protocol=None, tags=[], transport="mqtt"):

    # TODO: Move name, protocol, tags, topic_path, transport into ServiceFields
        self.time_started = time.time()
        self.name = name  # TODO: f"{ACTOR_TYPE}_{self.topic_path}" ?
        self.protocol = protocol
        self._tags = tags
        self.transport = transport
        aiko.process.add_service(self)  # Initializes service_id and topic_path

        self._registrar_handler_function = None
        self.topic_control = f"{self.topic_path}/control"
        self.topic_in = f"{self.topic_path}/in"
        self.topic_log = f"{self.topic_path}/log"
        self.topic_out = f"{self.topic_path}/out"
        self.topic_state = f"{self.topic_path}/state"

    def add_message_handler(self, message_handler, topic):
        aiko.process.add_message_handler(message_handler, topic)

    def remove_message_handler(self, message_handler, topic):
        aiko.process.remove_message_handler(message_handler, topic)

    def registrar_handler_call(self, action, registrar):
        if self._registrar_handler_function:
            self._registrar_handler_function(action, registrar)

    def set_registrar_handler(self, registrar_handler):
        self._registrar_handler_function = registrar_handler

    def add_tags(self, tags):
        for tag in tags:
            if not ServiceTags.match_tags(self._tags, [tag]):
                self._tags.append(tag)

    def add_tags_string(self, tags_string):
        if tags_string:
            tags = tags_string.split(",")
            self.add_tags(tags)

    def get_tags_string(self):
        return ' '.join([str(tag) for tag in self._tags])

# --------------------------------------------------------------------------- #
