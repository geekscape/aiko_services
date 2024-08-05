# Declaration order is determined by the dependency on static references
#
# To Do
# ~~~~~
# - None, yet !

__version__ = "0"

from .context import (
    Context, Interface, ServiceProtocolInterface, ContextService,
    ContextPipelineElement, ContextPipeline,
    service_args, actor_args, pipeline_element_args, pipeline_args
)

from .component import compose_class, compose_instance

from .connection import ConnectionState, Connection

from .event import (
    add_flatout_handler, add_mailbox_handler,
    add_queue_handler, add_timer_handler,
    loop, mailbox_put, queue_put,
    remove_flatout_handler, remove_mailbox_handler,
    remove_queue_handler, remove_timer_handler,
    terminate
)

from .process import aiko, process_create

from .lease import Lease

from .service import (
    ServiceFields, ServiceFilter, ServiceProtocol,
    ServiceTags, ServiceTopicPath, Services,
    Service, ServiceImpl
)

from .state import StateMachine

from .proxy import ProxyAllMethods, is_callable, proxy_trace

from .share import (
    ECConsumer, PROTOCOL_EC_CONSUMER,
    ECProducer, PROTOCOL_EC_PRODUCER,
    services_cache_create_singleton, services_cache_delete
)

from .actor import (
    Actor, ActorImpl, ActorTest, ActorTestImpl, ActorTopic
)

from .process_manager import ProcessManager

from .lifecycle import LifeCycleClient, LifeCycleManager

from .stream import (
    DEFAULT_STREAM_ID, FIRST_FRAME_ID, Frame, Stream,
    StreamEvent, StreamEventName, StreamState, StreamStateName
)

from .pipeline import (
    Pipeline, PipelineElement, PipelineElementImpl, PipelineImpl,
    PROTOCOL_PIPELINE
)

from .registrar import *

# from .cli import *

from .dashboard import LogUI, ServiceFrame

aiko.process = process_create()
