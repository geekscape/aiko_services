#!/usr/bin/env python3
#
# Aiko Services: OLED drawings
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Pencil-sketched cartoon scenes (house, tree, pine, cat, dog, bicycle,
# flower, forklift, a sun), outlined or shaded with hatching or stippling,
# drawn a little at a time as if by hand: a source of frames for the OLED
# Actor.  Nothing here uses a clock: the sketch is a generator that yields
# a frame each time a share of the drawing is done.  Ported from oled_test.py.
#
# Applet
# ~~~~~~~~~~~
#   draw [subject=NAME] [style=outline|hatch|stipple] [shade=on|off]
#        [speed=SECONDS_PER_DRAWING] [hold=SECONDS] [count=N] [seed=N]
#
# Not part of the Interface composition pattern (see ADR-022): plain
# presentation code owned by the Actor.

import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from aiko_services.examples.oled.applets import (
    APPLETS, Applet, AppletDone,
)
from aiko_services.examples.oled.graphics import HEIGHT, INK, WIDTH, blank, pixels

__all__ = [
    "DRAW_SECONDS", "GROUND", "STYLES", "SUBJECTS", "SUN", "DrawApplet",
    "erase_frames", "oval", "place", "scene_strokes", "sketch_frames",
]

def oval(cx, cy, rx, ry):
    n = max(12, round(math.pi * (rx + ry)))
    return [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n))
            for k in range(n)]

def spokes(cx, cy, r):
    return [("line", [(cx + r * math.cos(a), cy + r * math.sin(a)),
                      (cx - r * math.cos(a), cy - r * math.sin(a))])
            for a in (0.3, 0.3 + math.pi / 3, 0.3 + 2 * math.pi / 3)]

