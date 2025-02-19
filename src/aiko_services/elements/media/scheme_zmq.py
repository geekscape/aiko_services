# To Do
# ~~~~~
# - Provide Aiko Dashboard metrics and support Metrics
#
# - Support media types "text" and "text/zip" ?
#
# - Support ZMQ REQ/REP for bidirectional request / response for control flow
#   - Provide confirmation back to the ZMQ client (zmq.REQ/REP)

import queue
from threading import Thread
import zmq

import aiko_services as aiko
from aiko_services.main.utilities import get_network_port_free

__all__ = ["DataSchemeZMQ"]

_LOGGER = aiko.get_logger(__name__)

# --------------------------------------------------------------------------- #
# parameter: "data_sources" provides the ZMQ server bind details (incoming)
# - "data_sources" list should only contain a single entry
# - "(zmq://hostname:port_range)"  port_range may be a single port or a range
#   - "(zmq://*:*)"                any available TCP port      (only localhost)
#   - "(zmq://*:6502)"             a given TCP port            (only localhost)
#   - "(zmq://*:6502-6510)"        any TCP port in the specified range
#   - "(zmq://localhost:6502)"     given hostname and TCP port
#   - "(zmq://0.0.0.0:*)"          any available TCP port      (from any host)
#   - "(zmq://0.0.0.0:6502)"       a given TCP port            (from any host)
#   - "(zmq://0.0.0.0:6502-6510)"  any TCP port in the specified range
#
# parameter: "data_targets" provides the ZMQ client connect details (outgoing)
# - "data_targets" list should only contain a single entry
# - "(zmq://hostname:port)" ...
#   - "(zmq://*:6502)"             localhost and TCP port
#   - "(zmq://localhost:6502)"     localhost and TCP port
#   - "(zmq://0.0.0.0:6502)"       given hostname and TCP port

class DataSchemeZMQ(aiko.DataScheme):
    def create_sources(self,
        stream, data_sources, frame_generator=None, use_create_frame=False):

        if not frame_generator:
            frame_generator = self.frame_generator

        try:
            zmq_url = self._parse_zmq_url(data_sources, find_free_port=True)
        except ValueError as value_error:
            return aiko.StreamEvent.ERROR, {"diagnostic": value_error}
        self.share["zmq_url"] = zmq_url
        _LOGGER.debug(f"create_sources(): zmq_url: {zmq_url}")

        self.zmq_context = zmq.Context()
        self.zmq_socket = self.zmq_context.socket(zmq.PULL)
        self.zmq_socket.bind(zmq_url)  # TODO: Exception handling
        self.zmq_socket.setsockopt(zmq.RCVTIMEO, 1000)

        self.queue = queue.Queue()
        self.terminate = False
        Thread(target=self._run, daemon=True).start()
        self.pipeline_element.create_frames(stream, frame_generator)
        return aiko.StreamEvent.OKAY, {}

    def create_targets(self, stream, data_targets):
        try:
            zmq_url = self._parse_zmq_url(data_targets)
        except ValueError as value_error:
            return aiko.StreamEvent.ERROR, {"diagnostic": value_error}
        self.share["zmq_url"] = zmq_url
        _LOGGER.debug(f"create_targets(): zmq_url: {zmq_url}")

        self.zmq_context = zmq.Context()
        self.zmq_socket = self.zmq_context.socket(zmq.PUSH)
        self.zmq_socket.connect(zmq_url)  # TODO: Exception handling

        stream.variables["target_zmq_socket"] = self.zmq_socket
        return aiko.StreamEvent.OKAY, {}

    def destroy_sources(self, stream):
        self.terminate = True

    def destroy_targets(self, stream):
        self._zmq_destroy()

    def frame_generator(self, stream, frame_id):
        data_batch_size, _ = self.pipeline_element.get_parameter(
            "data_batch_size", default=1)
        data_batch_size = int(data_batch_size)

        records = []
        while (data_batch_size > 0):
            data_batch_size -= 1
            if not self.queue.qsize():
                break
            record = self.queue.get()
            records.append(record)

        if records:
            return aiko.StreamEvent.OKAY, {"records": records}
        else:
            return aiko.StreamEvent.NO_FRAME, {}

    def _parse_zmq_url(self, data_urls, find_free_port=False):
        data_url = data_urls[0]
        path = aiko.DataScheme.parse_data_url_path(data_url)
        tokens = path.split(":")  # "hostname:port_range", e.g "*:6502-6510"
        diagnostic =  \
            f'ZMQ Data URL "{data_url}" must be "zmq://host:port_range"'
        if len(tokens) != 2:
            raise ValueError(diagnostic)
        hostname = tokens[0]

        port_range = tokens[1].split("-")
        if len(port_range) == 1:
            port_range[0] = "0" if port_range[0] == "*" else port_range[0]
            port_range = [port_range[0], port_range[0]]
        for index, port_number in enumerate(port_range):
            if not port_number.isdigit():
                raise ValueError(diagnostic)
            port_range[index] = int(port_number)
        if find_free_port and port_range[0] != port_range[1]:
            port = get_network_port_free(port_range)
        else:
            port = port_range[0]

        return f"tcp://{hostname}:{port}"

    def _run(self):
        try:
            while not self.terminate:
                try:
                    payload = self.zmq_socket.recv()
                    self.queue.put(payload)
                except zmq.Again:
                    continue
        finally:
            self._zmq_destroy()

    def _zmq_destroy(self):
        if self.zmq_socket:
            self.zmq_socket.close()
            self.zmq_socket = None
        if self.zmq_context:
            self.zmq_context.term()
            self.zmq_context = None

aiko.DataScheme.add_data_scheme("zmq", DataSchemeZMQ)

# --------------------------------------------------------------------------- #
