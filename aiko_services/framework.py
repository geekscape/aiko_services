# To Do
# ~~~~~
# - For standalone applications, i.e not using messages or services,
#     don't start-up MQTT instance, because it takes time to connect
#
# - Add __all__ for all public functions
#
# - Rename "framework.py" to "service.py" and create a Service class ?
# - Implement Aiko class with "class public variables" becoming Aiko class instance variables
#   - "class private" becomes one of the Aiko class instance variables
#
# - Store Aiko class instance as the "ContextManager.__init__(aiko=)" parameter
#
# - Implement message to change logging level !
#
# To Do
# ~~~~~
# - #0: Bootstrap
#
# - #1: Create Service Abstract Base Class
#   - Provide access to "aiko.public" variables
#
# - #2: Integrate aiko_services_internal/video/video_process_service.py !
#   - IoC Pipeline stream processing
#   - Refactor Service discovery across Hosts / Containers into own file
#   - Handle Stream Frame handler resulting in multiple detections !
#     - Another ML Design Pattern !
#
# - on_message() ...
#   - messages should be queued and handled by a background thread
#   - try ... except: around common exceptions, e.g get unknown parameter
#   - Debug options (set via topic_control) ...
#     - Print incoming message topic and payload_in
#     - Print or publish(topic_log) any exceptions raised
#
# - Move silverbrane-worker/silverbrane/services/utilities/artifacts.py here
#
# - Iterator as frames are received, e.g telemetry, video
# - Correct use of /control, /state, /in, /out
# - Implement stream processing

# --------------------------------------------------------------------------- #

from logging import DEBUG
import sys
import time
import traceback

import aiko_services.event as event
from aiko_services.message import MQTT
from aiko_services.utilities.configuration import *
from aiko_services.utilities.context import ContextManager
from aiko_services.utilities.logger import get_logger
from aiko_services.utilities.parser import parse

# import aiko_services.framework as aks                      # TODO: Replace V1

class private:
    exit_status = 0
    message_handlers = {}
    registrar_handler = None
    stream_frame_handler = None
    task_start_handler = None
    task_stop_handler = None

class public:
#   aks_info = None                                          # TODO: Replace V1
    message = None
    namespace = "test"  # TODO: Determine namespace value
    parameters = None
    protocol = None
    service_name = None
    tags = []
    terminate_registrar_not_found = False
    topic_path = get_namespace() + "/" + get_hostname() + "/" + get_pid()
    topic_in = topic_path + "/in"
    topic_log = topic_path + "/log"
    topic_out = topic_path + "/out"
    topic_state = topic_path + "/state"

_LOGGER = get_logger(__name__)

REGISTRAR_PROTOCOL = "au.com.silverpond.protocol.registrar:0"
REGISTRAR_TOPIC = f"{public.namespace}/service/registrar"

def add_message_handler(topic, message_handler):
    if not topic in private.message_handlers:
        private.message_handlers[topic] = []
    private.message_handlers[topic].append(message_handler)

def add_topic_in_handler(topic_handler):
    add_message_handler(public.topic_in, topic_handler)

# TODO: Consider moving all registrar related code into the Registar
def on_registrar_message(aiko_, topic, payload_in):
    parse_okay = False
    registrar = {}
    command, parameters = parse(payload_in)
    if len(parameters) > 0:
        action = parameters[0]
        if command == "primary" and len(parameters) == 3:
            if action == "started":
                registrar["topic_path"] = parameters[1]
                registrar["timestamp"] = parameters[2]
                parse_okay = True
            if action == "stopped":
                parse_okay = True

    handler_finished = True
    if private.registrar_handler:
        handler_finished = private.registrar_handler(public, action, registrar)

# TODO: Need to implement message queue processing, otherwise mqtt.wait_disconnected() doesn't work properly
#       occasionally causing to "(primary started ...)" messages to be received, possibly because two MQTT
#       clients are running at the same time (first one hasn't fully disconnected yet)
    if not handler_finished:
        if action == "started":  # TODO: Temporary workaround, watch out for duplicate messages !
            if public.protocol:
                tags = ' '.join([str(tag) for tag in public.tags])
                payload_out = f"(add {public.topic_path} {public.protocol} {get_username()} ({tags}))"
                public.message.publish(registrar["topic_path"] + "/in", payload=payload_out)
        if action == "stopped" and public.terminate_registrar_not_found == True:
            terminate(1)

def set_registrar_handler(registrar_handler):
    private.registrar_handler = registrar_handler

