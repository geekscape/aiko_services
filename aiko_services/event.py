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
#     print(f"timer_test(): {time.time()}: {counter}")
#
# event.add_flatout_handler(flatout_test)
# event.add_timer_handler(timer_test, 1.0)
# event.loop()
#
# To Do
# ~~~~~
# - Make function names consistently verb_noun() or noun_verb(), but not both !
#
# - BUG: Handle case of calling event.terminate() before entering event.loop()
#        Due to event_enabled being overwritten at the start of event.loop()
# - BUG: Make _handler_count thread-safe, when adding and removing handlers !
#   - See "mutex": https://hg.python.org/cpython/file/3.5/Lib/queue.py
# - BUG: Why isn't event.add_timer_handler(_, _, True) firing immediately ?
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
# - New event types: Mailbox, Queue, GStreamer appsink, appsrc, serial

from collections import OrderedDict
import queue
import time
import threading

__all__ = [
    "add_flatout_handler", "add_mailbox_handler",
    "add_queue_handler", "add_timer_handler",
    "loop", "mailbox_put", "queue_put",
    "remove_flatout_handler", "remove_mailbox_handler",
    "remove_queue_handler", "remove_timer_handler",
    "terminate"
]

_MAILBOX_SIZE = 8

_handler_count = 0
_timer_counter = 0

def update_timer_counter():
    global _timer_counter
    if event_list.head:
        _timer_counter = event_list.head.time_next - time.time()

class Event:
    def __init__(self, handler, time_period, immediate=False):
        self.handler = handler
        self.time_next = time.time()
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
        previous = None
        current = self.head
        while current:
            if current.handler == handler:
                if previous:
                    previous.next = current.next
                else:
                    self.head = current.next
                    update_timer_counter()
                break
            previous = current
            current = current.next
        return current

    def reset(self):
        current = self.head
        current_time = time.time()
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
event_loop_lock = threading.Lock()
event_loop_running = False
event_queue = queue.Queue()
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

# First mailbox added has priority handling for all posted messages
def add_mailbox_handler(
    mailbox_handler,
    mailbox_name,
    mailbox_size=_MAILBOX_SIZE):

    global _handler_count
    if mailbox_name not in mailboxes:
        mailbox = queue.Queue(maxsize=mailbox_size)
        mailboxes[mailbox_name] = (mailbox_handler, mailbox)
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
        try:
            item = (item, time.time())
            mailbox_queue = mailboxes[mailbox_name][1]
            mailbox_queue.put(item, block=False)
        except queue.Full:
            raise RuntimeError(f"Mailbox {mailbox_name} full")
    else:
        raise RuntimeError(f"Mailbox {mailbox_name} not found")

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
    event_list.remove(handler)
    _handler_count -= 1

def loop(loop_when_no_handlers=False):
    global event_enabled, event_loop_running, _timer_counter

    event_loop_lock.acquire()
    if event_loop_running:
        return
    event_loop_running = True
    event_loop_lock.release()

    event_list.reset()

    try:
        event_enabled = True
        while event_enabled and (loop_when_no_handlers or _handler_count):
            event = event_list.head
            if event and _timer_counter <= 0:
                if time.time() >= event.time_next:
                    event.handler()
                    event_list.update()
            sleep_time = 0.001

            if event_queue.qsize():
                (item, item_type) = event_queue.get()
                if item_type in queue_handlers:
                    for queue_handler in queue_handlers[item_type]:
                        queue_handler(item, item_type)

            if len(mailboxes) > 0:
                # First mailbox added has priority for all posted messages
                _, priority_queue = mailboxes[list(mailboxes)[0]]
                handle_mailboxes = True
                while handle_mailboxes:
                    for mailbox_name in mailboxes:
                        mailbox_handler, mailbox_queue = mailboxes[mailbox_name]
                        while mailbox_queue.qsize() > 0:
                            item, time_posted = mailbox_queue.get()
                            mailbox_handler(mailbox_name, item, time_posted)
                            if mailbox_queue != priority_queue:
                                if priority_queue.qsize() > 0:
                                    break
                        if priority_queue.qsize() > 0:
                            break
                    handle_mailboxes = False

            if len(flatout_handlers):
                time_start = time.time()
                for flatout_handler in flatout_handlers:
                    flatout_handler()
                sleep_time = sleep_time - (time.time() - time_start)
# TODO:         _timer_counter -= sleep_time  # and don't sleep !
            if sleep_time > 0:
                time.sleep(sleep_time)
                _timer_counter -= sleep_time
    except KeyboardInterrupt:
        raise SystemExit("KeyboardInterrupt: abort !")
    finally:
        event_loop_lock.acquire()
        event_loop_running = False
        event_loop_lock.release()

def terminate():
    global event_enabled
    event_enabled = False
