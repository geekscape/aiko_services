# Usage
# ~~~~~
# pytest [-s] unit/test_whisplay.py
#
# Unit tests for the WhisPlay Actor (actors/whisplay/): the frame, the press
# rule, the panel and camera seams, and the Actor's dispatch and handlers.
#
# No hardware and no broker.  The frame composition and the press rule are
# pure functions, so they are tested directly.  The Actor is composed with
# the fake panel, camera and button, and with worker=False, so its handlers
# are called without the worker thread running.
#
# Every wire method has at least one negative test (ADR-014), and the
# allow-list is asserted exactly, because this Actor denies by default (P12).

import itertools
import queue
import time

from PIL import Image
import pytest

import aiko_services as aiko
from aiko_services.actors.whisplay import (
    ACTIONS, IMAGE_SIZE, PANEL_SIZE, PROTOCOL, SETTINGS, TEXT_LINES,
    WIRE_COMMANDS, WhisPlayImpl, Y_OFFSET, choose_button, choose_camera,
    choose_panel, classify, compose, parse_resolution, to_rgb565,
)

_counter = itertools.count()

def make_actor(**parameters):
    panel = parameters.pop("panel", None) or choose_panel("none")
    camera = parameters.pop("camera", None) or choose_camera("none")
    button = parameters.pop("button", None) or choose_button("none")
    init_args = aiko.actor_args(
        f"whisplay_test_{next(_counter)}", protocol=PROTOCOL)
    init_args.update({
        "panel": panel, "camera": camera, "button": button, "worker": False,
        **parameters})
    return aiko.compose_instance(WhisPlayImpl, init_args), panel, button

def run_until(predicate, timeout=5.0):
    """Run the event loop, with its mailboxes and timers, until predicate()
    is true.  Two things make a single timed call unreliable here.  A fixed
    window makes the test depend on wall-clock speed.  And the event loop is
    a global that earlier tests leave timer handlers in, so a handler that
    is not ours can terminate the loop after one pass.  So the loop is
    entered again until the predicate holds, or the deadline passes"""

    deadline = time.monotonic() + timeout

    def check():
        if predicate() or time.monotonic() > deadline:
            aiko.event.remove_timer_handler(check)
            aiko.process.terminate()

    aiko.event.add_timer_handler(check, 0.02)
    try:
        while not predicate() and time.monotonic() < deadline:
            aiko.process.run(mqtt_connection_required=False)
            time.sleep(0.01)         # a loop that exits at once must not spin
    finally:
        aiko.event.remove_timer_handler(check)

# The frame ---------------------------------------------------------------- #

def test_frame_is_the_panel_size():
    assert compose().size == PANEL_SIZE

def test_frame_puts_the_image_at_the_top():
    red = Image.new("RGB", IMAGE_SIZE, (255, 0, 0))
    frame = compose(red)

    assert frame.getpixel((0, 0)) == (255, 0, 0)            # image area
    assert frame.getpixel((0, IMAGE_SIZE[1] - 1)) == (255, 0, 0)
    assert frame.getpixel((0, IMAGE_SIZE[1] + 40)) == (0, 0, 0)   # text area

def test_frame_resizes_an_image_of_the_wrong_size():
    frame = compose(Image.new("RGB", (640, 480), (0, 255, 0)))
    assert frame.size == PANEL_SIZE
    assert frame.getpixel((120, 90)) == (0, 255, 0)

def test_frame_rotates_when_asked():
    """A 240x180 image turned 90 degrees is 180x240, and is then fitted"""

    image = Image.new("RGB", IMAGE_SIZE, (0, 0, 255))
    assert compose(image, rotate=90).size == PANEL_SIZE

def test_frame_accepts_an_array():
    import numpy

    array = numpy.zeros((IMAGE_SIZE[1], IMAGE_SIZE[0], 3), dtype=numpy.uint8)
    array[:, :, 0] = 255
    assert compose(array).getpixel((10, 10)) == (255, 0, 0)

def test_frame_draws_text_under_the_image():
    plain = compose(None, [])
    titled = compose(None, ["aiko01"])
    assert plain.tobytes() != titled.tobytes()

