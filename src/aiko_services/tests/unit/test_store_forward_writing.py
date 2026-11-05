# Usage
# ~~~~~
# pytest [-s] unit/test_store_forward_writing.py
#
# Unit tests for the one branch that stops a recording
# (elements/media/store_forward_io.py, VideoWriteStoreForward._skipping).
#
# Goal 3.  A host on its battery pack does not want a recording nobody
# asked for: the transfer queue grows with work that is not wanted, and
# then holds the host up to drain it.  So this element stops writing when
# the host says so.
#
# These tests are about the branch, and not about the Pipeline.  The
# Pipeline, the camera and the MP4 writing have their own test in
# test_store_forward_io.py, which needs OpenCV.  This one needs nothing, so
# the rule that drops frames is checked everywhere the suite runs.
#
# _skipping() takes the stream and the frames and nothing else, which is
# why it is a method of its own: the decision is testable without a
# Pipeline, a camera or a broker.

from aiko_services.elements.media.store_forward_io import (
    VideoWriteStoreForward
)

class FakeProducer:
    def __init__(self):
        self.updates = {}

    def update(self, name, value):
        self.updates[name] = value

class FakeWriting:
    """A WritingClient stand-in: one boolean, as the real one answers"""

    def __init__(self, okay=True):
        self.okay = okay

    def writing_ok(self):
        return self.okay

class FakeStream:
    def __init__(self, writing=None):
        self.variables = {"segment_writer": writing}

class Element:
    """Only what _skipping() touches.  The method is called unbound, so the
    code under test is the real one"""

    def __init__(self, writing=None, segment_writer=None):
        self._writing = writing
        self._frames_skipped = 0
        self._writing_was = True
        self.ec_producer = FakeProducer()
        self.closed = 0
        self.stream = FakeStream(segment_writer)
        self.logged = []

    def my_id(self):
        return "element"

    @property
    def logger(self):
        element = self

        class Logger:
            def info(self, text):
                element.logged.append(text)
        return Logger()

    def _close_segment(self, stream):
        self.closed += 1
        stream.variables["segment_writer"] = None

    def skipping(self, images):
        return VideoWriteStoreForward._skipping(self, self.stream, images)

IMAGES = ["frame", "frame", "frame"]

# Writing as usual --------------------------------------------------------- #

def test_a_host_with_no_power_manager_writes():
    """The client is None until a stream starts, and a host with no power
    manager answers True for ever.  Either way nothing is dropped"""

    assert Element().skipping(IMAGES) is False

def test_a_host_that_says_writing_is_okay_writes():
    assert Element(writing=FakeWriting(True)).skipping(IMAGES) is False

def test_nothing_is_counted_while_writing_is_okay():
    element = Element(writing=FakeWriting(True))
    element.skipping(IMAGES)
    assert element._frames_skipped == 0
    assert element.ec_producer.updates == {}

def test_a_segment_in_hand_is_left_alone_while_writing_is_okay():
    element = Element(writing=FakeWriting(True), segment_writer="open")
    element.skipping(IMAGES)
    assert element.closed == 0
    assert element.stream.variables["segment_writer"] == "open"

# Writing stopped ---------------------------------------------------------- #

def test_a_host_that_says_no_drops_the_frames():
    assert Element(writing=FakeWriting(False)).skipping(IMAGES) is True

def test_the_segment_in_hand_is_closed_so_that_it_can_go():
    """The point of closing rather than abandoning it: a closed segment is
    forwarded, and the queue drains and lets the host stop"""

    element = Element(writing=FakeWriting(False), segment_writer="open")
    assert element.skipping(IMAGES) is True
    assert element.closed == 1
    assert element.stream.variables["segment_writer"] is None

def test_the_segment_is_closed_once_however_many_frames_follow():
    element = Element(writing=FakeWriting(False), segment_writer="open")
    for _ in range(5):
        element.skipping(IMAGES)
    assert element.closed == 1

def test_no_segment_in_hand_is_not_an_error():
    element = Element(writing=FakeWriting(False))
    assert element.skipping(IMAGES) is True
    assert element.closed == 0

def test_the_dropped_frames_are_counted():
    element = Element(writing=FakeWriting(False))
    element.skipping(IMAGES)
    element.skipping(IMAGES)
    assert element._frames_skipped == 6

def test_the_count_is_published_so_an_operator_sees_why():
    """Nothing being written looks like a fault.  The count and the
    "writing_ok" flag are what say it is not"""

    element = Element(writing=FakeWriting(False))
    element.skipping(IMAGES)
    assert element.ec_producer.updates["frames_skipped"] == "3"

def test_an_empty_frame_list_counts_nothing():
    element = Element(writing=FakeWriting(False))
    assert element.skipping([]) is True
    assert element._frames_skipped == 0

# Going back and forth ----------------------------------------------------- #

def test_writing_starts_again_when_the_host_says_so():
    """A supply that comes back allows writing again, and the element asks
    on every frame rather than remembering an answer"""

    writing = FakeWriting(True)
    element = Element(writing=writing)
    assert element.skipping(IMAGES) is False
    writing.okay = False
    assert element.skipping(IMAGES) is True
    writing.okay = True
    assert element.skipping(IMAGES) is False
    assert element._frames_skipped == 3

def test_the_element_seeds_both_items_in_its_shared_state():
    """Nothing being written looks like a fault, so a Dashboard must show
    the reason before anything happens, and not only after the first drop"""

    import inspect

    source = inspect.getsource(VideoWriteStoreForward.__init__)
    assert '"writing_ok": True' in source
    assert '"frames_skipped": "0"' in source

# Where a change is published ---------------------------------------------- #
#
# On this element's own thread, and never from the client's handler.  A
# change arrives on whichever thread delivered it, and the shared state
# belongs to the element's thread (P11).  _skipping() runs on that thread
# for every frame, so it is where a change is noticed as well as acted on.

def test_a_change_to_not_okay_is_published_once():
    writing = FakeWriting(True)
    element = Element(writing=writing)
    element.skipping(IMAGES)
    assert "writing_ok" not in element.ec_producer.updates
    writing.okay = False
    element.skipping(IMAGES)
    assert element.ec_producer.updates["writing_ok"] is False
    assert len(element.logged) == 1
    element.skipping(IMAGES)
    assert len(element.logged) == 1               # Said once, not per frame

def test_a_change_back_to_okay_is_published_too():
    writing = FakeWriting(False)
    element = Element(writing=writing)
    element.skipping(IMAGES)
    writing.okay = True
    element.skipping(IMAGES)
    assert element.ec_producer.updates["writing_ok"] is True
    assert len(element.logged) == 2

def test_no_power_manager_publishes_nothing():
    """A host without one must look exactly as it did before"""

    element = Element()
    for _ in range(3):
        element.skipping(IMAGES)
    assert element.ec_producer.updates == {}
    assert element.logged == []