# Cartoon subjects: (box size, shapes in drawing order), coordinates in the
# box with y downwards.
#   poly, oval:  outlined, shaded, and hide whatever was drawn before them
#   line: open stroke;  ring: outline only;  dot, blob: small solid oval or polygon
SUBJECTS = {
    "house": (60, [
        ("poly", [(38, 24), (38, 10), (45, 10), (45, 24)]),
        ("ring", (42, 6, 3, 2)), ("ring", (47, 2, 2, 1.5)),
        ("poly", [(10, 30), (50, 30), (50, 58), (10, 58)]),
        ("poly", [(5, 31), (30, 11), (55, 31)]),
        ("poly", [(25, 58), (25, 42), (35, 42), (35, 58)]), ("dot", (33, 50, 1, 1)),
        ("poly", [(14, 36), (22, 36), (22, 44), (14, 44)]), ("line", [(18, 36), (18, 44)]),
        ("line", [(14, 40), (22, 40)]),
        ("poly", [(38, 36), (46, 36), (46, 44), (38, 44)]), ("line", [(42, 36), (42, 44)]),
        ("line", [(38, 40), (46, 40)]),
    ]),
    "tree": (60, [
        ("poly", [(26, 58), (28, 36), (33, 36), (35, 58)]),
        ("oval", (30, 24, 21, 17)),
        ("line", [(30, 40), (30, 30)]), ("line", [(30, 34), (23, 27)]), ("line", [(30, 31), (37, 24)]),
        ("dot", (19, 20, 1.5, 1.5)), ("dot", (39, 15, 1.5, 1.5)), ("dot", (42, 30, 1.5, 1.5)),
    ]),
    "pine": (60, [
        ("poly", [(27, 58), (27, 50), (33, 50), (33, 58)]),
        ("poly", [(10, 51), (30, 30), (50, 51)]),
        ("poly", [(14, 40), (30, 18), (46, 40)]),
        ("poly", [(18, 28), (30, 4), (42, 28)]),
    ]),
    "cat": (60, [
        ("line", [(42, 54), (50, 52), (54, 45), (53, 38), (56, 33)]),
        ("oval", (30, 45, 13, 13)),
        ("oval", (24, 57, 4, 2)), ("oval", (36, 57, 4, 2)),
        ("poly", [(21, 19), (21, 6), (28, 13)]), ("poly", [(32, 13), (39, 6), (39, 19)]),
        ("oval", (30, 22, 11, 10)),
        ("dot", (26, 21, 1.5, 2)), ("dot", (34, 21, 1.5, 2)),
        ("blob", [(29, 25), (31, 25), (30, 27)]), ("line", [(27, 29), (30, 27), (33, 29)]),
        ("line", [(25, 26), (14, 24)]), ("line", [(25, 27), (14, 30)]),
        ("line", [(35, 26), (46, 24)]), ("line", [(35, 27), (46, 30)]),
    ]),
    "dog": (60, [
        ("line", [(12, 36), (6, 30), (5, 23)]),
        ("line", [(16, 44), (15, 58)]), ("line", [(21, 45), (21, 58)]),
        ("line", [(33, 45), (33, 58)]), ("line", [(38, 44), (39, 58)]),
        ("oval", (26, 38, 16, 9)),
        ("oval", (45, 25, 9, 8)),
        ("oval", (53, 29, 6, 4)),
        ("poly", [(39, 19), (35, 32), (41, 33), (44, 20)]),
        ("dot", (47, 23, 1.3, 1.3)), ("dot", (58, 27, 1.8, 1.5)),
    ]),
    "bicycle": (60, [
        ("ring", (14, 46, 12, 12)), ("ring", (46, 46, 12, 12)),
        *spokes(14, 46, 11), *spokes(46, 46, 11),
        ("line", [(14, 46), (28, 46), (24, 30), (14, 46)]), ("line", [(24, 30), (41, 29), (28, 46)]),
        ("line", [(41, 29), (46, 46)]),
        ("line", [(24, 30), (24, 28)]), ("line", [(20, 28), (28, 28)]),
        ("line", [(41, 29), (39, 23), (45, 22)]),
        ("line", [(25, 50), (31, 42)]), ("line", [(23, 50), (27, 50)]), ("line", [(29, 42), (33, 42)]),
        ("dot", (14, 46, 1.5, 1.5)), ("dot", (46, 46, 1.5, 1.5)),
    ]),
    "forklift": (60, [
        ("poly", [(41, 56), (41, 6), (46, 6), (46, 56)]),
        ("line", [(15, 30), (15, 12)]), ("line", [(31, 30), (29, 12)]), ("line", [(12, 12), (34, 12)]),
        ("ring", (23, 18, 2.5, 2.5)), ("line", [(23, 21), (22, 28)]), ("line", [(23, 24), (28, 25)]),
        ("line", [(18, 30), (18, 23)]), ("line", [(31, 20), (27, 26)]),
        ("poly", [(6, 48), (6, 36), (10, 30), (36, 30), (39, 36), (39, 48)]),
        ("oval", (14, 51, 6, 6)), ("oval", (33, 51, 6, 6)),
        ("dot", (14, 51, 1.5, 1.5)), ("dot", (33, 51, 1.5, 1.5)),
        ("line", [(46, 39), (48, 39), (48, 52), (59, 52)]),
        ("poly", [(49, 51), (49, 38), (59, 38), (59, 51)]), ("line", [(49, 38), (59, 51)]),
        ("line", [(59, 38), (49, 51)]),
    ]),
    "flower": (60, [
        ("line", [(30, 58), (31, 48), (29, 38), (30, 28)]),
        ("poly", [(31, 48), (37, 42), (45, 40), (42, 46)]), ("poly", [(29, 42), (23, 36), (15, 35), (18, 40)]),
        *[("oval", (30 + 9 * math.cos(a), 18 + 9 * math.sin(a), 5.5, 5.5))
          for a in (k * math.pi / 3 + 0.5 for k in range(6))],
        ("oval", (30, 18, 5, 5)),
    ]),
}
SUN = (24, [("oval", (12, 12, 5, 5)),
            *[("line", [(12 + 7 * math.cos(a), 12 + 7 * math.sin(a)),
                        (12 + 10 * math.cos(a), 12 + 10 * math.sin(a))])
              for a in (k * math.pi / 4 for k in range(8))]])
