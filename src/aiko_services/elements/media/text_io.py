# Usage
# ~~~~~
# cd aiko_services/elements
# aiko_pipeline create pipeline_text_io_0.json --stream_id 1  \
#   --stream_parameters TextReadFile.path text.txt
#
# To Do
# ~~~~~
# - TextReadFile(s): Single file or list of files or directory
#   - Option: Each line is a record (streaming)
#   - Formatted as CR/LF records, JSON, XML, CSV
# - TextWriteFile(s): Single file or list of files or directory
#   - Option: Each line is a record (streaming)
#   - Formatted as CR/LF records, JSON, XML, CSV
# - TextFilters: strip(), lower(), upper(), line/word/character count, ...
# - Pre-processing / Post-processing, e.g abbrevations, acronyms
#   - Speech-To-Text: Words not easily recognised
#     - Example: Microphone --> Speech-To-Text --> Text
#   - Text-To-Speech: Poor pronouciation
#     - Example: Text --> Text-To-Speech --> Speaker
# - Text Framing for LLM

from typing import Tuple
from pathlib import Path

import aiko_services as aiko

# --------------------------------------------------------------------------- #
# TextReadFile is a DataSource with a text file "path" string parameter
#
# To Do
# ~~~~~
# - Check: Supports both Streams and direct process_frame() calls
#
# Test
# ~~~~
# export AIKO_LOG_LEVEL=DEBUG; export AIKO_LOG_MQTT=false
# aiko_pipeline create pipeline_text_io.json -fd "(path: z_in_01.txt)"
# aiko_pipeline create pipeline_text_io.json -s 1
# aiko_pipeline create pipeline_text_io.json -s 1  \
#                                         -sp TextReadFile.path z_in_01.txt

class TextReadFile(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        path, found = self.get_parameter("path")
        if not found:
            diagnostic = 'Must provide text file "path" parameter'
            return aiko.StreamEvent.ERROR, diagnostic

        self.create_frame(stream, {"path": path})
        return aiko.StreamEvent.OKAY, None

    def process_frame(self, stream, path) -> Tuple[bool, dict]:
        self.logger.debug(f"{self._id(stream)}: text file: {path}")

        if not Path(path).exists():
            diagnostic = f'Text file "{path}" does not exist'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        try:
            with open(path, "r") as file:
                text = file.read()
        except Exception as exception:
            diagnostic = f"Error loading text file: {exception}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        self.logger.debug(f"Text: {text}")
        return aiko.StreamEvent.OKAY, {"text": text}

# --------------------------------------------------------------------------- #

class TextFilter(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, text) -> Tuple[bool, dict]:
    #   option, _ = self.get_parameter("option")
        text = text.upper()
        return aiko.StreamEvent.OKAY, {"text": text}

# --------------------------------------------------------------------------- #
# TextWriteFile is a DataTarget with a text string parameter
#
# To Do
# ~~~~~
# - Check: Supports both Streams and direct process_frame() calls
#
# - File path template, e.g variable frame_id
# - Consider what causes Stream to be closed, e.g single frame processed ?
#
# Test
# ~~~~
# export AIKO_LOG_LEVEL=DEBUG; export AIKO_LOG_MQTT=false
#                                          -sp TextWriteFile.path z_out_01.txt

class TextWriteFile(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, text) -> Tuple[bool, dict]:
        path, found = self.get_parameter("path")
        if not found:
            diagnostic = 'Must provide text file "path" parameter'
            return aiko.StreamEvent.ERROR, diagnostic

    #   path = path_template  # TODO: Implement path_template processing

        self.logger.debug(f"{self._id(stream)}: text file path: {path}")

        try:
            with open(path, "w") as file:
                file.write(text)
        except Exception as exception:
            diagnostic = f"Error saving text file: {exception}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        self.logger.debug(f"Text: {text}")
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
