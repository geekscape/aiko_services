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

Access the web interface at https://localhost:5000

The JSON files under `src/aiko_services/examples` should be visible
inside the container, and updates to anything in that directory
should propagate into the container immediately
