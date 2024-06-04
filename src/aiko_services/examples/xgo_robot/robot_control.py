#!/usr/bin/env python3
#
# Usage
# ~~~~~
# - https://github.com/ultralytics/ultralytics/issues/3005
# pip uninstall av  # conflict between PyTorch and OpenCV imshow()
#
# ./robot_control.py ui [topic_path]  # Control robot and display camera input
# ./robot_control.py video_test       # Test for video transmission and display
#
# UI keyboard commands
# - r: Reset robot actuators to initial positions
# - s: Save image to disk as "z_image_??????.jpg"
# - v: Verbose screen detail (toggle state)
# - x: eXit
#
# Refactor
# ~~~~~~~~
# - ServiceDiscovery / ActorDiscovery (pipeline.py, transport/)
# - Combine _image_to_bgr() and _image_to_rgb() --> _image_convert()
# - Move to "aiko_services/video/" (or "media/") ...
#  - _camera*() and _screen*() functions
#  - _image_convert(), _image_resize()
# - Generalize daggy video (and audio) compression / transmission over MQTT
# - Generalize image overlay
# - Resource monitoring: CPU, memory, network, etc
#
# To Do
# ~~~~~
# - Discover "xgo_robot" Actor and use "topic_path/video" instead
#   - When absent, display a video image that shows "robot not found"
#   - Replace low-level aiko.message.publish() with high-level function calls
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# - Video image flip on vertical axis for correct orientation (robot view) !
#
# - Keyboard commands: Display "help" on screen, key='?' ...
#   - Reset (R)
#   - Terminate (T) and Halt/Shutdown (H)
#   - Action, e.g sit
#   - Arm mode ... and arm and claw position
#   - Pitch, roll, yaw: keyboard arrows and display value
#   - Translate: x, y, z: keyboard arrows and display value
#   - Move forward, back, left, right, turn
#   - Motor speed and display value
#   - Pick-up and put-down ball
#
# - Payload includes frame id and other status, e.g battery level, motor speed
#
# - Send text to display on video screen
# - Send video to the LCD screen (overlay with local status)
# - Send audio sample (MP3 ?) to speaker
# - Disable / enable microphone audio transmission

from abc import abstractmethod
import click
import cv2
from io import BytesIO
import numpy as np
from threading import Thread
import time
import zlib

import torch
from ultralytics import YOLO

import aiko_services as aiko

_VERSION = 0

ACTOR_TYPE_UI = "robot_control"
PROTOCOL_UI = f"{ServiceProtocol.AIKO}/{ACTOR_TYPE_UI}:{_VERSION}"
ACTOR_TYPE_VIDEO_TEST = "video_test"
PROTOCOL_VIDEO_TEST = f"{ServiceProtocol.AIKO}/{ACTOR_TYPE_VIDEO_TEST}:{_VERSION}"
ROBOT_NAME = "ROBOT_NAME"
TOPIC_DETECTIONS = f"{get_namespace()}/detections"
TOPIC_SPEECH = f"{get_namespace()}/speech"
TOPIC_VIDEO = f"{get_namespace()}/ROBOT_NAME/video"

_LOGGER = aiko.logger(__name__)

# --------------------------------------------------------------------------- #

class RobotControl(Actor):
    Interface.default("RobotControl", "__main__.RobotControlImpl")

    @abstractmethod
    def image(self, aiko, topic, payload_in):
        pass

