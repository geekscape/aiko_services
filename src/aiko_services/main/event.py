# Aiko Engine
# ~~~~~~~~~~~
#
# Usage
# ~~~~~
# import time
# import aiko_services.event as event
#
# counter = 1
# def flatout_test():
#     global counter
#     counter += 1
#
# def timer_test():
#     global counter
#     print(f"timer_test(): {time.monotonic()}: {counter}")
#
# event.add_flatout_handler(flatout_test)
# event.add_timer_handler(timer_test, 1.0)
# event.loop()
#
# To Do
# ~~~~~
# * Remove queue handler ... and replace usage with mailboxes *
#
# * For shared data, e.g Locks and more ...
#   - Ensure all updates occur via "events" (handlers, messages and timers)
#     managed by the event loop and executed solely by the event loop thread
#
# * Replace 'event.queue_put(message, "message")' with the general ability to
#   put any 'object' onto a queue to get "work" onto the "event loop" and
#   have that work done by a specified handler
#
# * Rename "event.py" to "handler.py" along with function and variable names ?
#
# * Make function names consistently verb_noun() or noun_verb(), but not both !
#
# - Provide unit tests !  For all add / remove all the various handler types.
#   - See "tests/unit/test_event.py" for event.loop() starvation tests
#
# - BUG: With multiple timer handlers using the same handler function,
#        then remove_timer_handler() make remove the wrong one.
#        Need an identifier to specific exactly which handler instance
#
# - BUG: Handle case of calling event.terminate() before entering event.loop()
#        Due to event_enabled being overwritten at the start of event.loop()
#
# - BUG: Make _handler_count thread-safe, when adding and removing handlers !
#   - See "mutex": https://hg.python.org/cpython/file/3.5/Lib/queue.py
#
# - BUG: Why isn't event.add_timer_handler(_, _, True) firing immediately ?
#
# - add_timer_handler(... count=None) to automatically expire after count
# - add_mailbox_handler(... max_size=None) to limit maximum queue size
#
# - Move "_timer_counter" and "update_timer_counter()" into EventList
# - Refactor all remaining functions into new EventEngine class
# - Coalesce remove_flatout_handler() and remove_timer_handler() into
#     single remove_handler() that works in all cases.
#
# - Provide simple wallclock time monitoring of handler invocation time
# - Currently, flatout_handlers invocation rate is limited by ...
#     "sleep_time = 0.001", i.e 1,000 Hz.  Make this configurable.
# - All Services should have initialise() and stream event handler()
#   - All Streams also have task_start() and task_stop()
# - Since handlers take time, need to adjust time.sleep() period
# - New event types: GStreamer appsink, appsrc, serial

from collections import OrderedDict  # All OrderedDict operations are O(1)
import queue
import time
from typing import Any, Tuple

from aiko_services.main.utilities import *

__all__ = [
    "add_flatout_handler", "add_mailbox_handler",
    "add_queue_handler", "add_timer_handler",
    "loop", "mailbox_put", "queue_put",
    "remove_flatout_handler", "remove_mailbox_handler",
    "remove_queue_handler", "remove_timer_handler",
    "terminate"
]

_MAILBOX_INCREMENT_WARNING = 4

# Bound the work done by each event.loop() pass, so that a mailbox or queue
# that is refilled as fast as it is drained can't starve timers (and Leases),
# the event queue (MQTT messages) or the other mailboxes

_MAILBOX_ITEMS_PER_PASS = 16  # per mailbox, including the priority mailbox
_QUEUE_ITEMS_PER_PASS = 64
_SLEEP_TIME = 0.01            # seconds, maximum sleep when no work is pending

_handler_count = 0
_timer_counter = 0

def update_timer_counter():
    global _timer_counter
    if event_list.head:
        _timer_counter = event_list.head.time_next - time.monotonic()

class Event:
    def __init__(self, handler, time_period, immediate=False):
        self.handler = handler
        self.time_next = time.monotonic()
        if not immediate:
            self.time_next += time_period
        self.time_period = time_period
        self.next = None