def test_frame_takes_no_more_lines_than_fit():
    many = [f"line {index}" for index in range(TEXT_LINES + 3)]
    assert compose(None, many).size == PANEL_SIZE
    assert compose(None, many).tobytes() ==  \
        compose(None, many[:TEXT_LINES]).tobytes()

def test_rows_fill_the_text_area():
    """Five rows of ROW_HEIGHT come to exactly the 100 pixels under the
    image"""

    from aiko_services.actors.whisplay.frame import ROW_HEIGHT, TEXT_SIZE

    assert TEXT_LINES * ROW_HEIGHT == TEXT_SIZE[1]

def test_the_bottom_rows_are_inset_for_the_rounded_corners():
    """The glass curve takes about the bottom 25 pixels, which is the last
    row and the end of the row above it"""

    from aiko_services.actors.whisplay.frame import (
        CORNER_ROWS, MARGIN, row_margin)

    for row in range(TEXT_LINES - CORNER_ROWS):
        assert row_margin(row) == MARGIN
    for row in range(TEXT_LINES - CORNER_ROWS, TEXT_LINES):
        assert row_margin(row) > MARGIN

def test_a_row_takes_left_centre_and_right_parts():
    plain = compose(None, [(), (), (), (), ()])
    left = compose(None, [("L", None, None)])
    centre = compose(None, [(None, "C", None)])
    right = compose(None, [(None, None, "R")])
    assert len({frame.tobytes() for frame in (plain, left, centre, right)}) == 4

def _rightmost_lit_column(image, top, height):
    """The last column holding a lit pixel, in one band of the picture"""

    band = image.crop((0, top, image.width, top + height))
    lit = [x for x in range(band.width)
           for y in range(band.height) if band.getpixel((x, y)) != (0, 0, 0)]
    return max(lit) if lit else None

def _lit_columns(image, top, height):
    """The first and last columns holding a lit pixel, in one band"""

    band = image.crop((0, top, image.width, top + height))
    lit = [x for x in range(band.width)
           for y in range(band.height) if band.getpixel((x, y)) != (0, 0, 0)]
    return (min(lit), max(lit)) if lit else (None, None)

def _fields_row(cpu, memory, temperature):
    from aiko_services.actors.whisplay.frame import IMAGE_SIZE, ROW_HEIGHT

    frame = compose(None, [(("C:", cpu, "%"), ("M:", memory, "%"),
                            ("", temperature, "C"))], aligns=["fields"])
    return _lit_columns(frame, IMAGE_SIZE[1], ROW_HEIGHT)

def test_the_letters_never_move():
    """"C:" starts in the same place and the temperature "C" ends in the
    same place, whether a reading has one digit or three"""

    assert _fields_row("1", "3", "7") == _fields_row("100", "100", "100")

def test_the_letters_never_move_for_any_width():
    widths = [_fields_row(value, value, value)
              for value in ("1", "30", "100", "-")]
    assert len(set(widths)) == 1

def test_the_numbers_are_right_aligned():
    """One digit or three, the last digit ends in the same place.

    "30" and "100" end in the same glyph, so their ink matches exactly.
    "1" is narrower than its cell, which is how tabular figures are drawn,
    so its ink stops two pixels earlier while its cell still lines up"""

    from aiko_services.actors.whisplay.frame import IMAGE_SIZE, ROW_HEIGHT

    def right_edge(value):
        frame = compose(None, [(("", value, ""), (), ())], aligns=["fields"])
        return _lit_columns(frame, IMAGE_SIZE[1], ROW_HEIGHT)[1]

    assert right_edge("30") == right_edge("100")
    assert abs(right_edge("1") - right_edge("100")) <= 3

def test_a_spread_row_moves_with_its_width():
    """The contrast: a spread row's right part is at the margin, so its
    own width decides where it starts"""

    from aiko_services.actors.whisplay.frame import IMAGE_SIZE, ROW_HEIGHT

    narrow = compose(None, [(None, None, "7C")])
    wide = compose(None, [(None, None, "100C")])
    assert _lit_columns(narrow, IMAGE_SIZE[1], ROW_HEIGHT)[0] !=  \
        _lit_columns(wide, IMAGE_SIZE[1], ROW_HEIGHT)[0]

