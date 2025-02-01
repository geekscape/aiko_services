# Usage: File
# ~~~~~~~~~~~
# aiko_pipeline create pipelines/text_pipeline_0.json -s 1 -sr -ll debug
#
# aiko_pipeline create pipelines/text_pipeline_0.json -s 1 -p rate 1.0
#
# aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
#   -p TextReadFile.data_batch_size 8
#
# aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
#   -p TextReadFile.data_sources file://data_in/in_{}.txt
#
# aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
#     -p TextWriteFile.path "file://data_out/out_{:02d}.txt"
#
# aiko_pipeline create pipelines/text_pipeline_0.json -s 1           \
#   -p TextReadFile.data_sources file://data_in/in_00.txt  \
#   -p TextTransform.transform titlecase                   \
#   -p TextWriteFile.data_targets file://data_out/out_00.txt
#
# Usage: Drop frame tests (local and remote)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# aiko_pipeline create pipelines/text_pipeline_1.json -s 1 -ll debug
#
# aiko_pipeline create pipelines/text_pipeline_2.json -s 1 -ll debug  # local
# aiko_pipeline create pipelines/text_pipeline_3.json      -ll debug  # remote
#
# Usage: ZMQ
# ~~~~~~~~~~
# aiko_pipeline create pipelines/text_zmq_pipeline_0.json -s 1 -sr  \
#            -ll debug -gt 10
#
# aiko_pipeline create pipelines/text_zmq_pipeline_0.json -s 1 -sr  \
#            -p TextReadZMQ.data_sources zmq://0.0.0.0:6502
#
# aiko_pipeline create pipelines/text_zmq_pipeline_1.json -s 1 -sr  \
#            -ll debug                                              \
#            -p TextReadFile.rate 2.0                               \
#            -p TextWriteZMQ.data_targets zmq://192.168.0.1:6502
#
# Resources
# ~~~~~~~~~
# - https://learning-0mq-with-pyzmq.readthedocs.io/en/latest/pyzmq/patterns/patterns.html
#
# To Do
# ~~~~~
# * ZMQ remote PipeElement that sends "content" out-of-band via ZMQ
#   * Compared to the default remote PipelineElement that uses in-band via MQTT
#   * Effectively ZMQ as another transport implementation :)
#
# - Support for "media type" encoding details for "text"
#   - Consider additional encoding information in out-of-band text records ?
#     - "frame_id" and/or "text:length:content" or "text/zip:length:content" ?
#
# - TextReadFile(s): Single file or list of files or directory
#   - Option: Each line is a record (streaming)
#   - Formatted as CR/LF records, JSON, XML, CSV
#
# - TextWriteFile(s): Single file or list of files or directory
#   - Option: Each line is a record (streaming)
#   - Formatted as CR/LF records, JSON, XML, CSV
#
# - TextFilter: line/word/character count, ...
# - TextTransform: strip(), ...
#
# - Rather than TextSample by frame ... sample by text count in [texts] input
#
# - Pre-processing / Post-processing, e.g abbrevations, acronyms
#   - Speech-To-Text: Words not easily recognised
#     - Example: Microphone --> Speech-To-Text --> Text
#   - Text-To-Speech: Poor pronouciation
#     - Example: Text --> Text-To-Speech --> Speaker
#
# - Text Framing for LLM

from typing import Tuple
from pathlib import Path

import aiko_services as aiko

__all__ = [
    "TextOutput", "TextReadFile", "TextReadZMQ",
    "TextSample", "TextTransform", "TextWriteFile", "TextWriteZMQ"
]

# --------------------------------------------------------------------------- #
# Useful for Pipeline output that should be all of the text processed

