---
title: Aiko Services release notes
description: Release notes for each Aiko Services version — GitHub full
  changelog link, features, testing and bug fixes — most recent release
  first
type: release-notes
audience: [developers, end-users]
status: operational
ste: false
version: "0.8-dev"
last_updated: 2026-08-01
---

# Aiko Services release notes

One section per release, most recent first.  Each release provides the
GitHub full changelog link and summarizes the noteworthy features, testing
and bug fixes.

**Language rule (adopted 2026-07-31).** Write each new release section in
ASD-STE100 Simplified Technical English, at the `adapted` level of
[constitution/t_04_SimplifiedTechnicalEnglish.md](constitution/t_04_SimplifiedTechnicalEnglish.md).
This rule applies to v0.8 and to each release after it. The v0.6
(human-written) and v0.7 (A.I-written) sections stay unchanged, because
they are a historical record. Thus the front-matter `ste:` field of this
document stays `false`: the document as a whole is not STE, but its new
sections are.

---

## Release Notes v0.8 (unreleased, in development)

**Full Changelog**: https://github.com/geekscape/aiko_services/compare/v0.7...v0.8

### Features

* Classes may now omit the *__init__()* method entirely when they need no
  constructor arguments beyond *context* and no explicit super-class
  initialization: the composition engine synthesizes the cooperative
  constructor, and an optional *PROTOCOL* class attribute replaces
  *context.set_protocol(...)*.  An explicit *__init__()* always takes
  precedence, so all existing code is unaffected

    ```python
    class AlohaHonua(aiko.Actor):    # no __init__() required
        PROTOCOL = "aloha_honua:0"

        def aloha(self, name):
            self.logger.info(f"Aloha {name} !")
    ```

* Eventual-consistency shared state now follows the standard Interface /
  Implementation composition style: *ECProducer* and *ECConsumer* are
  Interfaces implemented by *ECProducerImpl* and *ECConsumerImpl*, with
  new *ec_producer_args()* and *ec_consumer_args()* factories.
  Alternative implementations can now be substituted per composition,
  for example when testing

* New *ECCache*: a general local replica of the shared variables of any
  remote Service.  *ECCache* keeps one leased, filtered *ECConsumer*
  subscription for each Service that matches a *ServiceFilter*.  Each
  subscription feeds a local cache, which gives a synchronous,
  non-blocking *get()* and optional filtered "variable updated"
  call-backs (for example, water marks).  Thus a remote getter becomes a
  local read.  *ECCache* makes the *ServicesCache* pattern of the
  Dashboard available to each Service.  To construct one, use
  *compose_instance(ECCacheImpl, ec_cache_args(service, service_filter))*

* The Registrar Interface now declares its public API — *service_add()*,
  *service_remove()*, *services_share()* and *services_history()* — as
  real, documented methods that *RegistrarImpl* implements.  The wire
  commands *(add ...)*, *(remove ...)*, *(share ...)* and *(history ...)*
  are unchanged.  They now parse and delegate onto those methods.  The
  Recorder Interface likewise declares *recorder_handler()*

* Public API docstrings: the new and updated Interfaces (*ECProducer*,
  *ECConsumer*, *ECCache*, *Registrar*, *Recorder*, *Hooks*) document
  each method's contract, arguments, wire form and reply convention

