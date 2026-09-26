#!/usr/bin/env python3
#
# Aiko Services: OLED games
# ~~~~~~~~~~~~~~~~~~~~~~~~~
# Self-playing demonstrations of the classics (pong, asteroids, space
# invaders), a forklift that moves a pallet in and out of a racking bay by
# itself, and the forklift game (arrow keys through "(key ...)").  All are
# applets: sources of frames stepped by the OLED Actor; none uses a
# clock, so the same seed gives the same frames.  Ported from oled_test.py.
#
# Applets
# ~~~~~~~~~~~~
#   pong | asteroids | invaders [seed=N]      one game, for ever
#   games [duration=20] [seed=N]              the three in turn
#   forklift [duration=0] [seed=N]            the forklift at work; 0: for ever
#   forklift_game [seed=N]                    keys: left right up down
#
# Not part of the Interface composition pattern (see ADR-022): plain
# presentation classes owned by the Actor.

import math

from PIL import Image, ImageDraw

from aiko_services.examples.oled.applets import (
    APPLETS, Applet, AppletDone,
)
from aiko_services.examples.oled.drawings import GROUND, SUBJECTS, oval
from aiko_services.examples.oled.graphics import (
    HEIGHT, INK, WIDTH, blank, sprite, stamp,
)

__all__ = [
    "GAMES", "AsteroidsApplet", "ForkliftApplet", "ForkliftGame",
    "ForkliftGameApplet", "GamesApplet", "InvadersApplet",
    "PongApplet", "asteroids", "forklift_work", "invaders", "pong",
]

# --------------------------------------------------------------------------- #

