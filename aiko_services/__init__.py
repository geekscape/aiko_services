# Declaration order is determined by the dependency on static references
#
# To Do
# ~~~~~
# - None, yet !

__version__ = "0"

from .connection import ConnectionState, Connection

from .event import (
    add_flatout_handler, add_mailbox_handler,
    add_queue_handler, add_timer_handler,
    loop, mailbox_put, queue_put,
    remove_flatout_handler, remove_mailbox_handler,
    remove_queue_handler, remove_timer_handler,
    terminate
)

import aiko_services.event as event  # TODO: Remove this

from .process import aiko, process_create

from .lease import Lease

from .component import (
    Interface, ServiceProtocolInterface, compose_class, compose_instance
)

from .service import (
    ServiceFields, ServiceFilter, ServiceProtocol,
    ServiceTags, ServiceTopicPath, Services,
    Service, ServiceImpl, service_args
)

from .state import StateMachine

from .proxy import ProxyAllMethods, is_callable, proxy_trace

from .share import (
    ECConsumer, PROTOCOL_EC_CONSUMER,
    ECProducer, PROTOCOL_EC_PRODUCER,
    services_cache_create_singleton, services_cache_delete
)

from .actor import (
    Actor, ActorImpl, actor_args, ActorTest, ActorTestImpl, actor_args
)

from .process_manager import ProcessManager

from .lifecycle import LifeCycleClient, LifeCycleManager

from .pipeline import (
    Pipeline, PipelineElement, PipelineElementImpl, PipelineImpl
)

from .registrar import *

# from .cli import *

from .dashboard import LogUI, ServiceFrame

aiko.process = process_create()