class RobotControlImpl(RobotControl):
    def __init__(self, context, robot_topic):
        context.get_implementation("Actor").__init__(self, context)

        self.share["frame_id"] = 0
        self.share["robot_topic"] = robot_topic
        self.share["source_file"] = f"v{_VERSION}⇒ {__file__}"
        self.share["topic_video"] = TOPIC_VIDEO

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = YOLO("../yolo/yolov8n_robotdog.pt", "v8")
        self.selected = False

        self.add_message_handler(self.speech, TOPIC_SPEECH)
        self.add_message_handler(self.image, TOPIC_VIDEO, binary=True)

    def speech(self, aiko, topic, payload_in):
        try:
            command, parameters = parse(payload_in)
            if command == "action" and len(parameters) > 0:
                command = parameters[0]
                topic_out = f"{self.share['robot_topic']}/in"
                payload_out = None
                stop = False

                if command == "select":
                    if parameters[1] == "all":
                        parameters[1] = ROBOT_NAME
                    if parameters[1] == "bruce":
                        parameters[1] = "laika"
                    self.selected = parameters[1] == ROBOT_NAME
                if not self.selected:
                    return

                if command == "arm":
                    if parameters[1] == "lower":
                        payload_out = "(arm 130 -40)"
                    if parameters[1] == "raise":
                        payload_out = "(arm 80 80)"
                elif command == "backwards":
                    stop = True
                    payload_out = "(move x -10)"
                elif command == "crawl":
                    payload_out = "(action crawl)"
                elif command == "forwards":
                    stop = True
                    payload_out = "(move x 10)"
                elif command == "hand":
                    if parameters[1] == "close":
                        payload_out = "(claw 255)"
                    if parameters[1] == "open":
                        payload_out = "(claw 0)"
                elif command == "pee":
                    payload_out = "(action pee)"
                elif command == "pitch":
                    if parameters[1] == "down":
                        payload_out = "(attitude 15 0 0)"
                    if parameters[1] == "up":
                        payload_out = "(attitude 0 0 0)"
                elif command == "reset":
                    payload_out = "(reset)"
                elif command == "sit":
                    payload_out = "(action sit)"
                elif command == "sniff":
                    payload_out = "(action sniff)"
                elif command == "stop":
                    stop = True
                elif command == "stretch":
                    payload_out = "(action stretch)"
                elif command == "turn":
                    if parameters[1] == "left":
                        payload_out = "(turn 40)"
                    if parameters[1] == "right":
                        payload_out = "(turn -40)"
                elif command == "wag":
                    payload_out = "(action wiggle_tail)"

                if stop:
                    aiko.message.publish(topic_out, "(stop)")
                if payload_out:
                #   speech = speech.replace(" ", " ")  # Unicode U00A0 (NBSP)
                #   speech = speech.replace(" ", "_")  # TODO: Fix this mess :(
                    aiko.message.publish(topic_out, payload_out)
        except:
            pass

    def speech_naive(self, aiko, topic, payload_in):
        try:
            command, parameters = parse(payload_in)
            if command == "speech" and len(parameters) == 1:
                speech = parameters[0]
                topic_out = f"{self.share['robot_topic']}/in"
                payload_out = None
                stop = False
                if "reset" in speech:
                    payload_out = "(reset)"
                elif "stop" in speech:
                    stop = True
                elif "forward" in speech:
                    stop = True
                    payload_out = "(move x 10)"
                elif "backward" in speech:
                    stop = True
                    payload_out = "(move x -10)"
                elif "turn" in speech:
                    stop = True
                    if "left" in speech:
                        payload_out = "(turn 40)"
                    if "right" in speech:
                        payload_out = "(turn -40)"
                elif "arm" in speech:
                    if "raise" in speech:
                        payload_out = "(arm 80 80)"
                    if "lower" in speech:
                        payload_out = "(arm 130 -40)"
                elif "hand" in speech:
                    if "open" in speech:
                        payload_out = "(claw 0)"
                    if "close" in speech:
                        payload_out = "(claw 255)"
                elif "pitch" in speech:
                    if "down" in speech:
                        payload_out = "(attitude 15 0 0)"
                    if "up" in speech:
                        payload_out = "(attitude 0 0 0)"
                elif "crawl" in speech:
                    payload_out = "(action crawl)"
                elif "whiz" in speech:
                    payload_out = "(action pee)"
                elif "sit" in speech:
                    payload_out = "(action sit)"
                elif "sniff" in speech:
                    payload_out = "(action sniff)"
                elif "stretch" in speech:
                    payload_out = "(action stretch)"
                elif "wag" in speech:
                    payload_out = "(action wiggle_tail)"

                if stop:
                    aiko.message.publish(topic_out, "(stop)")
                if payload_out:
                #   speech = speech.replace(" ", " ")  # Unicode U00A0 (NBSP)
                    speech = speech.replace(" ", "_")  # TODO: Fix this mess :(
                    aiko.message.publish(topic_out, f"(speech {speech})")
                    aiko.message.publish(topic_out, payload_out)
        except:
            pass

    def image(self, aiko, topic, payload_in):
        frame_id = self.share["frame_id"]
        self.ec_producer.update("frame_id", frame_id + 1)

        payload_in = zlib.decompress(payload_in)
        payload_in = BytesIO(payload_in)
        image = np.load(payload_in, allow_pickle=True)

        image = self._image_resize(image)  # increase to 640x480
        image = self._image_detection(image)

        image = self._image_to_bgr(image)
        cv2.imshow("xgo_robot", image)
        key = cv2.waitKey(1) & 0xff
        if key == ord("r"):
            payload_out = "(reset)"
            aiko.message.publish(
                f"{self.share['robot_topic']}/in", payload_out)
            payload_out = "(claw 128)"
            aiko.message.publish(
                f"{self.share['robot_topic']}/in", payload_out)
        if key == ord("s"):
            cv2.imwrite(f"z_image_{frame_id:06d}.jpg", image)
        if key == ord("v"):
            payload_out = "(screen_detail)"  # toggle state
            aiko.message.publish(
                f"{self.share['robot_topic']}/in", payload_out)
        if key == ord("x"):
            cv2.destroyAllWindows()
            raise SystemExit()

    def _image_detection(self, image):
    #   results = self.model.predict(image, device=self.device, verbose=False)
        results = self.model(image, device=self.device, verbose=False)
        image = results[0].plot()  # bounding box, class and confidence

        if self.selected:
            names = set()
            for box in results[0].boxes:
                names.add(results[0].names[box.cls[0].item()])
            if names:
                names = " ".join(str(name) for name in names)
                payload_out = f"{ROBOT_NAME}: {names}"
                aiko.message.publish(TOPIC_DETECTIONS, payload_out)
        return image

    def _image_to_bgr(self, image):
        r, g, b = cv2.split(image)
        image = cv2.merge((b, g, r))
        return image

    def _image_resize(self, image, scale=2):
        width = int(image.shape[1] * scale * 2)
        height = int(image.shape[0] * scale * 2)
        dimensions = (width, height)
        image = cv2.resize(image, dimensions, interpolation=cv2.INTER_CUBIC)
        return image

