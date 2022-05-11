# Declaration order is based on the dependency on static references
#
# To Do
# ~~~~~
# - None, yet !

__version__ = "0"

from .state import (
    StateMachine
)

import aiko_services.event as event     # TODO: Remove this
import aiko_services.framework as aiko  # TODO: Remove this

from .event import (
    add_flatout_handler, add_mailbox_handler,
    add_queue_handler, add_timer_handler,
    loop, mailbox_put, queue_put,
    remove_flatout_handler, remove_mailbox_handler,
    remove_queue_handler, remove_timer_handler,
    terminate
)

from .proxy import (
    is_callable, ProxyAllMethods, proxy_trace
)

from .stream import (
    StreamElementState, StreamElement, StreamQueueElement
)

from .framework import (
    public, add_message_handler, remove_message_handler,
    add_topic_in_handler, set_registrar_handler,
    add_stream_handlers, add_stream_frame_handler,
    add_task_start_handler, add_task_stop_handler,
    process, add_tags, get_parameter, parse_tags,
    set_last_will_and_testament, set_protocol,
    set_terminate_registrar_not_found, set_transport,
    terminate, wait_connected, wait_parameters
)

from .pipeline import (
    Pipeline, load_pipeline_definition
)

# from .service import *

from .actor import (
    Actor, TestActor
)

from .process_manager import (
    ProcessManager
)

from .registrar import *

# from .cli import *
