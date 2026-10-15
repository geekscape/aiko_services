# Usage
# ~~~~~
# pytest [-s] unit/test_event.py
# pytest [-s] unit/test_event.py::test_priority_mailbox_flood_timer
#
# Tests for event.loop() starvation ...
# - A mailbox refilled as fast as it is drained must not starve timers,
#   the event queue (MQTT messages) or the other mailboxes
# - A priority mailbox item is still handled before other mailbox items
# - A timer handler that removes itself must not delay the other timers
#
# Each flood refills itself only until a deadline, so that the original
# (unbounded) event.loop() also terminates and these tests fail, not hang
#
# To Do
# ~~~~~
# - None, yet !

import queue
import threading
import time

import pytest

from aiko_services.main import event

_FLOOD_TIME = 1.0  # seconds
_WATCHDOG_TIME = 10.0  # seconds

@pytest.fixture
def clean_event():
    saved_mailboxes = event.mailboxes.copy()
    saved_flatout_handlers = list(event.flatout_handlers)
    saved_queue_handlers = dict(event.queue_handlers)
    saved_head = event.event_list.head
    saved_handler_count = event._handler_count
    saved_queue_items = []
    while not event.event_queue.empty():
        saved_queue_items.append(event.event_queue.get_nowait())

    event.mailboxes.clear()
    event.flatout_handlers.clear()
    event.queue_handlers.clear()
    event.event_list.head = None
    event._handler_count = 0

    watchdog = threading.Timer(_WATCHDOG_TIME, event.terminate)
    watchdog.daemon = True
    watchdog.start()
    yield
    watchdog.cancel()

    event.mailboxes.clear()
    event.mailboxes.update(saved_mailboxes)
    event.flatout_handlers[:] = saved_flatout_handlers
    event.queue_handlers.clear()
    event.queue_handlers.update(saved_queue_handlers)
    event.event_list.head = saved_head
    event._handler_count = saved_handler_count
    while not event.event_queue.empty():
        event.event_queue.get_nowait()
    for item in saved_queue_items:
        event.event_queue.put(item)

def _add_flood_mailbox(mailbox_name, deadline):
    counter = {"count": 0}
    def flood_handler(name, item, time_posted):
        counter["count"] += 1
        if time.monotonic() < deadline:
            event.mailbox_put(name, item)
    event.add_mailbox_handler(flood_handler, mailbox_name)
    event.mailbox_put(mailbox_name, "flood")
    return counter

def _add_stop_timer(deadline):
    def stop_handler():
        if time.monotonic() > deadline:
            event.remove_timer_handler(stop_handler)
            event.terminate()
    event.add_timer_handler(stop_handler, 0.05)

def test_priority_mailbox_flood_timer(clean_event):
    deadline = time.monotonic() + _FLOOD_TIME
    flood = _add_flood_mailbox("control", deadline)
    timer_fired = []
    def timer_handler():
        timer_fired.append(time.monotonic())
    event.add_timer_handler(timer_handler, 0.05)
    _add_stop_timer(deadline)

    event.loop()

    assert flood["count"] > 1
    assert timer_fired, "Timer never fired"
    assert timer_fired[0] < deadline, "Timer starved by priority mailbox"

def test_priority_mailbox_flood_queue(clean_event):
    deadline = time.monotonic() + _FLOOD_TIME
    queue_handled = []
    def queue_handler(item, item_type):
        queue_handled.append(time.monotonic())
    event.add_queue_handler(queue_handler, ["message"])
    def flood_handler(name, item, time_posted):
        if item == 100:  # MQTT message arrives during the flood
            event.queue_put("mqtt message", "message")
        if time.monotonic() < deadline:
            event.mailbox_put(name, item + 1)
    event.add_mailbox_handler(flood_handler, "control")
    event.mailbox_put("control", 0)
    _add_stop_timer(deadline)

    event.loop()

    assert queue_handled, "Event queue item never handled"
    assert queue_handled[0] < deadline, "Event queue starved by mailbox"

def test_mailbox_flood_other_mailbox(clean_event):
    deadline = time.monotonic() + _FLOOD_TIME
    event.add_mailbox_handler(lambda *args: None, "control")  # priority
    _add_flood_mailbox("busy", deadline)
    other_handled = []
    def other_handler(name, item, time_posted):
        other_handled.append(time.monotonic())
    event.add_mailbox_handler(other_handler, "other")
    event.mailbox_put("other", "item")
    _add_stop_timer(deadline)

    event.loop()

    assert other_handled, "Other mailbox item never handled"
    assert other_handled[0] < deadline, "Other mailbox starved by mailbox"

def test_priority_mailbox_preempts(clean_event):
    handled = []
    def control_handler(name, item, time_posted):
        handled.append(item)
    def in_handler(name, item, time_posted):
        handled.append(item)
        if item == "in_0":
            event.mailbox_put("control", "control_0")
        if item == "in_3":
            event.terminate()
    event.add_mailbox_handler(control_handler, "control")  # priority
    event.add_mailbox_handler(in_handler, "in")
    for index in range(4):
        event.mailbox_put("in", f"in_{index}")

    event.loop()

    assert handled == ["in_0", "control_0", "in_1", "in_2", "in_3"]

def test_timer_removes_itself(clean_event):
    time_start = time.monotonic()
    def once_handler():
        event.remove_timer_handler(once_handler)
    other_fired = []
    def other_handler():
        other_fired.append(time.monotonic() - time_start)
        event.remove_timer_handler(other_handler)
        event.terminate()
    event.add_timer_handler(once_handler, 0.0)
    event.add_timer_handler(other_handler, 0.2)

    event.loop()

    assert other_fired, "Other timer never fired"
    assert other_fired[0] < 0.35, "Other timer delayed by an extra period"

def test_remove_timer_handler_twice(clean_event):
    def timer_handler():
        pass
    event.add_timer_handler(timer_handler, 1.0)
    assert event._handler_count == 1
    event.remove_timer_handler(timer_handler)
    event.remove_timer_handler(timer_handler)  # not found: count unchanged
    assert event._handler_count == 0