# --------------------------------------------------------------------------- #

SLEEP_PERIOD = 0.2     # seconds
STATUS_XY = (10, 230)  # (10, 15)

class VideoTest(Actor):
    Interface.default("VideoTest",
        "aiko_services.examples.xgo_robot.robot_control.VideoTestImpl")

class VideoTestImpl(VideoTest):
    def __init__(self, context):
        context.get_implementation("Actor").__init__(self, context)

        self.share["sleep_period"] = SLEEP_PERIOD
        self.share["source_file"] = f"v{_VERSION}⇒ {__file__}"
        self.share["topic_video"] = TOPIC_VIDEO

        self._camera = self._camera_initialize()
        self._thread = Thread(target=self._run).start()

    def _camera_initialize(self):
        camera = cv2.VideoCapture(0)
        camera.set(3, 320)
        camera.set(4, 240)
        return camera

    def _image_to_rgb(self, image):
        b, g, r = cv2.split(image)
        image = cv2.merge((r, g, b))
        return image

    def _publish_image(self, image):
        payload_out = BytesIO()
        np.save(payload_out, image, allow_pickle=True)
        payload_out = zlib.compress(payload_out.getvalue())
        aiko.message.publish(self.share["topic_video"], payload_out)

    def _run(self):
        fps = 0
        while True:
            time_loop = time.time()
            status, image = self._camera.read()
            image = self._image_to_rgb(image)
            time_process = (time.time() - time_loop) * 1000

            status = f"{time_process:.01f} ms  {fps} FPS"
            cv2.putText(image, status, STATUS_XY, 0, 0.7, (255, 255, 255), 2)
            self._publish_image(image)

            self._sleep()
            fps = int(1 / (time.time() - time_loop))

    def _sleep(self, period=None):
        if not period:
            try:
                period = float(self.share["sleep_period"])
            except:
                period = SLEEP_PERIOD
        time.sleep(period)

# --------------------------------------------------------------------------- #

@click.group()

def main():
    pass

@main.command(help="Robot Control user interface")
@click.argument("robot_topic", default=None, required=False)

def ui(robot_topic):
    global ROBOT_NAME, TOPIC_VIDEO
    ROBOT_NAME = robot_topic.split("/")[1]
    TOPIC_VIDEO = f"{get_namespace()}/{ROBOT_NAME}/video"

    init_args = actor_args(ACTOR_TYPE_UI, protocol=PROTOCOL_UI)
    init_args["robot_topic"] = robot_topic
    robot_control = compose_instance(RobotControlImpl, init_args)
    aiko.process.run()

@main.command(name="video_test", help="Video test output")

def video_test():
    init_args = actor_args(ACTOR_TYPE_VIDEO_TEST, protocol=PROTOCOL_VIDEO_TEST)
    video_test = compose_instance(VideoTestImpl, init_args)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
