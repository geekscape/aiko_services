# Usage
# ~~~~~
# T=0 AIKO_LOG_MQTT=false aiko_pipeline create pipeline_transcription.json
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

import os
import numpy as np
from threading import Thread
import time
from typing import Tuple

from aiko_services import aiko, PipelineElement
from aiko_services.utilities import generate, get_namespace, LRUCache

_LOGGER = aiko.logger(__name__)

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into Pipeline parameters

AUDIO_CHANNELS = 1           # or 2 channels
AUDIO_CHUNK_DURATION = 3.0   # audio chunk duration in seconds
AUDIO_SAMPLE_DURATION = 3.0  # audio sample size to process
AUDIO_SAMPLE_RATE = 16000    # or 44100 Hz

AUDIO_CACHE_SIZE = int(AUDIO_SAMPLE_DURATION / AUDIO_CHUNK_DURATION)

class PE_AudioFraming(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "audio_framing:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

        self._lru_cache = LRUCache(AUDIO_CACHE_SIZE)
        _LOGGER.info(f"PE_AudioFraming: Sliding windows: {AUDIO_CACHE_SIZE}")

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

AUDIO_PATH_TEMPLATE = "y_audio_{frame_id:06}.wav"

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
        audio_pathname = AUDIO_PATH_TEMPLATE.format(frame_id=frame_id)
        audio_writer = sf.SoundFile(audio_pathname, mode="w",
            samplerate=AUDIO_SAMPLE_RATE, channels=AUDIO_CHANNELS)
        audio_writer.write(indata.copy())
        audio_writer.close()
        return True, {"audio", audio_pathname}

# --------------------------------------------------------------------------- #
# CoqUI produces audio as Python list, sampled at 22,050 Hz

COQUI_MODEL_NAME = "tts_models/en/vctk/vits"  # TTS().list_models()[0]
COQUI_SPEAKER_ID = "p364"

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
        def __init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline):

            protocol = "text_to_speech:0"
            implementations["PipelineElement"].__init__(self,
                implementations, name, protocol, tags, transport,
                definition, pipeline)

            self._ml_model = TTS(COQUI_MODEL_NAME)
            _LOGGER.info(f"PE_COQUI_TTS: ML model loaded: {COQUI_MODEL_NAME}")

            self.ec_producer.update("speech", "(nil)")
            self.ec_producer.update("frame_id", -1)

        def process_frame(self, context, text) -> Tuple[bool, dict]:
            frame_id = self.state["frame_id"] + 1
            self.ec_producer.update("frame_id", frame_id)

            audio = self._ml_model.tts(text, speaker=COQUI_SPEAKER_ID)

            _LOGGER.info(f"PE_COQUI: Speech {text}")
            self.ec_producer.update("speech", text.replace(" ", "_"))
            return True, {"audio": audio}

# --------------------------------------------------------------------------- #

class PE_SpeechFraming(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "speech_framing:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self, context, text) -> Tuple[bool, dict]:
        return True, {"text": text}

# --------------------------------------------------------------------------- #
# WhisperX expects audio as a numpy array of np.float32, sampled at 16,000 Hz
#
# TODO: Turn some of these literals into Pipeline parameters

CUDA_DEVICE = "cuda"
                                  # Parameters    VRAM size  Relative speed
# WHISPERX_MODEL_SIZE = "tiny"    #    39 M       2,030 Mb   32x
# WHISPERX_MODEL_SIZE = "base"    #    74 M       2,054 Mb   16x
# WHISPERX_MODEL_SIZE = "small"   #   244 M       2,926 Mb    6x
WHISPERX_MODEL_SIZE = "medium"    #   769 M       5,890 Mb    2x
# WHISPERX_MODEL_SIZE = "large"   # 1,550 M     > 6,140 Mb    1x

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
        def __init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline):

            protocol = "speech_to_text:0"
            implementations["PipelineElement"].__init__(self,
                implementations, name, protocol, tags, transport,
                definition, pipeline)

            self._ml_model = whisperx.load_model(
                WHISPERX_MODEL_SIZE, CUDA_DEVICE)
            _LOGGER.info(f"PE_WhisperX: ML model loaded: {WHISPERX_MODEL_SIZE}")

        def process_frame(self, context, audio) -> Tuple[bool, dict]:
            audio = np.squeeze(audio)

            frame_id = context["frame_id"]
            time_start = time.time()
            prediction = self._ml_model.transcribe(
                audio=audio, language="en")
            #   audio=audio, verbose=None, fp16=False, language="en")

            text = ""
            if len(prediction["segments"]):
                text = prediction["segments"][0]["text"].strip().lower()
                if len(text) and  \
                    text != "you" and text != "thank you." and  \
                    text != "thanks for watching!":
                    _LOGGER.info(f"PE_WhisperX[{frame_id}] {text}")
                    topic_out = f"{get_namespace()}/speech"
                    payload_out = generate("text", [text])
                    aiko.message.publish(topic_out, payload_out)
                else:
                    text = ""

            time_used = time.time() - time_start
            if time_used > 0.5:
                _LOGGER.info(f"PE_WhisperX[{frame_id}] Time: {time_used:0.3f}s")
            _LOGGER.debug(
                f"PE_WhisperX: {context}, in audio, out text: {text}")
            if text.removesuffix(".") == "terminate":
                raise SystemExit()
            return True, {"text": text}

# --------------------------------------------------------------------------- #
