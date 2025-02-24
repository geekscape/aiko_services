# Installation (Ubuntu)
# ~~~~~~~~~~~~
# sudo apt-get install portaudio19-dev  # Provides "portaudio.h"
# pip install pyaudio sounddevice
#
# Usage
# ~~~~~
# aiko_pipeline create pipelines/audio_pipeline_0.json -s 1 -sr -ll debug
#
# aiko_pipeline create pipelines/audio_pipeline_0.json -s 1 -p rate ?????
#
# aiko_pipeline create pipelines/audio_pipeline_0.json -s 1  \
#   -p AudioReadFile.data_batch_size 8
#
# aiko_pipeline create pipelines/audio_pipeline_0.json -s 1  \
#   -p AudioReadFile.data_sources file://data_in/in_{}.mp3
#
# aiko_pipeline create pipelines/audio_pipeline_0.json -s 1  \
#   -p AudioWriteFile.path "file://data_out/out_{:02d}.mp3"
#
# aiko_pipeline create pipelines/audio_pipeline_0.json -s 1  \
#   sp AudioReadFile.data_sources file://data_in/in_00.mp3   \
#   sp AudioResample.rate ?????                              \
#   sp AudioWriteFile.data_targets file://data_out/out_00.mp3
#
# Resources
# ~~~~~~~~~
# https://people.csail.mit.edu/hubert/pyaudio/#downloads  # Install PyAudio
# https://realpython.com/playing-and-recording-sound-python
# https://stackoverflow.com/questions/62159107/python-install-correct-pyaudio
#
# To Do
# ~~~~~
# - Support .mp3, .ogg and .wav ?
# - Refactor Speech-To-Text and Text-To-Speech PipelineElements

from typing import Tuple
from pathlib import Path

import aiko_services as aiko

__all__ = ["AudioOutput", "AudioReadFile"]  # "AudioWriteFile"

_LOGGER = aiko.get_logger(__name__)

_XXX_IMPORTED = False
try:
#   import xxx
    _XXX_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "audio_io.py: Couldn't import xxx module"
#   print(f"WARNING: {diagnostic}")
#   _LOGGER.warning(diagnostic)
#   raise ModuleNotFoundError(
#       'xxx package not installed.  '
#       'Install aiko_services with --extras "xxx" '
#       'or install xxx manually to use the "audio_io" module')

_CV2_IMPORTED = False
try:
    import cv2
    _CV2_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "audio_io.py: Couldn't import cv2 module"
#   print(f"WARNING: {diagnostic}")
#   _LOGGER.warning(diagnostic)
#   raise ModuleNotFoundError(
#       'opencv-python package not installed.  '
#       'Install aiko_services with --extras "opencv" '
#       'or install opencv-python manually to use the "audio_io" module')

# --------------------------------------------------------------------------- #
# Useful for Pipeline output that should be all of the audios processed

