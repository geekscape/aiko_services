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
# - BUG: Need to make handler_count, adding and removing handlers thread-safe !
#   - See "mutex": https://hg.python.org/cpython/file/3.5/Lib/queue.py
# - BUG: Why isn't event.add_timer_handler(_, _, True) firing immediately ?
# - Move "timer_counter" and "update_timer_counter()" into EventList
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
# - New event types: Queue, Messages, GStreamer appsink, appsrc, serial

from queue import Queue
import time

__all__ = ["add_timer_handler", "remove_timer_handler", "loop", "terminate"]

handler_count = 0
timer_counter = 0

def update_timer_counter():
    global timer_counter
    if event_list.head:
        timer_counter = event_list.head.time_next - time.time()

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
event_queue = Queue()
flatout_handlers = []
queue_handlers = {}

__all__ = ["add_flatout_handler", "add_queue_handler", "add_timer_handler", "loop", "queue_put", "remove_flatout_handler", "remove_queue_handler", "remove_timer_handler", "terminate"]

def add_flatout_handler(handler):
    global handler_count
    flatout_handlers.append(handler)
    handler_count += 1

def remove_flatout_handler(handler):
    global handler_count
    flatout_handlers.remove(handler)
    handler_count -= 1

def add_timer_handler(handler, time_period, immediate=False):
    global handler_count
    event = Event(handler, time_period, immediate)
    event_list.add(event)
    handler_count += 1

def remove_timer_handler(handler):
    global handler_count
    event_list.remove(handler)
    handler_count -= 1

def add_queue_handler(queue_handler, item_type="default"):
    if not item_type in queue_handlers:
        queue_handlers[item_type] = []
    queue_handlers[item_type].append(queue_handler)

def remove_queue_handler(queue_handler, item_type):
    if item_type in queue_handlers:
        if queue_handler in queue_handlers[item_type]:
            queue_handlers[item_type].remove(queue_handler)
        if len(queue_handlers[item_type]) == 0:
            del queue_handlers[item_type]

def queue_put(item, item_type="default"):
    event_queue.put((item, item_type))

def loop(loop_when_no_handlers=False):
    global event_enabled, timer_counter
    event_list.reset()

    try:
        event_enabled = True
        while event_enabled and (loop_when_no_handlers or handler_count):
            event = event_list.head
            if event and timer_counter <= 0:
                if time.time() >= event.time_next:
                    event.handler()
                    event_list.update()
            sleep_time = 0.001

            if event_queue.qsize():
                (item, item_type) = event_queue.get()
                if item_type in queue_handlers:
                    for queue_handler in queue_handlers[item_type]:
                        queue_handler(item, item_type)

            if len(flatout_handlers):
                time_start = time.time()
                for flatout_handler in flatout_handlers:
                    flatout_handler()
                sleep_time = sleep_time - (time.time() - time_start)
# TODO:         timer_counter -= sleep_time  # and don't sleep !
            if sleep_time > 0:
                time.sleep(sleep_time)
                timer_counter -= sleep_time
    except KeyboardInterrupt:
        raise SystemExit("KeyboardInterrupt: abort !")

def terminate():
    global event_enabled
    event_enabled = False
