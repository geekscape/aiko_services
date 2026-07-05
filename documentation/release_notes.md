---
# Release Notes v0.7

**Full Changelog**: https://github.com/geekscape/aiko_services/compare/v0.6...v0.7

## Features

* Introduced HyperSpace: hyperlinked distributed Services, providing
  Categories (Services that refer to other Services) and Dependencies,
  backed by file-system Storage persistence (*StorageFileImpl*).
  Includes the *aiko_hyperspace* CLI with distributed sub-commands
  *initialize*, *add*, *create*, *destroy*, *list [--recursive]*, *remove*
  and *update* ... plus the *aiko_storage_file* CLI for direct Storage
  commands.  See *src/aiko_services/examples/hyperspace/ReadMe.md*

* Significantly improved ProcessManager, which is now an Actor with a
  distributed CLI to create, list and destroy processes ... and can run
  a ProcessDefinition file.  Multiple ProcessManagers, typically on
  different hosts, are referred to by *name* (defaults to the `hostname`)

* Added Hooks (*main/hook.py*), an extensible mechanism enabling custom
  framework extensions, with initial Actor (message invocation) and
  Pipeline (process frame) hooks.  Hook handlers now receive the
  PipelineElement instance (PR#44)

* Improved Component Interface initialization via new
  *context.call_init(self, "InterfaceName", context, ...)*, which ensures
  that Interface based super-classes are only initialized once.
  All *elements/*, *examples/*, *main/* and *tests/* code updated

* Pipeline improvements ...

    * New *aiko_pipeline list* and *aiko_pipeline update* CLI commands.
      Update an existing Pipeline: create Streams and Frames, set
      parameters and change Pipeline / PipelineElement log levels
      on-the-fly, e.g *--log_level debug_all*
    * Pipeline Graphs now support multiple Graph Paths, selected via
      *create_stream(..., graph_path=...)* or per-frame
      *create_frame(..., graph_path=...)*.  Note: minor API break for
      *PipelineImpl.create_pipeline()*, which adds the *graph_path* argument
    * PipelineDefinition global parameters *_create_stream_* (automatically
      create a Stream) and *_destroy_stream_exit_* (terminate the Pipeline
      when the given Stream is destroyed)
    * Implemented *StreamEvent.DROP_FRAME*, skipping the remaining
      PipelineElements and continuing with the next Frame ... for both
      local and remote (distributed) Pipelines
    * Experimental distributed Streams sliding window protocol, enabled
      via *aiko_pipeline create --windows*
    * Frame generators may return a list of *frame_data* to create multiple
      Frames at once ... and Frame creation self-throttles when the
      Pipeline message mailbox is busy
    * Added memory usage metrics for the process, Frames and
      PipelineElements
    * PipelineDefinition may specify *log_level* for the Pipeline or
      specific PipelineElements
    * Note: *aiko_pipeline create --stream_parameters* (-sp) has been
      replaced by *--parameters* (-p)

* Refactored DataScheme framework out of *elements/media/common_io\*.py*
  into *main/scheme.py* and *main/source_target.py* ... **may affect
  third-party DataSource and DataTarget imports**.  DataSchemes are now
  modular plug-ins, currently *file://*, *tty://* (console text input /
  output), *zmq://* (out-of-band media transfer that avoids loading the
  MQTT server) and *rtsp://* (RTSP video cameras)

* New PipelineElements: ControlFlow *Loop* (*elements/control/*),
  *Expression* for evaluating S-Expressions over Frame data, e.g
  conditionals and defining / deleting / renaming *process_frame()*
  arguments (*elements/utilities/*), *Inspect* and *Metrics* promoted from
  *examples/* into *elements/observe/*, *Mock* and *NoOp* ... plus media
  elements *ImageOverlayFilter*, *ImageSquareCenterCrop*, *VideoReadRTSP*
  and *VideoWriteFiles* (fixed duration video clips stored in
  "yyyy/mm/dd/hh" directory paths)

* Improved Message Transport robustness with *ConnectionState* and
  *MessageState* updates for the MQTT server Connection, so that Services,
  Actors and Pipelines can more robustly manage sending and retrying
  remote function invocations.  Diagnose via *AIKO_LOG_LEVEL_PROCESS=DEBUG*

* Improved Service Discovery with consistent *do_discovery()*,
  *do_command()* and *do_request()* methods, used throughout ... see the
  *examples/aloha_honua/aloha_honua_[123].py* remote function call examples

* Improved Dashboard with a Services list Filter (press "f"), which can
  selectively show Service protocol types and reduces clutter for
  Processes hosting multiple Services ... plus pop-up dialogues when the
  MQTT server and/or Aiko Services Registrar can't be found

* MQTT logging now "rolls-up" duplicate log messages into a single
  "Repeated message count: N", controlled by *AIKO_LOG_REPEAT_PERIOD*
  (default 6 seconds)

* Registrar now shares *aiko.id* as an EventualConsistency variable, an
  aid to determining which Aiko Services "git commit" each Service uses

* New and improved examples: virtual robot simulating a 3D world using the
  Panda3D physics engine with an attached Machine Learning Pipeline,
  XGO-Mini 2 robot integration, YOLOE "Real-Time Seeing Anything",
  Google Colab support (web browser webcam images, audio,
  Speech-To-Text and Text-To-Speech) and *examples/system_pipelines/*
  combining a main Pipeline with a remote YOLOE detection Pipeline

* Added *documentation/concepts/*, one concept document per file covering
  the entire Aiko Services framework (runtime foundations, composition,
  messaging, Services, Pipelines, tools and utilities) ... and
  *documentation/elements/*, covering the PipelineElement library

## Testing

* Aiko Services now supports Python 3.9.7 through to 3.14.2
  (see *pyproject.toml*)

* Added GitHub Actions Continuous Integration, which runs Python *flake8*
  lint checks for critical syntax and runtime-related issues

* Added unit tests for Hooks, Pipeline Graphs and the Stream lock ...
  plus *tests/chaos/network_chaos_monkey.py* for seriously testing
  distributed systems failures (MQTT server, system and application
  Services)

## Bug Fixes

* Fixed Stream *state* race conditions and *stream.lock* acquire / release
  problems in *create_stream()*, *destroy_stream()*, frame generation and
  frame processing (PR#42, PR#45) ... locks are now correctly released
  under all circumstances, including *StreamEvent.ERROR*

* Fixed *stream_id* handling to always be a string type, which fixes
  "stream not found" warnings and a memory leak where completed
  *stream.frames* were not released

* Fixed distributed Pipeline robustness: remote *create_stream()* and
  *process_frame()* invocations are postponed until the remote Pipeline
  has been discovered and is ready ... and remote Pipeline discovery no
  longer creates superfluous remote proxy PipelineElement instances

* Fixed GStreamer *video_reader.py* memory leak caused by an unmanaged
  duplicate buffer ... and prevented the GStreamer C code from overwriting
  Python *image* contents by copying the image buffer

* Fixed *utilities/parser.py* S-Expression parsing of the empty string,
  generation of the empty string ... and Canonical S-Expression tokens
  (*length:data*) containing new-line characters, which avoids unexpected
  token truncation

* Fixed webcam capture on macOS 26 (Tahoe), which now requires OpenCV
  *cv2.CAP_AVFOUNDATION* and an integer camera index

* Fixed Dashboard problems: switching to the Log page or a custom Service
  page for the first time immediately switched back ... and filtering
  Service types caused the selected Service to reference the wrong Service

* Fixed Registrar to correctly remove a Service when the Service is
  removed but its Process is still running ... and to reset
  *service_count* when the MQTT server restarts

* Fixed *utc_iso8601.py* to replace deprecated *datetime.utcnow()* ... and
  replaced all *time.time()* usage with *time.monotonic()* for measuring
  elapsed time

* Fixed PipelineDefinition file parsing ResourceWarning by using a file
  open context manager (PR#47) ... and Pipeline frame generator rate
  timing now sleeps for the correct difference between the expected start
  time and the current time (PR#29)

* Fixed *pyproject.toml* so that *pip install -e .* no longer hangs due to
  large media files in *src/aiko_services/examples/*

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
