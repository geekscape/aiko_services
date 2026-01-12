# Usage
# ~~~~~
# aiko_pipeline create pipelines/colab_pipeline_1.json
#
# aiko_chat
# > :change_change yolo

import os
from typing import Tuple

import aiko_services as aiko

# --------------------------------------------------------------------------- #

class ConvertDetections(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("convert_detections:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, overlay) -> Tuple[aiko.StreamEvent, dict]:
        message = ""
        for object in overlay["objects"]:
            delimiter = "," if message else ""
            message += f"{delimiter}{object["name"]}"  # object["confidence"]
        return aiko.StreamEvent.OKAY, {"message": message}

# --------------------------------------------------------------------------- #

class ChatServer(aiko.Actor):  # Dummy class, methods won't be invoked
    pass

class MQTTPublish(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("mqtt_publish:0")
        context.call_init(self, "PipelineElement", context)
        self.chat_server_topic = None

    def discovery_add_handler(self, service_details, service):
        print(f"Connected {service_details[1]}: {service_details[0]}")
        chat_channel = self.share["chat_channel"]
        self.chat_server_topic = f"{service_details[0]}/{chat_channel}"

    def discovery_remove_handler(self, service_details):
        self.print(f"Disconnected {service_details[1]}: {service_details[0]}")
        self.chat_server_topic = None

    def start_stream(self, stream, stream_id):
        chat_channel, _ = self.get_parameter("chat_channel", "yolo")
        self.share["chat_channel"] = chat_channel

        username, _ = self.get_parameter("username", "<env_var>")
        if username == "<env_var>":
            username = os.environ.get("USER")
        self.share["username"] = username

        details, found = self.get_parameter("service_filter")

        if found:
            name = details["name"] if details["name"] else "*"
            protocol = details["protocol"] if details["protocol"] else "*"
            service_filter = aiko.ServiceFilter(
                "*", name, protocol, "*", "*", "*")

            service_discovery, service_discovery_handler = aiko.do_discovery(
                ChatServer, service_filter,
                self.discovery_add_handler, self.discovery_remove_handler)
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, message) -> Tuple[aiko.StreamEvent, dict]:
        if self.chat_server_topic and message:
            payload = f"{self.share["username"]}:{message}"
            aiko.process.message.publish(self.chat_server_topic, payload)

        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
