# Example
# ~~~~~~~
# from aiko_services.main.proxy_play import Proxy, ProxyExample
# class C():
#     def f(self, argument):
#         print(f"C.f({argument})")
# proxy_C = proxy.Proxy(C())
# proxy_C.f(1)
# --> C.f(1)
#
# intercepted_C = proxy.ProxyExample(C())
# intercepted_C.f(1, "2", 3, a=4, b=5)
# --> Intercepted: name: f, args: (1, "2", 3), kwargs: {"a": 4, "b": 5}
#
# Issues
# ~~~~~~
# Proxying user-types should work okay
# However, proxying builtin objects (ints, floats, lists, etc),
# has some limitation and inconsistencies, imposed by the interpreter
#
# Currently, can't use Proxy object as a dictionary key (rare case)
#
#   class A(object):
#       pass
#   p = proxy.Proxy(A)
#   {p: "asdasd"}
#   --> TypeError: unhashable type: "Proxy(type)"
#
# Resources
# ~~~~~~~~~
# Covered by https://creativecommons.org/licenses/by-sa/3.0
# - https://code.activestate.com/help/terms
# - https://code.activestate.com/recipes/496741-object-proxying
# - https://code.activestate.com/recipes/578014-lazy-load-object-proxying

from inspect import isfunction

__all__ = ["Proxy"]


class Proxy(object):
    intercept = None  # TODO: More flexible, if this isn't a class variable ?

    __slots__ = ["_obj", "__weakref__"]

    def __init__(self, obj):
        object.__setattr__(self, "_obj", obj)

    def __delattr__(self, name):
        delattr(object.__getattribute__(self, "_obj"), name)

    def __getattribute__(self, name):
        return getattr(object.__getattribute__(self, "_obj"), name)

    def __hash__(self):
        return hash(object.__getattribute__(self, "_obj"))

    def __nonzero__(self):
        return bool(object.__getattribute__(self, "_obj"))

    def __repr__(self):
        return repr(object.__getattribute__(self, "_obj"))

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_obj"), name, value)

    def __str__(self):
        return str(object.__getattribute__(self, "_obj"))
    #   return unicode(self).encode("utf-8")

#   def __unicode__(self):
#       return unicode(object.__getattribute__(self, "_obj"))

    _methods_to_wrap = [
        "__abs__", "__add__", "__and__", "__call__", "__cmp__", "__coerce__",
        "__contains__", "__delitem__", "__delslice__", "__div__", "__divmod__",
        "__eq__", "__float__", "__floordiv__", "__ge__", "__getitem__",
        "__getslice__", "__gt__", "__hex__", "__iadd__", "__iand__",
        "__idiv__", "__idivmod__", "__ifloordiv__", "__ilshift__", "__imod__",
        "__imul__", "__int__", "__invert__", "__ior__", "__ipow__",
        "__irshift__", "__isub__", "__iter__", "__itruediv__", "__ixor__",
        "__le__", "__len__", "__long__", "__lshift__", "__lt__", "__mod__",
        "__mul__", "__ne__", "__neg__", "__oct__", "__or__", "__pos__",
        "__pow__", "__radd__", "__rand__", "__rdiv__", "__rdivmod__",
        "__reduce__", "__reduce_ex__", "__repr__", "__reversed__",
        "__rfloorfiv__", "__rlshift__", "__rmod__", "__rmul__", "__ror__",
        "__rpow__", "__rrshift__", "__rshift__", "__rsub__", "__rtruediv__",
        "__rxor__", "__setitem__", "__setslice__", "__sub__", "__truediv__",
        "__xor__", "next"
    ]

    @classmethod
    def _create_class_proxy(cls, user_class):
        """Creates a proxy for the given class"""

        def make_method(name):
            def method(self, *args, **kwargs):
                user_instance = object.__getattribute__(self, "_obj")
                return getattr(user_instance, name)(*args, **kwargs)
            return method

        namespace = {}
        for name in cls._methods_to_wrap:
            if hasattr(user_class, name):
                namespace[name] = make_method(name)
        return type(f"{cls.__name__}({user_class.__name__})", (cls,), namespace)

    @classmethod
    def _update_instance_intercept(cls, user_class, user_instance):
        """For proxy instance, every user defined function is intercepted"""

        def make_method(name):
            def method(*args, **kwargs):
                return cls.intercept(name, *args, **kwargs)
            return method

        if cls.intercept:
            for name in dir(user_instance):
                if isfunction(getattr(user_class, name)):  # user defined ?
                    user_instance.__setattr__(name, make_method(name))

    def __new__(cls, obj, *args, **kwargs):
        """
        Creates an proxy instance referencing `obj`.
        (obj, *args, **kwargs) are passed to this class' __init__,
        so deriving classes can define an __init__ method of their own.
        Note: _class_proxy_cache is unique per deriving class
        (each deriving class must hold its own cache)
        """
        user_class = obj.__class__
        try:
            cache = cls.__dict__["_class_proxy_cache"]
        except KeyError:
            cls._class_proxy_cache = cache = {}
        try:
            theclass = cache[user_class]
        except KeyError:
            cache[user_class] = theclass = cls._create_class_proxy(user_class)

        user_instance = object.__new__(theclass)
        theclass.__init__(user_instance, obj, *args, **kwargs)
        cls._update_instance_intercept(user_class, user_instance)
        return user_instance


class ProxyExample(Proxy):
    def intercepted(name, *args, **kwargs):
        print(f"Intercepted: name: {name}, args: {args}, kwargs: {kwargs}")

    intercept = intercepted
