# Example
# ~~~~~~~
# from aiko_services.proxy import ProxyAllMethods, proxy_trace, Example
# example_proxy = ProxyAllMethods("Example", Example("v0"), proxy_trace)
# example_proxy.function_0("value_0", argument_1="value_1")
#
# Resources
# ~~~~~~~~~
# Python wrapt package
# - https://wrapt.readthedocs.io/en/latest/wrappers.html
#
# To Do
# ~~~~~
# - Proxy specified functions, see "MATCH_STRING" (below)
#   - Use [Interface] to specific which functions to match
#   - Wildcard list of functions to match
#   - Wildcard list of functions to not match
#
# - Support multiple proxy_functions per Proxy object
#   - __init__(..., proxy_function) --> __init__(..., [proxy_function])
#
# - Make @proxy and @remote_proxy decorators
#
# - Aspect Oriented Programming ...
#   - Intercept: logging (flight recorder, tracing for diagnosis)
#   - Intercept: remote function call
#   - Intercept: security access
#   - Intercept: timing (performance)

from inspect import getmembers, ismethod
import wrapt

__all__ = ["ProxyAllMethods", "proxy_trace"]

class ProxyAllMethods(wrapt.ObjectProxy):
    def __init__(
        self, proxy_name, actual_object, proxy_function,
        ignore="_"):

        super(ProxyAllMethods, self).__init__(actual_object)

        def make_closure(actual_function):
            def closure(*args, **kwargs):
                return proxy_function(
                    proxy_name, actual_object, actual_function,
                    *args, **kwargs
                )
            return closure

        for name, actual_function in getmembers(actual_object, ismethod):
            if ignore is None or not name.startswith(ignore):
                setattr(self, name, make_closure(actual_function))

    def __repr__(self):
        return f"[{self.__module__}.{type(self).__name__} " \
               f"object at {hex(id(self))}]"

def proxy_trace(proxy_name, actual_object, actual_function, *args, **kwargs):
      function_name = actual_function.__name__
      print(f"### Enter: {proxy_name}.{function_name} {args} {kwargs} ###")
      try:
          return actual_function(*args, **kwargs)
      finally:
          print(f"### Exit:  {proxy_name}.{function_name} ###")

class Example:
    def __init__(self, argument_0):
        print(f"           Example.__init__({argument_0})")

    def function_0(self, argument_0, argument_1=None):
        print(f"           Example.function_0({argument_0}, {argument_1})")
        return f"          {argument_0} {argument_1}"

# TODO: @proxy Decorator returns an instance of the "actual_class"
#       Need a factory "actual_class" that creates proxy instances !
#
# def proxy(proxy_function=proxy_trace, *args, **kwargs):
#     def new_function(actual_class):
#         proxy_name = actual_class.__name__
#         instance = actual_class()
#         proxy_object = ProxyAllMethods(proxy_name, instance, proxy_function)
#         return proxy_object
#     return new_function
#
#   from aiko_services.proxy import proxy, proxy_trace
#   @proxy
#   class C:
#       def f(self, argument_0):
#           print(f"C.f({argument_0})")
