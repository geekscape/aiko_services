# Usage: Colab
# ~~~~~~~~~~~~
# aiko_pipeline create pipelines/webcam_pipeline_0.json -s 1 -ll debug
#
# To Do
# ~~~~~
# - For "encode_silence()", consider caching "silence", which saves 40 ms 🤔
# - Consider DataScheme "mqtt://" ... can create own MQTT Connection
# - Plain web server / browser combination that works outside of Google Colab

import numpy as np
import subprocess
import tempfile
from typing import Tuple

import aiko_services as aiko

__all__ = [
    "do_print", "do_start_stream", "encode_silence",
    "handle_audio_frame", "handle_image_frame"
]

_LOGGER = aiko.process.logger(__name__)

# --------------------------------------------------------------------------- #

DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_CHANNELS = 1
DEFAULT_DURATION_SEC = 1.0

def encode_silence(
    mime_type: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    duration_sec: float = DEFAULT_DURATION_SEC
    ) -> bytes:

    # Generate PCM silence (float32)
    num_samples = int(sample_rate * duration_sec)
    silence = np.zeros((num_samples, channels), dtype=np.float32)

    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as pcm_file, \
         tempfile.NamedTemporaryFile(delete=False) as out_file:

        silence.tofile(pcm_file.name)

        if "opus" in mime_type:
            codec = "libopus"
            container = "webm" if "webm" in mime_type else "ogg"
        elif "wav" in mime_type:
            codec = "pcm_f32le"
            container = "wav"
        else:
            codec = "libopus"
            container = "webm"

        out_file_path = f"{out_file.name}.{container}"

        ffmpeg_command = ["ffmpeg", "-y", "-f", "f32le", "-ar",
            str(sample_rate), "-ac", str(channels), "-i", pcm_file.name,
            "-t", str(duration_sec), "-c:a", codec, out_file_path]

        subprocess.run(ffmpeg_command,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        with open(out_file_path, "rb") as f:
            return f.read()

# --------------------------------------------------------------------------- #

from base64 import b64decode, b64encode
from google.colab import output
from io import BytesIO
from IPython.display import display, Javascript, JSON
from PIL import Image

def do_print(message):
    print(message)

output.register_callback('notebook.do_print', do_print)

# Python function for JavaScript to create a frame for Pipeline processing

def handle_audio_frame(payload: dict):
    try:
        mime = payload.get("mime", "audio/webm")
        b64 = payload.get("b64", "")
        audio_in_bytes = b64decode(b64.encode("utf-8")) if b64 else b""

        if False:  # Use True to test audio input without the Pipeline
            out_bytes, out_mime = audio_in_bytes, mime
            stream_frame_ids = "<echo>"
        else:
            stream_frame_ids, out_bytes, out_mime = do_create_audio_frame(
                audio_in_bytes, mime)

        out_b64 = b64encode(out_bytes).decode("utf-8") if out_bytes else ""
        return JSON({"mime": out_mime, "b64": out_b64, "stream_frame_ids": stream_frame_ids})
    except Exception as e:
        # Return an error object JS can handle
        return JSON({"error": str(e)})

output.register_callback('notebook.handle_audio_frame', handle_audio_frame)

def handle_image_frame(data_url: str):
    header, encoded = data_url.split(',', 1)
    image_bytes = b64decode(encoded)
    image = Image.open(BytesIO(image_bytes)).convert("RGB")

    if False:  # Use True to test web camera input without the Pipeline
        new_image = image.transpose(Image.FLIP_TOP_BOTTOM)
    else:
        stream_frame_ids, new_image = do_create_image_frame(image)

    buffer = BytesIO()
    new_image.save(buffer, format="JPEG")
    new_image_b64 = b64encode(buffer.getvalue()).decode("utf-8")
    new_image_data_url = "data:image/jpeg;base64," + new_image_b64
    return JSON({"data_url": new_image_data_url})

output.register_callback('notebook.handle_image_frame', handle_image_frame)

# JavaScript code for web camera input and displaying Pipeline output

def do_start_stream():
    js_code = """
    async function startStream() {
      await google.colab.kernel.invokeFunction(
        'notebook.do_print', ['## JavaScript start_stream() (video+audio) invoked ##'], {}
      );

      // ---------- DOM helpers ----------
      const el = (tag, props = {}, children = []) => {
        const e = document.createElement(tag);
        Object.assign(e, props);
        (children || []).forEach(c => e.appendChild(c));
        return e;
      };

      // ---------- Video elements ----------
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

      // Default matches your existing hard-coded value:
      let frameIntervalMs = 500;     // 2 FPS default
      let videoRunning = true;       // sending frames
      let appRunning = true;         // whole widget alive

      // ---------- Audio elements ----------
      let audioStream = null;
      let mediaRecorder = null;
      let audioChunks = [];
      let isRecording = false;

      const audioOut = new Audio();
      audioOut.controls = true;  // optional: show browser controls for debugging
      audioOut.volume = 1.0;

      // ---------- UI ----------
      const container = el('div');
      container.style.display = 'flex';
      container.style.flexDirection = 'column';
      container.style.alignItems = 'center';
      container.style.gap = '10px';
      container.style.margin = '10px 0';
      container.style.padding = '10px';
      container.style.border = '1px solid #ddd';
      container.style.borderRadius = '8px';
      container.style.maxWidth = '720px';

      const title = el('div', { innerText: 'Colab Camera + Audio → Pipeline → Browser' });
      title.style.fontFamily = 'sans-serif';
      title.style.fontSize = '14px';
      title.style.fontWeight = '600';

      const canvasRow = el('div');
      canvasRow.style.display = 'flex';
      canvasRow.style.flexDirection = 'row';
      canvasRow.style.gap = '8px';

      const labelsRow = el('div');
      labelsRow.style.display = 'flex';
      labelsRow.style.flexDirection = 'row';
      labelsRow.style.justifyContent = 'space-between';
      labelsRow.style.width = '100%';
      labelsRow.style.fontFamily = 'monospace';
      labelsRow.style.fontSize = '12px';

      const labelIn = el('div', { innerText: 'Original (320x240)' });
      const labelOut = el('div', { innerText: 'Processed (Pipeline)' });
      labelsRow.appendChild(labelIn);
      labelsRow.appendChild(labelOut);

      canvasRow.appendChild(inputCanvas);
      canvasRow.appendChild(outputCanvas);

      const controls = el('div');
      controls.style.display = 'flex';
      controls.style.flexDirection = 'row';
      controls.style.flexWrap = 'wrap';
      controls.style.gap = '8px';
      controls.style.justifyContent = 'center';

      // (1) Record/Send audio toggle button
      const recordSendBtn = el('button', { innerText: 'Record audio' });

      // (2) Cancel audio
      const cancelAudioBtn = el('button', { innerText: 'Cancel audio' });
      cancelAudioBtn.disabled = true;

      // (5) Pause/Continue video input
      const pauseVideoBtn = el('button', { innerText: 'Pause video' });

      // Stop stream / remove UI
      const stopAllBtn = el('button', { innerText: 'Stop stream' });

      // (3) Speaker volume slider
      const volumeWrap = el('div');
      volumeWrap.style.display = 'flex';
      volumeWrap.style.alignItems = 'center';
      volumeWrap.style.gap = '6px';
      const volumeLabel = el('span', { innerText: 'Volume' });
      const volumeSlider = el('input');
      volumeSlider.type = 'range';
      volumeSlider.min = 0;
      volumeSlider.max = 1;
      volumeSlider.step = 0.01;
      volumeSlider.value = audioOut.volume;

      volumeSlider.oninput = () => {
        audioOut.volume = Number(volumeSlider.value);
      };

      volumeWrap.appendChild(volumeLabel);
      volumeWrap.appendChild(volumeSlider);

      // (4) Image sample rate slider (frame interval)
      // We'll make it "FPS-ish": slider controls interval from 100ms..2000ms
      const rateWrap = el('div');
      rateWrap.style.display = 'flex';
      rateWrap.style.alignItems = 'center';
      rateWrap.style.gap = '6px';

      const rateLabel = el('span', { innerText: 'Frame interval (ms)' });
      const rateSlider = el('input');
      rateSlider.type = 'range';
      rateSlider.min = 500;
      rateSlider.max = 2000;
      rateSlider.step = 50;
      rateSlider.value = frameIntervalMs;

      const rateValue = el('span', { innerText: String(frameIntervalMs) });
      rateValue.style.fontFamily = 'monospace';

      rateSlider.oninput = () => {
        frameIntervalMs = Number(rateSlider.value);
        rateValue.innerText = String(frameIntervalMs);
      };

      rateWrap.appendChild(rateLabel);
      rateWrap.appendChild(rateSlider);
      rateWrap.appendChild(rateValue);

      controls.appendChild(recordSendBtn);
      controls.appendChild(cancelAudioBtn);
      controls.appendChild(pauseVideoBtn);
      controls.appendChild(volumeWrap);
      controls.appendChild(rateWrap);
      controls.appendChild(stopAllBtn);

      container.appendChild(title);
      container.appendChild(labelsRow);
      container.appendChild(canvasRow);

      // Optional: show audio output element
      const audioRow = el('div');
      audioRow.style.display = 'flex';
      audioRow.style.flexDirection = 'column';
      audioRow.style.alignItems = 'center';
      audioRow.style.gap = '6px';
      const audioLabel = el('div', { innerText: 'Audio output (pipeline processed)' });
      audioLabel.style.fontFamily = 'monospace';
      audioLabel.style.fontSize = '12px';
      audioRow.appendChild(audioLabel);
      audioRow.appendChild(audioOut);

      container.appendChild(audioRow);
      container.appendChild(controls);

      document.body.appendChild(container);

      // Hide raw video element
      video.style.display = 'none';
      container.appendChild(video);

      // Keep iframe sized correctly
      const resizeIframe = () => {
        if (google && google.colab && google.colab.output) {
          google.colab.output.setIframeHeight(document.documentElement.scrollHeight, true);
        }
      };
      resizeIframe();

      // ---------- Acquire camera stream ----------
      let camStream = null;
      try {
        camStream = await navigator.mediaDevices.getUserMedia({
          video: { width: 320, height: 240 }
        });
      } catch (e) {
        console.error('Camera getUserMedia failed:', e);
        await google.colab.kernel.invokeFunction(
          'notebook.do_print', ['Camera getUserMedia failed: ' + e], {}
        );
        return;
      }

      video.srcObject = camStream;
      await video.play();

      // ---------- Acquire microphone stream (lazy or upfront) ----------
      async function ensureMicStream() {
        if (audioStream) return audioStream;
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        return audioStream;
      }

      // ---------- Video pause/continue ----------
      pauseVideoBtn.onclick = () => {
        videoRunning = !videoRunning;
        pauseVideoBtn.innerText = videoRunning ? 'Pause video' : 'Continue video';
      };

      // ---------- Stop all ----------
      stopAllBtn.onclick = () => {
        appRunning = false;
        videoRunning = false;

        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
          try { mediaRecorder.stop(); } catch {}
        }
        mediaRecorder = null;
        isRecording = false;
        audioChunks = [];

        if (camStream) camStream.getVideoTracks().forEach(t => t.stop());
        if (audioStream) audioStream.getAudioTracks().forEach(t => t.stop());

        container.remove();
      };

      // ---------- Audio record/send/cancel ----------
      function resetAudioButtons() {
        isRecording = false;
        recordSendBtn.innerText = 'Record audio';
        cancelAudioBtn.disabled = true;
        audioChunks = [];
      }

      cancelAudioBtn.onclick = () => {
        // Cancel recording and discard chunks
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
          try { mediaRecorder.stop(); } catch {}
        }
        resetAudioButtons();
      };

      recordSendBtn.onclick = async () => {
        try {
          if (!isRecording) {
            // Start recording
            await ensureMicStream();

            // Choose a mimeType the browser supports
            let mimeType = '';
            const candidates = [
              'audio/webm;codecs=opus',
              'audio/webm',
              'audio/ogg;codecs=opus',
              'audio/ogg'
            ];
            for (const c of candidates) {
              if (window.MediaRecorder && MediaRecorder.isTypeSupported(c)) { mimeType = c; break; }
            }

            mediaRecorder = new MediaRecorder(audioStream, mimeType ? { mimeType } : undefined);
            audioChunks = [];
            mediaRecorder.ondataavailable = (evt) => {
              if (evt.data && evt.data.size > 0) audioChunks.push(evt.data);
            };

            mediaRecorder.onstop = async () => {
              // If user hit "Send audio", we process. If they hit Cancel, chunks were cleared already.
              if (audioChunks.length === 0) {
                resetAudioButtons();
                return;
              }

              const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
              const blobMime = blob.type || (mediaRecorder.mimeType || 'audio/webm');

              // Convert blob -> base64
              const b64 = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => {
                  const dataUrl = reader.result; // data:...;base64,xxxx
                  const parts = String(dataUrl).split(',', 2);
                  resolve(parts.length === 2 ? parts[1] : '');
                };
                reader.onerror = reject;
                reader.readAsDataURL(blob);
              });

              // Send to Python
              const result = await google.colab.kernel.invokeFunction(
                'notebook.handle_audio_frame', [{ mime: blobMime, b64 }], {}
              );

              const resp = result.data['application/json'];
              if (resp.error) {
                console.error('handle_audio_frame error:', resp.error);
                await google.colab.kernel.invokeFunction(
                  'notebook.do_print', ['handle_audio_frame error: ' + resp.error], {}
                );
                resetAudioButtons();
                return;
              }

              const outMime = resp.mime || blobMime;
              const outB64 = resp.b64 || '';

              // Play returned audio
              if (outB64 && outB64.length > 0) {
                const byteChars = atob(outB64);
                const byteNums = new Array(byteChars.length);
                for (let i = 0; i < byteChars.length; i++) byteNums[i] = byteChars.charCodeAt(i);
                const outBlob = new Blob([new Uint8Array(byteNums)], { type: outMime });

                const url = URL.createObjectURL(outBlob);
                audioOut.src = url;
                audioOut.volume = Number(volumeSlider.value);

                try { await audioOut.play(); } catch (e) {
                  console.warn('Autoplay blocked or play failed:', e);
                }
              }

              resetAudioButtons();
              resizeIframe();
            };

            mediaRecorder.start();
            isRecording = true;
            recordSendBtn.innerText = 'Send audio';
            cancelAudioBtn.disabled = false;
          } else {
            // Stop recording -> triggers onstop -> send to Python -> play output
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
              mediaRecorder.stop();
            }
            // Keep button label until onstop completes; user sees "Send audio" until done
            cancelAudioBtn.disabled = true; // avoid cancel mid-stop confusion
          }
        } catch (e) {
          console.error('Audio record/send failed:', e);
          await google.colab.kernel.invokeFunction(
            'notebook.do_print', ['Audio record/send failed: ' + e], {}
          );
          resetAudioButtons();
        }
      };

      // ---------- Video frame loop ----------
      async function processFrameLoop() {
        while (appRunning) {
          if (!videoRunning) {
            await new Promise(r => setTimeout(r, 50));
            continue;
          }

          ctxIn.drawImage(video, 0, 0, inputCanvas.width, inputCanvas.height);
          const dataUrl = inputCanvas.toDataURL('image/jpeg', JPEG_QUALITY);

          try {
            const result = await google.colab.kernel.invokeFunction(
              'notebook.handle_image_frame', [dataUrl], {}
            );
            const newDataUrl = result.data['application/json']['data_url'];

            await new Promise((resolve) => {
              const img = new Image();
              img.onload = () => {
                ctxOut.clearRect(0, 0, outputCanvas.width, outputCanvas.height);
                ctxOut.drawImage(
                    img, 0, 0, outputCanvas.width, outputCanvas.height);
                resolve();
              };
              img.src = newDataUrl;
            });
          } catch (err) {
            console.error('Error calling Python handle_image_frame:', err);
            await google.colab.kernel.invokeFunction(
              'notebook.do_print', ['handle_image_frame error: ' + err], {}
            );
            appRunning = false;
            break;
          }

          await new Promise(r => setTimeout(r, frameIntervalMs));
        }
      }

      processFrameLoop();
    }

    startStream();
    """
    display(Javascript(js_code))

# --------------------------------------------------------------------------- #