* Every concepts document (*documentation/concepts/*) now links directly
  to its source code file at the top of its Overview section

* Aiko Services adopts **ASD-STE100 Simplified Technical English** (STE)
  for its documentation and technical communications.  STE is a controlled
  language: a limited vocabulary, one meaning for each word, short
  sentences, the active voice and no semicolons.  The documentation becomes
  easier to read for a person whose first language is not English.  It also
  becomes easier for a language model to translate.  Each OKF document
  declares its level in the new *ste:* front-matter field, which is *full*,
  *adapted* or *false*.  A declaration is earned: a document changes from
  *false* only when its text complies.  These release notes follow the same
  rules from v0.8 onward, and so do the commit messages

* New *documentation/tools/*: three command-line tools that verify and
  prepare a document for STE.  *asd_ste100_lint.py* is the gate, and it
  reports six counts: long sentences, prose semicolons, British spelling,
  swap-list words, Latin abbreviations and contractions.  A document is
  converted when all six read zero.  *asd_ste100_fix.py* applies the
  mechanical corrections only, and *asd_ste100_semisplit.py* divides the
  prose semicolons into sentences

### Deprecations and compatibility

The wire protocol is unchanged: implementations in other languages and
remote callers are unaffected.  For Python code:

* **Deprecated (still working in v0.8, removed in the next release):**
  positional construction of eventual-consistency state, for example
  *ECProducer(service, share)* and *ECConsumer(service, id, cache,
  topic_control, filter)*.  Migrate to the composed form:
  *compose_instance(ECProducerImpl, ec_producer_args(service, share))*

* **Breaking:** subclassing *ECProducer* or *ECConsumer* directly — they
  are now abstract Interfaces.  Subclass *ECProducerImpl* /
  *ECConsumerImpl* instead

* **Breaking (unlikely):** the *Registrar* and *Recorder* Interfaces now
  declare abstract methods.  Thus a custom subclass must implement those
  methods or compose the supplied Impl.  The former private
  *_service_add()* / *_service_remove()* methods of the Registrar are
  renamed to the public *service_add()* / *service_remove()*

* The republished *(add ...)* payload of the Registrar is now canonical
  *generate()* output, not a byte-for-byte echo of the payload of the
  client.  The two forms are identical for a conforming S-expression
  parser

* Identity checks *type(x) is ECProducer* are no longer true, because the
  instances are composed Implementations.  Use *isinstance(x,
  ECProducer)*

### Testing

* Unit test baseline raised from 5 to 25 tests.  All of them run without
  an MQTT broker.  New *test_component.py* pins the contract of the
  composition engine (unimplemented-Interface errors, override
  precedence, global-registry filtering, *call_init()* idempotency and
  the synthesized *__init__()*).  New *test_share.py* covers composed EC
  construction, the deprecated-form shim and *ECCache*.  New
  *test_registrar.py* covers the promoted Registrar API and wire
  delegation

### Bug Fixes

* Hook state is now per-component.  *HooksImpl* previously kept its hooks
  in a class-level dictionary that every Service in the process shared.
  Thus a hook added on one component was added to all.  Code that relied on
  attaching handlers to another component's hooks will now raise
  *RuntimeError* — attach handlers on the component that declared the
  hook

* Context defaults are no longer shared between Services.  Previously,
  *add_tags()* on one Service (for example, the automatic *ec=true* tag)
  changed the module-level default tags list.  This changed each context
  created after it

* *component.py:_check_interfaces_implemented()* no longer misclassifies
  a seed class without concrete methods as an unimplemented Interface
  (the seed class is the consumer of the Interface contracts, never one
  of them)

---

## Release Notes v0.7

**Full Changelog**: https://github.com/geekscape/aiko_services/compare/v0.6...v0.7

### Features

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

### Testing

* Aiko Services now supports Python 3.9.7 through to 3.14.2
  (see *pyproject.toml*)

* Added GitHub Actions Continuous Integration, which runs Python *flake8*
  lint checks for critical syntax and runtime-related issues

* Added unit tests for Hooks, Pipeline Graphs and the Stream lock ...
  plus *tests/chaos/network_chaos_monkey.py* for seriously testing
  distributed systems failures (MQTT server, system and application
  Services)

### Bug Fixes

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

## Release Notes v0.6

**Full Changelog**: https://github.com/geekscape/aiko_services/compare/v0.5...v0.6

### Features

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

### Testing

* Aiko Services *main/* and *elements/media/* code testing using Python 3.13.0

* Some *examples/* only work with Python 3.12.7, due to third-party
  dependencies not being updated and released for 3.13.0

    * Python package *opencv-python* works on Python 3.13.0
    * Python package *langchain*, Ollama and Llama 3.1 LLM works on Python 3.13.0
    * Python package *deepface* works on with Python 3.12.7, but not 3.13.0
    * Python package *torch* works on with Python 3.12.7, but not 3.13.0
    * Ultralytics YOLOv8 example works on Python 3.12.7, but not 3.13.0

### Bug Fixes

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
