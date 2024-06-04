#!/usr/bin/env python3
#
# Usage
# ~~~~~
# ./xgo_robot.py
#
# To Do
# ~~~~~
# - Wrap as a PipelineElement for audio / video / LLM Pipeline
#   - Can operate independently of "robot_control.py"
#
# - Replace "REAL_ROBOTS" with a mapping of host names to implementations
#   - Command line option: robot_implementation_class
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# - Add "period" to "move(direction, stride)" and "turn(speed)"
#
# - Implement (lamda NAME (COMMAND ...) (COMMAND ...)) --> saved as "NAME"
#   - (remove NAME), (run NAME) --> run in background thread
#   - (sleep TIME), (do NAME FROM TO INCREMENT)
#   - Nod head for "yes" or "no"
#
# - Add cv2.set(10, 1) for brightness
# - Acquire CPU% and display on screen
# - Button A (bottom-right) --> "(ml yolo)"
# - Send video images over MQTT as an HL DataSource
# - Send Yolo ML Model inferences over MQTT as an HL DataSource
#
# - Provide logging, especially for syntax errors and run-time Exceptions
# - Determine if "xgolib" can be made asychronous (non-blocking) ?
#
# - Fix event.add_timer_handler(..., immediate=True)
#
# - New menu and button actions
# - LCD screen (message /in)
# - Play sound (message /in)
# - Speech synthesis (message /in)
#
# - Provide camera video stream for off-board viewing and ML processing
#   - QR Code reader --> actions
#   - Aruco tag reader --> actions or location / pose
# - Select ML Model for local video processing (message /in)
#
# - LIDAR: LD06
# - Oak-D Lite camera
# - ROS2 integration

from abc import abstractmethod
import cv2              # pip install opencv-python
from io import BytesIO
import numpy as np
from PIL import Image
import platform
from threading import Thread
import time
import zlib

IS_ROBOT = None
REAL_ROBOTS = ["laika", "oscar"]  # real robot hostnames

def is_robot():
    global IS_ROBOT
    if IS_ROBOT is None:
        hostname = platform.uname()[1]
        IS_ROBOT = hostname in REAL_ROBOTS
    return IS_ROBOT

if is_robot():
    import RPi  # pip install RPi.GPIO
    import spidev
    from key import Button
    import LCD_2inch
    from xgolib import XGO

# --------------------------------------------------------------------------- #

import aiko_services as aiko

_VERSION = 0

ACTOR_TYPE = "xgo_robot"
PROTOCOL = f"{ServiceProtocol.AIKO}/{ACTOR_TYPE}:{_VERSION}"

_LOGGER = aiko.logger(__name__)

if is_robot():
    MODULE_PATH = "aiko_services.examples.xgo_robot.xgo_robot"
else:
    MODULE_PATH = "__main__"

# --------------------------------------------------------------------------- #

ACTIONS = {
  "fall":         1, "stand":           2, "crawl":      3, "circle":       4,
  "step":         5, "squat":           6, "roll":       7, "pitch":        8,
  "yaw":          9, "roll_pitch_yaw": 10, "pee":       11, "sit":         12,
  "beckon":      13, "stretch":        14, "wave":      15, "wiggle_body": 16,
  "wiggle_tail": 17, "sniff":          18, "shake_paw": 19, "arm":         20
}

BATTERY_MONITOR_PERIOD = 10.0  # seconds
DETAIL_XY = (10, 20)
SLEEP_PERIOD = 0.2             # seconds
STATUS_XY = (10, 235)
TOPIC_VIDEO = f"{get_namespace()}/video"

# --------------------------------------------------------------------------- #

class XGORobot(Actor):
    Interface.default("XGORobot", f"{MODULE_PATH}.XGORobotImpl")

    @abstractmethod
    def action(self, value):
        pass

    @abstractmethod
    def arm(self, x, z):  # x: -80 to 155, z: -95 to 155
        pass

    @abstractmethod
    def arm_mode(self, stabilize):  # stabilize: true or false
        pass

    @abstractmethod                                    # pitch: -15 to 15
    def attitude(pitch="nil", roll="nil", yaw="nil"):  # roll:  -20 to 10
        pass                                           # yaw:   -11 to 11

    @abstractmethod
    def body_mode(self, stabilize):  # stabilize: true or false
        pass

    @abstractmethod
    def claw(self, grip):  # grip: 0 (open) to 255 (closed) --> 0% to 100%
        pass

    @abstractmethod                           # direction: "x" or "y"
    def move(self, direction, stride="nil"):  # stride x:  -25 mm to 25 mm
        pass                                  # stride y:  -18 mm to 18 mm

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def screen_detail(self, enabled=None):  # enabled: bool, default: toggle
        pass

    @abstractmethod
    def stop(self):  # stop moving or rotating
        pass

    @abstractmethod
    def terminate(self, immediate=False):
        pass

    @abstractmethod                              # x: -35 (back) to 35 (forward)
    def translation(x="nil", y="nil", z="nil"):  # y: -18 (left) to 18 (right)
        pass                                     # z:  75 (down) to 115 (up)

    @abstractmethod
    def turn(self, speed):  # speed: -100 (clockwise) to 100 degrees / second
        pass

