import logging
import os
from base64 import b64decode, b64encode
from io import BytesIO
from queue import Queue
from threading import Thread

import aiko_services as aiko
from aiko_services.elements.media import convert_image
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
from PIL import Image

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

definition_pathname = os.environ.get("DEFINITION_PATHNAME", "examples/colab/pipelines/colab_pipeline_2.json")
frame_data = None
graph_path = None
grace_time = 3 * 60 * 60
name = None
parameters = {}
stream_id = "1"

pipeline_definition = aiko.PipelineImpl.parse_pipeline_definition(definition_pathname)

app.config["FRAME_ID"] = 0
app.config["QUEUE_RESPONSE"] = Queue()
app.config["PIPELINE"] = aiko.PipelineImpl.create_pipeline(
    definition_pathname,
    pipeline_definition,
    name,
    graph_path,
    stream_id,
    parameters,
    app.config["FRAME_ID"],
    frame_data,
    grace_time=grace_time,
    queue_response=app.config["QUEUE_RESPONSE"],
)

thread = Thread(target=app.config["PIPELINE"].run, args=(False,))
thread.daemon = True
thread.start()


def do_create_frame(image_in_pil=None):
    if image_in_pil is None:
        image_in_pil = Image.new("RGB", (320, 240), "black")
    image_in_numpy = convert_image(image_in_pil, "numpy")

    stream_in = {"stream_id": stream_id, "frame_id": app.config["FRAME_ID"]}
    frame_data_in = {"images": [image_in_numpy]}
    app.config["PIPELINE"].create_frame(stream_in, frame_data_in)
    app.config["FRAME_ID"] += 1

    response = app.config["QUEUE_RESPONSE"].get()
    stream_out, frame_data_out = response
    stream_frame_ids = f'<{stream_out["stream_id"]}:{stream_out["frame_id"]}>'
    image_out_numpy = frame_data_out["images"][0]
    image_out_pil = convert_image(image_out_numpy, "pil")
    app.logger.debug("Processed frame %s", stream_frame_ids)
    return stream_frame_ids, image_out_pil


@socketio.on("process_frame")
def handle_frame_socket(data):
    """
    WebSocket handler for frame processing
    """
    data_url = data["frame"]

    header, encoded = data_url.split(",", 1)
    image_bytes = b64decode(encoded)
    image = Image.open(BytesIO(image_bytes)).convert("RGB")

    stream_frame_ids, new_image = do_create_frame(image)

    buffer = BytesIO()
    new_image.save(buffer, format="JPEG")
    new_image_b64 = b64encode(buffer.getvalue()).decode("utf-8")
    new_image_data_url = "data:image/jpeg;base64," + new_image_b64

    emit("processed_frame", {"data_url": new_image_data_url})


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    # Flask built-in webserver
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
else:
    # Fixup logging if running under Gunicorn
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
