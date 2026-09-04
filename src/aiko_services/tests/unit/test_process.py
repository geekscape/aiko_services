# Usage
# ~~~~~
# pytest [-s] unit/test_process.py
# pytest [-s] unit/test_process.py::test_service_id_not_reused_after_remove
#
# Regression tests for Service identity allocation in "process.py".
#
# add_service() assigns "service_id", from which "topic_path" is built, and
# "topic_path" is the Service's identity on the bus. So the allocator must
# never issue an id that a live Service already holds.
#
# The bug these cover: "service_count" was both the live count (decremented by
# remove_service()) and the id allocator. Remove a non-last Service, add
# another, and the new Service takes the removed id, which is still held by a
# live Service: the new one overwrites the previous holder in "_services", and
# both carry the same topic_path.
#
# Reachable through hyperspace.py:296, which calls remove_service() when an
# empty Category is destroyed.
#
# To Do
# ~~~~~
# - None, yet !

import aiko_services as aiko


class ServiceStub:
    # A payload, not a Service: these tests exercise the allocator in
    # add_service() / remove_service(), which never inspects the object beyond
    # "protocol". "protocol" is None so the Registrar publish is skipped, and
    # no broker is needed
    def __init__(self, label):
        self.label = label
        self.service_id = None
        self.topic_path = None
        self.protocol = None


def _fresh_process():
    # "aiko.process" is a singleton shared across the suite, so each test resets
    # it explicitly rather than unwinding through remove_service(): with the bug
    # present, ids collide and "_services" loses entries, so an unwind leaves
    # "service_count" drifted and later tests fail for the wrong reason
    process = aiko.process
    process._services.clear()
    process.service_count = 0
    process._service_id_last = 0
    return process


def test_service_ids_are_distinct_without_removals():
    # Control: if this ever fails, the tests below prove nothing
    process = _fresh_process()
    a, b = ServiceStub("a"), ServiceStub("b")
    process.add_service(a)
    process.add_service(b)

    assert a.service_id != b.service_id
    assert a.topic_path != b.topic_path


def test_service_id_not_reused_after_remove():
    process = _fresh_process()
    a, b = ServiceStub("a"), ServiceStub("b")
    process.add_service(a)
    process.add_service(b)

    process.remove_service(a.service_id)  # remove the NON-last Service

    c = ServiceStub("c")
    process.add_service(c)

    assert c.service_id != b.service_id, \
        "new Service reused the id of a live Service"
    assert c.topic_path != b.topic_path, \
        "two live Services share a topic_path"


def test_live_service_survives_a_later_add():
    process = _fresh_process()
    a, b = ServiceStub("a"), ServiceStub("b")
    process.add_service(a)
    process.add_service(b)
    process.remove_service(a.service_id)
    process.add_service(ServiceStub("c"))

    assert b in process._services.values(), \
        "a live Service was evicted from _services by a later add_service()"


def test_service_count_still_tracks_live_services():
    # The allocator changed; the public return value must not
    process = _fresh_process()
    a = ServiceStub("a")

    assert process.add_service(a) == 1
    assert process.add_service(ServiceStub("b")) == 2
    assert process.remove_service(a.service_id) == 1