def add_stream_handlers(
    task_start_handler, stream_frame_handler, task_stop_handler):
    add_task_start_handler(task_start_handler)
    add_stream_frame_handler(stream_frame_handler)
    add_task_stop_handler(task_stop_handler)
    add_message_handler(on_message_stream)

def add_stream_frame_handler(stream_frame_handler):
    private.stream_frame_handler = stream_frame_handler

def add_task_start_handler(task_start_handler):
    private.task_start_handler = task_start_handler

def add_task_stop_handler(task_stop_handler):
    private.task_stop_handler = task_stop_handler

def on_message_stream(topic, payload_in):
    print("Aiko V2: on_message_stream():")
    return False

def on_message(mqtt_client, userdata, message):
    payload_in = message.payload.decode("utf-8")
    _LOGGER.info(f"### on_message(): {message.topic}: {payload_in}")
    try:
        event.queue_message(message)
    except Exception as exception:
        print(traceback.format_exc())

def process_message_queue(message_queue):
    while message_queue.qsize():
        message = message_queue.get()
        payload_in = message.payload.decode("utf-8")
        _LOGGER.info(f"### process_message_queue(): {message.topic}: {payload_in}")
        if _LOGGER.isEnabledFor(DEBUG):
            _LOGGER.debug(f"message: {message.topic}: {payload_in}")

        message_handler_list = []
        for match_topic in message.topic, "#":
            if match_topic in private.message_handlers:
                message_handler_list.extend(private.message_handlers[match_topic])

        if len(message_handler_list) > 0:
            for message_handler in message_handler_list:
                try:
                    if message_handler(public, message.topic, payload_in):
                        return
                except Exception as exception:
                    payload_out = traceback.format_exc()
                    print(payload_out)
#                   public.message.publish(public.topic_log, payload=payload_out)

def process_pipeline_arguments(pipeline=None):
    if pipeline:
        public.service_name = pipeline[0]
        public.protocol = pipeline[1]
        tags_string = pipeline[2]
        topic_path = pipeline[3]

        public.tags = [ "name=" + public.service_name ]
        parse_tags(tags_string)

        public.topic_in = topic_path + "/in"
        public.topic_state = topic_path + "/state"

#       aks.initialise_pipeline_service({                    # TODO: Replace V1
#           "name":       public.service_name,
#           "protocol":   public.protocol,
#           "tags":       tags_string,
#           "topic_path": topic_path
#       })

def initialize(pipeline=None):
    process_pipeline_arguments(pipeline)

#   public.aks_info = aks.initialise(                       # TODO: Replace V1
#       on_message=on_message,
#       protocol=public.protocol,
#       tags=public.tags
#   )

# TODO: on_connect user handler ?
# TODO: on_message user handler ?  Note: Aiko V2 provides add_message_handler() instead
# TODO: Implement protocol stuff, see set_protocol()
# TODO: Implement tags stuff, e.g set_tags() ?

    add_message_handler(REGISTRAR_TOPIC, on_registrar_message)
    event.set_message_queue_handler(process_message_queue)

    lwt_topic = public.topic_state
    lwt_payload = "(stopped)"
    lwt_retain = False

    public.message = MQTT(on_message, private.message_handlers, lwt_topic, lwt_payload, lwt_retain)
    context = ContextManager(public, public.message)
# TODO: Wait for and connect to message broker and handle failure, discovery and reconnection

#   public.parameters = public.aks_info.parameters           # TODO: Replace V1

def process(loop_when_no_handlers=False, pipeline=None):
    initialize(pipeline)
#   wait_connected()
#   wait_parameters(0)
    event.loop(loop_when_no_handlers)
    if private.exit_status:
        sys.exit(private.exit_status)

def add_tags(tags):
    for tag in tags: public.tags.append(tag)

def get_parameter(name):                                     # TODO: Replace V1
#   return aks.get_parameter(name)
    return None

def parse_tags(tags_string):
    if tags_string:
        tags = tags_string.split(",")
        add_tags(tags)

def set_last_will_and_testament(lwt_topic, lwt_payload="(stopped)", lwt_retain=False):
    public.message.set_last_will_and_testament(lwt_topic, lwt_payload, lwt_retain)

def set_protocol(protocol):
    public.protocol = protocol

def set_terminate_registrar_not_found(terminate_registrar_not_found):
    public.terminate_registrar_not_found = terminate_registrar_not_found

def terminate(exit_status=0):
    private.exit_status = exit_status
    event.terminate()

def wait_connected():                                        # TODO: Replace V1
#   aks.wait_connected()
    pass

def wait_parameters(level):                                  # TODO: Replace V1
#   aks.wait_parameters(level)
    pass
