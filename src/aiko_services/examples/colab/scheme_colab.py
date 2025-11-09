# To Do
# ~~~~~
# - Implement DataTarget

from base64 import b64decode, b64encode
from google.colab import output
from io import BytesIO
from IPython.display import display, Javascript, JSON
from PIL import Image
import queue

import aiko_services as aiko

__all__ = ["DataSchemeColab"]

# --------------------------------------------------------------------------- #
# parameter: "data_sources" uses Google Colab to get images (incoming)
# - "data_sources" list should only contain a single entry: "(colab://)"
#
# parameter: "data_sources" uses Google Colab to display images (outgoing)
# - "data_targets" list should only contain a single entry
# - "(colab://)" ...

class DataSchemeColab(aiko.DataScheme):
    def create_sources(self,
        stream, data_sources, frame_generator=None, use_create_frame=False):

        if not frame_generator:
            frame_generator = self.frame_generator

        self.queue_in = queue.Queue()
        self.queue_out = queue.Queue()
    #   self.pipeline_element.create_frames(stream, frame_generator)

    # Register callback so JavaScript can call it as "notebook.handle_frame"
        output.register_callback("notebook.handle_frame", self._handle_frame)
        self._start_browser_web_camera_stream()

        return aiko.StreamEvent.OKAY, {}

    def create_targets(self, stream, data_targets):
        return aiko.StreamEvent.OKAY, {}

#   def destroy_sources(self, stream):
#       pass

#   def destroy_targets(self, stream):
#       pass

    def frame_generator(self, stream, frame_id):
        data_batch_size, _ = self.pipeline_element.get_parameter(
            "data_batch_size", default=1)
        data_batch_size = int(data_batch_size)

        records = []
        while (data_batch_size > 0):
            data_batch_size -= 1
            if not self.queue_in.qsize():
                break
            record = self.queue_in.get()
            records.append(record)

        if records:
            return aiko.StreamEvent.OKAY, {"records": records}
        else:
            return aiko.StreamEvent.NO_FRAME, {}

    def _handle_frame(self, data_url: str):
        """Python callback
        Receive a data URL, vertically flip, return new data URL.
        Called from JavaScript via google.colab.kernel.invokeFunction.
        Returns JSON, so JavaScript can read result.data["application/json"]
        """

    # Strip header "data:image/jpeg;base64,"
        header, encoded = data_url.split(",", 1)
        image_bytes = b64decode(encoded)

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        flipped = image.transpose(Image.FLIP_TOP_BOTTOM)

        buffer = BytesIO()
        flipped.save(buffer, format="JPEG")
        flipped_b64 = b64encode(buffer.getvalue()).decode("utf-8")

        flipped_data_url = "data:image/jpeg;base64," + flipped_b64
        return JSON({"data_url": flipped_data_url})

    def _start_browser_web_camera_stream(self):
        """Start web camera stream
        JavaScript grabs frames at 320x240,
        sends them to Python for processing,
        then displays the returned frames
        """

        javascript_code = """
        async function startStream() {
          const video = document.createElement('video');
          const inputCanvas = document.createElement('canvas');
          const outputCanvas = document.createElement('canvas');
          const ctxIn = inputCanvas.getContext('2d');
          const ctxOut = outputCanvas.getContext('2d');

          inputCanvas.width = 320;
          inputCanvas.height = 240;
          outputCanvas.width = 320;
          outputCanvas.height = 240;

          const JPEG_QUALITY = 0.8;

          const container = document.createElement('div');
          container.style.display = 'flex';
          container.style.flexDirection = 'column';
          container.style.alignItems = 'center';
          container.style.gap = '8px';
          container.style.margin = '8px 0';

          const canvasRow = document.createElement('div');
          canvasRow.style.display = 'flex';
          canvasRow.style.flexDirection = 'row';
          canvasRow.style.gap = '8px';

          const labelsRow = document.createElement('div');
          labelsRow.style.display = 'flex';
          labelsRow.style.flexDirection = 'row';
          labelsRow.style.justifyContent = 'space-between';
          labelsRow.style.width = '100%';
          labelsRow.style.fontFamily = 'monospace';
          labelsRow.style.fontSize = '12px';

          const labelIn = document.createElement('div');
          labelIn.textContent = 'Original (320x240)';
          const labelOut = document.createElement('div');
          labelOut.textContent = 'Processed (vertical flip)';

          labelsRow.appendChild(labelIn);
          labelsRow.appendChild(labelOut);

          canvasRow.appendChild(inputCanvas);
          canvasRow.appendChild(outputCanvas);

          const controls = document.createElement('div');
          controls.style.display = 'flex';
          controls.style.flexDirection = 'row';
          controls.style.gap = '8px';

          const stopButton = document.createElement('button');
          stopButton.textContent = 'Stop stream';
          controls.appendChild(stopButton);

          container.appendChild(video);
          container.appendChild(labelsRow);
          container.appendChild(canvasRow);
          container.appendChild(controls);

          document.body.appendChild(container);

          const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 320, height: 240 }
          });
          video.srcObject = stream;
          video.style.display = 'none';
          await video.play();

          if (google && google.colab && google.colab.output) {
            google.colab.output.setIframeHeight(
                document.documentElement.scrollHeight, true);
          }

          let running = true;
          stopButton.onclick = () => {
            running = false;
            if (stream) {
              stream.getVideoTracks().forEach(t => t.stop());
            }
            container.remove();
          };

          async function handleFrame() {
            if (!running) return;

            ctxIn.drawImage(video, 0, 0, inputCanvas.width, inputCanvas.height);

            // Encode frame as JPEG data URL at 320x240
            const dataUrl = inputCanvas.toDataURL('image/jpeg', JPEG_QUALITY);

            try {
              const result = await google.colab.kernel.invokeFunction(
                'notebook.handle_frame', [dataUrl], {}
              );

              const newDataUrl = result.data['application/json']['data_url'];

              await new Promise((resolve) => {
                const img = new Image();
                img.onload = () => {
                  ctxOut.clearRect
                    (0, 0, outputCanvas.width, outputCanvas.height);
                  ctxOut.drawImage(
                    img, 0, 0, outputCanvas.width, outputCanvas.height);
                  resolve();
                };
                img.src = newDataUrl;
              });
            } catch (err) {
              console.error('Error calling Python handle_frame():', err);
              running = false;
            }

            if (running) {
              requestAnimationFrame(handleFrame);
            }
          }

          requestAnimationFrame(handleFrame);
        }

        startStream();
        """

        display(Javascript(javascript_code))

aiko.DataScheme.add_data_scheme("colab", DataSchemeColab)

# --------------------------------------------------------------------------- #
