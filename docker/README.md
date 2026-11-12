# Docker Image

This directory contains resources for building and managing Aiko
Services in a software container, which can provide a more frictionless
experience when standing up a development environment, as well as
better isolation/sandboxing

## Usage
```bash
cd docker
docker compose up
```

This should start an MQTT message bus, a registrar, and a minimalist LLM