class EventList:
    def __init__(self):
        self.head = None

    def add(self, event):
        if not self.head or event.time_next < self.head.time_next:
            event.next = self.head
            self.head = event
            update_timer_counter()
        else:
            current = self.head
            while current.next:
                if current.next.time_next > event.time_next: break
                current = current.next
            event.next = current.next
            current.next = event

    def print_event_list(self):
        current = self.head
        while current:
            print(current)
            current = current.next

    def remove(self, handler):
        return self._remove(lambda current: current.handler == handler)

    def _remove(self, match):
        previous = None
        current = self.head
        while current:
            if match(current):
                if previous:
                    previous.next = current.next
                else:
                    self.head = current.next
                    update_timer_counter()
                break
            previous = current
            current = current.next
        return current

# Advance an Event that has just fired, if its handler didn't remove it

    def reschedule(self, event):
        if self._remove(lambda current: current is event):
            event.time_next += event.time_period
            event.next = None
            self.add(event)

    def reset(self):
        current = self.head
        current_time = time.monotonic()
        while current:
            current.time_next = current_time + current.time_period
            current = current.next
        update_timer_counter()

    def update(self):
        if self.head:
            event = self.head
            event.time_next += event.time_period
            if event.next:
                if event.time_next > event.next.time_next:
                    self.head = event.next
                    self.add(event)
            update_timer_counter()


event_enabled = False
event_list = EventList()
event_loop_lock = Lock(f"{__name__}.loop")
event_loop_running = False
event_queue: "queue.Queue[Tuple[Any, Any]]" = queue.Queue()
flatout_handlers = []
mailboxes = OrderedDict()
queue_handlers = {}

def add_flatout_handler(handler):
    global _handler_count
    flatout_handlers.append(handler)
    _handler_count += 1

def remove_flatout_handler(handler):
    global _handler_count
    flatout_handlers.remove(handler)
    _handler_count -= 1

class Mailbox:
    def __init__(
        self, handler, name, increment_warning=_MAILBOX_INCREMENT_WARNING):

        self.handler = handler
        self.name = name
        self.increment_warning = increment_warning

        self.high_water_mark = 0
        self.last_warned_increment = 0
        self.queue = queue.Queue()
        self.size = 0

    def put(self, item):
        self.queue.put(item, block=False)
        self.size = self.queue.qsize()
        if self.size > self.high_water_mark:
            self.high_water_mark = self.size
        if self.size >= self.last_warned_increment + self.increment_warning:
            message = f"Mailbox {self.name}: size={self.size}"
            message = f"\033[91m{message}\033[0m"  # highlight red
        #   print(message)
            self.last_warned_increment += self.increment_warning

# First mailbox added has priority handling for all posted messages

def add_mailbox_handler(
    mailbox_handler,
    mailbox_name,
    mailbox_increment_warning=_MAILBOX_INCREMENT_WARNING):

    global _handler_count
    if mailbox_name not in mailboxes:
        mailbox = Mailbox(
            mailbox_handler, mailbox_name, mailbox_increment_warning)
        mailboxes[mailbox_name] = mailbox
        _handler_count += 1
    else:
        raise RuntimeError(f"Mailbox {mailbox_name}: Already exists")

def remove_mailbox_handler(mailbox_handler, mailbox_name):
    global _handler_count
    if mailbox_name in mailboxes:
        del(mailboxes[mailbox_name])
        _handler_count -= 1

def mailbox_put(mailbox_name, item):
    if mailbox_name in mailboxes:
        item = (item, time.monotonic())
        mailboxes[mailbox_name].put(item)
    else:
        raise RuntimeError(f"Mailbox {mailbox_name}: Not found")

def add_queue_handler(queue_handler, item_types=["default"]):
    global _handler_count
    for item_type in item_types:
        if not item_type in queue_handlers:
            queue_handlers[item_type] = []
        queue_handlers[item_type].append(queue_handler)
        _handler_count += 1

