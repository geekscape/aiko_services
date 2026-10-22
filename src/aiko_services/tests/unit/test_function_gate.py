# Aiko Services tests: the FunctionGate aspect
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# No hardware, no message broker, no event loop.
#
# The filter itself is pure, so most of these tests compose it alone.  The
# composition tests use the framework's own ActorTest, because the aspect's
# whole point is that it reaches every Actor.
#
# Two rules this file exists to hold, from the operating guide's section 9:
# a deny-by-default guard needs a test that something gets *through*, and
# the default must stay open, or every Actor in the framework changes
# behaviour at once (D13).
#
# To Do
# ~~~~~
# - A test for a policy Implementation that reads the HyperSpace, when the
#   To Do in "function_gate.py" is done

from abc import abstractmethod
import itertools

import pytest

import aiko_services as aiko
from aiko_services.main.actor import ActorTest, ActorTestImpl
from aiko_services.main.function_gate import (
    DENY_FUNCTION, DENY_PARAMETERS, DENY_PARSE,
    FunctionGate, FunctionGateImpl, interface_functions,
)

FRAMEWORK = frozenset({"set_log_level", "stop"})
_counter = itertools.count()

class _One(aiko.Interface):
    """Two abstract functions, one of them private, and one concrete"""

    @abstractmethod
    def one(self):
        pass

    @abstractmethod
    def _hidden(self):
        pass

    def concrete(self):
        pass

class _Two(aiko.Interface):
    @abstractmethod
    def two(self):
        pass

def make_gate(functions=None):
    """The aspect alone: no Actor, no Service, no composition of either"""

    init_args = {"context": aiko.Context()}
    if functions is not None:
        init_args["functions"] = functions
    return aiko.compose_instance(FunctionGateImpl, init_args)

def make_actor(impl=ActorTestImpl):
    """A composed Actor whose posted messages are collected, not run"""

    name = f"filter_test_{next(_counter)}"
    protocol = f"{aiko.SERVICE_PROTOCOL_AIKO}/filter_test:0"
    actor = aiko.compose_instance(impl, aiko.actor_args(name, protocol=protocol))
    posted = []
    actor._post_message = lambda topic, name, args: posted.append((name, args))
    return actor, posted

class _FilteredActorTestImpl(ActorTestImpl):
    """An Actor that configures the aspect with its own allow list, which
    is how every Actor that wants deny by default does it"""

    def __init__(self, context):
        context.call_init(self, "FunctionGate", context,
            functions=interface_functions(ActorTest))
        context.call_init(self, "Actor", context)
        self.test_count = None

# The allow list, derived from the contract ------------------------------- #

def test_no_interface_gives_the_framework_functions():
    assert interface_functions() == FRAMEWORK

def test_an_interface_contributes_its_abstract_functions():
    functions = interface_functions(ActorTest)

    assert {"initialize", "control_test", "test"} <= functions
    assert FRAMEWORK <= functions

def test_the_framework_functions_are_droppable():
    assert interface_functions(ActorTest, extra=()) ==  \
        frozenset({"initialize", "control_test", "test"})

def test_a_private_abstract_function_is_never_in_the_allow_list():
    assert "_hidden" not in interface_functions(_One)

def test_several_interfaces_are_a_union():
    assert interface_functions(_One, _Two, extra=()) ==  \
        frozenset({"one", "two"})

def test_a_concrete_function_is_not_in_the_allow_list():
    assert "concrete" not in interface_functions(_One, extra=())

def test_what_the_framework_declares_is_never_in_the_allow_list():
    """ADR-025 decision 1, enforced and not only documented: "run" must
    never reach the bus, however an Interface is passed in"""

    assert interface_functions(aiko.Actor, extra=()) == frozenset()
    assert "run" not in interface_functions(aiko.Actor)
    assert "add_message_handler" not in interface_functions(aiko.Service)

# The filter, alone ------------------------------------------------------- #

def test_an_unconfigured_filter_allows_everything():
    """D13: every Actor that does not configure the aspect keeps the
    behaviour it had before the aspect existed"""

    function_gate = make_gate()
    for name in ("test", "exit", "_remove", "anything at all"):
        assert function_gate.deny_function(name, []) is None