class TextOutput(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("text_output:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, texts) -> Tuple[aiko.StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {"texts": texts}

# --------------------------------------------------------------------------- #
# TextReadFile is a DataSource which supports ...
# - Individual text files
# - Directory of text files with an optional filename filter
# - TODO: Archive (tgz, zip) of text files with an optional filename filter
#
# parameter: "data_sources" is the read file path, format variable: "frame_id"
#
# Note: Only supports Streams with "data_sources" parameter

class TextReadFile(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("text_read_file:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, paths) -> Tuple[aiko.StreamEvent, dict]:
        texts = []
        for path in paths:
            try:
                with path.open("r") as file:
                    text = file.read()
                texts.append(text)
                self.logger.debug(f"{self.my_id()}: {path} ({len(text)})")
            except Exception as exception:
                diagnostic = f"Error loading text: {exception}"
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        return aiko.StreamEvent.OKAY, {"texts": texts}

# --------------------------------------------------------------------------- #

class TextReadTTY(aiko.DataSource):  # PipelineElement
    def __init__(self, context):
        context.set_protocol("text_read_tty:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        print('# Type "/?" for help and "/x" to exit')
        self.commands = {
            "/?":   (self._command_help,    "Help"),
            "//":   (None,                  "Escape sequence for '/'"),
            "/h":   (self._command_history, "List command line history"),
            "/h N": (self._command_history, "Execute command line 'N'"),
            "/x":   (self._command_exit,    "Exit")
        }
        stream.variables["tty_command_lines"] = []
        return super().start_stream(stream, stream_id)

    def _command_exit(self, stream, tokens):
        raise SystemExit("Process terminated")

    def _command_help(self, stream, tokens):
        for command, command_details in self.commands.items():
            print(f"{command:4s}: {command_details[1]}")
        return None

    def _command_history(self, stream, tokens):
        command_line = None
        tty_command_lines = stream.variables["tty_command_lines"]
        if len(tokens):
            if tokens[0].isdigit():
                index = int(tokens[0])
                if index < len(tty_command_lines):
                    command_line = tty_command_lines[index]
        else:
            for index, tty_command_line in enumerate(tty_command_lines):
                print(f"{index:03d}: {tty_command_line}")
        return command_line

    def _parse_command_line(self, stream, text):
        tokens = text.split()
        command = tokens[0] if len(tokens) else ""
        command_line = None
        if command in self.commands:
            command_function = self.commands[command][0]
            if command_function:
                command_line = command_function(stream, tokens[1:])
            else:
                command_line = text[3:]
        return command_line

    def process_frame(self, stream, records) -> Tuple[aiko.StreamEvent, dict]:
        texts = []
        for text in records:
            command_line = text
            save = True
            if command_line.startswith("/"):
                command_line = self._parse_command_line(stream, command_line)
                save = False
            if command_line:
                if save:
                    stream.variables["tty_command_lines"].append(command_line)
                texts.append(command_line)
        return aiko.StreamEvent.OKAY, {"texts": texts}
    #   return aiko.StreamEvent.DROP_FRAME, {}  # TODO: If command_line is None

# --------------------------------------------------------------------------- #
# TextReadZMQ is a DataSource which supports ...
# - TextWriteZMQ(DataTarget) ZMQ client --> TextReadZMQ(DataSource) ZMQ server
#   - Individual text records produced by ZMQ client and consumed by ZMQ server
#
# parameter: "data_sources" is the ZMQ server bind details (scheme_zmq.py)
#
# Note: Only supports Streams with "data_sources" parameter

class TextReadZMQ(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("text_read_zmq:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, records) -> Tuple[aiko.StreamEvent, dict]:
        texts = []
        for record in records:
            text = record.decode()
    #       if text.startswith("text:"):  # TODO: "text:length:content" ?
    #           tokens = text.split(":")
    #           text = tokens[2:][0]      # just the "content"
            texts.append(text)
            self.logger.debug(f"{self.my_id()}: {text} ({len(text)})")
        return aiko.StreamEvent.OKAY, {"texts": texts}

# --------------------------------------------------------------------------- #

class TextSample(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("text_sample:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, texts) -> Tuple[aiko.StreamEvent, dict]:
        sample_rate, _ = self.get_parameter("sample_rate", 1)
        if stream.frame_id % sample_rate:
            self.logger.debug(f"{self.my_id()}: frame dropped")
            return aiko.StreamEvent.DROP_FRAME, {}
        else:
            self.logger.debug(f"{self.my_id()}: frame not dropped")
            return aiko.StreamEvent.OKAY, {"texts": texts}

# --------------------------------------------------------------------------- #

class TextTransform(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("text_transform:0")
        context.get_implementation("PipelineElement").__init__(self, context)

        self.transforms = {
            "lowercase": lambda text: text.lower(),  # looks like this !
            "none":      lambda text: text,          # looks unchanged !
            "titlecase": lambda text: text.title(),  # Looks Like This !
            "uppercase": lambda text: text.upper()   # LOOKS LIKE THIS !
        }

    def process_frame(self, stream, texts) -> Tuple[aiko.StreamEvent, dict]:
        transform_type, found = self.get_parameter("transform")
        if not found:
            diagnostic = 'Must provide "transform" parameter'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        transform = self.transforms.get(transform_type, None)
        if not transform:
            diagnostic = f"Unknown text transform type: {transform_type}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        texts_transformed = []
        if transform_type == "none":
            texts_transformed = texts  # optimization :)
        else:
            for text in texts:
                transformed_text = transform(text)
                texts_transformed.append(transformed_text)

        return aiko.StreamEvent.OKAY, {"texts": texts_transformed}

# --------------------------------------------------------------------------- #
# TextWriteFile is a DataTarget with a text string parameter
#
# parameter: "data_targets" is the write file path, format variable: "frame_id"
#
# stream.variables["target_path_template"] indicates whether ...
# - False: All text records should be written to the same "target_path"
# - True:  Each text record is written to a different "target_path_template"
#
# Note: Only supports Streams with "data_targets" parameter

class TextWriteFile(aiko.DataTarget):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("text_write_file:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        stream_event, diagnostic = super().start_stream(stream, stream_id)
        if stream_event != aiko.StreamEvent.OKAY:
            return stream_event, diagnostic

        if not stream.variables["target_path_template"]:
            path = stream.variables["target_path"]
            self.logger.debug(f"{self.my_id()}: {path}")
            try:
                stream.variables["target_file"] = Path(path).open("w")
            except Exception as exception:
                diagnostic = f"Error saving text: {exception}"
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, texts) -> Tuple[aiko.StreamEvent, dict]:
        for text in texts:
            if stream.variables["target_path_template"]:
                path = stream.variables["target_path"]
                path = path.format(stream.variables["target_file_id"])
                stream.variables["target_file_id"] += 1

                self.logger.debug(f"{self.my_id()}: {path}")
                try:
                    with Path(path).open("w") as file:
                        file.write(text)
                except Exception as exception:
                    diagnostic = f"Error saving text: {exception}"
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
            else:
                try:
                    stream.variables["target_file"].write(f"{text}")
                except Exception as exception:
                    diagnostic = f"Error saving text: {exception}"
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        stream_event, diagnostic = super().stop_stream(stream, stream_id)
        if "target_file" in stream.variables:
            stream.variables["target_file"].close()
            del stream.variables["target_file"]
        return stream_event, diagnostic

# --------------------------------------------------------------------------- #

class TextWriteTTY(aiko.DataTarget):  # PipelineElement
    def __init__(self, context):
        context.set_protocol("text_write_tty:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, texts) -> Tuple[aiko.StreamEvent, dict]:
        for text in texts:
            print(text)
        command_lines_length = len(stream.variables["tty_command_lines"])
        tty_prompt, _ = self.get_parameter("tty_prompt", default="> ")
        tty_prompt = f"{command_lines_length:03d}:{tty_prompt}"
        print(f"{tty_prompt}", flush=True, end="")
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
# TextWriteZMQ is a DataTarget which supports ...
# - TextWriteZMQ(DataTarget) ZMQ client --> TextReadZMQ(DataSource) ZMQ server
#   - Individual text records produced by ZMQ client and consumed by ZMQ server
#
# parameter: "data_targets" is the ZMQ connect details (scheme_zmq.py)
#
# Note: Only supports Streams with "data_targets" parameter

class TextWriteZMQ(aiko.DataTarget):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("text_write_zmq:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, texts) -> Tuple[aiko.StreamEvent, dict]:
        media_type = "text"                            # TODO: "text/zip" ?
        for text in texts:
     #      text = f"{media_type}:{len(text)}:{text}"  # "text:length:content" ?
            stream.variables["target_zmq_socket"].send(text.encode())

        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
