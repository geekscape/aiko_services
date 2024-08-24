# Usage
# ~~~~~
# cd aiko_services/elements
# export AIKO_LOG_LEVEL=DEBUG; export AIKO_LOG_MQTT=false
# aiko_pipeline create pipeline_text_io_0.json --stream_id 1   \
#   --stream_parameters PE_TextReadFile.path  data/in_00.txt   \
#   --stream_parameters PE_TextWriteFile.path data/out_00.txt
#
# To Do
# ~~~~~
# - PE_TextReadFile(s): Single file or list of files or directory
#   - Option: Each line is a record (streaming)
#   - Formatted as CR/LF records, JSON, XML, CSV
#
# - PE_TextWriteFile(s): Single file or list of files or directory
#   - Option: Each line is a record (streaming)
#   - Formatted as CR/LF records, JSON, XML, CSV
#
# - PE_TextFilters: strip(), lower(), upper(), line/word/character count, ...
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

__all__ = ["PE_TextReadFile", "PE_TextConvert", "PE_TextWriteFile"]

def containsAll(source: str, match: chr):  # TODO: Refactor common code
    return False not in [character in source for character in match]

# --------------------------------------------------------------------------- #
# PE_TextReadFile is a DataSource with a text file "path" string parameter
#
# Supports both Streams and direct process_frame() calls ?
#
# To Do
# ~~~~~
# - Check: Supports both Streams and direct process_frame() calls
#
# Test
# ~~~~
# export AIKO_LOG_LEVEL=DEBUG; export AIKO_LOG_MQTT=false
# aiko_pipeline create pipeline_text_io.json -fd "(path: in_01.txt)"
# aiko_pipeline create pipeline_text_io.json -s 1
# aiko_pipeline create pipeline_text_io.json -s 1  \
#                                      -sp PE_TextReadFile.path in_01.txt

class PE_TextReadFile(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        path, found = self.get_parameter("path")
        if not found:
            diagnostic = 'Must provide file "path" parameter'
            return aiko.StreamEvent.ERROR, diagnostic

        self.create_frame(stream, {"path": path})
        return aiko.StreamEvent.OKAY, None

    def process_frame(self, stream, path) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.debug(f"{self.my_id()}: path: {path}")

        if not Path(path).exists():
            diagnostic = f'Text file "{path}" does not exist'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        try:
            with open(path, "r") as file:
                text = file.read()
        except Exception as exception:
            diagnostic = f"Error loading path: {exception}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        self.logger.debug(f"Text: {text}")
        return aiko.StreamEvent.OKAY, {"text": text}

# --------------------------------------------------------------------------- #

class PE_TextConvert(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, text) -> Tuple[aiko.StreamEvent, dict]:
    #   option, _ = self.get_parameter("option")
        text = text.upper()
        return aiko.StreamEvent.OKAY, {"text": text}

# --------------------------------------------------------------------------- #
# PE_TextWriteFile is a DataTarget with a text string parameter
#
# To Do
# ~~~~~
# - Check: Supports both Streams and direct process_frame() calls
#
# - Consider what causes Stream to be closed, e.g single frame processed ?
#
# Test
# ~~~~
# export AIKO_LOG_LEVEL=DEBUG; export AIKO_LOG_MQTT=false
# aiko_pipeline create pipeline_text_io.json -s 1  \
#                                      -sp PE_TextWriteFile.path out_01.txt

class PE_TextWriteFile(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, text) -> Tuple[aiko.StreamEvent, dict]:
        path, found = self.get_parameter("path")
        if not found:
            diagnostic = 'Must provide file "path" parameter'
            return aiko.StreamEvent.ERROR, diagnostic

        if containsAll(path, "{}"):
            path = path.format(stream.frame_id)
        self.logger.debug(f"{self.my_id()}: text write file path: {path}")

        try:
            with open(path, "w") as file:
                file.write(text)
        except Exception as exception:
            diagnostic = f"Error saving path: {exception}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        self.logger.debug(f"Text: {text}")
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
