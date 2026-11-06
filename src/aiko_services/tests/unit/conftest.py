# Usage
# ~~~~~
# pytest src/aiko_services/tests/unit
# AIKO_TEST_REPORT_LEAKS=1 pytest src/aiko_services/tests/unit  # list leaks
#
# Unit test isolation for the event loop.  The event loop is process-global:
# a timer or a mailbox that one test registers and leaves behind stays
# registered for every later test.  Each composed Actor adds two mailboxes,
# and Leases, Pipelines, Registrars and other Services add timers, so a full
# unit run accumulated about 490 mailboxes and 70 timers.  Every event loop
# pass visits them all, so a later test that runs the real event loop was
# slower in a full run than alone, and a timing test failed only in full
# runs on a Raspberry Pi 4.
#
# The autouse fixture below restores the event loop's registrations after
# each test: it removes the timers (matched by identity, never by handler,
# so that a timer registered earlier with the same handler is kept) and the
# mailboxes that the test added.  Queue and flatout handlers are not
# touched, because aiko.process registers its message queue handler once,
# in the first test that initializes the process, and never again.
#
# This implements the constitution's rule "Fixtures reset process-global
# state" (e_06_TestingStrategy).  A test should still release what it
# registers.  AIKO_TEST_REPORT_LEAKS=1
# lists the tests that leave timers or mailboxes behind, at the end of the
# run, so that a leak can be fixed where it starts.
#
# To Do
# ~~~~~
# - Fix the leaking tests at their source, then make a leak a failure

import os

import pytest

from aiko_services.main import event

_REPORT_LEAKS = os.environ.get("AIKO_TEST_REPORT_LEAKS", "").lower() in (
    "1", "true", "yes")
_leaks = []                      # (nodeid, timer names, mailbox names)

def _timer_events():
    events = []
    current = event.event_list.head
    while current:
        events.append(current)
        current = current.next
    return events

def _timer_name(timer_event):
    handler = timer_event.handler
    owner = getattr(handler, "__self__", None)
    name = getattr(handler, "__name__", repr(handler))
    return f"{type(owner).__name__}.{name}" if owner is not None else name

def _remove_timer_event(timer_event):
    """Remove this Event, not the first Event with the same handler"""

    if event.event_list._remove(lambda current: current is timer_event):
        event._handler_count -= 1

@pytest.fixture(autouse=True)
def restore_event_loop_registrations(request):
    timers_before = _timer_events()   # held, so that ids are not reused
    timer_ids_before = {id(timer_event) for timer_event in timers_before}
    mailboxes_before = set(event.mailboxes)

    yield

    leaked_timers = [timer_event for timer_event in _timer_events()
                     if id(timer_event) not in timer_ids_before]
    leaked_mailboxes = [name for name in event.mailboxes
                        if name not in mailboxes_before]
    if _REPORT_LEAKS and (leaked_timers or leaked_mailboxes):
        _leaks.append((request.node.nodeid,
                       sorted(_timer_name(timer) for timer in leaked_timers),
                       leaked_mailboxes))
    for timer_event in leaked_timers:
        _remove_timer_event(timer_event)
    for mailbox_name in leaked_mailboxes:
        event.remove_mailbox_handler(None, mailbox_name)

def pytest_terminal_summary(terminalreporter):
    if not _REPORT_LEAKS:
        return
    terminalreporter.section("event loop registrations left behind")
    if not _leaks:
        terminalreporter.write_line("none")
    for nodeid, timers, mailboxes in _leaks:
        terminalreporter.write_line(
            f"{nodeid}: {len(timers)} timers {timers}, "
            f"{len(mailboxes)} mailboxes")
