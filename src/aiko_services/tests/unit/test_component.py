# Usage
# ~~~~~
# pytest [-s] unit/test_component.py
# pytest [-s] unit/test_component.py::test_compose_instance_basic
#
# Regression tests for the composition engine "component.py", required by
# Design Principle P7 (amendment 2026-07-07) before any further refactoring
# builds on it, covering the two flagged latent-bug areas ...
#
# 1. _check_interfaces_implemented(): unimplemented Interfaces must raise,
#    marker (empty) Interfaces must compose when a default is registered
#
# 2. Over-broad default-implementation pickup: Interface.context is a single
#    shared registry, so get_implementations() returns every registered
#    default; _keep_specified_implementations() must keep only those
#    matching the seed class's own Interface hierarchy
#
# Each test uses uniquely-named Interfaces ("TCmp...") because the default
# registry is global and shared with the framework's own registrations.
#
# To Do
# ~~~~~
# - None, yet !

from abc import abstractmethod

import aiko_services as aiko
from aiko_services.main.component import compose_class, compose_instance
from aiko_services.main.context import Context, Interface


class TCmpGreeter(Interface):
    @abstractmethod
    def greet(self, name): pass

class TCmpGreeterImpl(TCmpGreeter):
    def __init__(self, context):
        self.greeted = []

    def greet(self, name):
        self.greeted.append(name)

Interface.default("TCmpGreeter", TCmpGreeterImpl)


def test_compose_instance_basic():
    greeter = compose_instance(TCmpGreeterImpl, {"context": Context()})
    greeter.greet("Pele")
    assert greeter.greeted == ["Pele"]
    assert type(greeter).__name__ == "TCmpGreeterImpl"

def test_unimplemented_interface_raises():
    class TCmpOrphan(Interface):  # no Interface.default() registration
        @abstractmethod
        def method_0(self): pass

    class TCmpOrphanImpl(TCmpOrphan):
        def __init__(self, context):
            pass

        def method_0(self):
            pass

    try:
        compose_instance(TCmpOrphanImpl, {"context": Context()})
        assert False, "Expected ValueError for unimplemented Interface"
    except ValueError as value_error:
        assert "TCmpOrphan" in str(value_error)

def test_marker_interface_composes():
    # Empty marker Interfaces (e.g. Registrar today) must compose when a
    # default implementation is registered for them

    class TCmpMarker(Interface):
        Interface.default("TCmpMarker", TCmpGreeterImpl)

    class TCmpMarkerImpl(TCmpMarker):
        def __init__(self, context):
            pass

    Interface.default("TCmpMarker", TCmpMarkerImpl)
    marker = compose_instance(TCmpMarkerImpl, {"context": Context()})
    assert marker is not None

def test_unrelated_defaults_not_picked_up():
    # The default registry is global: get_implementations() returns every
    # registered default.  Composition must keep only the Interfaces in the
    # seed class's own hierarchy — an unrelated Interface's methods must
    # never leak into the composed class

    class TCmpUnrelated(Interface):
        @abstractmethod
        def unrelated_method(self): pass

    class TCmpUnrelatedImpl(TCmpUnrelated):
        def __init__(self, context):
            pass

        def unrelated_method(self):
            pass

    Interface.default("TCmpUnrelated", TCmpUnrelatedImpl)

    assert "TCmpUnrelated" in TCmpGreeterImpl.get_implementations()
    frankenstein_class, implementations = compose_class(TCmpGreeterImpl)
    assert "TCmpUnrelated" not in implementations
    assert not hasattr(frankenstein_class, "unrelated_method")

def test_impl_override():
    # Overrides substitute an Interface's implementation beneath an
    # application seed class.  Note: methods the seed class itself defines
    # concretely are never replaced (_add_methods contract) — hence the
    # seed here is an application class, not the Impl

    class TCmpGreeterApp(TCmpGreeter):
        def __init__(self, context):
            context.call_init(self, "TCmpGreeter", context)

    class TCmpGreeterQuiet(TCmpGreeter):
        def __init__(self, context):
            self.greeted = []

        def greet(self, name):
            pass  # quietly ignore

    greeter = compose_instance(TCmpGreeterApp, {"context": Context()},
        impl_overrides={"TCmpGreeter": TCmpGreeterQuiet})
    greeter.greet("Pele")
    assert greeter.greeted == []  # quiet override, not the default Impl

