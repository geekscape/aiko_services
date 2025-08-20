# Usage
# ~~~~~
# grep -A8 '"graph"' ../robot_pipeline.json  # Show PipelineDefinition Graph
# grep   '{ "name"'  ../robot_pipeline.json  # Show PipelineElements list  }
#
# (cd ../virtual; ./world.py -gp World_ZMQ -frp 1)
# aiko_pipeline create ../../../elements/media/webcam_zmq_pipeline_0.json  \
#       -s 1 -p resolution 640x480
#
# aiko_pipeline create ../robot_pipeline.json -s 1 -gt 3600 -ll warning
#
# To Do
# ~~~~~
# - Console (keyboard) input and output ... Aiko Dashboard plug-in ?
#   - Change Pipeline / PipelineElements debug level or set any parameter
#   - Select robot: None, One or All, e.g "/robot name" or "/r all"
#     - Prompt shows selected robot(s), i.e use "stream.variables[]"
#   - Emergency stop and robot commands (literal and direct)
#   - Show text response ... speech to human and commands to robot
#   - Subscribe to MQTT topic(s)
#
# - Provide Microphone     --> Speech-To-Text [push-to-talk]
# - Provide Text-To-Speech --> Speaker        [mute]

from typing import Tuple

import aiko_services as aiko
from aiko_services.main import do_discovery, ServiceFilter
from aiko_services.main.utilities import parse

__all__ = ["PromptMediaFusion", "RobotActions", "RobotAgents"]

# --------------------------------------------------------------------------- #
# TODO: Merge with RobotAgents ?

class PromptMediaFusion(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("robot_actions:0")
        context.call_init(self, "PipelineElement", context)

    def start_stream(self, stream, stream_id):
        stream.variables["ml_memory_detections"] = []
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, detections, texts)  \
        -> Tuple[aiko.StreamEvent, dict]:

    # "ml_memory_detections": Remove old detections
    # "ml_memory_detections": Add new detections

        detections = ["octopus", "oak_tree"]

        return aiko.StreamEvent.OKAY, {
            "detections": detections, "texts": texts}

# --------------------------------------------------------------------------- #

class RobotActions(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("robot_actions:0")
        context.call_init(self, "PipelineElement", context)

    def _get_robot(self, stream):
        return stream.variables["robot_actions_actor"]

    def _set_robot(self, stream, robot):
        stream.variables["robot_actions_actor"] = robot

    def start_stream(self, stream, stream_id):
        self._set_robot(stream, None)

        from aiko_services.examples.xgo_robot.xgo_robot import XGORobot
        service_name, found = self.get_parameter("service_name", None)
        if not found:
            diagnostic = 'Must provide "service_name" parameter'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        def discovery_add_handler(service_details, service):
            self.logger.warning(f"Discovered robot: {service_name}")
            self._set_robot(stream, service)

        def discovery_remove_handler(service_details):
            self.logger.warning(f"Lost robot: {service_name}")
            self._set_robot(stream, None)

        self.logger.warning(f'Waiting to discover robot "{service_name}"')
        service_filter = ServiceFilter("*", service_name, "*", "*", "*", "*")
        service_discovery, service_discovery_handler =  \
            do_discovery(
                XGORobot, service_filter,
                discovery_add_handler, discovery_remove_handler)

        stream.variables["robot_selected"] = True
        stream.variables["robot_actions_discovery_details"] = (
            service_discovery, service_discovery_handler, service_filter)
        return aiko.StreamEvent.OKAY, {}

    def process_command(self, stream, robot, command, parameters):
        if command == "action" and len(parameters) > 0:
            command = parameters[0]

        #   if command == "select":
        #       if parameters[1] == "all":
        #           parameters[1] = ROBOT_NAME  # TODO: Get ROBOT_NAME
        #       if parameters[1] == "bruce":
        #           parameters[1] = "laika"
        #       selected = parameters[1] == ROBOT_NAME  # TODO: Get ROBOT_NAME
        #       stream.variables["robot_selected"] = selected

            if not stream.variables["robot_selected"]:
                self.logger.warning("A robot has not been selected")
                return False

            if command == "arm":
                if parameters[1] == "lower":
                    robot.arm(130, -40)
                if parameters[1] == "raise":
                    robot.arm(80, 80)
            elif command == "backwards":
                robot.stop()
                robot.move("x", -10)
            elif command == "crawl":
                robot.action("crawl")
            elif command == "forwards":
                robot.stop()
                robot.move("x", +10)
            elif command == "hand":
                if parameters[1] == "close":
                    robot.claw(255)
                if parameters[1] == "open":
                    robot.claw(0)
            elif command == "pee":
                robot.action("pee")
            elif command == "pitch":
                if parameters[1] == "down":
                    robot.attitude(15, 0, 0)
                if parameters[1] == "up":
                    robot.attitude(0, 0, 0)
            elif command == "reset":
                robot.reset()
            elif command == "sit":
                robot.action("sit")
            elif command == "sniff":
                robot.action("sniff")
            elif command == "stop":
                robot.stop()
            elif command == "stretch":
                robot.action("stretch")
            elif command == "turn":
                if parameters[1] == "left":
                    robot.turn(+40)
                if parameters[1] == "right":
                    robot.turn(-40)
            elif command == "wag":
                robot.action("wiggle_tail")
            else:
                return False
        return True

    def process_frame(self, stream, texts) -> Tuple[aiko.StreamEvent, dict]:
        if texts:
            robot = self._get_robot(stream)
            for text in texts:
                if not text:
                    continue
                try:
                    success = "❌"
                    if robot:  # TODO: Check only when a robot command occurs
                        success = "❓"
                        text = text if text != "r" else "action reset"
                        text = text if text != "s" else "action stop"
                        command, parameters = parse(text)
                        if self.process_command(
                            stream, robot, command, parameters):
                            success = "✅"

                    self.logger.warning(f"{self.my_id()}: {success}: {text}")
                except Exception as exception:
                    self.logger.warning(exception)
        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        self._set_robot(stream, None)
        service_discovery, service_discovery_handler, service_filter =  \
            stream.variables["robot_actions_discovery_details"]
        service_discovery.remove_handler(
            service_discovery_handler, service_filter)
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
# TODO: Merge with PromptMediaFusion ?

def create_initial_value(stream, name):  # TODO: Move to "main/stream.py"
    frame = stream.frames[stream.frame_id]
    return frame.swag[name] if name in frame.swag else []

class RobotAgents(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("robot_actions:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {
            "detections": create_initial_value(stream, "detections"),
            "texts":      create_initial_value(stream, "texts")}

# --------------------------------------------------------------------------- #
