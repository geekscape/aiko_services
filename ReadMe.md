# Aiko Services

Distributed system framework supporting
[AIoT](https://en.wikipedia.org/wiki/Artificial_intelligence_of_things), [Machine Learning](https://en.wikipedia.org/wiki/Machine_learning), [Media streaming](https://en.wikipedia.org/wiki/Streaming_media) and [Robotics](https://en.wikipedia.org/wiki/Robotics)

## Features

- Supports multi-nodal Machine Learning streaming pipelines ... that span from edge (embedded) devices all the way through to the data centre systems and back again

- Consistent distributed system approach integrating [best-of-breed](https://wiki.c2.com/?BestOfBreed) technology choices
    - Supports the [Actor Model](https://en.wikipedia.org/wiki/Actor_model)
    - Supports [Flow based programming](https://en.wikipedia.org/wiki/Flow-based_programming) via distributed pipeline graphs
    - [Low-latency performance](https://en.wikipedia.org/wiki/Event-driven_programming) with fully asynchronous [message passing](https://en.wikipedia.org/wiki/Message_passing#Distributed_objects)

- Ease of visualization and diagnosis for systems with many interconnected components

- Light-weight core design, i.e a [micro-controller reference implementation](https://github.com/geekscape/aiko_engine_mp), e.g [ESP32](https://en.wikipedia.org/wiki/ESP32) running [microPython](https://micropython.org)

- Flexible deployment choices when deciding which components should run in the same process (for performance) or across different processes and/or hosts (for flexibility)

- Aiming to make the difficult parts ... much easier !

# Installation

## Installing from PyPI (Python Package Index)

Recommended when simply trying Aiko Services by using existing examples and tools.  
Installs the [Aiko Services package from PyPI](https://pypi.org/project/aiko_services)
```
pip install aiko_services
```

## Installing from GitHub

Recommended when using Aiko Services as a framework for development
```
git clone https://github.com/geekscape/aiko_services.git
cd aiko_services
python3 -m venv venv      # Once only
source venv/bin/activate  # Each terminal session
pip install -U pip        # Install latest pip
pip install -e .          # Install Aiko Services for development
```

## Installing for package maintainers

Recommended when making an [Aiko Services release to PyPI](https://pypi.org/project/aiko_services)  
After **installing from GitHub** *(above)*, perform these additional commands
```
pip install -U hatch  # Install latest Hatch build and package manager
hatch shell           # Run shell using Hatch to manage dependencies
# hatch test          # Run local tests (to be completed)
hatch build           # Publish Aiko Services package to PyPI
```

# Quick start

After **installing from GitHub** *(above)*, choose whether to use a public MQTT server ... or to install and run your own MQTT server

It is easier to start by using a public remotely hosted MQTT server to tryout a few examples.  
For the longer term, it is better and more secure to install and run your own MQTT server.

## Running your own mosquitto (MQTT) server

- Install the mosquitto (MQTT) server on [Linux](https://docs.vultr.com/install-mosquitto-mqtt-broker-on-ubuntu-20-04-server), [Mac OS X](https://subscription.packtpub.com/book/iot-and-hardware/9781787287815/1/ch01lvl1sec12/installing-a-mosquitto-broker-on-macos) or [Windows](https://cedalo.com/blog/how-to-install-mosquitto-mqtt-broker-on-windows)

On Linux or Mac OS X: Start mosquitto, aiko_registrar and aiko_dashboard
```
./scripts/system_start.sh  # default AIKO_MQTT_HOST=localhost
```

# Examples

- [Aloha Honua examples](src/aiko_services/examples/aloha_honua/ReadMe.md)
  (hello world)

# To Do

See [GitHub Issues](https://github.com/geekscape/aiko_services/issues)

# Presentations

- [Building an open framework combining AIoT, Media, Robotics & Machine Learning (YouTube)](https://www.youtube.com/watch?v=htbzn_xwEnU)
    - [Slide deck (Google slides)](https://docs.google.com/presentation/d/1dR8jw6sEKkgPBMDsKkZd87Y79LMk7jhVxxAmRMbjmbE/edit#)
    - Everything Open conference March 2023: Melbourne

- [Using Python to stream media using GStreamer for RTSP and WebRTC applications (YouTube)](https://www.youtube.com/watch?v=VwnWHC04Qp8)
    - [Slide deck (Google slides)](https://docs.google.com/presentation/d/1yc8jMcq8967L3fzIBmiy7MMYaBhSKD1L3XJ979_VanE/edit#)
    - PyCon AU conference August 2023: Adelaide

- [microPython distributed, embedded services (YouTube)](https://www.youtube.com/watch?v=25Ij-EUjqS4)
    - [Slide deck (Google slides)](https://docs.google.com/presentation/d/1V0_Hr3AKxRysg6AvgI1w2viBhFNmvcF1RwdIBMJJVCI/edit#)
    - microPython meet-up November 2023: Melbourne
