# Usage
# ~~~~~
# T=0 AIKO_LOG_MQTT=false aiko_pipeline create pipeline_transcription.json
#
# M=0 AIKO_LOG_MQTT=false aiko_pipeline create pipeline_microphone.json
#
# W=0 AIKO_LOG_MQTT=true  aiko_pipeline create pipeline_whisperx.json
#
# To Do
# ~~~~~
# - Match microphone audio output with WhisperX audio input data type needs
#   - Stop using audio stored in files
#
# - Pipeline "lifecycle" should depend on all PipelineElement "lifecycle"
#   - Wait until WhisperX ML Model is loaded, before Pipeline is "ready"
#
# - "AUDIO_CHUNK_DURATION" and "AUDIO_SAMPLE_DURATION" --> self.state[]
#
# - PE_MicrophoneFile could more precisely send the exact sample chunk size
#   - Carve off desired sample length from that given to _audio_sampler()
#
# - Improve PE_WhisperX to include more precise timing functionality
#
# - Perform FFT and provide sound amplitude and simple silence detection ?
# - Perform proper WhisperX VAD (Voice Activity Detection)

from hashlib import md5
from io import BytesIO
import os
import numpy as np
import sounddevice as sd
import soundfile as sf
from threading import Thread
import time
from typing import Tuple
import whisperx
import zlib

from aiko_services import aiko, PipelineElement
from aiko_services.utilities import generate, get_namespace, LRUCache

_LOGGER = aiko.logger(__name__)

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into Pipeline parameters

AUDIO_CHANNELS = 1           # or 2 channels
AUDIO_CHUNK_DURATION = 3.0   # audio chunk duration in seconds
AUDIO_SAMPLE_DURATION = 3.0  # audio sample size to process
AUDIO_SAMPLE_RATE = 16000    # or 44100 Hz

_AUDIO_CACHE_SIZE = int(AUDIO_SAMPLE_DURATION / AUDIO_CHUNK_DURATION)
_AUDIO_PATH_TEMPLATE = "y_audio_{frame_id:06}.wav"