def remove_queue_handler(queue_handler, item_types=["default"]):
    global _handler_count
    for item_type in item_types:
        if item_type in queue_handlers:
            if queue_handler in queue_handlers[item_type]:
                queue_handlers[item_type].remove(queue_handler)
                _handler_count -= 1
            if len(queue_handlers[item_type]) == 0:
                del queue_handlers[item_type]

def queue_put(item, item_type="default"):
    event_queue.put((item, item_type))

def add_timer_handler(handler, time_period, immediate=False):
    global _handler_count
    event = Event(handler, time_period, immediate)
    event_list.add(event)
    _handler_count += 1

def remove_timer_handler(handler):
    global _handler_count
    if event_list.remove(handler):  # only count a timer that was removed
        _handler_count -= 1

# Each timer that is due fires at most once per event.loop() pass

def _handle_timers():
    fired = set()
    while True:
        event = event_list.head
        if not event or event in fired or time.monotonic() < event.time_next:
            return len(fired)
        fired.add(event)
        event.handler()
        event_list.reschedule(event)

def _handle_queue():
    count = 0
    while count < _QUEUE_ITEMS_PER_PASS:
        try:
            item, item_type = event_queue.get_nowait()
        except queue.Empty:
            break
        count += 1
        if item_type in queue_handlers:
            for queue_handler in queue_handlers[item_type]:
                queue_handler(item, item_type)
    return count

def _mailbox_get(mailbox_name, mailbox):
    try:
        item, time_posted = mailbox.queue.get_nowait()
    except queue.Empty:
        return False
    mailbox.handler(mailbox_name, item, time_posted)
    return True

# The first mailbox added has priority: Before handling each item from any
# other mailbox, a pending priority mailbox item is handled first.
# Every mailbox, including the priority mailbox, handles at most
# _MAILBOX_ITEMS_PER_PASS items per pass

def _handle_mailboxes():
    if not mailboxes:
        return 0
    count = 0
    priority_name, priority_mailbox = next(iter(mailboxes.items()))
    priority_count = 0
    for mailbox_name, mailbox in mailboxes.copy().items():
        if mailbox is priority_mailbox:
            while priority_count < _MAILBOX_ITEMS_PER_PASS:
                if not _mailbox_get(priority_name, priority_mailbox):
                    break
                priority_count += 1
            continue
        mailbox_count = 0
        while mailbox_count < _MAILBOX_ITEMS_PER_PASS:
            if priority_count < _MAILBOX_ITEMS_PER_PASS:
                if _mailbox_get(priority_name, priority_mailbox):
                    priority_count += 1
                    continue
            if not _mailbox_get(mailbox_name, mailbox):
                break
            mailbox_count += 1
        count += mailbox_count
    return count + priority_count

def _is_work_pending():
    if not event_queue.empty():
        return True
    for mailbox in mailboxes.copy().values():
        if not mailbox.queue.empty():
            return True
    return False

def loop(loop_when_no_handlers=False):
    global event_enabled, event_loop_running

    try:
        event_loop_lock.acquire("loop() #1")
        if event_loop_running:
            return
        event_loop_running = True
    finally:
        event_loop_lock.release()

    event_list.reset()

    try:
        event_enabled = True
        while event_enabled and (loop_when_no_handlers or _handler_count):
            _handle_timers()
            _handle_queue()
            _handle_mailboxes()

            sleep_time = _SLEEP_TIME
            if len(flatout_handlers):
                time_start = time.monotonic()
                for flatout_handler in flatout_handlers:
                    flatout_handler()
                sleep_time = sleep_time - (time.monotonic() - time_start)

            if _is_work_pending():
                sleep_time = 0
            elif event_list.head:
                time_timer = event_list.head.time_next - time.monotonic()
                sleep_time = min(sleep_time, time_timer)
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        raise SystemExit("KeyboardInterrupt: abort !")
    finally:
        try:
            event_loop_lock.acquire("loop() #2")
            event_loop_running = False
        finally:
            event_loop_lock.release()

def terminate():
    global event_enabled
    event_enabled = False
