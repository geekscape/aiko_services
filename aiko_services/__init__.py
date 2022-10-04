# Declaration order is based on the dependency on static references
#
# To Do
# ~~~~~
# - None, yet !

__version__ = "0"

from .connection import (
    ConnectionState, Connection
)

from .component import (
    Interface, ServiceProtocolInterface, compose_class, compose_instance
)

from .service import (
    ServiceFields, ServiceProtocol, ServiceTags, TopicPath,
    Service, ServiceImpl, ServiceImpl2
)

import aiko_services.event as event     # TODO: Remove this
import aiko_services.framework as aiko  # TODO: Remove this

from .state import (
    StateMachine
)

from .event import (
    add_flatout_handler, add_mailbox_handler,
    add_queue_handler, add_timer_handler,
    loop, mailbox_put, queue_put,
    remove_flatout_handler, remove_mailbox_handler,
    remove_queue_handler, remove_timer_handler,
    terminate
)

from .lease import (
    Lease
)

from .proxy import (
    ProxyAllMethods, is_callable, proxy_trace
)

from .stream_2020 import (
    StreamElementState, StreamElement, StreamQueueElement
)

from .framework import (
    ServiceField, public,
    add_message_handler, remove_message_handler,
    add_topic_in_handler, set_registrar_handler,
    add_stream_handlers, add_stream_frame_handler,
    add_task_start_handler, add_task_stop_handler,
    add_tags, add_tags_string, get_parameter, logger,
    get_tag, match_tags, parse_tags, process,
    set_last_will_and_testament, set_protocol,
    set_terminate_registrar_not_found, set_transport,
    terminate, wait_connected, wait_parameters
)

from .share import (
    ECConsumer, PROTOCOL_EC_CONSUMER,
    ECProducer, PROTOCOL_EC_PRODUCER,
    ServiceFilter,
    filter_services, filter_services_by_actor_names,
    filter_services_by_attributes, filter_services_by_topic_paths,
    service_cache_create_singleton, service_cache_delete
)

from .pipeline_2020 import (
    Pipeline_2020, load_pipeline_definition_2020
)

from .actor import (
    Actor, ActorImpl, TestActor, TestActorImpl
)

from .process_manager import (
    ProcessManager
)

from .lifecycle import (
    LifeCycleClient, LifeCycleManager
)

from .registrar import *

# from .cli import *
