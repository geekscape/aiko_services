# Installation (Ubuntu)
# ~~~~~~~~~~~~
# sudo apt-get install portaudio19-dev  # Provides "portaudio.h"
# pip install pyaudio
#
# Usage
# ~~~~~
# aiko_pipeline create ../../examples/pipeline/pipeline_mic_fft_graph.json
#
# On "Spectrum" window, press "x" to exit
#
# Resources
# ~~~~~~~~~
# https://people.csail.mit.edu/hubert/pyaudio/#downloads  # Install PyAudio
# https://realpython.com/playing-and-recording-sound-python
# https://stackoverflow.com/questions/62159107/python-install-correct-pyaudio
#
# To Do
# ~~~~~
# - Ensure that Registar interaction occurs prior to flooding the Pipeline !
#
# - Implement Microphone PipelineElement start_stream(), move __init__() code

import numpy as np
from typing import Tuple

from aiko_services import aiko, PipelineElement

__all__ = [
    "PE_AudioFilter", "PE_AudioResampler",
    "PE_FFT", "PE_GraphXY", "PE_Microphone"
]

_LOGGER = aiko.logger(__name__)

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into PipelineElement parameters
# TODO: Place some of these PipelineElement parameters into self.state[]
# TODO: Update via ECProducer

AMPLITUDE_MINIMUM = 0.1
AMPLITUDE_MAXIMUM = 12
FREQUENCY_MINIMUM = 10    # Hertz
FREQUENCY_MAXIMUM = 9000  # Hertz
SAMPLES_MAXIMUM = 100

class PE_AudioFilter(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "audio_filter:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self,
        context, amplitudes, frequencies) -> Tuple[bool, dict]:

        data = list(zip(np.abs(frequencies), amplitudes))
        data = [(x,y) for x,y in data if y >= AMPLITUDE_MINIMUM]
        data = [(x,y) for x,y in data if x >= FREQUENCY_MINIMUM]
        data = [(x,y) for x,y in data if y <= AMPLITUDE_MAXIMUM]
        data = [(x,y) for x,y in data if x <= FREQUENCY_MAXIMUM]
        amplitude_key = 1
        data = sorted(data, key=lambda x: x[amplitude_key], reverse=True)
        data = data[:SAMPLES_MAXIMUM]
        frequencies, amplitudes = zip(*data)

        return True, {"amplitudes": amplitudes, "frequencies": frequencies}

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into PipelineElement parameters
# TODO: Place some of these PipelineElement parameters into self.state[]
# TODO: Update via ECProducer

BAND_COUNT = 8

