# Notes
# ~~~~~
# mosquitto_pub --topic $TOPIC_PATH/in --message "(action sit)"
#
# ACTIONS = {
#   "fall":         1, "stand":           2, "crawl":      3, "circle":       4,
#   "step":         5, "squat":           6, "roll":       7, "pitch":        8,
#   "yaw":          9, "roll_pitch_yaw": 10, "pee":       11, "sit":         12,
#   "beckon":      13, "stretch":        14, "wave":      15, "wiggle_body": 16,
#   "wiggle_tail": 17, "sniff":          18, "shake_paw": 19, "arm":         20
# }
#
# To Do
# ~~~~~
# - Update "xgo_robot.py" to import this file and replace "class XGORobot"
#
# - Design a generic Robot interface and rename from "XGORobot" to "Robot"
#   - May be extended by the specific "XGORobot" and "XGORobotImpl" ?

from abc import abstractmethod
import platform

import aiko_services as aiko

IS_ROBOT = None
REAL_ROBOTS = ["laika", "oscar"]  # real robot hostnames

def is_robot():
    global IS_ROBOT
    if IS_ROBOT is None:
        hostname = platform.uname()[1]
        IS_ROBOT = hostname in REAL_ROBOTS
    return IS_ROBOT

if is_robot():
    MODULE_PATH = "aiko_services.examples.xgo_robot.xgo_robot"
else:
    MODULE_PATH = "__main__"

# --------------------------------------------------------------------------- #

class XGORobot(aiko.Actor):
    aiko.Interface.default("XGORobot", f"{MODULE_PATH}.XGORobotImpl")

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
