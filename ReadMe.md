# Aiko Services

Distributed service framework using asynchronous messages supporting
AIoT, Machine Learning, Media streaming and Robotics

# Development set-up

Recommended regular development ...
```
git clone https://github.com/geekscape/aiko_services.git
cd aiko_services
python3 -m venv venv      # Once only
source venv/bin/activate  # Each terminal session
pip install -U pip        # Install latest pip
pip install -e .          # Install Aiko Services
```

Recommended for package maintainers ...
```
pip install -U hatch      # Install latest Hatch build and package manager
hatch shell               # Run shell using Hatch to manage dependencies
# hatch test              # Run local tests [to be completed]
```

# Aiko Services Examples

- [Aloha Honua documentation](src/aiko_services/examples/aloha_honua/ReadMe.md)
  (hello world)

Build and publish Aiko Services Package to PyPi

```
hatch build
```

# To Do

See [GitHub Issues](https://github.com/geekscape/aiko_services/issues)

# Presentations

- [Building an open framework combining AIoT, Media, Robotics & Machine Learning (YouTube)](https://www.youtube.com/watch?v=htbzn_xwEnU)
    - [Slide-deck (Google slides)](https://docs.google.com/presentation/d/1dR8jw6sEKkgPBMDsKkZd87Y79LMk7jhVxxAmRMbjmbE/edit#)
    - Everything Open March 2023: Melbourne
- [Using Python to stream media using GStreamer for RTSP and WebRTC applications (YouTube)](https://www.youtube.com/watch?v=VwnWHC04Qp8)
    - [Slide-desk (Google slides)](https://docs.google.com/presentation/d/1yc8jMcq8967L3fzIBmiy7MMYaBhSKD1L3XJ979_VanE/edit#)
    - PyCon August 2023: Adelaide
- [microPython distributed, embedded services (YouTube)](https://www.youtube.com/watch?v=25Ij-EUjqS4)
    - [slide-desk (Google slides)](https://docs.google.com/presentation/d/1V0_Hr3AKxRysg6AvgI1w2viBhFNmvcF1RwdIBMJJVCI/edit#)
    - microPython meet-up November 2023: Melbourne