class PE_AudioResampler(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "resample:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

# Frequencies: [0:2399] --> 0, 10, 20, ... 23990 Hz
# Extract 0 to 8000 Hz
# Consolidate that into 8 bands !
# Check the maths and the normalization !

    def process_frame(self,
        context, amplitudes, frequencies) -> Tuple[bool, dict]:

        amplitudes = amplitudes[0:len(amplitudes) // 2]
        frequencies = frequencies[0:len(frequencies) // 2]

        frequency_range = frequencies[-1] - frequencies[0]
        band_width = frequency_range / BAND_COUNT / 10  # TODO: MAGIC NUMBER !!
        band_frequencies = []
        band_amplitudes = []

        for band in range(BAND_COUNT):
            band_start = band * band_width
            band_end = band_start + band_width

        # TODO: Easier to just use indices / slices, rather than a mask ?
            mask = (frequencies >= band_start) & (frequencies < band_end)
            amplitudes_sum = np.sum(amplitudes[mask])

            band_frequency_count = np.sum(mask)
            normalized_amplitudes_sum = amplitudes_sum / band_frequency_count

            band_frequencies.append((band_start + band_end) / 2)
            band_amplitudes.append(normalized_amplitudes_sum)

        frequencies = np.array(band_frequencies)
        amplitudes = np.array(band_amplitudes)

        for frequency, amplitude in zip(frequencies, amplitudes):
            print(f"Band: {frequency:.0f} Hz, amplitude: {amplitude:.4f}")

        return True, {}

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into PipelineElement parameters
# TODO: Place some of these PipelineElement parameters into self.state[]
# TODO: Update via ECProducer

AMPLITUDE_SCALER = 1_000_000

class PE_FFT(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "fft:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self, context, audio) -> Tuple[bool, dict]:
        fft_output = np.fft.fft(audio)

        amplitudes = np.abs(fft_output / AMPLITUDE_SCALER)
        top_index = np.argmax(amplitudes)

        frequencies = np.fft.fftfreq(AUDIO_CHUNK_SIZE, 1 / AUDIO_SAMPLE_RATE)
        top_amplitude = int(amplitudes[top_index])
        top_frequency = np.abs(frequencies[top_index])
        _LOGGER.debug(
            f"{self._id(context)} Loudest: {top_frequency} Hz: {top_amplitude}")

        return True, {"amplitudes": amplitudes, "frequencies": frequencies}

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into PipelineElement parameters
# TODO: Place some of these PipelineElement parameters into self.state[]
# TODO: Update via ECProducer

import cv2
import io
from PIL import Image
import pygal

GRAPH_FRAME_PERIOD = 1  # milliseconds
GRAPH_TITLE = "Spectrum"
WINDOW_TITLE = GRAPH_TITLE

class PE_GraphXY(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "graph_xy:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self,
        context, amplitudes, frequencies) -> Tuple[bool, dict]:

        data = list(zip(np.abs(frequencies), amplitudes))

        graph = pygal.XY(
            x_title="Frequency (Hz)", y_title="Amplitude", stroke=False)
        graph.title = GRAPH_TITLE
    #   graph.x_limit = [0, FREQUENCY_MAXIMUM]  # Fails :(
    #   graph.y_limit = [0, AMPLITUDE_MAXIMUM]  # Fails :(
        graph.add("Audio", data)
        graph.add("Limit", [(0, 0), (FREQUENCY_MAXIMUM, AMPLITUDE_MAXIMUM)])

        memory_file = io.BytesIO()
        graph.render_to_png(memory_file)
        memory_file.seek(0)
        image = Image.open(memory_file)
        image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        cv2.imshow(WINDOW_TITLE, image)
        if cv2.waitKey(GRAPH_FRAME_PERIOD) & 0xff == ord('x'):
            return False, {}
        else:
            return True, {"amplitudes": amplitudes, "frequencies": frequencies}

# --------------------------------------------------------------------------- #
# TODO: Turn some of these literals into PipelineElement parameters
# TODO: Place some of these PipelineElement parameters into self.state[]
# TODO: Update via ECProducer

import pyaudio
from threading import Thread

AUDIO_CHANNELS = 1              # or 2 channels
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_SAMPLE_RATE = 48000       # or 44,100 Hz or 48,000 Hz
AUDIO_CHUNK_SIZE = int(AUDIO_SAMPLE_RATE / 10)

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
import sys

def pyaudio_initialize():
    hide_alsa_messages()
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)

    py_audio = pyaudio.PyAudio()

    os.dup2(old_stderr, 2)
    os.close(old_stderr)
    return py_audio

class PE_Microphone(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "microphone:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

        self.state["frame_id"] = -1

        self.py_audio = pyaudio_initialize()
        self.audio_stream = self.py_audio.open(
            channels=AUDIO_CHANNELS,
            format=AUDIO_FORMAT,
            frames_per_buffer=AUDIO_CHUNK_SIZE,
            input=True,
            rate=AUDIO_SAMPLE_RATE)
        self.pipeline.create_stream(0)
        self.thread = Thread(target=self._audio_run).start()

    def _audio_run(self):
        self.terminate = False
        while not self.terminate:
            audio_sample_raw = self.audio_stream.read(AUDIO_CHUNK_SIZE)
            audio_sample = np.frombuffer(audio_sample_raw, dtype=np.int16)

            frame_id = self.state["frame_id"] + 1
            self.ec_producer.update("frame_id", frame_id)
            context = {"stream_id": 0, "frame_id": frame_id}
            self.pipeline.create_frame(context, {"audio": audio_sample})

        self.audio_stream.close()
        self.py_audio.terminate()

    def process_frame(self, context, audio) -> Tuple[bool, dict]:
    #   _LOGGER.debug(f"{self._id(context)} len(audio): {len(audio)}")
        return True, {"audio": audio}

    def stop_stream(self, context, stream_id):
        _LOGGER.debug(f"{self._id(context)}: stop_stream()")
        self.terminate = True

# --------------------------------------------------------------------------- #
