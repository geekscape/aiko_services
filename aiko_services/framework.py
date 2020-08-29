# To Do
# ~~~~~
# - Rename "framework.py" to "service.py" and create a Service class ?
# - Implement Aiko class with "class public variables" becoming Aiko class instance variables
#   - "class private" becomes one of the Aiko class instance variables
# - Store Aiko class instance as the "ContextManager.__init__(aiko=)" parameter
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

import time
import traceback

import aiko_services.event as event
from aiko_services.message import MQTT
from aiko_services.utilities import ContextManager, parse

# import aiko_services.framework as aks                      # TODO: Replace V1

class private:
    message_handlers = {}
    service_registrar_handler = None
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
    topic_in = "test/host/pid/in"        # TODO: Determine topic path
    topic_state = "test/host/pid/state"  # TODO: Determine topic path

SERVICE_REGISTRAR_PROTOCOL = "au.com.silverpond.protocol.service_registrar:0"
SERVICE_REGISTRAR_TOPIC = f"{public.namespace}/service/registrar"

def add_message_handler(topic, message_handler):
    if not topic in private.message_handlers:
        private.message_handlers[topic] = []
    private.message_handlers[topic].append(message_handler)

def add_service_registrar_handler(service_registrar_handler):
    if not private.service_registrar_handler:
        add_message_handler(SERVICE_REGISTRAR_TOPIC, on_service_registrar_message)
    private.service_registrar_handler = service_registrar_handler

def on_service_registrar_message(aiko_, topic, payload_in):
    if private.service_registrar_handler:
        command, parameters = parse(payload_in)
        if command == "primary" and len(parameters) == 2:
            topic_path = parameters[0]
            timestamp = parameters[1]
            private.service_registrar_handler(public, "add", topic_path, timestamp)
        if command == "nil":
            private.service_registrar_handler(public, "remove", None, None)

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
#               public.message.publish(public.topic_log, payload=payload_out)

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

# TODO: check_service_manager ?
# TODO: on_connect user handler ?
# TODO: on_message user handler ?  Note: Aiko V2 provides add_message_handler() instead
# TODO: on_service_registrar user handler ?
# TODO: Implement protocol stuff, see set_protocol()
# TODO: Implement tags stuff, e.g set_tags() ?

    if public.protocol == SERVICE_REGISTRAR_PROTOCOL:
        lwt_topic = SERVICE_REGISTRAR_TOPIC
        lwt_retain = True
    else:
        lwt_topic = public.topic_state
        lwt_retain = False

    public.message = MQTT(on_message, private.message_handlers, lwt_topic, lwt_retain)
    context = ContextManager(public, public.message)
# TODO: Wait for and connect to message broker and handle failure, discovery and reconnection

#   public.parameters = public.aks_info.parameters           # TODO: Replace V1
#   public.topic_log = public.aks_info.TOPIC_LOG             # TODO: Replace V1
#   public.topic_out = public.aks_info.TOPIC_OUT             # TODO: Replace V1

def process(pipeline=None):
    initialize(pipeline)
#   wait_connected()
#   wait_parameters(0)
#   wait_terminated()
    event.loop()

def get_parameter(name):                                     # TODO: Replace V1
#   return aks.get_parameter(name)
    return None

def parse_tags(tags_string):
    if tags_string:
        tags = tags_string.split(",")
        for tag in tags: public.tags.append(tag)

def set_protocol(protocol):
    public.protocol = protocol

def wait_connected():                                        # TODO: Replace V1
#   aks.wait_connected()
    pass

def wait_parameters(level):                                  # TODO: Replace V1
#   aks.wait_parameters(level)
    pass

def wait_terminated():                                       # TODO: Replace V1
#   aks.wait_terminated()
    pass