class AudioOutput(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("audio_output:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, audio_samples)  \
        -> Tuple[aiko.StreamEvent, dict]:

        return aiko.StreamEvent.OKAY, {"audio_samples": bytes}

# --------------------------------------------------------------------------- #
# AudioReadFile is a DataSource which supports ...
# - Individual audio files
# - Directory of audio files with an optional filename filter
# - TODO: Archive (tgz, zip) of audio files with an optional filename filter
#
# parameter: "data_sources" is the read file path, format variable: "audio_id"
#
# Note: Only supports Streams with "data_sources" parameter

class AudioReadFile(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("audio_read_file:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
    #   stream.variables["audio_capture"] = None
        stream.variables["audio_frame_generator"] = None
        return super().start_stream(stream, stream_id, use_create_frame=False)

    def audio_frame_iterator(self, audio_capture):
        while True:
    #       status, image_bgr = audio_capture.read()
    #       if not status:
    #           break
    #       image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            yield # audio_sample

    def frame_generator(self, stream, frame_id):
        audio_frame_generator = stream.variables["audio_frame_generator"]
        while True:
            if not audio_frame_generator:
                try:
                    path, file_id = next(
                        stream.variables["source_paths_generator"])
                except StopIteration:
                    stream.variables["source_paths_generator"] = None
                    diagnostic = "End of audio file(s)"
                    return aiko.StreamEvent.STOP, {"diagnostic": diagnostic}

                if not path.is_file():
                    diagnostic = f'path "{path}" must be a file'
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

            # TODO: handle integer audio "path" ... maybe ?
            #   if isinstance(path, str) and path.isdigit():
            #       path = int(str(path))

                audio_capture = cv2.VideoCapture(str(path))
                if not audio_capture.isOpened():
                    diagnostic = f"Couldn't open audio file: {path}"
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
                stream.variables["audio_capture"] = audio_capture
                audio_frame_generator = self.audio_frame_iterator(audio_capture)
                stream.variables["audio_frame_generator"] =  \
                    audio_frame_generator

            try:
                image_rgb = next(audio_frame_generator)
                return aiko.StreamEvent.OKAY, {"images": [image_rgb]}
            except StopIteration:
                audio_frame_generator = None
                stream.variables["audio_frame_generator"] = None

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.debug(f"{self.my_id()}")
        return aiko.StreamEvent.OKAY, {"images": images}

    def stop_stream(self, stream, stream_id):
        audio_capture = stream.variables["audio_capture"]
        if audio_capture.isOpened():
            audio_capture.release()
            stream.variables["audio_capture"] = None
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
"""
# Usage
# ~~~~~
# aiko_pipeline create ../../examples/pipeline/pipeline_mic_fft_graph.json
#
# On "Spectrum" window, press "x" to exit
#
# To Do
# ~~~~~
# - Ensure that Registar interaction occurs prior to flooding the Pipeline !
# - Implement Microphone PipelineElement start_stream(), move __init__() code

from hashlib import md5
from io import BytesIO
import numpy as np
from typing import Tuple
import zlib

import aiko_services as aiko
from aiko_services.main.utilities import get_namespace, parse_number

__all__ = [
    "PE_AudioFilter", "PE_AudioResampler",
    "PE_FFT", "PE_GraphXY",
    "PE_MicrophonePA", "PE_MicrophoneSD", "PE_Speaker"
]

_LOGGER = aiko.logger(__name__)

# PipelineElement parameters
# ~~~~~~~~~~~~~~~~~~~~~~~~~~
# PE_MicrophonePA, PE_MicrophoneSD
AUDIO_CHANNELS = 1  # 1 or 2 channels

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into PipelineElement parameters
# TODO: Place some of these PipelineElement parameters into self.share[]
# TODO: Update via ECProducer

AF_AMPLITUDE_MINIMUM = 0.1
AF_AMPLITUDE_MAXIMUM = 12
AF_FREQUENCY_MINIMUM = 10    # Hertz
AF_FREQUENCY_MAXIMUM = 9000  # Hertz
AF_SAMPLES_MAXIMUM = 100

class PE_AudioFilter(PipelineElement):
    def __init__(self, context):
        context.set_protocol("audio_filter:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self,
        stream, amplitudes, frequencies) -> Tuple[aiko.StreamEvent, dict]:

        data = list(zip(np.abs(frequencies), amplitudes))
        data = [(x,y) for x,y in data if y >= AF_AMPLITUDE_MINIMUM]
        data = [(x,y) for x,y in data if x >= AF_FREQUENCY_MINIMUM]
        data = [(x,y) for x,y in data if y <= AF_AMPLITUDE_MAXIMUM]
        data = [(x,y) for x,y in data if x <= AF_FREQUENCY_MAXIMUM]
        amplitude_key = 1
        data = sorted(data, key=lambda x: x[amplitude_key], reverse=True)
        data = data[:AF_SAMPLES_MAXIMUM]
        if len(data):
            frequencies, amplitudes = zip(*data)
        else:
            frequencies, amplitudes = [], []

        return aiko.StreamEvent.AIKO,
               {"amplitudes": amplitudes, "frequencies": frequencies}

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into PipelineElement parameters
# TODO: Place some of these PipelineElement parameters into self.share[]
# TODO: Update via ECProducer

AR_BAND_COUNT = 8

class PE_AudioResampler(PipelineElement):  # TODO: AudioTransform ?
    def __init__(self, context):
        context.set_protocol("audio_resample:0")
        context.get_implementation("PipelineElement").__init__(self, context)
        self.counter = 0

# Frequencies: [0:2399] --> 0, 10, 20, ... 23990 Hz
# Extract 0 to 8000 Hz
# Consolidate that into 8 bands !
# Check the maths and the normalization !

    def process_frame(self,
        stream, amplitudes, frequencies) -> Tuple[aiko.StreamEvent, dict]:

        amplitudes = amplitudes[0:len(amplitudes) // 2]     # len: 2400
        frequencies = frequencies[0:len(frequencies) // 2]  # len: 2400

        frequency_range = frequencies[-1] - frequencies[0]  # 23990.0
        band_width = frequency_range / AR_BAND_COUNT / 10      # 299.875  # TODO: MAGIC NUMBER !!
        band_frequencies = []
        band_amplitudes = []

        for band in range(AR_BAND_COUNT):
            band_start = band * band_width
            band_end = band_start + band_width

        # TODO: Easier to just use indices / slices, rather than a mask ?
            mask = (frequencies >= band_start) & (frequencies < band_end)
            amplitudes_sum = np.sum(amplitudes[mask])

            band_frequency_count = np.sum(mask)
            normalized_amplitudes_sum = amplitudes_sum / band_frequency_count

            band_frequencies.append((band_start + band_end) / 2)
            band_amplitudes.append(amplitudes_sum)
        #   band_amplitudes.append(normalized_amplitudes_sum)

        frequencies = np.array(band_frequencies)
        amplitudes = np.array(band_amplitudes)

        topic_path = "aiko/esp32_ed6cxc/0/0/in"
        self.counter += 1
        if self.counter % 5:
            aiko.message.publish(topic_path, "(led:fill 0 0 0)")
            x = 0
            for frequency, amplitude in zip(frequencies, amplitudes):
                print(f"Band: {frequency:.0f} Hz, amplitude: {amplitude:.4f}")
                a = f"{amplitude:.0f}"
                payload_out = f"(led:line 255 0 0 {x} 0 {x} {a})"
                aiko.message.publish(topic_path, payload_out)
                x += 1
            aiko.message.publish(topic_path, "(led:write)")

        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into PipelineElement parameters
# TODO: Place some of these PipelineElement parameters into self.share[]
# TODO: Update via ECProducer

FFT_AMPLITUDE_SCALER = 1_000_000

class PE_FFT(PipelineElement):
    def __init__(self, context):
        context.set_protocol("fft:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, audio) -> Tuple[aiko.StreamEvent, dict]:
        fft_output = np.fft.fft(audio)

        amplitudes = np.abs(fft_output / FFT_AMPLITUDE_SCALER)
        top_index = np.argmax(amplitudes)

        frequencies = np.fft.fftfreq(
            PA_AUDIO_CHUNK_SIZE, 1 / PA_AUDIO_SAMPLE_RATE)
        top_amplitude = int(amplitudes[top_index])
        top_frequency = np.abs(frequencies[top_index])
        _LOGGER.debug(
            f"{self.my_id()} Loudest: {top_frequency} Hz: {top_amplitude}")

        return aiko.StreamEvent.OKAY,
               {"amplitudes": amplitudes, "frequencies": frequencies}

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into PipelineElement parameters
# TODO: Place some of these PipelineElement parameters into self.share[]
# TODO: Update via ECProducer

import cv2
import io
from PIL import Image
import pygal

GRAPH_FRAME_PERIOD = 1  # milliseconds
GRAPH_TITLE = "Spectrum"
WINDOW_TITLE = GRAPH_TITLE

class PE_GraphXY(PipelineElement):
    def __init__(self, context):
        context.set_protocol("graph_xy:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self,
        stream, amplitudes, frequencies) -> Tuple[aiko.StreamEvent, dict]:

        data = list(zip(np.abs(frequencies), amplitudes))

        graph = pygal.XY(
            x_title="Frequency (Hz)", y_title="Amplitude", stroke=False)
        graph.title = GRAPH_TITLE
    #   graph.x_limit = [0, AF_FREQUENCY_MAXIMUM]  # Fails :(
    #   graph.y_limit = [0, AF_AMPLITUDE_MAXIMUM]  # Fails :(
        graph.add("Audio", data)
        graph.add("Limit",
            [(0, 0), (AF_FREQUENCY_MAXIMUM, AF_AMPLITUDE_MAXIMUM)])

        memory_file = io.BytesIO()
        graph.render_to_png(memory_file)
        memory_file.seek(0)
        image = Image.open(memory_file)
        image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        cv2.imshow(WINDOW_TITLE, image)
        if cv2.waitKey(GRAPH_FRAME_PERIOD) & 0xff == ord('x'):
            return False, {}
        else:
            return aiko.StreamEvent.OKAY,
                   {"amplitudes": amplitudes, "frequencies": frequencies}

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into PipelineElement parameters
# TODO: Place some of these PipelineElement parameters into self.share[]
# TODO: Update via ECProducer

import pyaudio
from threading import Thread

PA_AUDIO_FORMAT = pyaudio.paInt16

PA_AUDIO_SAMPLE_RATE = 16000       # voice 16,000 or 44,100 or 48,000 Hz
# PA_AUDIO_SAMPLE_RATE = 48000     # music / spectrum analyser

PA_AUDIO_CHUNK_SIZE = PA_AUDIO_SAMPLE_RATE * 2          # Voice: 2.0 seconds
# PA_AUDIO_CHUNK_SIZE = int(PA_AUDIO_SAMPLE_RATE / 10)  # FFT:   0.1 seconds

def py_error_handler(filename, line, function, err, fmt):
    pass

from ctypes import *

def hide_alsa_messages():
    ERROR_HANDLER_FUNC = CFUNCTYPE(
        None, c_char_p, c_int, c_char_p, c_int, c_char_p)
    c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
    asound = cdll.LoadLibrary("libasound.so")
    asound.snd_lib_error_set_handler(c_error_handler)

import os
import platform
import sys

def pyaudio_initialize():
    if platform.system() == "Linux":
        hide_alsa_messages()  # Fails on Mac OS X and Windows
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)

    py_audio = pyaudio.PyAudio()

    os.dup2(old_stderr, 2)
    os.close(old_stderr)
    return py_audio

class PE_MicrophonePA(PipelineElement):
    def __init__(self, context):
        context.set_protocol("microphone:0")
        context.get_implementation("PipelineElement").__init__(self, context)

        self.share["frame_id"] = -1

        audio_channels, _ = self.get_parameter("audio_channels", AUDIO_CHANNELS)
        self.py_audio = pyaudio_initialize()
        self.audio_stream = self.py_audio.open(
            channels=audio_channels,
            format=PA_AUDIO_FORMAT,
            frames_per_buffer=PA_AUDIO_CHUNK_SIZE,
            input=True,
            rate=PA_AUDIO_SAMPLE_RATE)
        self.pipeline.create_stream(0)
        self.thread = Thread(target=self._audio_run, daemon=True).start()

    def _audio_run(self):
        self.terminate = False
        while not self.terminate:
            audio_sample_raw = self.audio_stream.read(PA_AUDIO_CHUNK_SIZE)
            audio_sample = np.frombuffer(audio_sample_raw, dtype=np.int16)

            frame_id = self.share["frame_id"] + 1
            self.ec_producer.update("frame_id", frame_id)
            stream = {"stream_id": 0, "frame_id": frame_id}
            self.create_frame(stream, {"audio": audio_sample})

        self.audio_stream.close()
        self.py_audio.terminate()

    def process_frame(self, stream, audio) -> Tuple[aiko.StreamEvent, dict]:
    #   _LOGGER.debug(f"{self.my_id()} len(audio): {len(audio)}")
        return aiko.StreamEvent.OKAY, {"audio": audio}

    def stop_stream(self, stream, stream_id):
        _LOGGER.debug(f"{self.my_id()}: stop_stream()")
        self.terminate = True
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #

SD_AUDIO_CHUNK_DURATION = 5.0    # voice: audio chunk duration in seconds
# SD_AUDIO_CHUNK_DURATION = 0.1  # music / spectrum analyser

SD_AUDIO_SAMPLE_DURATION = 5.0   # audio sample size to process
SD_AUDIO_SAMPLE_RATE = 16000     # voice 16,000 or 44,100 or 48,000 Hz
# SD_AUDIO_SAMPLE_RATE = 48000   # music / spectrum analyser

SD_SAMPLES_PER_CHUNK = SD_AUDIO_SAMPLE_RATE * SD_AUDIO_CHUNK_DURATION

import sounddevice as sd

class PE_MicrophoneSD(PipelineElement):
    def __init__(self, context):
        context.set_protocol("microphone:0")
        context.get_implementation("PipelineElement").__init__(self, context)

        self.share["mute"] = 0
        self.share["frame_id"] = -1
        self.pipeline.create_stream(0)
        self._time_mute = 0
        self._thread = Thread(target=self._audio_run, daemon=True).start()

    def _audio_run(self):
        self.terminate = False
        self._audio_sampler_start()
        audio_channels, _ = self.get_parameter("audio_channels", AUDIO_CHANNELS)

        with sd.InputStream(callback=self._audio_sampler,
            channels=audio_channels, samplerate=SD_AUDIO_SAMPLE_RATE):

            while not self.terminate:
                sd.sleep(int(SD_AUDIO_CHUNK_DURATION * 1000))

    def _audio_sampler_start(self):
        frame_id = self.share["frame_id"] + 1
        self.ec_producer.update("frame_id", frame_id)
        self._audio_sample = np.empty((0, 1), dtype=np.float32)
        return frame_id - 1

    def _audio_sampler(self, indata, frames, time_, status):
        if status:
            _LOGGER.error(f"SoundDevice error: {status}")
        else:
        #   _LOGGER.debug(f"SoundDevice callback: {len(indata)} bytes")
            if self._time_mute == 0 or time.monotonic() > self._time_mute:
                if self._time_mute:
                    self._time_mute = 0
                    self.ec_producer.update("mute", 0)

                indata = indata.copy().astype(np.float32)
                self._audio_sample = np.concatenate(
                    (self._audio_sample, indata), axis=0)
                if len(self._audio_sample) > SD_SAMPLES_PER_CHUNK:
                    audio_sample = self._audio_sample
                    frame_id = self._audio_sampler_start()
                    stream = {"stream_id": 0, "frame_id": frame_id}
                    self.create_frame(stream, {"audio": audio_sample})

    def mute(self, duration):
        duration = parse_number(duration)
        time_mute = time.monotonic() + duration
        if duration == 0 or time_mute >= self._time_mute:
            self._audio_sample = np.empty((0, 1), dtype=np.float32)
            self._time_mute = time_mute
            self.ec_producer.update("mute", duration)

    def process_frame(self, stream, audio) -> Tuple[aiko.StreamEvent, dict]:
        audio_channels, _ = self.get_parameter("audio_channels", AUDIO_CHANNELS)
        _LOGGER.info(f"SoundDevice audio_channels: {audio_channels}")
        return aiko.StreamEvent.OKAY, {"audio": audio}

    def stop_stream(self, stream, stream_id):
        _LOGGER.debug(f"{self.my_id()}: stop_stream()")
        self.terminate = True
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #

import time

# SP_AUDIO_SAMPLE_RATE = PA_AUDIO_SAMPLE_RATE
# SP_AUDIO_SAMPLE_RATE = SD_AUDIO_SAMPLE_RATE
SP_AUDIO_SAMPLE_RATE = 22050                   # coqui.ai text-to-speech
SP_SPEED_UP = 0.7                              # talk time fine tuning !

class PE_Speaker(PipelineElement):
    def __init__(self, context):
        context.set_protocol("speaker:0")
        context.get_implementation("PipelineElement").__init__(self, context)

        self._microphone_service = None
        do_discovery(
            PE_MicrophoneSD,
            ServiceFilter("*", "*", "microphone:0", "*", "*", "*"),
                lambda _, service: self._discovery_handler(service),
                lambda _:          self._discovery_handler(None))

    def _discovery_handler(self, service):
        self._microphone_service = service

    def process_frame(self, stream, audio) -> Tuple[aiko.StreamEvent, dict]:
        if audio is not None:
            sd.play(audio, SP_AUDIO_SAMPLE_RATE)
            duration = len(audio) / SD_AUDIO_SAMPLE_RATE * SP_SPEED_UP
            if self._microphone_topic_path:
                self._microphone_topic_path.mute(duration)
            time.sleep(duration)
        return aiko.StreamEvent.OKAY, {"audio": audio}
"""
# --------------------------------------------------------------------------- #