STYLES = ("outline", "hatch", "stipple")
GROUND = HEIGHT - 2
DRAW_SECONDS = 8.0     # default time for one drawing
SHADING_WEIGHT = 0.3   # shading strokes are drawn this much faster than outlines
SOLID_LENGTH = 4       # a solid dot takes as long to draw as a line this long

# --------------------------------------------------------------------------- #

def place(subject, left, top, flip):
    """Screen shapes for a subject: (kind, points) in drawing order"""

    size, shapes = subject
    placed = []
    for kind, data in shapes:
        points = oval(*data) if kind in ("oval", "ring", "dot") else data
        points = [(left + (size - x if flip else x), top + y) for x, y in points]
        placed.append((kind, points if kind == "line" else points + [points[0]]))
    return placed

def filled(points):
    mask = blank()
    ImageDraw.Draw(mask).polygon(points, fill=INK, outline=INK)
    return mask

def thicken(mask, size):
    """Grow (size > 0) or shrink (size < 0) the lit area of a mask by a pixel"""

    image_filter = ImageFilter.MaxFilter(3) if size > 0 else ImageFilter.MinFilter(3)
    return mask.convert("L").filter(image_filter).convert("1", dither=Image.Dither.NONE)

def shading_strokes(region, style, rng):
    """Hatch lines or stipple rows covering the lit pixels of region, as
    [start, end] strokes"""

    lit = region.load()
    if style == "hatch":
        slope = rng.choice((1, -1))
        lines = [[(c + slope * y, y) for y in range(HEIGHT) if 0 <= c + slope * y < WIDTH]
                 for c in range(-HEIGHT, WIDTH + HEIGHT, 3)]
    else:
        lines = [[(x, y) for x in range(WIDTH)] for y in range(0, HEIGHT, 2)]
    strokes = []
    for cells in lines:
        run = []
        for cell in cells + [None]:
            if cell and lit[cell]:
                run.append(cell)
            elif run:
                strokes.append([run[0], run[-1]] if len(strokes) % 2 else [run[-1], run[0]])
                run = []
    return strokes

def scene_strokes(shapes, style, rng):
    """Strokes for a scene: every shape's outline, the ground, then shading
    for the closed shapes: (points, visible mask, solid, weight)"""

    masks = [filled(points) if kind in ("poly", "oval") else None for kind, points in shapes]
    details = []  # eyes, whiskers etc, widened a pixel: shading keeps clear of them
    for kind, points in shapes:
        detail = filled(points) if kind in ("dot", "blob") else blank()
        if kind in ("line", "ring"):
            ImageDraw.Draw(detail).line(points, fill=INK)
        details.append(thicken(detail, 1))
    visibles = []
    for i in range(len(shapes)):
        hidden = blank()
        for mask in masks[i + 1:]:
            if mask:
                hidden = ImageChops.logical_or(hidden, mask)
        visibles.append(ImageChops.invert(hidden))
    strokes = [(points, visible, kind in ("dot", "blob"), 1)
               for (kind, points), visible in zip(shapes, visibles)]
    strokes.append(([(0, GROUND), (WIDTH - 1, GROUND)], blank(INK), False, 1))
    if style != "outline":
        texture = blank(INK) if style == "hatch"  \
            else pixels(lambda x, y: x % 2 == 0 and y % 2 == 0)
        for i, (mask, visible) in enumerate(zip(masks, visibles)):
            if mask:
                region = ImageChops.logical_and(thicken(mask, -1), visible)
                for detail in details[i + 1:]:
                    region = ImageChops.logical_and(region, ImageChops.invert(detail))
                shading = ImageChops.logical_and(region, texture)
                strokes += [(points, shading, False, SHADING_WEIGHT)
                            for points in shading_strokes(region, style, rng)]
    return strokes

def _compose(paper, layer, visible):
    return ImageChops.logical_or(paper, ImageChops.logical_and(layer, visible))

