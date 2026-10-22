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

def run_loop(seconds=0.4):
    """Run the event loop for a moment: mailboxes and timers"""

    def stop():
        aiko.event.remove_timer_handler(stop)
        aiko.process.terminate()

    aiko.event.add_timer_handler(stop, seconds)
    aiko.process.run(mqtt_connection_required=False)

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

def test_fake_button_reports_a_press():
    button = choose_button("none")
    seen = []
    button.add_handler(lambda kind, seconds: seen.append((kind, seconds)))
    button.press(4.0)
    assert seen == [("long", 4.0)]

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
    assert actor.share["rate"] == "3.0"
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
        run_loop(0.6)
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