class PE_AudioWriteFile(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "audio_write_file:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self, context, audio) -> Tuple[bool, dict]:
        frame_id = context["frame_id"]
        audio_pathname = _AUDIO_PATH_TEMPLATE.format(frame_id=frame_id)
        audio_writer = sf.SoundFile(audio_pathname, mode="w",
            samplerate=AUDIO_SAMPLE_RATE, channels=AUDIO_CHANNELS)
        audio_writer.write(indata.copy())
        audio_writer.close()
        return True, {"audio", audio_pathname}

# --------------------------------------------------------------------------- #

class PE_AudioFraming(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "audio_framing:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

        self._lru_cache = LRUCache(_AUDIO_CACHE_SIZE)
        _LOGGER.info(f"PE_AudioFraming: Sliding windows: {_AUDIO_CACHE_SIZE}")

    def process_frame(self, context, audio) -> Tuple[bool, dict]:
        time_start = time.time()
        audio_input_file = audio
        audio_waveform = whisperx.load_audio(audio_input_file)
        os.remove(audio_input_file)

        self._lru_cache.put(context["frame_id"], audio_waveform)
        audio_waveform = np.concatenate(self._lru_cache.get_list())

        time_used = time.time() - time_start
        if time_used > 0.5:
            frame_id = context["frame_id"]
            lru_cache_size = len(self._lru_cache.lru_cache)
            _LOGGER.info(f"PE_AudioFraming[{frame_id}] Time: {time_used:0.3f}s: LRU: {lru_cache_size}, Audio: {audio_waveform.shape}")

        return True, {"audio": audio_waveform}

# --------------------------------------------------------------------------- #
"""
class PE_MicrophoneFile(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "microphone:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

        self.state["frame_id"] = -1
        self._audio_writer = None
        self._thread = Thread(target=self._run).start()

    def _audio_sample_start(self):
        frame_id = self.state["frame_id"] + 1
        self.ec_producer.update("frame_id", frame_id)
        audio_pathname = _AUDIO_PATH_TEMPLATE.format(frame_id=frame_id)

        self._audio_sample_time = time.time() + AUDIO_CHUNK_DURATION
        if self._audio_writer:
            self._audio_writer.close()
        self._audio_writer = sf.SoundFile(audio_pathname, mode="w",
            samplerate=AUDIO_SAMPLE_RATE, channels=AUDIO_CHANNELS)

        return frame_id - 1

    def _audio_sampler(self, indata, frames, time_, status):
        if status:
            _LOGGER.error(f"SoundDevice error: {status}")
        else:
        #   _LOGGER.debug(f"SoundDevice callback: {len(indata)} bytes")
            self._audio_writer.write(indata.copy())
            if time.time() > self._audio_sample_time:
                frame_id = self._audio_sample_start()
                context = {"stream_id": 0, "frame_id": frame_id}
                self.pipeline.create_frame(context, {})

    def process_frame(self, context) -> Tuple[bool, dict]:
        frame_id = context["frame_id"]
        audio_pathname = _AUDIO_PATH_TEMPLATE.format(frame_id=frame_id)
        _LOGGER.debug(
            f"PE_MicrophoneFile[{frame_id}] out audio: {audio_pathname}")
        return True, {"audio": audio_pathname}

    def _run(self):
        self._audio_sample_start()
        with sd.InputStream(callback=self._audio_sampler,
            channels=AUDIO_CHANNELS, samplerate=AUDIO_SAMPLE_RATE):

            while True:  # self.running
                sd.sleep(int(AUDIO_CHUNK_DURATION * 1000))
"""
# --------------------------------------------------------------------------- #

class PE_MockTTS(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "audio:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

        self.ec_producer.update("speech", "(nil)")
        self.ec_producer.update("frame_id", -1)

    def process_frame(self, context, audio) -> Tuple[bool, dict]:
        frame_id = self.state["frame_id"] + 1
        self.ec_producer.update("frame_id", frame_id)
        speech = f'This is frame number {frame_id}'
        self.ec_producer.update("speech", speech.replace(" ", "_"))
        _LOGGER.info(f"PE_MockTTS: Speech {speech}")
        return True, {"speech": speech}

# --------------------------------------------------------------------------- #

class PE_SpeechFraming(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "speech_framing:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self, context, speech) -> Tuple[bool, dict]:
        return True, {"speech": speech}

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into Pipeline parameters
"""
CUDA_DEVICE = "cuda"
                                  # Parameters    VRAM size  Relative speed
# WHISPERX_MODEL_SIZE = "tiny"    #    39 M       2,030 Mb   32x
# WHISPERX_MODEL_SIZE = "base"    #    74 M       2,054 Mb   16x
# WHISPERX_MODEL_SIZE = "small"   #   244 M       2,926 Mb    6x
WHISPERX_MODEL_SIZE = "medium"    #   769 M       5,890 Mb    2x
# WHISPERX_MODEL_SIZE = "large"   # 1,550 M     > 6,140 Mb    1x

class PE_WhisperX(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "transcription:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

        self._ml_model = whisperx.load_model(WHISPERX_MODEL_SIZE, CUDA_DEVICE)
        _LOGGER.info(f"PE_WhisperX: ML model loaded: {WHISPERX_MODEL_SIZE}")

    def process_frame(self, context, audio) -> Tuple[bool, dict]:
        frame_id = context["frame_id"]
        time_start = time.time()
        prediction = self._ml_model.transcribe(
        #   audio=audio, language="en")
            audio=audio, verbose=None, fp16=False, language="en")
        speech = prediction["text"].strip().lower()
        if len(speech) and  \
            speech != "you" and speech != "thanks for watching!":
            _LOGGER.info(f"PE_WhisperX[{frame_id}] {speech}")
            payload_out = generate("speech", [speech])
            aiko.message.publish(f"{get_namespace()}/speech", payload_out)
        else:
            speech = ""
        time_used = time.time() - time_start
        if time_used > 0.5:
            _LOGGER.info(f"PE_WhisperX[{frame_id}] Time: {time_used:0.3f}s")
        _LOGGER.debug(f"PE_WhisperX: {context}, in audio, out speech: {speech}")
        if speech.removesuffix(".") == "terminate":
            raise SystemExit()
        return True, {"speech": speech}
"""
# --------------------------------------------------------------------------- #

TOPIC_AUDIO = f"{get_namespace()}/audio"

class PE_RemoteReceive0(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "remote_receive:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

        self.state["frame_id"] = 0
        self.state["topic_audio"] = f"{TOPIC_AUDIO}/{self.name[-1]}"
        self.add_message_handler(
            self._audio_receive, self.state["topic_audio"], binary=True)

    def _audio_receive(self, aiko, topic, payload_in):
        payload_in = zlib.decompress(payload_in)
        payload_in = BytesIO(payload_in)
        if False:
            buffer = payload_in.getbuffer()
            digest = md5(buffer).hexdigest()
            print(f"payload_in: len: {len(buffer)}, md5: {digest}")
        audio_sample = np.load(payload_in, allow_pickle=True)
        frame_id = self.state["frame_id"]
        self.ec_producer.update("frame_id", frame_id + 1)
        context = {"stream_id": 0, "frame_id": frame_id}
        self.pipeline.create_frame(context, {"audio": audio_sample})

    def process_frame(self, context, audio) -> Tuple[bool, dict]:
        return True, {"audio": audio}

class PE_RemoteReceive1(PE_RemoteReceive0):
    pass

# --------------------------------------------------------------------------- #

class PE_RemoteSend0(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "remote_send:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

        self.state["topic_audio"] = f"{TOPIC_AUDIO}/{self.name[-1]}"

    def process_frame(self, context, audio) -> Tuple[bool, dict]:
        payload_out = BytesIO()
        np.save(payload_out, audio, allow_pickle=True)
        if False:
            buffer = payload_out.getbuffer()
            digest = md5(buffer).hexdigest()
            print(f"{self._id(context)}, len: {len(buffer)}, md5: {digest}")
        payload_out = zlib.compress(payload_out.getvalue())
        aiko.message.publish(self.state["topic_audio"], payload_out)
        return True, {}

class PE_RemoteSend1(PE_RemoteSend0):
    pass

# --------------------------------------------------------------------------- #