# --------------------------------------------------------------------------- #

class RobotCore:
    def __init__(self, context):
        print(f"MQTT topic: {self.topic_path}")

        self.share["battery"] = -1
        self.share["screen_detail"] = False
        self.share["sleep_period"] = SLEEP_PERIOD
        self.share["source_file"] = f"v{_VERSION}⇒ {__file__}"
        self.share["topic_video"] = TOPIC_VIDEO
        self.share["version_firmware"] = "v0"

        self._direction = "x"
        self._pitch = 0
        self._roll = 0
        self._stride = 0
        self._terminated = False
        self._x = 0
        self._y = 0
        self._yaw = 0
        self._z = 0

        self._xgo = None
      # self._button = Button()                   # TODO: Mock later
        self._camera = self._camera_initialize()  # TODO: Optional
        self._screen = None
        self._thread = Thread(target=self._run).start()

    def _run(self):
        fps = 0
        while not self._terminated:
            time_loop = time.time()
            status, image = self._camera.read()
            image = cv2.flip(image, 1)
            image = self._image_to_rgb(image)
            time_process = (time.time() - time_loop) * 1000

            if self._screen:
                self._screen_overlay(image, fps, time_process)  # TODO: Always
                self._screen_show(image)
            self._publish_image(image)

    # GUI robot_control.py button(s) --[MQTT function call]--> xgo_robot.py
        if is_robot():                  # TODO: Mock later
            if self._button.press_c():  # Top-left button
                self.screen_detail()

            if self._button.press_b():  # Bottom-left button
                self.terminate()

        self._sleep()
        fps = int(1 / (time.time() - time_loop))

# --------------------------------------------------------------------------- #

class XGORobotImpl(XGORobot, RobotCore):
    def __init__(self, context):
        context.get_implementation("Actor").__init__(self, context)
        RobotCore.__init__(self, context)

        if is_robot():
            self._xgo = XGO(port="/dev/ttyAMA0", version="xgomini")
            self.share["version_firmware"] = self._xgo.read_firmware()
            self.share["version_xgolib"] = self._xgo.read_lib_version()

            self._button = Button()
            self._screen = self._screen_initialize()
            self._xgo.claw(0)  # Show signs of life !

            event.add_timer_handler(  # TODO: Use laptop battery status
                self._monitor_battery, BATTERY_MONITOR_PERIOD, immediate=True)

    # Review "xgolib": Blocks robot (all threads) until action is completed :(
    def action(self, action_type):
        if action_type in ACTIONS:
# MOCK      self._xgo.action(ACTIONS[action_type])
            payload_out = f"(action {action_type})"
            aiko.message.publish(self.topic_out, payload_out)

    def arm(self, x, z):
        try:
# MOCK      self._xgo.arm(int(x), int(z))
            payload_out = f"(arm {x} {z})"
            aiko.message.publish(self.topic_out, payload_out)
        except:
            pass

    def arm_mode(self, stabilize):
        stabilize = 1 if stabilize == "true" else 0
# MOCK  self._xgo.arm_mode(stabilize)
        payload_out = f"(arm_mode {stabilize})"
        aiko.message.publish(self.topic_out, payload_out)

    def attitude(self, pitch="nil", roll="nil", yaw="nil"):
        try:
            self._pitch = int(pitch)
        except:
            pass

        try:
            self._roll = int(roll)
        except:
            pass

        try:
            self._yaw = int(yaw)
        except:
            pass

# MOCK  self._xgo.attitude(["p","r","y"], [self._pitch, self._roll, self._yaw])
        payload_out = f"(attitude {self._pitch} {self._roll} {self._yaw})"
        aiko.message.publish(self.topic_out, payload_out)

    def body_mode(self, stabilize):
        stabilize = 1 if stabilize == "true" else 0
