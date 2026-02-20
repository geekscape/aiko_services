FROM python:3.13-slim

WORKDIR /build
COPY . aiko_services

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux ; \
    cp -v /build/aiko_services/docker/files/* . ; \
    apt-get update ; \
    apt-get -y install git libgl1 libglib2.0-0 ; \
    pip install uv ; \
    uv pip install --system flask flask-socketio gunicorn ; \
    uv pip install --system -e /build/aiko_services ; \
    apt-get -y autoremove ; \
    apt-get -y clean ; \
    rm -rf /root/.cache \
            /var/lib/apt/lists/* ; \
    find /build -depth -name __pycache__ -type d | xargs rm -rf ;

# NOTE(nic): Set up and "dry-fire" the app to run the Ultralytics auto-update
#  This burns an image layer, but it also serves as a build sanity-check,
#  as well as trying/helping to minimize container startup overhead
RUN set -eux ; \
    DEFINITION_PATHNAME=/build/aiko_services/src/aiko_services/examples/colab/pipelines/colab_pipeline_2.json \
    python -B -c "from app import app; app.app_context().push()" ; \
    rm -rf __pycache__ /root/.cache ;

EXPOSE 5000

ENV GUNICORN_CMD_ARGS="--worker-class=gthread --workers=1 --threads=1024 --bind=0.0.0.0:5000 --log-level=debug --access-logfile=-"
CMD ["gunicorn", "app:app"]
