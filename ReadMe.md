# Aiko Services

Distributed system framework supporting
[**Machine Learning**](https://en.wikipedia.org/wiki/Machine_learning),
[**Robotics**](https://en.wikipedia.org/wiki/Robotics),
[**Media streaming**](https://en.wikipedia.org/wiki/Streaming_media) and
[**AIoT**](https://en.wikipedia.org/wiki/Artificial_intelligence_of_things)

# Features

- Supports multi-nodal Machine Learning streaming pipelines ... that span from edge (embedded) devices all the way through to the data centre servers and back again

- Consistent distributed system approach integrating [best-of-breed](https://wiki.c2.com/?BestOfBreed) technology choices
    - Uses the [Actor Model](https://en.wikipedia.org/wiki/Actor_model)
    - Provides [HyperSpace](documentation/concepts/hyperspace.md) ([example](src/aiko_services/examples/hyperspace)) ... a unified distributed Services graph for everything !
    - Uses [Flow based programming](https://en.wikipedia.org/wiki/Flow-based_programming) via distributed [Pipelines](/documentation/concepts/pipeline.md) and [PipelineElements](documentation/elements/ReadMe.md)
    - Provides [low-latency performance](https://en.wikipedia.org/wiki/Event-driven_programming) with fully asynchronous function calls / method invocation via [message passing](https://en.wikipedia.org/wiki/Message_passing#Distributed_objects)

- Ease of visualization and diagnosis for systems with many interconnected components via
the [Aiko Dashboard](src/aiko_services/main/dashboard.py)

- Light-weight, extensible core design for performance on high-end servers ... and supports operation on embedded devices, i.e a [micro-controller reference implementation](https://github.com/geekscape/aiko_engine_mp), e.g [ESP32](https://en.wikipedia.org/wiki/ESP32) running [microPython](https://micropython.org)

- Flexible deployment choices when deciding which components should run in the same process (for performance) or across different processes and/or hosts (for flexibility)

- Aims to make the difficult challenges much easier !

# Documentation

- [Design overview](documentation/concepts/design_overview.md)
- [Concepts guide](documentation/concepts/ReadMe.md) 👀
- [Pipeline](/documentation/concepts/pipeline.md) and [PipelineElements guide](documentation/elements/ReadMe.md)
- [Examples reference](documentation/examples/ReadMe.md)
- [Release notes](documentation/release_notes.md)

Uses the [Open Knowledge Format](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) ... and so the documentation is immediately useable by your favorite A.I coding assistant 🤖

See the [Wiki](https://github.com/geekscape/aiko_services/wiki) for [Glossary (concepts)](https://github.com/geekscape/aiko_services/wiki/Glossary), [Roadmap for v1.0](https://github.com/geekscape/aiko_services/wiki#roadmap-for-v10), [Work In Progress (WIP)](https://github.com/geekscape/aiko_services/wiki#work-in-progress) and [Reference pages](https://github.com/geekscape/aiko_services/wiki#reference-pages)

# Installation

## Installing from PyPI (Python Package Index)

Recommended when simply trying Aiko Services by using existing examples and tools.

Installs the [Aiko Services package from PyPI](https://pypi.org/project/aiko_services)

```bash
pip install aiko_services
```

## Installing from GitHub for developers

Recommended when using Aiko Services as a framework for development

```bash
git clone https://github.com/geekscape/aiko_services.git
cd aiko_services
python3 -m venv venv      # Once only
source venv/bin/activate  # Each terminal session
pip install -U pip        # Install latest pip
pip install -e .          # Install Aiko Services for development
```

## Installing for package maintainers

Recommended when making an [Aiko Services release to PyPI](https://pypi.org/project/aiko_services)

Before building, ensure that the release version has been updated and committed
in **both** of these files ...

- `src/aiko_services/__init__.py` ... `__version__` and `__id__`
- `pyproject.toml` ... `version` (used by Hatch for the package version)

**Important:** Always build from a fresh `git clone`, never from a development
working tree.  Hatch bundles all directory contents into the package, so any
untracked local files, e.g media files or back-up copies, would be included

```bash
git clone https://github.com/geekscape/aiko_services.git aiko_services_release
cd aiko_services_release
python3 -m venv venv      # Once only
source venv/bin/activate  # Each terminal session
pip install -U pip        # Install latest pip
pip install -U hatch      # Install latest Hatch build and package manager
# hatch test              # Run local tests (to be completed)
hatch build               # Build Aiko Services package: dist/*.whl and dist/*.tar.gz
```

Check that the build output is correct, i.e the wheel should be well under
1 MB and only contain source code (plus a few small sample data files)

```bash
unzip -l dist/aiko_services-*.whl
```

Publishing to PyPI requires a [PyPI API token](https://pypi.org/manage/account/token/)
scoped to the *aiko-services* project ... `username` / `password` uploads are no
longer supported by PyPI

```bash
HATCH_INDEX_USER=__token__ HATCH_INDEX_AUTH=pypi-YOUR_API_TOKEN  \
  hatch publish dist/   # Publish Aiko Services package to PyPI
```

# Quick start

After [**installing**](#Installation) *(above)*, choose whether to use a public MQTT server ... or to install and run your own MQTT server

It is easier to start by using a public remotely hosted MQTT server to tryout a few examples.

For the longer term, it is better and more secure to install and run your own MQTT server.

## Running your own mosquitto (MQTT) server

- Install the mosquitto (MQTT) server on [Linux](https://docs.vultr.com/install-mosquitto-mqtt-broker-on-ubuntu-20-04-server), [Mac OS X](https://subscription.packtpub.com/book/iot-and-hardware/9781787287815/1/ch01lvl1sec12/installing-a-mosquitto-broker-on-macos) or [Windows](https://cedalo.com/blog/how-to-install-mosquitto-mqtt-broker-on-windows)

On Linux or Mac OS X: Start `mosquitto`, `aiko_registrar` and `aiko_dashboard`

```bash
./scripts/system_start.sh  # default AIKO_MQTT_HOST=localhost
```

# Examples

- [Aloha Honua examples](src/aiko_services/examples/aloha_honua/ReadMe.md) ... Hello world Actor
- [HyperSpace](documentation/concepts/hyperspace.md) [example](src/aiko_services/examples/hyperspace) ... Unified distributed Services graph

| Package | Contents |
|---------|----------|
| [aloha_honua/](documentation/examples/aloha_honua/ReadMe.md) | The graduated four-stage hello-world Actor tutorial — plain Actor, discovery client, remote stop, request/response |
| [pipeline/](documentation/examples/pipeline/ReadMe.md) | Teaching Pipelines — local vs remote deployment, Graph Paths, frame data encode/decode, plus the multitude/ scale stress tests |
| [colab/](documentation/examples/colab/ReadMe.md) | Google Colab integration — running Pipelines inside a notebook with browser camera, microphone and speaker widgets |
| [speech/](documentation/examples/speech/ReadMe.md) | Speech processing — microphone capture, WhisperX transcription, Coqui text-to-speech and the speech-to-LLM round trip |
| [llm/](documentation/examples/llm/ReadMe.md) | Large Language Model elements — LangChain over Ollama or OpenAI, driven by the speech pipelines or a terminal |
| [yolo/](documentation/examples/yolo/ReadMe.md) | YOLOv8 and YOLOE open-vocabulary object detection Pipelines |
| [aruco_marker/](documentation/examples/aruco_marker/ReadMe.md) | ArUco fiducial marker detection and overlay |
| [face/](documentation/examples/face/ReadMe.md) | Face detection using DeepFace, with shared detection counters |
| [robot/](documentation/examples/robot/ReadMe.md) | Robot OODA-loop elements and the Panda3D virtual robot world |
| [xgo_robot/](documentation/examples/xgo_robot/ReadMe.md) | XGO-Mini 2 robot dog — on-robot Actor, laptop-side remote control and video monitor |
| [system_pipelines/](documentation/examples/system_pipelines/ReadMe.md) | System bootstrap via ProcessManager and the distributed webcam-to-YOLOE Pipeline pair |

# To Do

See [GitHub Issues](https://github.com/geekscape/aiko_services/issues)

# Presentations

- An open-source framework for creating awesome Machine Learning applications
    - [Slide deck (Google slides)](https://docs.google.com/presentation/d/1lMgo-QPcHy2ywFjHfFN32kn7dxTX3o6AQtCqfDG9qmI/edit#)
    - Everything Open conference January 2025: Adelaide, Australia

- [microPython distributed, embedded services (YouTube)](https://www.youtube.com/watch?v=25Ij-EUjqS4)
    - [Slide deck (Google slides)](https://docs.google.com/presentation/d/1V0_Hr3AKxRysg6AvgI1w2viBhFNmvcF1RwdIBMJJVCI/edit#)
    - microPython meet-up November 2023: Melbourne, Australia

- [Using Python to stream media using GStreamer for RTSP and WebRTC applications (YouTube)](https://www.youtube.com/watch?v=VwnWHC04Qp8)
    - [Slide deck (Google slides)](https://docs.google.com/presentation/d/1yc8jMcq8967L3fzIBmiy7MMYaBhSKD1L3XJ979_VanE/edit#)
    - PyCon AU conference August 2023: Adelaide, Australia

- [Building an open framework combining AIoT, Media, Robotics & Machine Learning (YouTube)](https://www.youtube.com/watch?v=htbzn_xwEnU)
    - [Slide deck (Google slides)](https://docs.google.com/presentation/d/1dR8jw6sEKkgPBMDsKkZd87Y79LMk7jhVxxAmRMbjmbE/edit#)
    - Everything Open conference March 2023: Melbourne, Australia
