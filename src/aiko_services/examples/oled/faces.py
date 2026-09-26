#!/usr/bin/env python3
#
# Aiko Services: OLED faces
# ~~~~~~~~~~~~~~~~~~~~~~~~~
# Two applets with faces: an analog clock face, and a pair of animated eyes
# that show a range of emotions.  The eyes use no clock, only frame counts
# and a seeded random generator, so the same seed gives the same animation.
#
# Applets
# ~~~~~~~
#   clock [title=off] [seconds=on]  hour, minute and second hands, the day of
#                                   the month in a window, weekday and month
#   eyes [seed=N] [emotion=NAME] [blink=on]
#                                   eyes with iris, pupil, lids, brows and
#                                   smile lines; the emotion changes at random
#
# Not part of the Interface composition pattern (see ADR-022): plain
# presentation classes owned by the Actor.

from datetime import datetime
import math
import random

from PIL import Image, ImageChops, ImageDraw

from aiko_services.examples.oled.applets import APPLETS, Applet, on_off
from aiko_services.examples.oled.graphics import INK, stamp

__all__ = ["EMOTIONS", "ClockApplet", "EyesApplet"]

# --------------------------------------------------------------------------- #

class ClockApplet(Applet):
    """An analog clock face: hour, minute and second hands, the day of the
    month in a window at three o'clock, the weekday and the month beside
    the face.  Full screen unless "title=on" """

    name = "clock"
    fps = 1
    OPTIONS = {"title": on_off, "seconds": on_off}
    description = "clock"
    summary = "An analog clock face with a seconds hand and the day of the month"

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.wants_title = self.options.get("title", False)
        self.seconds = self.options.get("seconds", True)
        self._shown = None

    def step(self):
        now = datetime.now().replace(microsecond=0)
        shown = (now if self.seconds else now.replace(second=0), self.host.font,
                 self.host.title_rows())
        if shown == self._shown:
            return None
        self._shown = shown
        return self.face(now)

    def face(self, now):
        """The clock face for a datetime (pure: tests draw fixed times)"""

        frame = self.frame()
        draw = ImageDraw.Draw(frame)
        font = self.host.font
        top = self.host.title_rows() if self.wants_title else 0
        height = self.host.height - top
        cx, cy = self.host.width // 2, top + height // 2
        r = height // 2 - 1
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK)
        for hour in range(12):
            angle = math.radians(hour * 30)
            inner = r - (4 if hour % 3 == 0 else 2)
            draw.line((cx + inner * math.sin(angle), cy - inner * math.cos(angle),
                       cx + (r - 1) * math.sin(angle), cy - (r - 1) * math.cos(angle)),
                      fill=INK)
        day = font.render_line(f"{now.day:2d}")
        window_x, window_y = cx + round(r * 0.55), cy
        box = (window_x - day.width // 2 - 4, window_y - day.height // 2 - 3,
               window_x + day.width // 2 + 4, window_y + day.height // 2 + 3)
        draw.rectangle(box, fill=0, outline=INK)   # the date window, with room
        stamp(frame, day, box[0] + 5, box[1] + 4)

        def hand(degrees, length, width):
            angle = math.radians(degrees)
            draw.line((cx, cy, cx + length * math.sin(angle), cy - length * math.cos(angle)),
                      fill=INK, width=width)

        minutes = now.minute + now.second / 60
        hours = now.hour % 12 + minutes / 60
        hand(hours * 30, r * 0.5, 3)
        hand(minutes * 6, r * 0.78, 2)
        if self.seconds:
            hand(now.second * 6, r * 0.9, 1)
        draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=INK)
        weekday = font.render_line(now.strftime("%a"))
        month = font.render_line(now.strftime("%b"))
        left, right = (cx - r) // 2, cx + r + (self.host.width - cx - r) // 2
        stamp(frame, weekday, left - weekday.width // 2, cy - weekday.height // 2)
        stamp(frame, month, right - month.width // 2, cy - month.height // 2)
        return frame

# --------------------------------------------------------------------------- #

# Emotions: how open each eye is (left, right), how high each brow is, the
# angle of each brow (the inner end: + down, - up), the pupil size and the
# smile (smile lines at the outer corners, the lower lids raised)
EMOTIONS = {
    "neutral":    {"open": (1.0, 1.0), "brow_height": (0.0, 0.0), "brow_angle": (0.0, 0.0),
                   "pupil": 1.0, "smile": 0.0},
    "happy":      {"open": (0.75, 0.75), "brow_height": (0.4, 0.4), "brow_angle": (0.0, 0.0),
                   "pupil": 1.0, "smile": 1.0},
    "sad":        {"open": (0.7, 0.7), "brow_height": (0.2, 0.2), "brow_angle": (-1.0, -1.0),
                   "pupil": 1.0, "smile": 0.0},
    "angry":      {"open": (0.6, 0.6), "brow_height": (-0.6, -0.6), "brow_angle": (1.0, 1.0),
                   "pupil": 0.9, "smile": 0.0},
    "surprised":  {"open": (1.0, 1.0), "brow_height": (1.0, 1.0), "brow_angle": (0.0, 0.0),
                   "pupil": 0.6, "smile": 0.0},
    "sleepy":     {"open": (0.35, 0.35), "brow_height": (-0.2, -0.2), "brow_angle": (0.0, 0.0),
                   "pupil": 1.1, "smile": 0.0},
    "suspicious": {"open": (0.55, 1.0), "brow_height": (-0.3, 0.2), "brow_angle": (0.6, 0.0),
                   "pupil": 0.9, "smile": 0.0},
    "curious":    {"open": (1.0, 1.0), "brow_height": (0.9, 0.0), "brow_angle": (-0.4, 0.0),
                   "pupil": 0.8, "smile": 0.3},
    "loving":     {"open": (0.65, 0.65), "brow_height": (0.5, 0.5), "brow_angle": (-0.5, -0.5),
                   "pupil": 1.3, "smile": 0.8},
}
BLINK = (0.6, 0.2, 0.0, 0.0, 0.2, 0.6)  # how open the eyes are through a blink

def _emotion(text):
    if text not in EMOTIONS:
        raise ValueError(text)
    return text

class EyesApplet(Applet):
    """A pair of eyes: iris, pupil with a highlight, upper and lower lids,
    brows and smile lines.  The eyes look around, blink, and show a random
    range of emotions (neutral, happy, sad, angry, surprised, sleepy,
    suspicious, curious, loving), easing from one to the next; "emotion="
    holds one.  Only frame counts, so a seed repeats the animation"""

    name = "eyes"
    fps = 30
    OPTIONS = {"seed": int, "emotion": _emotion, "blink": on_off}
    summary = "Animated eyes showing a random range of emotions"
    EYE_RX, EYE_RY, IRIS, PUPIL = 20, 13, 8, 4
    CENTRES = (36, 92)  # x of the left and right eye; the nose is between

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.rng = host.rng if "seed" not in self.options  \
            else random.Random(self.options["seed"])
        self.blinking = self.options.get("blink", True)
        self.emotion = self.options.get("emotion", "neutral")
        self.description = self.emotion
        self.fixed = "emotion" in self.options
        self.current = {key: (list(value) if isinstance(value, tuple) else value)
                        for key, value in EMOTIONS["neutral"].items()}
        self.target = EMOTIONS[self.emotion]
        self.gaze, self.gaze_target = [0.0, 0.0], [0.0, 0.0]
        self.frame_no = 0
        self.next_emotion = self.rng.randint(2 * self.fps, 4 * self.fps)
        self.next_gaze = self.rng.randint(self.fps // 2, 2 * self.fps)
        self.next_blink = self.rng.randint(1 * self.fps, 4 * self.fps)
        self.blink_phase = None
        host.status(self.emotion)

    def _choose_emotion(self):
        names = [name for name in EMOTIONS if name != self.emotion]
        self.emotion = self.rng.choice(names)
        self.target = EMOTIONS[self.emotion]
        self.description = self.emotion
        self.host.status(self.emotion)

    def step(self):
        self.frame_no += 1
        if not self.fixed and self.frame_no >= self.next_emotion:
            self._choose_emotion()
            self.next_emotion = self.frame_no + self.rng.randint(2 * self.fps, 5 * self.fps)
        if self.frame_no >= self.next_gaze:
            self.gaze_target = [self.rng.uniform(-1, 1), self.rng.uniform(-0.6, 0.6)]
            self.next_gaze = self.frame_no + self.rng.randint(self.fps // 2, 3 * self.fps)
        if self.blinking and self.blink_phase is None and self.frame_no >= self.next_blink:
            self.blink_phase = 0
        elif self.blink_phase is not None:
            self.blink_phase += 1
            if self.blink_phase >= len(BLINK):
                self.blink_phase = None
                self.next_blink = self.frame_no + self.rng.randint(2 * self.fps, 6 * self.fps)
        for key, target in self.target.items():
            if isinstance(target, tuple):
                for side in (0, 1):
                    self.current[key][side] += (target[side] - self.current[key][side]) * 0.25
            else:
                self.current[key] += (target - self.current[key]) * 0.25
        for axis in (0, 1):
            self.gaze[axis] += (self.gaze_target[axis] - self.gaze[axis]) * 0.3
        return self.draw()

    def draw(self):
        frame = self.frame()
        draw = ImageDraw.Draw(frame)
        cy = self.host.height // 2 + 3
        for side, cx in enumerate(self.CENTRES):
            openness = self.current["open"][side]
            if self.blink_phase is not None:
                openness *= BLINK[self.blink_phase]
            self._eye(frame, draw, cx, cy, side, openness)
        return frame

    def _eye_shape(self, cx, cy, nose, open_top, open_bottom, tilt):
        """The lens shape of an eye: an upper and a lower arc between the two
        corners, each arc's height scaled by how open that lid is, the whole
        tilted (+: the inner corner down)"""

        RX, RY = self.EYE_RX, self.EYE_RY
        points = []
        for k in range(32):
            theta = 2 * math.pi * k / 32
            x = cx + RX * math.cos(theta)
            ry = RY * (open_top if math.sin(theta) < 0 else open_bottom)
            y = cy + ry * math.sin(theta) + tilt * nose * (x - cx) / RX
            points.append((x, y))
        return points

    def _eye(self, frame, draw, cx, cy, side, openness):
        RX, RY = self.EYE_RX, self.EYE_RY
        nose = 1 if side == 0 else -1              # towards the other eye
        smile = self.current["smile"]
        tilt = self.current["brow_angle"][side] * 2.5
        open_top = max(0.0, min(1.0, openness))
        open_bottom = (1 - 0.45 * smile) * (0.3 + 0.7 * open_top)
        shape = self._eye_shape(cx, cy, nose, open_top, open_bottom, tilt)
        # The iris, pupil and highlight, clipped to the eye
        region = Image.new("1", frame.size)
        ImageDraw.Draw(region).polygon(shape, fill=INK)
        content = Image.new("1", frame.size)
        inside = ImageDraw.Draw(content)
        iris = self.IRIS
        ix = cx + self.gaze[0] * (RX - iris - 2)
        iy = cy + self.gaze[1] * (RY - iris + 3)
        inside.ellipse((ix - iris, iy - iris, ix + iris, iy + iris), fill=INK)
        pupil = self.PUPIL * self.current["pupil"]
        inside.ellipse((ix - pupil, iy - pupil, ix + pupil, iy + pupil), fill=0)
        inside.point((round(ix - pupil / 2), round(iy - pupil / 2)), fill=INK)
        frame.paste(INK, (0, 0), ImageChops.logical_and(content, region))
        draw.polygon(shape, outline=INK)
        # The brow: a thick line whose inner end follows the angle
        height = self.current["brow_height"][side]
        angle = self.current["brow_angle"][side]
        brow_y = cy - RY - 5 - height * 5
        draw.line((cx - nose * (RX - 2), brow_y - angle * 3,
                   cx + nose * (RX - 4), brow_y + angle * 3), fill=INK, width=2)
        # Smile lines at the outer corner
        if smile > 0.3:
            x = cx - nose * (RX + 3)
            draw.line((x, cy + RY - 6, x - nose * 3, cy + RY - 1), fill=INK)
            draw.line((x - nose * 3, cy + RY - 1, x - nose * 2, cy + RY + 3), fill=INK)

for applet in (ClockApplet, EyesApplet):
    APPLETS[applet.name] = applet
