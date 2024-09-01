# Usage
# ~~~~~
# T=0 aiko_pipeline create pipeline_transcription.json
#
# W=0 AIKO_LOG_MQTT=true aiko_pipeline create pipeline_whisperx.json
#
# To Do
# ~~~~~
# - Match microphone audio output with WhisperX audio input data type needs
#   - Stop using audio stored in files
#
# - Pipeline "lifecycle" should depend on all PipelineElement "lifecycle"
#   - Wait until WhisperX ML Model is loaded, before Pipeline is "ready"
#
# - "AUDIO_CHUNK_DURATION" and "AUDIO_SAMPLE_DURATION" --> self.share[]
#
# - PE_MicrophoneFile could more precisely send the exact sample chunk size
#   - Carve off desired sample length from that given to _audio_sampler()
#
# - Improve PE_WhisperX to include more precise timing functionality
#
# - Perform FFT and provide sound amplitude and simple silence detection ?
# - Perform proper WhisperX VAD (Voice Activity Detection)

import os
import numpy as np
from threading import Thread
import time
from typing import Tuple

import aiko_services as aiko
from aiko_services.main.utilities import generate, get_namespace, LRUCache

_LOGGER = aiko.logger(__name__)

# PipelineElement parameters
# ~~~~~~~~~~~~~~~~~~~~~~~~~~
# PE_AudioWriteFile
AUDIO_CHANNELS = 1  # 1 or 2 channels

# --------------------------------------------------------------------------- #

