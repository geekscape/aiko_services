---
# Release Notes v0.6

**Full Changelog**: https://github.com/geekscape/aiko_services/compare/v0.5...v0.6

## Features

* Updated Python package dependency version numbers in *pyproject.toml*

* Significant improvements for media primitives such as text, images, video
  and web cameras.  Now supports various different types of *media URL scheme*
  via DataSource and DataTarget, which are PipelineElements that are at
  head or tail of a Pipeline.  The overall naming and implementation details
  are now more consistent.
  For example, use of *aiko.StreamEvent.(OKAY|STOP|ERROR)*

* Refactored Streams and Frames dictionary to a more robust approach using
  Python dataclasses.  Now supports multiple concurrent Frames and per-Stream
  variable.

* Significant improvements for YOLO and face detection examples.
  Also introduced an Aruco Marker detector

* Added PipelineElement *PE_Inspect*, which writes selected *output* values
  to either the terminal console, log or a file

* Improved PipelineElement loading to provide proper diagnostic messages
  should there be a problem

* Improved Pipeline robustness to handle various PipelineElement exceptions
  during calls to start_stream(), frame_generator(), process_frame() and
  stop_stream()

* Pipeline output is determined by the output of the tail (last)
  PipelineElement.  This also allows Pipeline output be either returned
  to a specified queue ... or to a calling parent Pipeline ... or to the
  Pipeline's standard output MQTT topic path

* S-Expressions now support both single-quoted and double-quoted strings

* S-Expressions now serialize and deserialize *None* and *0:*, which fixed
  a problem with the PE_Metrics PipelineElement

* Improved stack trace information for easier debugging for exceptions raised
  by Actor:Message.invoke()

* ActorImpl._post_message() now supports a *delay* parameter for invoking
  methods in the future.  Initially used to wait until remote Pipeline
  lifecycle state is ready, before invoking remote Pipeline.create_stream()

* By default, AIKO_LOG_MQTT environment variable is *all*, meaning that logging
  is sent to both the console and MQTT

## Testing

* Aiko Services *main/* and *elements/media/* code testing using Python 3.13.0

* Some *examples/* only work with Python 3.12.7, due to third-party
  dependencies not being updated and released for 3.13.0

    * Python package *opencv-python* works on Python 3.13.0
    * Python package *langchain*, Ollama and Llama 3.1 LLM works on Python 3.13.0
    * Python package *deepface* works on with Python 3.12.7, but not 3.13.0
    * Python package *torch* works on with Python 3.12.7, but not 3.13.0
    * Ultralytics YOLOv8 example works on Python 3.12.7, but not 3.13.0

## Bug Fixes

* Fixed issues with running single process Pipelines without needing MQTT or
  Aiko Services Registrar.  Improve *main/message/mqtt.py* to only raise a
  SystemError (and not always exit), depending upon whether an MQTT connection
  is required

* Removed incorrect validation diagnostic message in PipelineImpl.validate()

* Fixed issues in Pipeline.create_frame() to handle stream arguments correctly

* Corrected imports in *media/text_io.py* to resolve an issue with
  *common_io.py:contains_all()*

* Fixed issue with multiple data sources in *image_io.py*

---