def pong(rng, host):
    """Two computer players, each of which misjudges the ball now and then"""

    paddle_height, xs = 12, (2, WIDTH - 4)
    faces = (xs[0] + 2, xs[1] - 2)  # ball x (its left edge) at each paddle
    paddles, aims, scores = [26.0, 26.0], [0.0, 0.0], [0, 0]

    def serve(direction):
        return [WIDTH / 2, rng.uniform(16, 48)], [direction * 4.8, rng.uniform(-3, 3)]

    ball, velocity = serve(rng.choice((-1, 1)))
    while True:
        for side in (0, 1):
            coming = (velocity[0] < 0) == (side == 0)
            # Where the ball will reach this paddle, allowing for bounces
            bounce = (ball[1] + velocity[1] * (faces[side] - ball[0]) / velocity[0])  \
                % (2 * (HEIGHT - 2))
            arrival = min(bounce, 2 * (HEIGHT - 2) - bounce)
            target = arrival + 1 + aims[side] - paddle_height / 2 if coming  \
                else (HEIGHT - paddle_height) / 2
            paddles[side] += max(-3.6, min(3.6, target - paddles[side]))
            paddles[side] = max(0.0, min(HEIGHT - paddle_height, paddles[side]))
        previous_x = ball[0]
        ball[0] += velocity[0]
        ball[1] += velocity[1]
        if not 0 <= ball[1] <= HEIGHT - 2:
            velocity[1] = -velocity[1]
            ball[1] = max(0.0, min(HEIGHT - 2, ball[1]))
        for side, face in enumerate(faces):
            crossed = (previous_x - face) * (ball[0] - face) <= 0
            if (velocity[0] < 0) == (side == 0) and crossed  \
                    and paddles[side] - 2 <= ball[1] <= paddles[side] + paddle_height:
                ball[0] = face
                velocity[0] = -max(-9.0, min(9.0, velocity[0] * 1.05))
                velocity[1] = max(-6.0, min(6.0, velocity[1]
                    + 3 * (ball[1] + 1 - paddles[side] - paddle_height / 2) / 4))
                aims[1 - side] = rng.uniform(-8, 8)
        if not -2 <= ball[0] <= WIDTH:
            scores[ball[0] < 0] += 1
            ball, velocity = serve(1 if ball[0] < 0 else -1)
        image = blank()
        draw = ImageDraw.Draw(image)
        for y in range(0, HEIGHT, 4):
            draw.line((WIDTH // 2 - 1, y, WIDTH // 2 - 1, y + 1), fill=INK)
        for side, x in enumerate(xs):
            draw.rectangle((x, round(paddles[side]), x + 1,
                round(paddles[side]) + paddle_height - 1), fill=INK)
            label = host.font.render_line(str(scores[side]))
            stamp(image, label,
                WIDTH // 2 - 8 - label.width if side == 0 else WIDTH // 2 + 6, 1)
        draw.rectangle((round(ball[0]), round(ball[1]),
            round(ball[0]) + 1, round(ball[1]) + 1), fill=INK)
        yield image

def asteroids(rng, host):
    """A ship turns, aims and fires at the nearest rock; big rocks split"""

    cx, cy = WIDTH / 2, HEIGHT / 2
    points_for = {9: 20, 5: 50, 3: 100}
    angle, cooldown, respawn, score, lives = 0.0, 0, 0, 0, 3
    bullets, sparks = [], []

    def rock(x, y, size):
        heading, speed = rng.uniform(0, 2 * math.pi), rng.uniform(0.25, 0.8)
        return {"x": x, "y": y, "vx": speed * math.cos(heading),
                "vy": speed * math.sin(heading), "r": size, "turn": 0.0,
                "spin": rng.uniform(-0.05, 0.05),
                "shape": [rng.uniform(0.7, 1.15) for _ in range(9)]}

    def explode(x, y, count):
        for _ in range(count):
            heading, speed = rng.uniform(0, 2 * math.pi), rng.uniform(0.3, 1.5)
            sparks.append([x, y, speed * math.cos(heading),
                speed * math.sin(heading), rng.randint(8, 20)])

    rocks = []
    while True:
        if not rocks:
            rocks = [rock(rng.choice((0, WIDTH - 1)), rng.uniform(0, HEIGHT), 9)
                     for _ in range(4)]
        for r in rocks:
            r["x"] = (r["x"] + r["vx"]) % WIDTH
            r["y"] = (r["y"] + r["vy"]) % HEIGHT
            r["turn"] += r["spin"]
        if respawn:
            respawn -= 1
        else:
            target = min(rocks, key=lambda r: math.dist((cx, cy), (r["x"], r["y"])))
            lead = math.dist((cx, cy), (target["x"], target["y"])) / 3
            aim = math.atan2(target["y"] + target["vy"] * lead - cy,
                             target["x"] + target["vx"] * lead - cx)
            turn = (aim - angle + math.pi) % (2 * math.pi) - math.pi
            angle += max(-0.12, min(0.12, turn))
            cooldown = max(0, cooldown - 1)
            if abs(turn) < 0.1 and not cooldown:
                bullets.append([cx + 6 * math.cos(angle), cy + 6 * math.sin(angle),
                    3 * math.cos(angle), 3 * math.sin(angle), 30])
                cooldown = 7
        for bullet in bullets:
            bullet[0] = (bullet[0] + bullet[2]) % WIDTH
            bullet[1] = (bullet[1] + bullet[3]) % HEIGHT
            bullet[4] -= 1
        for bullet in list(bullets):
            hit = next((r for r in rocks
                if math.dist(bullet[:2], (r["x"], r["y"])) < r["r"] + 1), None)
            if hit:
                bullets.remove(bullet)
                rocks.remove(hit)
                score += points_for[hit["r"]]
                explode(hit["x"], hit["y"], hit["r"])
                if hit["r"] > 3:
                    rocks += [rock(hit["x"], hit["y"], 5 if hit["r"] == 9 else 3)
                              for _ in range(2)]
        bullets = [bullet for bullet in bullets if bullet[4] > 0]
        crash = None if respawn else next((r for r in rocks
            if math.dist((cx, cy), (r["x"], r["y"])) < r["r"] + 3), None)
        if crash:
            rocks.remove(crash)
            explode(cx, cy, 20)
            respawn, lives = 50, lives - 1
            if not lives:
                score, lives = 0, 3
        for spark in sparks:
            spark[0] += spark[2]
            spark[1] += spark[3]
            spark[4] -= 1
        sparks = [spark for spark in sparks if spark[4] > 0]
        image = blank()
        draw = ImageDraw.Draw(image)
        for r in rocks:
            draw.polygon([(r["x"] + r["r"] * m * math.cos(r["turn"] + 2 * math.pi * k / 9),
                           r["y"] + r["r"] * m * math.sin(r["turn"] + 2 * math.pi * k / 9))
                          for k, m in enumerate(r["shape"])], outline=INK)
        if not respawn:
            draw.polygon([(cx + 5 * math.cos(angle + a), cy + 5 * math.sin(angle + a))
                          if a == 0 else
                          (cx + 4 * math.cos(angle + a), cy + 4 * math.sin(angle + a))
                          for a in (0, 2.5, math.pi, -2.5)], outline=INK)
        for x, y, *_ in bullets + sparks:
            draw.point((x, y), fill=INK)
        stamp(image, host.font.render_line(str(score)), 1, 1)
        for i in range(lives):
            x = WIDTH - 5 - 6 * i
            draw.polygon([(x, 1), (x - 2, 6), (x + 2, 6)], outline=INK)
        yield image

INVADERS = [  # (points, two animation frames), top row first
    (30, [sprite(["...##...", "..####..", ".##..##.", "########", "..#..#..", ".#.##.#."]),
          sprite(["...##...", "..####..", ".##..##.", "########", ".#.##.#.", "#......#"])]),
    (20, [sprite(["..#..#..", "#.####.#", "##.##.##", "########", ".#....#.", "#......#"]),
          sprite(["..#..#..", "..####..", ".#.##.#.", "########", "#.#..#.#", ".#....#."])]),
    (10, [sprite(["..####..", ".######.", "##.##.##", "########", ".##..##.", "##....##"]),
          sprite(["..####..", ".######.", "##.##.##", "########", "..#..#..", ".#.##.#."])]),
]
CANNON = sprite(["...#...", "..###..", "#######", "#######"])
SAUCER = sprite(["..####..", ".######.", "#.#.#.#.", ".##..##."])
BLAST = sprite(["#..#..#.", ".#.#.#..", "#......#", "..#.#.#.", ".#..#..#"])
BUNKER = sprite(["..########..", ".##########.", "############", "############",
                 "####....####", "###......###"])

def invaders(rng, host):
    """Marching invaders, a cannon that picks them off, bombs, crumbling
    bunkers and a passing saucer"""

    cannon_y, bunker_y = HEIGHT - 6, HEIGHT - 17
    score = 0
    while True:
        alive = {(row, column) for row in range(3) for column in range(8)}
        score_height = host.font.line_height + 2
        grid_x, grid_y, direction, tick, pose = 10.0, score_height + 6.0, 1, 0, 0
        bunkers = blank()
        for x in (18, 58, 98):
            stamp(bunkers, BUNKER, x, bunker_y)
        cannon_x, cannon_hit, target, shot, saucer = 60.0, 0, None, None, None
        bombs, blasts = [], []

        def position(row, column):
            return grid_x + 12 * column, grid_y + 9 * row

        while alive and max(position(*invader)[1] for invader in alive) + 6 < bunker_y:
            tick += 1
            if tick >= 2 + len(alive) // 3:  # the fewer left, the faster they march
                tick, pose = 0, 1 - pose
                xs = [position(*invader)[0] for invader in alive]
                if min(xs) + 2 * direction < 1 or max(xs) + 8 + 2 * direction > WIDTH - 1:
                    grid_y, direction = grid_y + 2, -direction
                else:
                    grid_x += 2 * direction
            if cannon_hit:
                cannon_hit -= 1
            else:
                if target not in alive:
                    column = rng.choice(sorted({column for _, column in alive}))
                    target = max(invader for invader in alive if invader[1] == column)
                aim = position(*target)[0] + 4 - 3
                cannon_x += max(-1.5, min(1.5, aim - cannon_x))
                if shot is None and abs(aim - cannon_x) < 2:
                    shot = [cannon_x + 3, cannon_y - 3]
            if shot:
                for _ in range(3):
                    shot[1] -= 1
                    x, y = round(shot[0]), round(shot[1])
                    hit = next((invader for invader in alive
                        if 0 <= x - position(*invader)[0] < 8
                        and 0 <= y - position(*invader)[1] < 6), None)
                    if y < score_height:
                        shot = None
                    elif hit:
                        alive.remove(hit)
                        score += INVADERS[hit[0]][0]
                        blasts.append([*position(*hit), 8])
                        shot = None
                    elif saucer and 0 <= x - saucer[0] < 8 and 0 <= y - score_height < 4:
                        score += 100
                        blasts.append([saucer[0], score_height, 12])
                        saucer, shot = None, None
                    elif bunkers.getpixel((x, y)):
                        ImageDraw.Draw(bunkers).rectangle((x - 1, y - 2, x + 1, y), fill=0)
                        shot = None
                    if shot is None:
                        break
            if alive and rng.random() < 0.04:
                column = rng.choice(sorted({column for _, column in alive}))
                x, y = position(*max(invader for invader in alive if invader[1] == column))
                bombs.append([x + 4, y + 6])
            for bomb in list(bombs):
                bomb[1] += 1.2
                x, y = round(bomb[0]), round(bomb[1])
                if y >= HEIGHT - 1:
                    bombs.remove(bomb)
                elif bunkers.getpixel((x, y)):
                    ImageDraw.Draw(bunkers).rectangle((x - 1, y, x + 1, y + 2), fill=0)
                    bombs.remove(bomb)
                elif not cannon_hit and 0 <= x - cannon_x < 7 and y >= cannon_y:
                    blasts.append([cannon_x, cannon_y - 1, 12])
                    bombs.remove(bomb)
                    cannon_hit = 40
            if saucer is None and rng.random() < 0.004:
                saucer = [-8.0, 0.8] if rng.random() < 0.5 else [float(WIDTH), -0.8]
            if saucer:
                saucer[0] += saucer[1]
                if not -8 <= saucer[0] <= WIDTH:
                    saucer = None
            for blast in blasts:
                blast[2] -= 1
            blasts = [blast for blast in blasts if blast[2] > 0]
            image = bunkers.copy()
            draw = ImageDraw.Draw(image)
            for row, column in alive:
                stamp(image, INVADERS[row][1][pose], *position(row, column))
            if not cannon_hit or cannon_hit % 8 < 4:
                stamp(image, CANNON, cannon_x, cannon_y)
            if shot:
                draw.line((shot[0], shot[1], shot[0], shot[1] + 2), fill=INK)
            for x, y in bombs:
                draw.line([(x, y), (x + 1, y + 1), (x, y + 2)], fill=INK)
            if saucer:
                stamp(image, SAUCER, saucer[0], score_height)
            for x, y, _ in blasts:
                stamp(image, BLAST, x, y)
            draw.line((0, HEIGHT - 1, WIDTH - 1, HEIGHT - 1), fill=INK)
            stamp(image, host.font.render_line(f"SCORE {score}"), 0, 0)
            yield image

GAMES = {"pong": pong, "asteroids": asteroids, "invaders": invaders}

# --------------------------------------------------------------------------- #
# The forklift: the one from the drawings (at 80%), a pallet and a racking bay
# with 3 levels: 0 its floor, 1 and 2 (the top) on beams.  Screen rows: the
# ground line is GROUND; things standing on the ground have their bottom on
# the row above it.  Pallets are (left column, bottom row)

LIFT_SCALE = 0.8

def shape_points(kind, data):
    return oval(*data) if kind in ("oval", "ring", "dot") else data

LIFT_BODY = [(kind, data) for kind, data in SUBJECTS["forklift"][1]  # no mast, forks, crate
             if max(x for x, _ in shape_points(kind, data)) <= 46
             and min(x for x, _ in shape_points(kind, data)) != 41]
LIFT_MAST = (41 * LIFT_SCALE, 46 * LIFT_SCALE)  # the mast's columns, from the left
LIFT_MAST_TOP = round(GROUND - 1 - (57 - 6) * LIFT_SCALE) + 4  # 4 rows shorter: inner mast shows
LIFT_CARRIAGE = 48 * LIFT_SCALE  # the carriage (the forks' upright), from the left
FORK_LENGTH, CARRIAGE_HEIGHT, INNER_MAST_ABOVE = 9, 10, 5
PALLET_WIDTH, PALLET_HEIGHT = 13, 13
RACK_X, RACK_WIDTH, RACK_TOP = 107, 18, 8  # front upright, width, top bar's row
LEVELS = {0: GROUND - 1, 1: 43, 2: 25}  # level: the row a pallet there has its bottom on
BEAMS = {1: 44, 2: 26}  # the top rows of the beams (2 rows deep) of levels 1 and 2
FORKS_DOWN, FORKS_TOP = GROUND - 1, 18  # the forks' lowest and highest rows
FORKS_CARRY = FORKS_DOWN - 4  # forks when driving with a pallet
PALLET_SLOTS = 1  # a pallet rests on the forks with its bottom this many rows below
GROUND_SPOTS = (32, RACK_X - PALLET_WIDTH - 4)  # where a pallet can stand on the ground
LIFT_X_MAX = RACK_X - 1 - LIFT_MAST[1]  # the forklift's furthest x: mast short of the rack

def pallet_lines(left, bottom):
    """The lines a pallet and its crate are made of (the pieces it breaks into)"""

    right, top = left + PALLET_WIDTH - 1, bottom - PALLET_HEIGHT + 1
    return [((left + 1, top), (right - 1, top)), ((left + 1, bottom - 3), (right - 1, bottom - 3)),
            ((left + 1, top), (left + 1, bottom - 3)), ((right - 1, top), (right - 1, bottom - 3)),
            ((left + 1, top), (right - 1, bottom - 3)), ((right - 1, top), (left + 1, bottom - 3)),
            ((left, bottom - 2), (right, bottom - 2)), ((left, bottom), (right, bottom))]

def draw_pallet(draw, left, bottom):
    """A pallet with a crate on it, like the one in the forklift drawing"""

    right, top = left + PALLET_WIDTH - 1, bottom - PALLET_HEIGHT + 1
    for (x0, y0), (x1, y1) in pallet_lines(left, bottom):
        if y0 == y1 == bottom - 1:  # the blocks, with the fork slots between them
            draw.rectangle((x0, y0, x1, y1), fill=INK)
    draw.rectangle((left + 1, top, right - 1, bottom - 3), fill=0, outline=INK)
    draw.rectangle((left, bottom - 2, right, bottom), fill=0)
    for (x0, y0), (x1, y1) in pallet_lines(left, bottom):
        if not y0 == y1 == bottom - 1:
            draw.line((x0, y0, x1, y1), fill=INK)
    for x in (left, (left + right) // 2 - 1, right - 1):
        draw.rectangle((x, bottom - 1, x + 1, bottom - 1), fill=INK)

def draw_forklift(draw, x, forks):
    """The forklift with its left at column x and its forks at row forks"""

    def screen(points):
        return [(x + px * LIFT_SCALE, GROUND - 1 - (57 - py) * LIFT_SCALE) for px, py in points]

    draw.rectangle((x + LIFT_MAST[0], LIFT_MAST_TOP, x + LIFT_MAST[1], GROUND - 1),
        fill=0, outline=INK)
    for kind, data in LIFT_BODY:
        points = screen(shape_points(kind, data))
        if kind == "line":
            draw.line(points, fill=INK)
        else:  # outlines filled black, so later parts hide earlier ones
            draw.polygon(points, fill=INK if kind in ("dot", "blob") else 0, outline=INK)
    carriage, top = x + LIFT_CARRIAGE, forks - CARRIAGE_HEIGHT
    if top - INNER_MAST_ABOVE < LIFT_MAST_TOP:  # the inner mast slides up
        draw.rectangle((x + 42 * LIFT_SCALE, top - INNER_MAST_ABOVE,
            x + 45 * LIFT_SCALE, LIFT_MAST_TOP), fill=0, outline=INK)
    draw.line((carriage, top, carriage, forks), fill=INK)
    draw.line((carriage, forks, carriage + FORK_LENGTH, forks), fill=INK)

def draw_warehouse(x, forks, pallet, pieces=()):
    """The ground, racking bay, forklift and pallet (if any), and the pieces
    of a broken pallet"""

    image = blank()
    draw = ImageDraw.Draw(image)
    draw.line((0, GROUND, WIDTH - 1, GROUND), fill=INK)
    for post in (RACK_X, RACK_X + RACK_WIDTH):
        draw.line((post, RACK_TOP, post, GROUND - 1), fill=INK)
    for row in (RACK_TOP, *BEAMS.values()):
        draw.rectangle((RACK_X, row, RACK_X + RACK_WIDTH, row + 1), outline=INK)
    draw_forklift(draw, x, round(forks))
    if pallet:
        draw_pallet(draw, round(pallet[0]), round(pallet[1]))
    for x0, y0, x1, y1, *_ in pieces:
        draw.line((x0, y0, x1, y1), fill=INK)
    return image

def forklift_work(rng, host):
    """Frames of the forklift moving the pallet between the ground and random
    rack levels by itself, for ever"""

    drive, lift = 1.4, 1.0  # pixels per frame
    at_rack = RACK_X + 1 - LIFT_CARRIAGE  # x with its pallet in the rack
    before_rack = RACK_X - PALLET_WIDTH - 2 - LIFT_CARRIAGE  # x with the pallet clear
    mirrored = rng.random() < 0.5  # the rack on the left instead
    state = {"x": 0.0, "forks": float(FORKS_CARRY), "carried": False,
             "pallet": None, "level": None, "moves": 0}
    if rng.random() < 0.5:
        state["level"] = rng.choice(list(LEVELS))
        state["pallet"] = [RACK_X + 2, LEVELS[state["level"]]]
        state["x"] = rng.uniform(-4, before_rack - 10)
    else:
        left = rng.randint(*GROUND_SPOTS)
        state["pallet"] = [left, GROUND - 1]
        state["x"] = rng.uniform(-4, left - 14 - LIFT_CARRIAGE)

    def frame():
        if state["carried"]:
            state["pallet"] = [round(state["x"] + LIFT_CARRIAGE) + 1,
                               round(state["forks"]) + PALLET_SLOTS]
        image = draw_warehouse(state["x"], state["forks"], state["pallet"])
        if mirrored:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)
        label = host.font.render_line(f"Moves {state['moves']}")
        stamp(image, label, WIDTH - label.width - 1 if mirrored else 1, 0)
        return image

    def go(key, target, speed):
        while state[key] != target:
            step = target - state[key]
            state[key] = target if abs(step) <= speed  \
                else state[key] + math.copysign(speed, step)
            yield frame()

    def pause(frames):
        for _ in range(frames):
            yield frame()

    while True:
        if state["level"] is None:  # on the ground: take it to a random level
            level = rng.choice(list(LEVELS))
            host.status(f"ground_to_bay_{level}")
            left = state["pallet"][0]
            yield from go("forks", FORKS_DOWN, lift)
            yield from go("x", left - 1 - LIFT_CARRIAGE, drive)
            yield from go("forks", GROUND - 1 - PALLET_SLOTS, lift)
            state["carried"] = True
            yield from go("forks", FORKS_CARRY, lift)
            yield from go("x", before_rack, drive)
            resting = LEVELS[level] - PALLET_SLOTS  # forks with the pallet on its level
            yield from go("forks", min(resting - 3, FORKS_CARRY), lift)
            yield from go("x", at_rack, drive / 2)
            yield from go("forks", resting, lift / 2)
            state["carried"], state["level"] = False, level
            yield from go("forks", min(resting + 1, FORKS_DOWN), lift)
            yield from pause(10)
            yield from go("x", before_rack, drive)
            yield from go("forks", FORKS_CARRY, lift)
        else:  # in the rack: fetch it and set it down on the ground somewhere
            host.status(f"bay_{state['level']}_to_ground")
            resting = LEVELS[state["level"]] - PALLET_SLOTS
            yield from go("x", before_rack, drive)
            yield from go("forks", min(resting + 1, FORKS_DOWN), lift)
            yield from go("x", at_rack, drive / 2)
            yield from go("forks", resting, lift / 2)
            state["carried"], state["level"] = True, None
            yield from go("forks", min(resting - 3, FORKS_CARRY), lift / 2)
            yield from go("x", before_rack, drive / 2)
            yield from go("forks", FORKS_CARRY, lift)
            left = rng.randint(*GROUND_SPOTS)
            yield from go("x", left - 1 - LIFT_CARRIAGE, drive)
            yield from go("forks", GROUND - 1 - PALLET_SLOTS, lift / 2)
            state["carried"] = False
            yield from go("forks", FORKS_DOWN, lift)
            yield from pause(10)
            yield from go("x", max(-4.0, state["x"] - rng.uniform(8, 20)), drive)
        state["moves"] += 1
        yield from pause(15)

def overlap(start, end, other_start, other_end):
    """How far two ranges (ends included) overlap: 0 or more when they touch"""

    return min(end, other_end) - max(start, other_start)

class ForkliftGame:
    """The forklift game: drive and lift with the arrow keys to put the
    pallet where the top line says.  Time is counted in frames at "fps".

    The pallet's "physics": it rests on the highest thing under it - the
    forks, a beam or the ground.  Resting only on the forks, it goes where
    they go; touching a beam or the ground, that holds it (so the forks can
    slide out).  A pallet whose middle isn't over its beam falls when the
    forks leave it, and breaks if it falls far.  Nothing goes through the
    racking bay's beams, or through a pallet, except the forks into the
    slots at its bottom"""

    DRIVE, LIFT, GRAVITY = 1.4, 1, 0.35  # pixels per frame, rows per frame, rows/frame/frame
    TARGETS = ("ground", "bay 0", "bay 1", "bay 2")

    def __init__(self, rng, host, fps=30):
        self.rng, self.host, self.fps = rng, host, fps
        self.frame_no = 0
        self.x, self.forks = rng.uniform(-4, 20), FORKS_CARRY
        self.pallet = [float(rng.randint(GROUND_SPOTS[0] + 20, GROUND_SPOTS[1])), GROUND - 1]
        self.falling = None  # (speed, the row it fell from) while the pallet falls
        self.pieces = []  # a broken pallet's pieces: [x0, y0, x1, y1, vx, vy]
        self.new_pallet_at = None  # the frame a broken pallet gets replaced
        self.placed, self.broken = 0, 0
        self.message, self.message_until = "", 0
        self.new_target()

    # Where things are

    def pallet_box(self, left=None, bottom=None):
        left = self.pallet[0] if left is None else left
        bottom = self.pallet[1] if bottom is None else bottom
        return left, left + PALLET_WIDTH - 1, bottom - PALLET_HEIGHT + 1, bottom

    def forks_in_slots(self, x=None, forks=None):
        carriage = (self.x if x is None else x) + LIFT_CARRIAGE
        forks = self.forks if forks is None else forks
        left, right, _, bottom = self.pallet_box()
        return overlap(carriage, carriage + FORK_LENGTH, left, right) >= 4  \
            and bottom - PALLET_SLOTS <= forks <= bottom

    def on_forks(self):
        return self.pieces == [] and self.falling is None and self.forks_in_slots()

    def support(self, left=None, bottom=None):
        """What the pallet stands on: "ground", a beam's level (1 or 2), or None"""

        left, right, _, bottom = self.pallet_box(left, bottom)
        if bottom >= GROUND - 1:
            return "ground"
        return next((level for level, row in BEAMS.items() if bottom + 1 == row
                     and overlap(left, right, RACK_X, RACK_X + RACK_WIDTH) >= 0), None)

    def balanced(self):
        middle = self.pallet[0] + PALLET_WIDTH / 2
        return self.support() == "ground" or RACK_X <= middle <= RACK_X + RACK_WIDTH

    def location(self):
        """Where the pallet has been put: one of TARGETS, or None"""

        if self.pieces or self.falling is not None or not self.balanced():
            return None
        support = self.support()
        in_bay = RACK_X <= self.pallet[0] + PALLET_WIDTH / 2 <= RACK_X + RACK_WIDTH
        if support == "ground":
            return "bay 0" if in_bay else "ground"  \
                if self.pallet[0] + PALLET_WIDTH <= RACK_X else None
        return f"bay {support}" if support else None

    @staticmethod
    def hits_rack(left, right, top, bottom):
        return any(overlap(left, right, RACK_X, RACK_X + RACK_WIDTH) >= 0
                   and overlap(top, bottom, row, row + 1) >= 0
                   for row in (RACK_TOP, *BEAMS.values()))

    # Moving

    def try_move(self, x, forks):
        if not (-4 <= x <= LIFT_X_MAX and FORKS_TOP <= forks <= FORKS_DOWN):
            return False
        left, bottom = self.pallet
        new_left, new_bottom = left, bottom
        if self.on_forks():
            if not self.support():  # riding only on the forks: it goes where they go
                new_left, new_bottom = left + (x - self.x), bottom + (forks - self.forks)
            elif forks < self.forks:  # the forks lift it off the beam or ground
                new_bottom = min(bottom, forks + PALLET_SLOTS)
        carriage = x + LIFT_CARRIAGE
        if self.hits_rack(carriage, carriage + FORK_LENGTH, forks, forks) or  \
                self.hits_rack(carriage, carriage, forks - CARRIAGE_HEIGHT, forks):
            return False
        if not self.pieces:
            box = self.pallet_box(new_left, new_bottom)
            if (new_left, new_bottom) != (left, bottom):
                if self.hits_rack(*box):
                    return False
            else:  # the forks, carriage and mast against the pallet standing still
                p_left, p_right, p_top, p_bottom = box
                if overlap(carriage, carriage + FORK_LENGTH, p_left, p_right) >= 0  \
                        and p_top <= forks <= p_bottom  \
                        and not p_bottom - PALLET_SLOTS <= forks <= p_bottom:
                    return False
                if overlap(carriage, carriage, p_left, p_right) >= 0 and  \
                        overlap(forks - CARRIAGE_HEIGHT, forks, p_top, p_bottom) >= 0:
                    return False
                if overlap(x + LIFT_MAST[0], x + LIFT_MAST[1], p_left, p_right) >= 0 and  \
                        overlap(LIFT_MAST_TOP, GROUND - 1, p_top, p_bottom) >= 0:
                    return False
        self.x, self.forks, self.pallet = x, forks, [new_left, new_bottom]
        return True

    def step(self, held):
        """One frame: move as the keys say, then let the pallet fall, break
        or be placed"""

        self.frame_no += 1
        if "up" in held or "down" in held:
            self.try_move(self.x, self.forks + (1 if "down" in held else -1) * self.LIFT)
        if "left" in held or "right" in held:
            self.try_move(self.x + (1 if "right" in held else -1) * self.DRIVE, self.forks)
        if self.pieces:
            self.shatter()
        elif self.falling is not None:
            self.fall()
        elif not self.on_forks() and not (self.support() and self.balanced()):
            self.falling = (0.0, self.pallet[1])  # nothing under it, or it tips
            self.show_message("Whoops!")
        elif self.location() == self.target and not self.forks_in_slots():
            seconds = (self.frame_no - self.started) / self.fps
            self.placed += 1
            self.show_message(f"Done in {seconds:.1f}s!")
            self.host.status(f"placed_{self.placed}_broken_{self.broken}")
            self.new_target()

    def fall(self):
        speed, start = self.falling
        speed += self.GRAVITY
        self.pallet[1] += speed
        self.falling = (speed, start)
        if self.pallet[1] >= GROUND - 1:
            self.pallet[1], self.falling = GROUND - 1, None
            if GROUND - 1 - start > 6:
                self.break_pallet()

    def break_pallet(self):
        self.broken += 1
        self.pieces = [[x0, y0, x1, y1, self.rng.uniform(-1.5, 1.5), self.rng.uniform(-2.5, -0.5)]
                       for (x0, y0), (x1, y1) in pallet_lines(*self.pallet)]
        self.new_pallet_at = self.frame_no + round(2.5 * self.fps)
        self.show_message("Broken!")
        self.host.status(f"broken_{self.broken}")

    def shatter(self):
        """Move the broken pieces, bouncing on the ground; then a new pallet"""

        for piece in self.pieces:
            piece[4] *= 0.97
            piece[5] += self.GRAVITY
            piece[0] += piece[4]
            piece[2] += piece[4]
            piece[1] += piece[5]
            piece[3] += piece[5]
            below = max(piece[1], piece[3]) - (GROUND - 1)
            if below > 0:
                piece[1], piece[3] = piece[1] - below, piece[3] - below
                piece[4], piece[5] = piece[4] * 0.5, -piece[5] * 0.3 if piece[5] > 1 else 0
        if self.frame_no >= self.new_pallet_at:
            carriage = self.x + LIFT_CARRIAGE
            spots = [left for left in range(*GROUND_SPOTS)
                     if left > carriage + FORK_LENGTH + 3 or left + PALLET_WIDTH < self.x]
            self.pieces = []
            self.pallet = [float(self.rng.choice(spots or [GROUND_SPOTS[1]])), GROUND - 1]
            self.new_target()

    def new_target(self):
        self.target = self.rng.choice([target for target in self.TARGETS
                                       if target != self.location()])
        self.started = self.frame_no
        self.host.status("to_" + self.target.replace(" ", "_"))

    def show_message(self, message):
        self.message, self.message_until = message, self.frame_no + 2 * self.fps

    def frame(self):
        image = draw_warehouse(self.x, self.forks, None if self.pieces else self.pallet,
                               self.pieces)
        seconds = (self.frame_no - self.started) / self.fps
        line = self.message if self.frame_no < self.message_until  \
            else f"To {self.target}  {seconds:.1f}s"
        stamp(image, self.host.font.render_line(line), 1, 0)
        return image

# --------------------------------------------------------------------------- #
# Applets

class GeneratorApplet(Applet):
    """An applet whose frames come from a generator function
    generator(rng, host); "seed=" repeats the same play"""

    fps = 30
    OPTIONS = {"seed": int}
    generator = None

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.rng = host.rng if "seed" not in self.options  \
            else __import__("random").Random(self.options["seed"])
        self._frames = type(self).generator(self.rng, host)

    def step(self):
        try:
            return next(self._frames)
        except StopIteration:
            raise AppletDone

class PongApplet(GeneratorApplet):
    name = "pong"
    description = "pong"
    summary = "Self-playing pong"
    generator = staticmethod(pong)

class AsteroidsApplet(GeneratorApplet):
    name = "asteroids"
    description = "asteroids"
    summary = "Self-playing asteroids"
    generator = staticmethod(asteroids)

class InvadersApplet(GeneratorApplet):
    name = "invaders"
    description = "invaders"
    summary = "Self-playing space invaders"
    generator = staticmethod(invaders)

class GamesApplet(Applet):
    """The three games in turn, "duration" seconds each"""

    name = "games"
    fps = 30
    OPTIONS = {"seed": int, "duration": float}
    summary = "Pong, asteroids and invaders in turn"

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.rng = host.rng if "seed" not in self.options  \
            else __import__("random").Random(self.options["seed"])
        self.duration = max(1.0, self.options.get("duration", 20.0))
        self._names = list(GAMES)
        self._turn = -1
        self._next_game()

    def _next_game(self):
        self._turn = (self._turn + 1) % len(self._names)
        name = self._names[self._turn]
        self._frames = GAMES[name](self.rng, self.host)
        self._left = round(self.duration * self.fps)
        self.description = name
        self.host.status(name)

    def step(self):
        if self._left <= 0:
            self._next_game()
        self._left -= 1
        return next(self._frames)

class ForkliftApplet(GeneratorApplet):
    """The forklift at work by itself; "duration" seconds, 0 for ever"""

    name = "forklift"
    description = "forklift"
    OPTIONS = {"seed": int, "duration": float}
    summary = "A forklift moves a pallet in and out of a racking bay by itself"
    generator = staticmethod(forklift_work)

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        duration = self.options.get("duration", 0)
        self._left = round(duration * self.fps) if duration else None

    def step(self):
        if self._left is not None:
            if self._left <= 0:
                raise AppletDone
            self._left -= 1
        return super().step()

class ForkliftGameApplet(Applet):
    """The forklift game, driven by (key left|right|up|down)"""

    name = "forklift_game"
    fps = 30
    OPTIONS = {"seed": int}
    description = "forklift_game"
    summary = "The forklift game: (key left|right|up|down) drive and lift"

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        rng = host.rng if "seed" not in self.options  \
            else __import__("random").Random(self.options["seed"])
        self.game = ForkliftGame(rng, host, self.fps)

    def step(self):
        self.game.step(self.host.keys_held())
        return self.game.frame()

for applet in (PongApplet, AsteroidsApplet, InvadersApplet,
                    GamesApplet, ForkliftApplet, ForkliftGameApplet):
    APPLETS[applet.name] = applet
