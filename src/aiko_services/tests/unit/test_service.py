# Usage
# ~~~~~
# pytest [-s] unit/test_service.py
# pytest [-s] unit/test_service.py::test_an_iterator_is_iterable
#
# Regression tests for "Services" and "ServicesIterator" in "service.py",
# which had none.
#
# "ServicesIterator" defined "__next__" and no "__iter__", so it was an
# incomplete iterator and "iter()" refused it: "TypeError:
# 'ServicesIterator' object is not iterable".
#
# Measured, because which consumer that stops is a function of the Python
# version, and one reading of it misleads (2026-10-30):
#
#   construct                          3.12.15   3.13.5   3.14.9
#   plain "for" statement              ok        ok       ok
#   list comprehension, generator      ok        raises   ok
#   "list()", "sorted()", "tuple()"    ok        ok       ok
#   "iter(iterator)"                   raises    raises   raises
#
# Python 3.13 alone refuses a comprehension, which is why
# "registrar.py:list_command()" crashed on aiko01, on 3.13, and passed on a
# 3.12 Mac.  Each shape is held below, because the CI matrix is 3.9 to 3.14
# and no one version shows the whole fault.
#
# Each test registers at least one Service, because "Services.__iter__"
# returns "iter([])" for an empty dict and never builds a
# "ServicesIterator" at all.  Each earlier test of these paths used an
# empty cache, which is why none of them could find this.
#
# To Do
# ~~~~~
# - Cover "filter_services()" and "Services.copy()", whose clone does not
#   carry "_count" ("dashboard.py:392" works around it)

from collections.abc import Iterator

import pytest

from aiko_services.main.service import Services

# topic_path, name, protocol, transport, owner, tags: the six fields that
# the Registrar registers, in the order "registrar:2" puts them on the wire

def service_details(process_id, service_id=1, name="actor"):
    topic_path = f"namespace/host/{process_id}/{service_id}"
    return [topic_path, name, "protocol:0", "mqtt", "owner", ["a=b"]]

@pytest.fixture
def services():
    """Two Services in one process, and a third in another, because the
    iterator steps over a dict of processes, each a dict of Services"""

    services = Services()
    for details in (service_details(1234, 1), service_details(1234, 2),
            service_details(5678, 1)):
        services.add_service(details[0], details)
    return services

# The iterator protocol --------------------------------------------------- #

def test_a_for_loop_reads_every_service(services):
    """What worked before the fix, and must keep working"""

    found = []
    for details in services:
        found.append(details[0])

    assert found == ["namespace/host/1234/1", "namespace/host/1234/2",
        "namespace/host/5678/1"]

def test_an_iterator_is_iterable(services):
    """The defect: "iter()" refuses an object without "__iter__", however
    complete its "__next__" is"""

    iterator = iter(services)

    assert isinstance(iterator, Iterator)
    assert iter(iterator) is iterator

@pytest.mark.parametrize("consumer", [list, tuple, sorted],
    ids=["list", "tuple", "sorted"])
def test_a_bulk_consumer_reads_every_service(services, consumer):
    """These pass on each version measured, with the fix or without it.
    They are here because the next release need not"""

    assert len(consumer(services)) == 3

def test_a_comprehension_over_the_services(services):
    """"registrar.py:list_command()" reads the cache exactly this way"""

    topic_paths = [details[0] for details in services]

    assert len(topic_paths) == 3

def test_a_partly_read_iterator_is_finished_by_a_consumer(services):
    """The shape that the missing "__iter__" actually broke: take the
    iterator, read one, and hand the rest to something else"""

    iterator = iter(services)
    first = next(iterator)

    assert first[0] == "namespace/host/1234/1"
    assert len(list(iterator)) == 2

def test_an_empty_services_yields_nothing(services):
    """The case that every earlier test used, and the reason the defect
    stayed hidden: this path never builds a "ServicesIterator" at all"""

    assert list(Services()) == []

# What the iterator walks ------------------------------------------------- #

def test_one_service_in_one_process():
    services = Services()
    details = service_details(1234)
    services.add_service(details[0], details)

    assert list(services) == [details]

def test_a_removed_service_is_not_iterated(services):
    services.remove_service("namespace/host/1234/1")

    assert [details[0] for details in services] ==  \
        ["namespace/host/1234/2", "namespace/host/5678/1"]

def test_the_last_service_of_a_process_takes_the_process_with_it(services):
    """An empty process dict would stop the iterator early, so
    "remove_service()" deletes it.  This holds that behavior"""

    services.remove_service("namespace/host/1234/1")
    services.remove_service("namespace/host/1234/2")

    assert [details[0] for details in services] == ["namespace/host/5678/1"]

def test_every_service_removed(services):
    for topic_path in list(services.get_topic_paths()):
        services.remove_service(topic_path)

    assert list(services) == []
    assert services.count == 0

# --------------------------------------------------------------------------- #
