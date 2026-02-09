# Usage
# ~~~~~
# aiko_pipeline create pipelines/colab_pipeline_1.json -ll debug_all
#
# aiko_chat
# > :change_change yolo
#
# To Do
# ~~~~~
# - None, yet !

from abc import abstractmethod
from dataclasses import dataclass
import io
import numpy as np
import os
import subprocess
from typing import Optional, Tuple

import aiko_services as aiko
from aiko_services.elements.media import convert_images
from aiko_services.elements.utilities import all_outputs

__all__ = [
    "AudioPassThrough", "ConvertDetections", "ChatServer", "MQTTPublish",
    "SpeechToText", "TextToSpeech", "VideoReadColab"
]

# --------------------------------------------------------------------------- #

class AudioPassThrough(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("audio_pass_through:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, audio, mime_type)  \
        -> Tuple[aiko.StreamEvent, dict]:

        self.logger.debug(f"{self.my_id()}: len: {len(audio)}, {mime_type}")
        return aiko.StreamEvent.OKAY, {"audio": audio, "mime_type": mime_type}

# --------------------------------------------------------------------------- #

class ConvertDetections(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("convert_detections:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, overlay) -> Tuple[aiko.StreamEvent, dict]:
        message = ""
        for object in overlay["objects"]:
            delimiter = "," if message else ""
            message += f"{delimiter}{object["name"]}"  # object["confidence"]
        return aiko.StreamEvent.OKAY, {"message": message}

# --------------------------------------------------------------------------- #

class ChatServer(aiko.Actor):
    @abstractmethod
    def send_message(self, username, recipients, message):
        pass

class MQTTPublish(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("mqtt_publish:0")
        context.call_init(self, "PipelineElement", context)
        self.chat_server = None
        self.chat_server_topic = None

    def discovery_add_handler(self, service_details, service):
        print(f"Connected {service_details[1]}: {service_details[0]}")
        chat_channel = self.share["chat_channel"]
        self.chat_server = service
        self.chat_server_topic = f"{service_details[0]}/{chat_channel}"

    def discovery_remove_handler(self, service_details):
        print(f"Disconnected {service_details[1]}: {service_details[0]}")
        self.chat_server = None
        self.chat_server_topic = None

    def start_stream(self, stream, stream_id):
        chat_channel, _ = self.get_parameter("chat_channel", "yolo")
        self.share["chat_channel"] = chat_channel

        username, _ = self.get_parameter("username", "<env_var>")
        if username == "<env_var>":
            username = os.environ.get("USER")
        self.share["username"] = username

        details, found = self.get_parameter("service_filter")

        if found:
            name = details["name"] if details["name"] else "*"
            protocol = details["protocol"] if details["protocol"] else "*"
            service_filter = aiko.ServiceFilter(
                "*", name, protocol, "*", "*", "*")

            service_discovery, service_discovery_handler = aiko.do_discovery(
                ChatServer, service_filter,
                self.discovery_add_handler, self.discovery_remove_handler)
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, message) -> Tuple[aiko.StreamEvent, dict]:
        if message:
            message = f"{self.share['username']}:{message}"

            if self.chat_server:
                username = self.share["username"]
                recipients = [self.share["chat_channel"]]
                self.chat_server.send_message(username, recipients, message)

        #   if self.chat_server_topic:
        #       aiko.process.message.publish(self.chat_server_topic, payload)

        return aiko.StreamEvent.OKAY, all_outputs(self, stream)

# -------- Audio helpers (no temp files) ------------------------------------ #

def _ffmpeg_decode_to_pcm_f32_mono(audio_bytes: bytes, mime_type: str, target_sr: int) -> np.ndarray:
    """
    Decode encoded audio bytes (webm/ogg/mp4/etc) to float32 mono PCM at target_sr.
    Returns a 1-D numpy float32 array in [-1, 1].
    """
    # ffmpeg demux/decoder guesses format from content; mime_type can help if needed later.
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0",
        "-ac", "1",
        "-ar", str(target_sr),
        "-f", "f32le",
        "pipe:1",
    ]
    out = subprocess.check_output(cmd, input=audio_bytes)
    pcm = np.frombuffer(out, dtype=np.float32)
    return pcm

# -------- PipelineElement: SpeechToText (faster-whisper) -------------------- #

class SpeechToText(aiko.PipelineElement):
    """
    STT: encoded audio bytes -> text
    Model: faster-whisper (local), default "small" for good latency/quality tradeoff.
    """

    def __init__(self, context):
        context.set_protocol("speech_to_text:0")
        context.call_init(self, "PipelineElement", context)
        self._whisper = None
        self._target_sr = 16000

    def start_stream(self, stream, stream_id):
        # Lazy import + model load (fast startup for pipeline creation)
        model_name, _ = self.get_parameter("stt_model", "small")  # tiny/base/small/medium/large-v3 etc
        device, _ = self.get_parameter("device", "cuda")          # "cuda" or "cpu"
        compute_type, _ = self.get_parameter("compute_type", "int8_float16")  # good default on Colab GPU

        try:
            from faster_whisper import WhisperModel
        except Exception as e:
            raise RuntimeError("Install faster-whisper: pip install faster-whisper") from e

        # If no GPU, fall back gracefully
        if device == "cuda":
            try:
                import torch
                if not torch.cuda.is_available():
                    device = "cpu"
                    compute_type = "int8"
            except Exception:
                device = "cpu"
                compute_type = "int8"

        self.logger.info(f"{self.my_id()}: loading Whisper model={model_name} device={device} compute={compute_type}")
        self._whisper = WhisperModel(model_name, device=device, compute_type=compute_type)

        # Optional parameters
        target_sr, found = self.get_parameter("stt_sample_rate", None)
        if found:
            self._target_sr = int(target_sr)

        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        # Models can be kept cached; nothing required
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, audio, mime_type) -> Tuple[aiko.StreamEvent, dict]:
        if self._whisper is None:
            # In case start_stream isn't called by your runner in some modes
            self.start_stream(stream, stream.get("stream_id", "<unknown>"))

        if not audio:
            self.logger.debug(f"{self.my_id()}: Not audio: {mime_type}")
            return aiko.StreamEvent.OKAY, {
                "audio": audio, "mime_type": mime_type, "text": ""}

        pcm = _ffmpeg_decode_to_pcm_f32_mono(audio, mime_type, self._target_sr)

        # faster-whisper accepts numpy float32
        language, _ = self.get_parameter("language", None)   # e.g., "en"
        task, _ = self.get_parameter("task", "transcribe")   # "transcribe" or "translate"
        vad_filter, _ = self.get_parameter("vad_filter", True)

        segments, info = self._whisper.transcribe(
            pcm,
            language=language,
            task=task,
            vad_filter=bool(vad_filter),
        )

        text = "".join(seg.text for seg in segments).strip()
        self.logger.debug(f"{self.my_id()}: {mime_type}: [{text}]")
        return aiko.StreamEvent.OKAY, {
            "audio": audio, "mime_type": mime_type, "text": text}

# --------------------------------------------------------------------------- #

def _wav_bytes_from_pcm_mono(pcm: np.ndarray, sample_rate: int) -> bytes:
    pcm = np.clip(pcm.astype(np.float32, copy=False), -1.0, 1.0)
    int16 = (pcm * 32767.0).astype(np.int16)

    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(int16.tobytes())
    return buf.getvalue()

# -------- Strict MIME/container/codec mapping ------------------------------ #

@dataclass(frozen=True)
class AudioFormat:
    container: str   # "webm", "ogg", "mp4", "wav"
    codec: str       # "opus", "aac", "pcm_s16le"
    mime: str        # what we will return


def _parse_audio_mime_strict(mime_type: str) -> Optional[AudioFormat]:
    """
    Map an input MIME to a strict (container, codec) we can encode.
    Returns None if we can't confidently map it.
    """
    if not mime_type:
        return None

    mt = mime_type.strip().lower()

    # WAV / PCM
    if mt.startswith("audio/wav") or mt.startswith("audio/wave"):
        return AudioFormat(container="wav", codec="pcm_s16le", mime="audio/wav")

    # WebM/Opus (Chrome/Edge/Brave typical)
    if mt.startswith("audio/webm"):
        # Most browser MediaRecorder audio/webm is opus
        return AudioFormat(container="webm", codec="opus", mime="audio/webm;codecs=opus")

    # Ogg/Opus (Firefox often)
    if mt.startswith("audio/ogg") or mt.startswith("application/ogg"):
        return AudioFormat(container="ogg", codec="opus", mime="audio/ogg;codecs=opus")

    # MP4/AAC (Safari typical)
    if mt.startswith("audio/mp4") or mt.startswith("audio/aac") or mt.startswith("audio/m4a"):
        # Normalize to audio/mp4 (AAC)
        return AudioFormat(container="mp4", codec="aac", mime="audio/mp4")

    return None


def _ffmpeg_transcode_wav_bytes_to_format_strict(wav_bytes: bytes, fmt: AudioFormat) -> bytes:
    """
    Transcode WAV bytes to the given strict format, in-memory via ffmpeg.
    Requires ffmpeg in PATH.
    """
    if fmt.container == "wav":
        return wav_bytes

    if fmt.codec == "opus" and fmt.container in ("webm", "ogg"):
        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0",
            "-c:a", "libopus",
            "-f", fmt.container,
            "pipe:1",
        ]
        return subprocess.check_output(cmd, input=wav_bytes)

    if fmt.codec == "aac" and fmt.container == "mp4":
        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0",
            "-c:a", "aac",
            "-f", "mp4",
            "pipe:1",
        ]
        return subprocess.check_output(cmd, input=wav_bytes)

    raise ValueError(f"Unsupported strict transcode target: {fmt}")