def sketch_frames(strokes, frame_count):
    """Frames of the strokes being drawn a little at a time, about
    frame_count frames in all, the last one the finished drawing"""

    total = sum(weight * (SOLID_LENGTH if solid else sum(map(math.dist, points, points[1:])))
                for points, _, solid, weight in strokes)
    per_frame = max(total, 1) / max(1, frame_count)
    paper, budget = blank(), per_frame
    for points, visible, solid, weight in strokes:
        layer = blank()
        draw = ImageDraw.Draw(layer)
        if solid:
            draw.polygon(points, fill=INK, outline=INK)
            budget -= weight * SOLID_LENGTH
            while budget <= 0:
                yield _compose(paper, layer, visible)
                budget += per_frame
            points = []
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            length = math.dist((x0, y0), (x1, y1))
            steps = max(1, math.ceil(length / 2))
            for i in range(steps):
                a, b = i / steps, (i + 1) / steps
                draw.line((x0 + (x1 - x0) * a, y0 + (y1 - y0) * a,
                           x0 + (x1 - x0) * b, y0 + (y1 - y0) * b), fill=INK)
                budget -= weight * length / steps
                while budget <= 0:
                    yield _compose(paper, layer, visible)
                    budget += per_frame
        paper = _compose(paper, layer, visible)
    yield paper

def erase_frames(paper):
    """An eraser sweeping across the drawing"""

    for x in range(0, WIDTH + 8, 8):
        frame = paper.copy()
        ImageDraw.Draw(frame).rectangle((0, 0, x, HEIGHT), fill=0)
        yield frame

def scene(rng, subjects, style):
    """(names, shapes) for a random scene of one or two subjects, maybe a sun"""

    names = rng.sample(subjects, k=min(rng.choice((1, 2)), len(subjects)))
    if len(names) == 2:
        shapes = place(SUBJECTS[names[0]], 2, 3, rng.random() < 0.5)  \
            + place(SUBJECTS[names[1]], 66, 3, rng.random() < 0.5)
    else:
        left = rng.randint(4, WIDTH - 64)
        shapes = place(SUBJECTS[names[0]], left, 3, rng.random() < 0.5)
        gap_left, gap_right = left, WIDTH - left - 60
        if max(gap_left, gap_right) >= 28:
            sun_left = (gap_left - 24) // 2 if gap_left > gap_right  \
                else left + 60 + (gap_right - 24) // 2
            shapes += place(SUN, sun_left, 2, False)
    return names, shapes

def _on_off(text):
    if text in ("on", "true", "1", "yes"):
        return True
    if text in ("off", "false", "0", "no"):
        return False
    raise ValueError(text)

def _subject(text):
    if text not in SUBJECTS:
        raise ValueError(text)
    return text

def _style(text):
    if text not in STYLES:
        raise ValueError(text)
    return text

class DrawApplet(Applet):
    """Pencil-draw random cartoon scenes, "speed" seconds each, hold them
    "hold" seconds, erase, and draw the next; "count" drawings (0: for ever)"""

    name = "draw"
    fps = 20
    summary = "Pencil-sketched cartoon scenes, drawn a little at a time"
    OPTIONS = {"subject": _subject, "style": _style, "shade": _on_off, "speed": float,
               "hold": float, "count": int, "seed": int}

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.rng = host.rng if "seed" not in self.options  \
            else random.Random(self.options["seed"])
        self.subjects = [self.options["subject"]] if "subject" in self.options  \
            else sorted(SUBJECTS)
        self.seconds = max(0.5, self.options.get("speed", DRAW_SECONDS))
        self.hold = max(0.0, self.options.get("hold", 3.0))
        self.count = max(0, self.options.get("count", 0))
        self._frames = self._drawings()

    def _drawings(self):
        drawn = 0
        while not self.count or drawn < self.count:
            style = self.options.get("style") or (
                self.rng.choice(STYLES) if self.options.get("shade", True) else "outline")
            names, shapes = scene(self.rng, self.subjects, style)
            self.host.status("_".join(names) + "_" + style)
            paper = None
            for paper in sketch_frames(scene_strokes(shapes, style, self.rng),
                                       round(self.seconds * self.fps)):
                yield paper
            for _ in range(round(self.hold * self.fps)):
                yield None
            drawn += 1
            if not self.count or drawn < self.count:
                yield from erase_frames(paper)

    def step(self):
        try:
            return next(self._frames)
        except StopIteration:
            raise AppletDone

APPLETS[DrawApplet.name] = DrawApplet