def test_the_widest_readings_do_not_touch():
    """Measured at 20 point, the three fields at their widest leave 12 and
    15 pixels between them"""

    from PIL import ImageFont
    from aiko_services.actors.whisplay.frame import (
        FIELD_PLACES, MARGIN, TEXT_SIZE_POINTS)

    font = ImageFont.load_default(size=TEXT_SIZE_POINTS)
    widest = font.getlength("100")
    for index, (prefix, suffix) in enumerate([("C:", "%"), ("M:", "%"),
                                              ("", "C")]):
        prefix_x, value_x = FIELD_PLACES[index]
        assert prefix_x + font.getlength(prefix) <= value_x - widest
        if index < 2:
            ends = value_x + font.getlength(suffix)
            assert ends + 4 <= FIELD_PLACES[index + 1][0]
    assert FIELD_PLACES[0][0] >= MARGIN

def test_an_overlay_is_drawn_over_the_image():
    from aiko_services.actors.whisplay.frame import IMAGE_SIZE, ROW_HEIGHT

    plain = compose(Image.new("RGB", IMAGE_SIZE, (40, 40, 40)))
    marked = compose(Image.new("RGB", IMAGE_SIZE, (40, 40, 40)),
                     overlay=("1234", None, "12:00:00"))
    assert plain.tobytes() != marked.tobytes()
    # The difference is inside the image, above where the rows begin
    band = (0, IMAGE_SIZE[1] - ROW_HEIGHT, IMAGE_SIZE[0], IMAGE_SIZE[1])
    assert plain.crop(band).tobytes() != marked.crop(band).tobytes()

def test_rgb565_is_two_bytes_for_each_pixel():
    data = to_rgb565(compose())
    assert len(data) == PANEL_SIZE[0] * PANEL_SIZE[1] * 2

def test_rgb565_encodes_red_as_f800():
    data = to_rgb565(Image.new("RGB", (1, 1), (255, 0, 0)))
    assert data == b"\xf8\x00"

def test_rgb565_encodes_blue_as_001f():
    assert to_rgb565(Image.new("RGB", (1, 1), (0, 0, 255))) == b"\x00\x1f"

# The resolution ----------------------------------------------------------- #

def test_parse_resolution():
    assert parse_resolution("240x180") == (240, 180)
    assert parse_resolution("640X480") == (640, 480)

@pytest.mark.parametrize("text", ["240", "240x", "x180", "240x180x3", ""])
def test_parse_resolution_refuses_nonsense(text):
    with pytest.raises(ValueError):
        parse_resolution(text)

@pytest.mark.parametrize("text", ["0x180", "240x0", "-240x180"])
def test_parse_resolution_refuses_a_size_that_is_not_positive(text):
    with pytest.raises(ValueError):
        parse_resolution(text)

# The press rule ----------------------------------------------------------- #

def test_classify_a_long_press():
    assert classify(3.5) == "long"

def test_classify_a_short_press():
    assert classify(0.2) == "short"

def test_classify_at_the_boundary_is_short():
    """Longer *than* three seconds, so exactly three is short"""

    assert classify(3.0) == "short"
    assert classify(3.0001) == "long"

def test_classify_takes_another_threshold():
    assert classify(1.5, long_press_seconds=1.0) == "long"

def test_the_button_is_active_high():
    """The vendor driver says "pressed is 5V, released is 0V".  With the
    opposite setting every event arrives inverted: a press reports a
    release, the press is never seen, and a countdown started by a release
    never stops.  That cost a debugging session, so it is asserted"""

    from aiko_services.actors.whisplay.button import BUTTON_ACTIVE_HIGH

    assert BUTTON_ACTIVE_HIGH is True

def test_fake_button_reports_a_press():
    """Down first, so the countdown can start, then the release"""

    button = choose_button("none")
    seen = []
    button.add_handler(lambda kind, seconds: seen.append((kind, seconds)))
    button.press(4.0)
    assert seen == [("down", 0.0), ("long", 4.0)]

# The countdown ------------------------------------------------------------ #

def test_the_countdown_is_absent_while_the_button_is_up():
    actor, _, _ = make_actor()
    assert actor._countdown(None) is None

def test_the_countdown_runs_three_two_one_zero():
    """At 0 the press is long enough, and letting go acts"""

    import time as _time

    actor, _, _ = make_actor(long_press=3.0)
    now = _time.monotonic()
    assert actor._countdown(now) == 3                  # just pressed
    assert actor._countdown(now - 1.0) == 2
    assert actor._countdown(now - 2.0) == 1
    assert actor._countdown(now - 3.0) == 0
    assert actor._countdown(now - 9.0) == 0            # never goes negative