# -------- PipelineElement: TextToSpeech (coqui-tts) ------------------------ #

class TextToSpeech(aiko.PipelineElement):
    """
    TTS: text -> encoded audio bytes
    Uses coqui-tts (import path remains 'from TTS.api import TTS'). :contentReference[oaicite:3]{index=3}

    Strict output: container/codec matches input mime_type.
    """

    def __init__(self, context):
        context.set_protocol("text_to_speech:0")
        context.call_init(self, "PipelineElement", context)
        self._tts = None
        self._tts_sr = 22050

    def start_stream(self, stream, stream_id):
        # coqui-tts keeps the same import path for the inference API. :contentReference[oaicite:4]{index=4}
        try:
            from TTS.api import TTS
        except Exception as e:
            raise RuntimeError(f"Coqui TTS import failed: {e!r}") from e

        # Choose a good default; override via pipeline parameters if desired.
        # You can list models using: `tts --list_models` (CLI). :contentReference[oaicite:5]{index=5}
        model_name, _ = self.get_parameter(
            "tts_model",
            "tts_models/en/ljspeech/tacotron2-DDC"
        )

        use_gpu, _ = self.get_parameter("tts_gpu", True)

        gpu = False
        if bool(use_gpu):
            try:
                import torch
                gpu = torch.cuda.is_available()
            except Exception:
                gpu = False

        self.logger.info(f"{self.my_id()}: loading coqui-tts model={model_name} gpu={gpu}")
        self._tts = TTS(model_name=model_name, progress_bar=False, gpu=gpu)

        # Best-effort: use model’s output sample rate if exposed
        try:
            sr = getattr(self._tts.synthesizer, "output_sample_rate", None)
            if sr:
                self._tts_sr = int(sr)
        except Exception:
            pass

        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, text, mime_type) -> Tuple[aiko.StreamEvent, dict]:
        if self._tts is None:
            self.start_stream(stream, stream.get("stream_id", "<unknown>"))

        # STRICT: determine exact target container/codec from input mime_type
        target = _parse_audio_mime_strict(mime_type)
        if target is None:
            return aiko.StreamEvent.ERROR, {
                "error": f"Strict TTS: unsupported input mime_type: {mime_type}"
            }

        text = (text or "").strip()

        # Synthesize to waveform (mono float32)
        if not text:
            wav = np.zeros(int(self._tts_sr * 1.0), dtype=np.float32)
        else:
            wav = np.asarray(self._tts.tts(text), dtype=np.float32)

        # Convert PCM -> WAV bytes
        wav_bytes = _wav_bytes_from_pcm_mono(wav, self._tts_sr)

        # WAV -> strict container/codec bytes
        out_bytes = _ffmpeg_transcode_wav_bytes_to_format_strict(wav_bytes, target)
    #   with open("/tmp/out.webm", "wb") as f:  # TODO: DEBUGING
    #       f.write(out_bytes)
    #       print("Wrote /tmp/out.webm", len(out_bytes), "bytes")

        # If you want the *exact original mime string* returned (verbatim),
        # return mime_type instead of target.mime. Otherwise target.mime is normalized.
        return aiko.StreamEvent.OKAY, {
            "audio": out_bytes, "mime_type": target.mime, "text": ""}

# --------------------------------------------------------------------------- #
# VideoReadColab is a DataSource supporting web cameras running in Google Colab
#
# parameter: "data_sources" is the read file path or device number
#
# Note: Only supports Streams with "data_sources" parameter

class VideoReadColab(aiko.DataSource):  # PipelineElement
    def __init__(self, context):
        context.set_protocol("colab:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        media_type, _ = self.get_parameter("media_type", None)
        if media_type:
            images = convert_images(images, media_type)
        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
