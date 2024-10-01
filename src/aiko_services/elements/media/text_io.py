# Usage
# ~~~~~
# aiko_pipeline create text_pipeline_0.json -s 1 -sr -ll debug
#
# aiko_pipeline create text_pipeline_0.json -s 1 -sp rate 1.0
#
# aiko_pipeline create text_pipeline_0.json -s 1  \
#   -sp TextReadFile.data_batch_size 8
#
# aiko_pipeline create text_pipeline_0.json -s 1  \
#   -sp TextReadFile.data_sources file://data_in/in_{}.txt
#
# aiko_pipeline create text_pipeline_0.json -s 1  \
#     -sp TextWriteFile.path "file://data_out/out_{:02d}.txt"
#
# aiko_pipeline create text_pipeline_0.json -s 1            \
#   -sp TextReadFile.data_sources file://data_in/in_00.txt  \
#   -sp TextTransform.transform titlecase                   \
#   -sp TextWriteFile.data_targets file://data_out/out_00.txt
#
# To Do
# ~~~~~
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
from aiko_services.elements.media import contains_all, DataSource, DataTarget

__all__ = ["TextOutput", "TextReadFile", "TextTransform", "TextWriteFile"]

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

class TextReadFile(DataSource):  # common_io.py PipelineElement
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
                return aiko.StreamEvent.ERROR,  \
                        {"diagnostic": f"Error loading text: {exception}"}

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
            return aiko.StreamEvent.ERROR,  \
                {"diagnostic": 'Must provide "transform" parameter'}

        transform = self.transforms.get(transform_type, None)
        if not transform:
            return aiko.StreamEvent.ERROR,  \
                {"diagnostic": f"Unknown text transform type: {transform_type}"}

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
# Note: Only supports Streams with "data_targets" parameter

class TextWriteFile(DataTarget):  # common_io.py PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("text_write_file:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, texts) -> Tuple[aiko.StreamEvent, dict]:
        for text in texts:
            path = stream.variables["target_path"]
            if contains_all(path, "{}"):
                path = path.format(stream.variables["target_file_id"])
                stream.variables["target_file_id"] += 1
            self.logger.debug(f"{self.my_id()}: {path}")

            try:
                with Path(path).open("w") as file:
                    file.write(text)
            except Exception as exception:
                return aiko.StreamEvent.ERROR,  \
                       {"diagnostic": f"Error saving text: {exception}"}

        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