# MOCK  self._xgo.imu(stabilize)
        payload_out = f"(body_mode {stabilize})"
        aiko.message.publish(self.topic_out, payload_out)

    def _camera_initialize(self):
        camera = cv2.VideoCapture(0)
        camera.set(3, 320)
        camera.set(4, 240)
        return camera

    def claw(self, grip):  # grip: 0% - 100%
        try:
# MOCK      self._xgo.claw(int(grip))
            payload_out = f"(claw {grip})"
            aiko.message.publish(self.topic_out, payload_out)
        except:
            pass

    def _image_to_rgb(self, image):
        b, g, r = cv2.split(image)
        image = cv2.merge((r, g, b))
        return image

    def _monitor_battery(self):
        self.share["battery"] = self._xgo.read_battery()
        self.ec_producer.update("battery", self.share["battery"])
        payload_out = f"(battery {self.share['battery']})"
        aiko.message.publish(self.topic_out, payload_out)

    def move(self, direction, stride="nil"):
        self._direction = "y" if direction == "y" else "x"
        try:
            self._stride = int(stride)
        except:
            pass

# MOCK  self._xgo.move(self._direction, self._stride)
        payload_out = f"(move {self._direction} {self._stride})"
        aiko.message.publish(self.topic_out, payload_out)

    def _publish_image(self, image):
        payload_out = BytesIO()
        np.save(payload_out, image, allow_pickle=True)
        payload_out = zlib.compress(payload_out.getvalue())
        aiko.message.publish(self.share["topic_video"], payload_out)

    def reset(self):
# MOCK  self._xgo.reset()
        self._pitch = self._roll = self._yaw = 0
        self._x = self._y = self._z = 0
        self._direction = "x"
        self._stride = 0
        aiko.message.publish(self.topic_out, "(reset)")

    def screen_detail(self, enabled=None):
        if enabled == None:  # Toggle "screen_detail" enabled
            try:
                enabled = not bool(self.share["screen_detail"])
            except:
                enabled = False
        self.ec_producer.update("screen_detail", enabled)
        payload_out = f"(screen_detail {enabled})"
        aiko.message.publish(self.topic_out, payload_out)

    def _screen_initialize(self):
        screen = None
    #   screen = LCD_2inch.LCD_2inch()
    #   screen.clear()
    #   image = Image.new("RGB", (screen.height, screen.width), "black")
    #   screen.ShowImage(image)
        return screen

    def _screen_overlay(self, image, fps, time_process):
        status = f"{self.share['battery']}%  {time_process:.01f} ms  {fps} FPS"
        cv2.putText(image, status, STATUS_XY, 0, 0.7, (255, 255, 255), 2)

        if self.share["screen_detail"]:
            detail = f"{self.topic_path}"
            cv2.putText(image, detail, DETAIL_XY, 0, 0.7, (255, 255, 255), 2)

    def _screen_show(self, image):
        image = Image.fromarray(image)
# MOCK  self._screen.ShowImage(image)

    def _sleep(self, period=None):
        if not period:
            try:
                period = float(self.share["sleep_period"])
            except:
                period = SLEEP_PERIOD
        time.sleep(period)

    def stop(self):
# MOCK  self._xgo.stop()
        self._direction = "x"
        self._stride = 0
        payload_out = f"(stop)"
        aiko.message.publish(self.topic_out, payload_out)

    def terminate(self, immediate=False):
# MOCK  self._xgo.reset()
# MOCK  self._xgo.claw(128)
        aiko.process.terminate()
        self._terminated = True

    def translation(self, x="nil", y="nil", z="nil"):
        try:
            self._x = int(x)
        except:
            pass

        try:
            self._y = int(y)
        except:
            pass

        try:
            self._z = int(z)
        except:
            pass

# MOCK  self._xgo.translation(["x", "y", "z"], [self._x, self._y, self._z])
        payload_out = f"(attitude {self._x} {self._y} {self._z})"
        aiko.message.publish(self.topic_out, payload_out)

    def turn(self, speed):  # speed: -100 (clockwise) to 100 degrees / second
        try:
# MOCK      self._xgo.turn(int(speed))
            payload_out = f"(turn {speed})"
            aiko.message.publish(self.topic_out, payload_out)
        except:
            pass

# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    init_args = actor_args(ACTOR_TYPE, protocol=PROTOCOL)
    xgo_robot = compose_instance(XGORobotImpl, init_args)
    aiko.process.run()

# --------------------------------------------------------------------------- #
