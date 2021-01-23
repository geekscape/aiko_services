from aiko_services.stream import StreamElement

import numpy as np
from pathlib import Path

__all__ = ["MathList", "RandInt", "Print"]


class MathList(StreamElement):
    """Adds the numbers in inputs["numbers"]"""

    expected_parameters = ("operation",)  # "add", "multiply"
    expected_inputs = ("numbers",)
    expected_outputs = ("result",)

    def stream_start_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")

        if self.operation == "add":
            self.fn = np.sum
        elif self.operation == "product":
            self.fn = np.product
        else:
            self.logger.error(f"Unsupported operation: '{self.operation}'")
            return False, None

        return True, None

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        result = {"result": self.fn(inputs.numbers)}
        return True, result


class RandInt(StreamElement):
    """Generates list of ints in 'range'. Result of length 'list_len' for
    'iterations' loops
    """

    expected_parameters = (
        ("list_len", 10),
        ("iterations", 10),
        ("min", 0),
        ("max", 10),
    )
    expected_inputs = ()
    expected_outputs = ("list",)

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        if frame_id == self.iterations:
            self.logger.info("Number of iterations completed. Exiting")
            return False, None

        result = {
            "list": list(np.random.randint(self.min, self.max, size=(self.list_len)))
        }
        return True, result


class Print(StreamElement):
    """Prints:
    f'{message}{inputs.to_print}'
    """

    expected_parameters = (
        "message_1",
        "message_2",
    )
    expected_inputs = (
        "to_print_1",
        "to_print_2",
    )
    expected_outputs = ()

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(
            f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}"
        )
        self.logger.info(f"{self.message_1}{inputs.to_print_1}")
        self.logger.info(f"{self.message_2}{inputs.to_print_2}")
        return True, None