class PE_LLM(PipelineElement):
    def __init__(self, context):
        context.set_protocol("llm:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, text) -> Tuple[StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {"text": text}

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into Pipeline parameters

AUDIO_CHUNK_DURATION = 5.0   # audio chunk duration in seconds
AUDIO_SAMPLE_DURATION = 5.0  # audio sample size to process
AUDIO_SAMPLE_RATE = 16000    # or 44100 Hz

AUDIO_CACHE_SIZE = int(AUDIO_SAMPLE_DURATION / AUDIO_CHUNK_DURATION)

class PE_AudioFraming(PipelineElement):
    def __init__(self, context):
        context.set_protocol("audio_framing:0")
        context.get_implementation("PipelineElement").__init__(self, context)

        self._lru_cache = LRUCache(AUDIO_CACHE_SIZE)
        _LOGGER.info(f"PE_AudioFraming: Sliding windows: {AUDIO_CACHE_SIZE}")

    def process_frame(self, stream, audio) -> Tuple[StreamEvent, dict]:
        time_start = time.time()
        audio_input_file = audio
        audio_waveform = whisperx.load_audio(audio_input_file)
        os.remove(audio_input_file)

        self._lru_cache.put(stream["frame_id"], audio_waveform)
        audio_waveform = np.concatenate(self._lru_cache.get_list())

        time_used = time.time() - time_start
        if time_used > 0.5:
            frame_id = stream["frame_id"]
            lru_cache_size = len(self._lru_cache.lru_cache)
            _LOGGER.info(f"PE_AudioFraming[{frame_id}] Time: {time_used:0.3f}s: LRU: {lru_cache_size}, Audio: {audio_waveform.shape}")

        return aiko.StreamEvent.OKAY, {"audio": audio_waveform}

# --------------------------------------------------------------------------- #

AUDIO_PATH_TEMPLATE = "y_audio_{frame_id:06}.wav"

class PE_AudioWriteFile(PipelineElement):
    def __init__(self, context):
        context.set_protocol("audio_write_file:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, audio) -> Tuple[StreamEvent, dict]:
        frame_id = stream["frame_id"]
        audio_pathname = AUDIO_PATH_TEMPLATE.format(frame_id=frame_id)
        audio_channels = self.get_parameter("audio_channels", AUDIO_CHANNELS)
        audio_writer = sf.SoundFile(audio_pathname, mode="w",
            samplerate=AUDIO_SAMPLE_RATE, channels=audio_channels)
        audio_writer.write(indata.copy())
        audio_writer.close()
        return aiko.StreamEvent.OKAY, {"audio", audio_pathname}

# --------------------------------------------------------------------------- #
# CoqUI produces audio as Python list, sampled at 22,050 Hz
#
# CoqUI TTS: version 0.22.0  VRAM size: 594 Mb

COQUI_MODEL_NAME = "tts_models/en/vctk/vits"  # TTS().list_models()[0]
COQUI_SPEAKER_ID = "p364"                     # British, female
# COQUI_SPEAKER_ID = "p226"                   # Male

COQUI_TTS_LOADED = False  # coqui.ai Text-To-Speech (TTS)
try:
    from TTS.api import TTS
    COQUI_TTS_LOADED = True
except Exception as exception:
    diagnostic = "speech_elements.py: Couldn't import TTS module"
    print(f"WARNING: {diagnostic}")
    _LOGGER.warning(diagnostic)

if COQUI_TTS_LOADED:
    class PE_COQUI_TTS(PipelineElement):
        def __init__(self, context):
            context.set_protocol("text_to_speech:0")
            implementation = context.get_implementation("PipelineElement")
            implementation.__init__(self, context)

            self._ml_model = TTS(COQUI_MODEL_NAME, gpu=True)
            _LOGGER.info(f"PE_COQUI_TTS: ML model loaded: {COQUI_MODEL_NAME}")

            self.ec_producer.update("speech", "<silence>")
            self.ec_producer.update("frame_id", -1)

        def process_frame(self, stream, text) -> Tuple[StreamEvent, dict]:
            frame_id = self.share["frame_id"] + 1
            self.ec_producer.update("frame_id", frame_id)
            if text != "<silence>":
                audio = self._ml_model.tts(text, speaker=COQUI_SPEAKER_ID)
                text = text.replace(" ", " ")  # Unicode U00A0 (NBSP)
            else:
                audio = None
                text = "<silence>"
            _LOGGER.debug(f"PE_COQUI TTS: {text}")
            self.ec_producer.update("speech", text)
            return aiko.StreamEvent.OKAY, {"audio": audio}

# --------------------------------------------------------------------------- #

class PE_SpeechFraming(PipelineElement):
    def __init__(self, context):
        context.set_protocol("speech_framing:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, text) -> Tuple[StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {"text": text}

# --------------------------------------------------------------------------- #
# WhisperX expects audio as a numpy array of np.float32, sampled at 16,000 Hz
#
# TODO: Turn some of these literals into Pipeline parameters

import requests

AIDE_SERVER_URL = "http://localhost:8080"

def aide_http_request(user_id, message, welcome=False):
    aide_server_url = f"{AIDE_SERVER_URL}/welcome"
    payload = {
        "streaming": False,
        "uiType": "voice",
        "userId": user_id
    }
    if welcome == False:
        aide_server_url = f"{AIDE_SERVER_URL}/chat"
        payload["message"] = message

    response = requests.post(aide_server_url, json=payload)
    result = response.json()
    if response.status_code == 200:
        reply = result["response"]
    else:
        reply = "Error application server status code {response.status_code}"
    return reply

CUDA_DEVICE = "cuda"
# WhisperX: version 3.1.2           Parameters    VRAM size  Relative speed
# WHISPERX_MODEL_SIZE = "tiny"    #    39 M         442 Mb   32x
# WHISPERX_MODEL_SIZE = "base"    #    74 M         506 Mb   16x
# WHISPERX_MODEL_SIZE = "small"   #   244 M         890 Mb    6x
# WHISPERX_MODEL_SIZE = "medium"  #   769 M       1,914 Mb    2x
WHISPERX_MODEL_SIZE = "large"     # 1,550 M       3,418 Mb    1x

WHISPERX_LOADED = False  # whisperX Speech-To-Text (STT)
try:
    import whisperx
    WHISPERX_LOADED = True
except Exception as exception:
    diagnostic = "speech_elements.py: Couldn't import whisperx module"
    print(f"WARNING: {diagnostic}")
    _LOGGER.warning(diagnostic)

if WHISPERX_LOADED:
    class PE_WhisperX(PipelineElement):
        def __init__(self, context):
            context.set_protocol("speech_to_text:0")
            implementation = context.get_implementation("PipelineElement")
            implementation.__init__(self, context)

        # WORKAROUND: https://github.com/m-bain/whisperX/issues/708
        # 2024-02-25: "faster-whisper" updated recently and
        # "https://github.com/m-bain/whisperX" needs to catch up !
        #
        # whisperx/asr.py:TranscriptionOptions:
        #   __new__() missing 3 required positional arguments:
        #  'max_new_tokens', 'clip_timestamps', and
        #  'hallucination_silence_threshold'

            asr_options = {
                "max_new_tokens": None,
                "clip_timestamps": None,
                "hallucination_silence_threshold": None
            }
            self._ml_model = whisperx.load_model(
                WHISPERX_MODEL_SIZE, CUDA_DEVICE, asr_options=asr_options)
            _LOGGER.info(f"PE_WhisperX: ML model loaded: {WHISPERX_MODEL_SIZE}")
            self._welcome = True

        def process_frame(self, stream, audio) -> Tuple[StreamEvent, dict]:
            audio = np.squeeze(audio)
            frame_id = stream["frame_id"]
            time_start = time.time()
            prediction = self._ml_model.transcribe(audio=audio, language="en")
            time_used = time.time() - time_start
            if time_used > 0.5:
                _LOGGER.debug(f"PE_WhisperX[{frame_id}] Time: {time_used:0.3f}")

            text = ""
            reply = "<silence>"
            if len(prediction["segments"]):
                text = prediction["segments"][0]["text"].strip().lower()
                if len(text) and  \
                    text != "you" and text != "thank you." and  \
                    text != "thanks for watching!":
                    text = text.removesuffix(".")
                    _LOGGER.info(f"PE_WhisperX[{frame_id}] INPUT: {text}")

                #   reply = aide_http_request(0, text, welcome=self._welcome)
                #   self._welcome = False
                #   _LOGGER.info(f"PE_WhisperX[{frame_id}] OUTPUT: {reply}")

                #   topic_out = f"{get_namespace()}/speech"
                #   payload_out = generate("text", [reply])
                #   aiko.message.publish(topic_out, payload_out)

                    reply = text
                else:
                    reply = "<silence>"

            if text == "terminate":
                raise SystemExit()
            return aiko.StreamEvent.OKAY, {"text": reply}

# --------------------------------------------------------------------------- #