def test_the_countdown_follows_the_long_press_setting():
    import time as _time

    actor, _, _ = make_actor(long_press=5.0)
    assert actor._countdown(_time.monotonic()) == 5

def test_the_overlay_shows_the_countdown():
    actor, _, _ = make_actor()
    assert actor._overlay(7, 3)[1] == "Off: 3"
    assert actor._overlay(7, 0)[1] == "Off: 0"
    assert actor._overlay(7, None)[1] is None

def test_the_countdown_takes_the_whole_overlay_row():
    """Beside the time it had four pixels of room, which read as one word"""

    actor, _, _ = make_actor()
    assert actor._overlay(1234, 3) == (None, "Off: 3", None)
    frames, _, clock = actor._overlay(1234, None)
    assert frames == "1234" and ":" in clock

def test_pressing_down_starts_the_countdown():
    """P11: the handler runs on the event-loop thread and hands the worker
    a time through the queue, rather than sharing a variable"""

    actor, _, _ = make_actor()
    actor._button_press("down", "0.00")
    queued = actor._queue.get_nowait()
    assert "pressed_at" in queued and queued["pressed_at"] is not None

def test_releasing_ends_the_countdown(monkeypatch):
    actor, _, _ = make_actor()
    monkeypatch.setattr(
        "aiko_services.actors.whisplay.whisplay.subprocess.Popen", lambda c: None)
    monkeypatch.setattr(actor, "stop", lambda: None)

    actor._button_press("short", "0.20")
    assert actor._queue.get_nowait() == {"pressed_at": None}
    actor._button_press("long", "3.40")
    assert actor._queue.get_nowait() == {"pressed_at": None}

# The seams ---------------------------------------------------------------- #

def test_null_panel_keeps_the_last_frame():
    panel = choose_panel("none")
    frame = compose(None, ["hello"])
    panel.open(); panel.show(frame)
    assert panel.frame is frame

def test_null_panel_tracks_power():
    panel = choose_panel("none")
    panel.power(False)
    assert panel.powered is False

def test_choose_panel_refuses_an_unknown_panel():
    with pytest.raises(ValueError):
        choose_panel("eink")

def test_choose_camera_refuses_an_unknown_camera():
    with pytest.raises(ValueError):
        choose_camera("webcam")

def test_choose_button_refuses_an_unknown_button():
    with pytest.raises(ValueError):
        choose_button("touch")

def test_fake_camera_matches_the_size_it_opened():
    camera = choose_camera("none")
    camera.open((320, 240))
    assert camera.capture().shape == (240, 320, 3)

def test_st7789_window_adds_the_panel_offset():
    """The glass starts at row 20 of a 240x320 controller.  Get this wrong
    and the picture is shifted, not absent"""

    panel = choose_panel("st7789")
    sent = []
    panel._command = lambda command, *data: sent.append((command, data))
    panel._set_window(0, 0, 239, 279)

    columns = next(data for command, data in sent if command == 0x2A)
    rows = next(data for command, data in sent if command == 0x2B)
    assert columns == (0, 0, 0, 239)                       # x, unchanged
    assert rows == (0, Y_OFFSET, 1, 279 + Y_OFFSET - 256)  # y, offset by 20
    assert sent[-1][0] == 0x2C                             # write to memory

# The Actor ---------------------------------------------------------------- #

def test_actor_shares_its_settings():
    actor, _, _ = make_actor()
    for name in SETTINGS:
        assert name in actor.share
    assert actor.share["action"] == "power_off"
    assert actor.share["rate"] == "8.0"
    assert actor.share["resolution"] == "240x180"

def test_actor_denies_every_command_but_the_allow_list():
    """P12: the surface is exactly this, and nothing else"""

    assert WIRE_COMMANDS == frozenset({"set_log_level", "stop"})
    for name in ["_power_off", "_button_press", "_frames", "_worker_error", "run",
                 "_run", "create", "_topic_in_handler"]:
        assert name not in WIRE_COMMANDS

