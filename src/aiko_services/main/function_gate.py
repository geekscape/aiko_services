# Description
# ~~~~~~~~~~~
# Which functions a Service accepts from the message bus: the FunctionGate
# aspect (P12, ADR-023 deny by default).
#
# An aspect, in the way that "Hooks" is an aspect of Service: its own
# Interface, its own default Implementation, and one "context.call_init()"
# in the composed Implementation.  "Actor" composes it, so every Actor,
# PipelineElement, Pipeline and Agent has one, and any other Implementation
# under development can compose it as well.
#
# The default allows every function, which is what every Actor did before
# this aspect existed, so composing the aspect changes nothing by itself.
# An Implementation that wants deny by default gives the gate a list ...
#
#     class ExampleImpl(Example):
#         def __init__(self, context):
#             context.call_init(self, "FunctionGate", context,
#                 functions=interface_functions(Example))
#             context.call_init(self, "Actor", context)
#
# "call_init()" is idempotent, so an Implementation configures the aspect
# before the Actor initializes it, and the Actor then leaves it alone.
#
# deny_function() is pure: a function of the name and the parameters, with
# no logging and no state of its own.  So a policy is tested with no Actor,
# no composition and no message broker.  The Actor reports a denial, because
# the Actor owns the logger and the shared state.
#
# Usage
# ~~~~~
# from aiko_services.main import *
#
# FUNCTIONS = interface_functions(Example)   # the Interface's own functions
# gate = compose_instance(FunctionGateImpl, {"context": Context(),
#     "functions": FUNCTIONS})
# gate.deny_function("example", [])      # None: allowed
# gate.deny_function("exit", [])         # "function": denied
#
# To Do
# ~~~~~
# - An Implementation that reads its policy from the HyperSpace, so that a
#   deployment changes what it allows with no code change
# - CC8 (Aiko Services Security) may replace this Implementation with the
#   general security model.  The Interface is the seam that lets it

from abc import abstractmethod

from aiko_services.main.context import Interface

__all__ = [
    "DENY_FUNCTION", "DENY_PARAMETERS", "DENY_PARSE",
    "FunctionGate", "FunctionGateImpl", "interface_functions"
]

DENY_FUNCTION = "function"        # the function is not in the allow list
DENY_PARAMETERS = "parameters"    # the parameters are not a list
DENY_PARSE = "parse"              # the payload did not parse

# The two framework functions that an Actor does accept from the bus.
# Everything else the framework declares stays off it (ADR-025 decision 1)
FUNCTIONS_FRAMEWORK = ("set_log_level", "stop")

def _functions_framework():
    """The function names that Actor and Service declare.  Read lazily,
    because "actor.py" imports this module, not the other way around"""

    from aiko_services.main.actor import Actor
    from aiko_services.main.service import Service

    return {name
        for interface in (Actor, Service)
        for name, member in vars(interface).items()
        if getattr(member, "__isabstractmethod__", False)}

def interface_functions(*interfaces, extra=FUNCTIONS_FRAMEWORK):
    """The abstract function names declared by each Interface, plus "extra".
    Deriving the allow list from the Interfaces means that the list and the
    contract cannot drift apart.

    What Actor and Service declare is removed, so that "run" and the
    message handlers can never reach the bus by accident (ADR-025 decision
    1).  "extra" is applied last, so it decides its own names"""

    names = {name
        for interface in interfaces
        for name, member in vars(interface).items()
        if getattr(member, "__isabstractmethod__", False)
        and not name.startswith("_")}
    return frozenset((names - _functions_framework()) | set(extra))

class FunctionGate(Interface):
    """
    Which functions a Service accepts from the message bus (P12, ADR-023).
    An aspect: "Actor" composes it, and any other Implementation may do the
    same.  Local API only -- the gate itself does not cross the wire
    """
    Interface.default("FunctionGate",
        "aiko_services.main.function_gate.FunctionGateImpl")

    @abstractmethod
    def deny_function(self, name, parameters):
        """None when "name" may be called with "parameters".  Otherwise a
        short reason token, for the log and for "last_error" in the shared
        state.  Pure: no logging, no state change, no message published"""

class FunctionGateImpl(FunctionGate):
    """
    Allow every function, or allow only the functions in a list.

    "functions" is None by default, which allows every function: what each
    Actor did before this aspect existed, and what each Actor that does not
    configure the aspect still does.  A list of names denies every function
    that is not in the list (P12, deny by default)
    """

    def __init__(self, context, functions=None, **_):
        self.functions = None if functions is None else frozenset(functions)

    def deny_function(self, name, parameters):
        if not isinstance(parameters, list):
            return DENY_PARAMETERS
        if self.functions is None:
            return None                       # no list: allow everything
        return None if name in self.functions else DENY_FUNCTION

# --------------------------------------------------------------------------- #
