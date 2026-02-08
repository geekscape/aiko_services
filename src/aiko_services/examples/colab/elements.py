# Usage
# ~~~~~
# aiko_pipeline create pipelines/colab_pipeline_1.json -ll debug_all
#
# aiko_chat
# > :change_change yolo
#
# To Do
# ~~~~~
# - For "encode_silence()", consider caching "silence", which saves 40 ms 🤔

from abc import abstractmethod
import numpy as np
import os
import subprocess
import tempfile
from typing import Optional, Tuple

import aiko_services as aiko

# --------------------------------------------------------------------------- #

DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_CHANNELS = 1
DEFAULT_DURATION_SEC = 1.0

def encode_silence(
    mime_type: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    duration_sec: float = DEFAULT_DURATION_SEC
    ) -> bytes:

    # Generate PCM silence (float32)
    num_samples = int(sample_rate * duration_sec)
    silence = np.zeros((num_samples, channels), dtype=np.float32)

    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as pcm_file, \
         tempfile.NamedTemporaryFile(delete=False) as out_file:

        silence.tofile(pcm_file.name)

        if "opus" in mime_type:
            codec = "libopus"
            container = "webm" if "webm" in mime_type else "ogg"
        elif "wav" in mime_type:
            codec = "pcm_f32le"
            container = "wav"
        else:
            codec = "libopus"
            container = "webm"

        out_file_path = f"{out_file.name}.{container}"

        ffmpeg_command = ["ffmpeg", "-y", "-f", "f32le", "-ar",
            str(sample_rate), "-ac", str(channels), "-i", pcm_file.name,
            "-t", str(duration_sec), "-c:a", codec, out_file_path]

        subprocess.run(ffmpeg_command,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        with open(out_file_path, "rb") as f:
            return f.read()

# --------------------------------------------------------------------------- #

class AudioPassThrough(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("audio_pass_through:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, audio, mime_type)  \
        -> Tuple[aiko.StreamEvent, dict]:

        self.logger.info(f"{self.my_id()}: len: {len(audio)}, {mime_type}")
        return aiko.StreamEvent.OKAY, {"audio": audio, "mime_type": mime_type}

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

class ChatServer(aiko.Actor):
    @abstractmethod
    def send_message(self, username, recipients, message):
        pass

class MQTTPublish(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("mqtt_publish:0")
        context.call_init(self, "PipelineElement", context)
        self.chat_server = None
        self.chat_server_topic = None

    def discovery_add_handler(self, service_details, service):
        print(f"Connected {service_details[1]}: {service_details[0]}")
        chat_channel = self.share["chat_channel"]
        self.chat_server = service
        self.chat_server_topic = f"{service_details[0]}/{chat_channel}"

    def discovery_remove_handler(self, service_details):
        print(f"Disconnected {service_details[1]}: {service_details[0]}")
        self.chat_server = None
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
        if message:
            message = f"{self.share['username']}:{message}"

            if self.chat_server:
                username = self.share["username"]
                recipients = [self.share["chat_channel"]]
                self.chat_server.send_message(username, recipients, message)

        #   if self.chat_server_topic:
        #       aiko.process.message.publish(self.chat_server_topic, payload)

        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
