# Description
# ~~~~~~~~~~~
# Provide functions for ... design by composition (of interfaces).
# Utilize "context.py" to provide required data fields as a single argument.
# Support defining interface default implementation, which may be over-ridden.
#
# Usage
# ~~~~~
# from abc import abstractmethod
# from aiko_services.main import *
#
# class Example(Interface):
#     Interface.default("Example", "__main__.ExampleImpl")
#
#     @abstractmethod
#     def method_0(self): pass
#
# class ExampleImpl(Example):
#     def __init__(self, context, parameter):
#         print(f"ExampleImpl.__init__({parameter})")
#
#     def method_0(self):
#         print("ExampleImpl.method_0()")
#
# init_args = server_args("example")
# init_args["parameter"] = "value"
# example = compose_instance(ExampleImpl, init_args)
# example.method_0()
#
# To Do
# ~~~~~
# - BUG: _check_interfaces_implemented() working correctly ?
#
# - Support composing a class once and using it to create multiple instances
#
# - "impl_seed_class.get_implementations()" always picks up all the
#     AikoServices #   interfaces default implementations
#
# - Design "protocol" (Interface hieracrchy) for inbound and outbound methods
#   - Different Interfaces may optionally have different "connection pads"

from abc import ABC
from inspect import getmembers, isclass, isfunction

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = ["compose_class", "compose_instance"]

def compose_class(impl_seed_class, impl_overrides=None):
    """
    Build a concrete FrankensteinClass whose API is defined using Interfaces
    (classes with only abstract methods) and then composed from specified
    implementations for those Interfaces

    The impl_seed_class will inherit from a pure Interface hierarchy
    that specifies the default implementations for each of the Interfaces

    When creating the FrankensteinClass instance, those default implementations
    may be overridden as required
    """

    if impl_overrides == None:
        impl_overrides = {}

    all_implementations = {
        **impl_seed_class.get_implementations(), **impl_overrides
    }
    implementations = _keep_specified_implementations(
        impl_seed_class, all_implementations)

    unimplemented_interfaces = _check_interfaces_implemented(
        impl_seed_class, implementations)

    if len(unimplemented_interfaces) > 0:
        interface_names = ", ".join(unimplemented_interfaces)
        raise ValueError(f"Unimplemented interfaces: {interface_names}")

    implementations_loaded = _load_implementations(implementations)

    class FrankensteinClass(impl_seed_class):
        pass

    _add_methods(FrankensteinClass, implementations_loaded)
    setattr(FrankensteinClass, "__init__", impl_seed_class.__init__)
    _update_abstractmethods(FrankensteinClass)
    FrankensteinClass.__name__ = impl_seed_class.__name__

    return FrankensteinClass, implementations_loaded

def compose_instance(impl_seed_class, init_args, impl_overrides=None):
    """
    Build an instance of a FrankensteinClass ... see compose_class()
    """

    if impl_overrides == None:
        impl_overrides = {}

    frankenstein_class, implementations = compose_class(
        impl_seed_class, impl_overrides)

    # It's alive ... https://www.youtube.com/watch?v=1qNeGSJaQ9Q&t=2m24s !!
    # Of course, Frankstein was the doctor's name and not his creation :)

    context = init_args["context"]
    context.set_implementations(implementations)
    return frankenstein_class(**init_args)

def _add_methods(base_class, implementations):
    """
    Apply the implementation methods to the base class as follows ...
    - If the method doesn't exist in the base class then add the method
    - If the method in the base class is abstract then replace the method
    - If the method in the base class is concrete then don't replace it
    This allows subclasses to override abstract methods from superclasses
    """

    for impl_class in implementations.values():
        for impl_attr_name, impl_attr in getmembers(impl_class, isfunction):
            if not impl_attr_name.startswith("__"):
                base_class_attr = getattr(base_class, impl_attr_name, None)
                if base_class_attr is None or _is_abstract(base_class_attr):
                    setattr(base_class, impl_attr_name, impl_attr)

def _check_interfaces_implemented(cls, implementations):
    unimplemented_interfaces = []
    for ancestor in cls.__mro__:
        if _is_interface(ancestor) and  \
            ancestor not in [ABC, Interface, ServiceProtocolInterface, object]:

            if not ancestor.__name__ in implementations:
                unimplemented_interfaces.append(ancestor.__name__)
    return unimplemented_interfaces

def _is_abstract(method):
    return  \
        hasattr(method, "__isabstractmethod__") and method.__isabstractmethod__

def _is_interface(cls):
    all_methods_abstract = True
    methods = getmembers(cls, isfunction)
    for method_name, method in methods:
        if not (hasattr(method, "__isabstractmethod__")  \
                and method.__isabstractmethod__):
            all_methods_abstract = False
            break
    return all_methods_abstract

def _keep_specified_implementations(impl_seed_class, implementations):
    """Keep implementations that correspond to inherited interfaces"""
    specified_impls = {}
    for ancestor in impl_seed_class.__mro__:
        if _is_interface(ancestor) and ancestor.__name__ in implementations:
            specified_impls[ancestor.__name__] =  \
                implementations[ancestor.__name__]
        elif (not _is_interface(ancestor)) and ancestor.__name__ in implementations:
            print(f"Warning: When composing {impl_seed_class}, ignoring parent {ancestor}, because some methods are not abstract")
    return specified_impls

def _load_implementations(implementations):
    """
    For a dictionary of implementations (aliases and pathnames),
    load the specified module and return a dictionary containing ...
      Key:   Interface implementation alias (same as the override alias)
      Value: Class reference
    """

    implementations_loaded = {}
    for impl_alias, impl_path in implementations.items():
        if not isclass(impl_path):
            module_name, _, class_name = impl_path.rpartition(".")
            if module_name == "":
                raise ValueError(
                    f"For {impl_alias} interface, the implementation "
                    f"module name must be provided: {impl_path}")
            module = load_module(module_name)
            impl_class = getattr(module, class_name)
        else:
            impl_class = impl_path
        implementations_loaded[impl_alias] = impl_class
    return implementations_loaded

def _update_abstractmethods(cls):
    """
    ! This method first appears in Python 3.10.4
    ! Copied from https://github.com/python/cpython/blob/3.10/Lib/abc.py

    Recalculate the set of abstract methods of an abstract class.

    If a class has had one of its abstract methods implemented after the
    class was created, the method will not be considered implemented until
    this function is called. Alternatively, if a new abstract method has been
    added to the class, it will only be considered an abstract method of the
    class after this function is called.
    This function should be called before any use is made of the class,
    usually in class decorators that add methods to the subject class.
    Returns cls, to allow usage as a class decorator.
    If cls is not an instance of ABC, does nothing.
    """
    if not hasattr(cls, '__abstractmethods__'):
        # We check for __abstractmethods__ here because cls might by a C
        # implementation or a python implementation (especially during
        # testing), and we want to handle both cases.
        return cls

    abstracts = set()
    # Check the existing abstract methods of the ancestors and
    # keep only the ones that are not implemented
    for scls in cls.__bases__:
        for name in getattr(scls, '__abstractmethods__', ()):
            value = getattr(cls, name, None)
            if getattr(value, "__isabstractmethod__", False):
                abstracts.add(name)
    # Also add any other newly added abstract methods.
    for name, value in cls.__dict__.items():
        if getattr(value, "__isabstractmethod__", False):
            abstracts.add(name)
    cls.__abstractmethods__ = frozenset(abstracts)
    return