def test_a_configured_filter_allows_a_listed_function():
    """The test that an earlier guard did not have: something gets through"""

    assert make_gate({"test"}).deny_function("test", ["1"]) is None

def test_a_configured_filter_denies_an_unlisted_function():
    assert make_gate({"test"}).deny_function("exit", []) == DENY_FUNCTION

def test_an_empty_allow_list_denies_every_function():
    function_gate = make_gate(frozenset())
    for name in ("test", "set_log_level", "stop"):
        assert function_gate.deny_function(name, []) == DENY_FUNCTION

def test_parameters_that_are_not_a_list_are_denied():
    for parameters in ("a string", {"a": "dict"}, None, 7):
        assert make_gate({"test"}).deny_function("test", parameters) ==  \
            DENY_PARAMETERS

def test_parameters_are_checked_before_the_allow_list():
    """Even an unconfigured filter denies parameters it cannot dispatch"""

    assert make_gate().deny_function("test", "not a list") ==  \
        DENY_PARAMETERS

def test_the_filter_is_an_interface_with_a_default():
    assert issubclass(FunctionGateImpl, FunctionGate)
    assert "FunctionGate" in aiko.Interface.get_implementations()

# The aspect, composed into an Actor -------------------------------------- #

def test_every_actor_has_the_aspect():
    actor, _ = make_actor()

    assert callable(actor.deny_function)
    assert actor.functions is None            # unconfigured: allow all

def test_pipeline_and_pipeline_element_inherit_the_aspect():
    """The reason the aspect goes on Actor: it reaches everything that
    refines Actor, with no change to any of them"""

    from aiko_services.main.pipeline import Pipeline, PipelineElement

    for interface in (aiko.Actor, PipelineElement, Pipeline):
        assert FunctionGate in interface.__mro__

def test_an_unconfigured_actor_posts_any_function():
    actor, posted = make_actor()
    actor._topic_in_handler(None, "topic/in", "(anything 1 2)")

    assert posted == [("anything", ["1", "2"])]

def test_a_configured_actor_posts_an_allowed_function():
    actor, posted = make_actor(_FilteredActorTestImpl)
    actor._topic_in_handler(None, "topic/in", "(test 7)")

    assert posted == [("test", ["7"])]

def test_a_configured_actor_denies_an_unlisted_function():
    actor, posted = make_actor(_FilteredActorTestImpl)
    actor._topic_in_handler(None, "topic/in", "(_remove 1)")

    assert posted == []

def test_a_configured_actor_denies_a_payload_it_cannot_parse():
    actor, posted = make_actor(_FilteredActorTestImpl)
    actor._topic_in_handler(None, "topic/in", "(((")

    assert posted == []

def test_the_impl_configuration_survives_the_actors_own_call_init():
    """call_init() is idempotent, which is what lets an Implementation
    configure the aspect before it calls up to the Actor"""

    actor, _ = make_actor(_FilteredActorTestImpl)

    assert actor.functions == interface_functions(ActorTest)

def test_a_prefixed_name_is_not_an_alias_of_an_allowed_function():
    """Function name aliases were dropped (project-lead direction,
    2026-10-23): one function has one name, and a prefixed form is simply
    a function that is not in the allow list"""

    actor, posted = make_actor(_FilteredActorTestImpl)
    actor._topic_in_handler(None, "topic/in", "(actor_test:test 7)")

    assert posted == []

def test_a_denial_is_reported_in_the_shared_state():
    actor, _ = make_actor(_FilteredActorTestImpl)
    actor.share["last_error"] = "-"
    actor._topic_in_handler(None, "topic/in", "(_remove 1)")

    assert actor.share["last_error"] == f"{DENY_FUNCTION} _remove"

def test_a_parse_denial_reports_the_reason_without_a_name():
    actor, _ = make_actor(_FilteredActorTestImpl)
    actor.share["last_error"] = "-"
    actor._topic_in_handler(None, "topic/in", "(((")

    assert actor.share["last_error"] == DENY_PARSE

def test_an_actor_without_last_error_still_denies():
    """An Actor whose share has no "last_error" must not raise while it
    reports a denial"""

    actor, posted = make_actor(_FilteredActorTestImpl)
    actor.share.pop("last_error", None)
    actor._topic_in_handler(None, "topic/in", "(_remove 1)")

    assert posted == []

# --------------------------------------------------------------------------- #
