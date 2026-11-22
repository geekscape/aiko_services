# NOTE(nic): The current deployment target is a container that runs the
#  aiko_registrar.  That service only requires a subset of the functionality
#  required by this package, and therefore only requires a subset of third-party
#  dependencies.  So this Dockerfile ends up being a mixture of container best
#  practices and project-specific workarounds, to keep the image size down:
#
#   - Prevent bytecode files from being generated on package install.  The
#     container regenerates these anyhow, so they just waste space
#
#   - Prefer `uv` over `pip` as the package manager, as it is (much) faster and
#     has a (much) better solver
#
#   - But once the build is done, `uv` provides no more value and takes up a ton
#     of room, so remove it at the end of the install
#
#   - Install only the subset of packages required to get the registrar running.
#     This is brittle and likely the first thing to break on code changes, but
#     it does prevent things like NumPy and requests from getting installed into
#     a container that will literally never use them
FROM python:3.13-slim

WORKDIR /build/aiko_services
COPY . .

WORKDIR /tmp
ARG PYTHONDONTWRITEBYTECODE=1
RUN set -eux ; \
    pip install --no-compile --no-cache-dir uv ; \
    uv pip install --system --no-compile-bytecode psutil paho-mqtt transitions \
            wrapt click avro avro-validator asciimatics pyperclip ; \
    uv pip install --system --no-compile-bytecode --no-deps -e /build/aiko_services ; \
    uv pip uninstall --system uv ; \
    rm -rf /root/.cache

# NOTE(nic): no entrypoint, no commands, leave such things up to the caller