def test_seed_concrete_methods_never_replaced():
    # _add_methods contract: a concrete method on the seed class always
    # wins over any implementation's method of the same name

    class TCmpGreeterLoud(TCmpGreeter):
        def __init__(self, context):
            context.call_init(self, "TCmpGreeter", context)

        def greet(self, name):
            self.greeted.append(name.upper())

    greeter = compose_instance(TCmpGreeterLoud, {"context": Context()})
    greeter.greet("Pele")
    assert greeter.greeted == ["PELE"]

def test_call_init_idempotent():
    # Context.call_init() must initialize each implementation exactly once
    # (diamond hierarchies reach a shared base Interface a single time).
    # Idempotency applies to inits routed through call_init(): direct
    # construction runs the seed's own __init__ outside that guard

    class TCmpCounting(Interface):
        @abstractmethod
        def count(self): pass

    class TCmpCountingImpl(TCmpCounting):
        def __init__(self, context):
            self.init_count = getattr(self, "init_count", 0) + 1

        def count(self):
            return self.init_count

    Interface.default("TCmpCounting", TCmpCountingImpl)

    context = Context()
    instance = compose_instance(TCmpCountingImpl, {"context": context})
    assert instance.count() == 1        # direct construction
    context.call_init(instance, "TCmpCounting", context)
    assert instance.count() == 2        # first call_init() executes ...
    context.call_init(instance, "TCmpCounting", context)
    assert instance.count() == 2        # ... second is guarded

# Synthesized default __init__ (ADR-021) ------------------------------------

def test_synthesized_init():
    class TCmpNoInit(TCmpGreeter):  # no __init__() at all
        pass

    greeter = compose_instance(TCmpNoInit, {"context": Context()})
    greeter.greet("Pele")
    assert greeter.greeted == ["Pele"]  # TCmpGreeterImpl.__init__ ran

def test_synthesized_init_actor_with_protocol():
    class TCmpAloha(aiko.Actor):  # no __init__(); protocol via attribute
        PROTOCOL = "tcmp_aloha:0"

        def aloha(self, name):
            self.share["aloha"] = name

    instance = compose_instance(TCmpAloha, aiko.actor_args("tcmp_aloha"))
    assert type(instance).__name__ == "TCmpAloha"
    assert instance.protocol == "tcmp_aloha:0"
    assert hasattr(instance, "logger") and hasattr(instance, "share")
    instance.aloha("Pele")
    assert instance.share["aloha"] == "Pele"

def test_synthesized_init_dual_interface():
    class TCmpOther(Interface):
        @abstractmethod
        def other(self): pass

    class TCmpOtherImpl(TCmpOther):
        def __init__(self, context):
            self.other_initialized = True

        def other(self):
            return self.other_initialized

    Interface.default("TCmpOther", TCmpOtherImpl)

    class TCmpDual(TCmpGreeter, TCmpOther):  # no __init__(); two parents
        pass

    dual = compose_instance(TCmpDual, {"context": Context()})
    dual.greet("Pele")
    assert dual.greeted == ["Pele"]     # first parent initialized ...
    assert dual.other() is True         # ... and the second

def test_synthesized_init_forwards_kwargs():
    class TCmpConfigurable(Interface):
        @abstractmethod
        def get_option(self): pass

    class TCmpConfigurableImpl(TCmpConfigurable):
        def __init__(self, context, option="default"):
            self.option = option

        def get_option(self):
            return self.option

    Interface.default("TCmpConfigurable", TCmpConfigurableImpl)

    class TCmpConfigured(TCmpConfigurable):  # no __init__()
        pass

    instance = compose_instance(
        TCmpConfigured, {"context": Context(), "option": "custom"})
    assert instance.get_option() == "custom"

def test_explicit_init_always_wins():
    class TCmpExplicit(TCmpGreeter):
        def __init__(self, context):
            context.call_init(self, "TCmpGreeter", context)
            self.explicit = True

    instance = compose_instance(TCmpExplicit, {"context": Context()})
    assert instance.explicit is True
    instance.greet("Pele")
    assert instance.greeted == ["Pele"]