def test_actor_passes_an_allowed_command_to_the_mailbox():
    """The deny-list must not deny everything: an earlier version called a
    function that does not exist, so every command was refused as a parse
    error, including the allowed ones"""

    actor, _, _ = make_actor()
    posted = []
    actor._post_message = lambda topic, command, args: posted.append(
        (command, args))

    actor._topic_in_handler(None, "topic/in", "(set_log_level DEBUG)")
    assert posted == [("set_log_level", ["DEBUG"])]

def test_actor_refuses_an_unknown_wire_command():
    actor, _, _ = make_actor()
    actor._topic_in_handler(None, "topic/in", "(_power_off)")
    assert actor.share["last_error"] == "unknown_command"

def test_actor_refuses_a_payload_it_cannot_parse():
    actor, _, _ = make_actor()
    actor._topic_in_handler(None, "topic/in", "(((")
    assert actor.share["last_error"] == "parse_error"

def test_actor_acts_on_a_long_press(monkeypatch):
    actor, panel, _ = make_actor()
    halted = []
    monkeypatch.setattr(
        "aiko_services.actors.whisplay.whisplay.subprocess.Popen",
        lambda command: halted.append(command))
    monkeypatch.setattr(actor, "stop", lambda: None)

    actor._button_press("long", "3.40")
    assert halted == [["sudo", "-n", "shutdown", "-h", "now"]]

def test_actor_ignores_a_short_press(monkeypatch):
    actor, _, _ = make_actor()
    halted = []
    monkeypatch.setattr(
        "aiko_services.actors.whisplay.whisplay.subprocess.Popen",
        lambda command: halted.append(command))

    actor._button_press("short", "0.20")
    assert halted == []

def test_actor_does_nothing_on_a_long_press_when_the_action_is_none(monkeypatch):
    actor, _, _ = make_actor(action="none")
    halted = []
    monkeypatch.setattr(
        "aiko_services.actors.whisplay.whisplay.subprocess.Popen",
        lambda command: halted.append(command))

    actor._button_press("long", "4.00")
    assert halted == []

def test_worker_reports_frames_through_the_mailbox():
    """P11 end to end: the worker thread captures and shows, and never
    touches shared state.  It posts, and the event-loop thread applies"""

    panel, camera = choose_panel("none"), choose_camera("none")
    init_args = aiko.actor_args(
        f"whisplay_test_{next(_counter)}", protocol=PROTOCOL)
    init_args.update({
        "panel": panel, "camera": camera, "button": choose_button("none"),
        "action": "none", "rate": "30.0"})        # worker=True, on purpose
    actor = aiko.compose_instance(WhisPlayImpl, init_args)
    try:
        run_until(lambda: camera.captures > 0 and panel.frame is not None
            and int(actor.share["frames"]) > 0)
        assert camera.captures > 0                # the thread ran
        assert panel.frame is not None            # and drew something
        assert int(actor.share["frames"]) > 0     # applied on the loop thread
    finally:
        actor._stopping = True

def test_actor_queues_a_new_rate_for_the_worker():
    """P11: the handler validates on the event-loop thread, then hands the
    worker thread a copy through the queue"""

    actor, _, _ = make_actor()
    actor._ec_producer_change_handler("update", "rate", "1.5")
    assert actor._queue.get_nowait() == {"rate": 1.5}

def test_actor_queues_a_new_resolution_for_the_worker():
    actor, _, _ = make_actor()
    actor._ec_producer_change_handler("update", "resolution", "320x240")
    assert actor._queue.get_nowait() == {"resolution": (320, 240)}

def test_actor_refuses_a_rate_out_of_range():
    actor, _, _ = make_actor()
    actor._ec_producer_change_handler("update", "rate", "99")
    assert "rate must be" in actor.share["last_error"]
    with pytest.raises(queue.Empty):
        actor._queue.get_nowait()

def test_actor_refuses_an_unknown_action():
    actor, _, _ = make_actor()
    actor._ec_producer_change_handler("update", "action", "self_destruct")
    assert "action must be" in actor.share["last_error"]
    assert "self_destruct" not in ACTIONS

def test_actor_ignores_a_setting_it_does_not_own():
    actor, _, _ = make_actor()
    actor._ec_producer_change_handler("update", "nonsense", "1")
    with pytest.raises(queue.Empty):
        actor._queue.get_nowait()
