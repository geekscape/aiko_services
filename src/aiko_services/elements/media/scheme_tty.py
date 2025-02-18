# To Do
# ~~~~~
# - Implement character-per-record option, e.g tty://mode=raw ?
#
# - Implment TextReadTTY parameter {"tty_history": N} for command line history
#   - "N" is maximum command lines kept and "N=0" means no history (default)
#
# - Prompt uses "{}" template to optionally insert "len(tty_command_lines)"

import queue
from threading import Thread

import aiko_services as aiko

__all__ = ["DataSchemeTTY"]

# --------------------------------------------------------------------------- #
# parameters: "data_sources" provides the "tty" scheme URL
# - "data_sources" list should only contain a single entry
#   - "(tty://)"
#
# parameters: "data_targets" provides the "tty" scheme URL
# - "data_targets" list should only contain a single entry
#   - "(tty://)"

class DataSchemeTTY(aiko.DataScheme):
    def create_sources(self,
        stream, data_sources, frame_generator, use_create_frame):

        self.queue = queue.Queue()
        self.terminate = False
        Thread(target=self._run, daemon=True).start()

        rate, _ = self.pipeline_element.get_parameter("rate", default=20.0)
        self.pipeline_element.create_frames(
            stream, self.frame_generator, rate=float(rate))
        return aiko.StreamEvent.OKAY, {}

    def create_targets(self, stream, data_targets):
        return aiko.StreamEvent.OKAY, {}

    def destroy_sources(self, stream):
        self.terminate = True

    def frame_generator(self, stream, frame_id):
        if self.queue.qsize():
            record = self.queue.get()
            if record is not None:
                return aiko.StreamEvent.OKAY, {"records": [record]}
            else:
                diagnostic = "All frames generated"
                return aiko.StreamEvent.STOP, {"diagnostic": diagnostic}
        else:
            return aiko.StreamEvent.NO_FRAME, {}

    def _run(self):
        tty_prompt, _ = self.pipeline_element.get_parameter(
                            "tty_prompt", default="> ")
        print(f"000:{tty_prompt}", end="")
        while not self.terminate:
            try:
                self.queue.put(input())
            except EOFError:
                self.queue.put(None)

aiko.DataScheme.add_data_scheme("tty", DataSchemeTTY)

# --------------------------------------------------------------------------- #
"""
import threading
import queue
import sys
import termios
import tty

def non_blocking_keyboard_input():
    input_queue = queue.Queue()

    def input_reader():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                user_input = sys.stdin.read(1)  # Read one character
                input_queue.put(user_input)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    input_thread = threading.Thread(target=input_reader, daemon=True)
    input_thread.start()

    while True:
        try:
            user_input = input_queue.get(timeout=0.1)
            yield user_input
        except queue.Empty:
            continue
"""
# --------------------------------------------------------------------------- #
