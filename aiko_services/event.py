#!/usr/bin/env python3
#
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
# - All Services should have initialise() and stream event handler()
#   - All Streams also have task_start() and task_stop()
# - Since handlers take time, need to adjust time.sleep() period
# - New event types: Messages, GStreamer appsink, appsrc, serial

import time

__all__ = ["add_timer_handler", "remove_timer_handler", "loop", "terminate"]

timer_counter = 0

def update_timer_counter():
    global timer_counter
    if event_list.head:
        timer_counter = event_list.head.time_next - time.time()

class Event:
    def __init__(self, handler, time_period):
        self.handler = handler
        self.time_next = time.time() + time_period
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
flatout_handlers = []

def add_flatout_handler(handler):
    flatout_handlers.append(handler)

def remove_flatout_handler(handler):
    flatout_handlers.remove(handler)

def add_timer_handler(handler, time_period):
    event = Event(handler, time_period)
    event_list.add(event)

def remove_timer_handler(handler):
    event_list.remove(handler)

def loop():
    global event_enabled, timer_counter
    event_list.reset()

    event_enabled = True
    while event_enabled:
        event = event_list.head
        if event and timer_counter <= 0:
            if time.time() >= event.time_next:
                event.handler()
                event_list.update()
        sleep_time = 0.001
        if len(flatout_handlers):
            time_start = time.time()
            for flatout_handler in flatout_handlers:
                flatout_handler()
            sleep_time = sleep_time - (time.time() - time_start)
        if sleep_time > 0:
            time.sleep(sleep_time)
            timer_counter -= sleep_time

def terminate():
    global event_enabled
    event_enabled = False
