# Description
# ~~~~~~~~~~~
# Hooks enable developers to flexibly extend the Aiko Services framework.
# A Hook is created within the framework and used by a third-party developer.
# For a given framework component ... the Hooks are a class variable
#
# Create a Hook within the framework ...
# - A component is composed with the "Hooks" interface
# - A new Hook is created via "self.add_hook(hook_name)"
# - Invoke "run_hook(hook_name)", which calls all provided "hook_functions()"
#
# Third-party developer extends the framework Hook ...
# - Provides "hook_function(hook_name, component, logger, variables)"
# - Add the hook function via "self.add_hook_handler(hook_name, hook_function)
#
# Resource costs
# ~~~~~~~~~~~~~~
# CPU time used by run_hook() ...
# - 0x hook_handlers:  1 microsecond
# - 1x hook_handlers: 14 microseconds
# - 2x hook_handlers: 24 microseconds
#
# Usage: framework
# ~~~~~~~~~~~~~~~~
# NAME = "component.hook:version"  # if hook variables change, then bump version
#
# class HookTest(aiko.Actor):
#     def __init__(self, context):
#         self.add_hook(NAME)
#
#     def method_with_a_hook(self):
#         self.run_hook(NAME, lambda: {"variable", variable_value})
#
# Usage: third-party developer
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# add_hook_handler(NAME, self.hook_function)
#
# def hook_function(self, hook_name, component, logger, variables):
#     logger.debug(f"{hook_name} invoked for {component} with {variables}")
#
# Test
# ~~~~
# pytest ../tests/unit/test_hook.py
#
# To Do
# ~~~~~
# - Provide Hook for PipelineDefinition
# - Refactor Metrics to use Hooks for capturing CPU time and beyond !

from abc import abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field, is_dataclass
from typing import Any, Callable, Dict

from aiko_services.main import *

__all__ = ["DEFAULT_HOOK", "Hook", "Hooks"]

ENABLED_DEFAULT = False

# --------------------------------------------------------------------------- #

@dataclass
class HookHandler:
    function: Callable[[object, object, dict], None]
    options: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.hash = hash(self.function) + hash(repr(self.options))

@dataclass
class Hook:
    name: str  # "component_name.hook_name:version"
    enabled: bool = ENABLED_DEFAULT
    handlers: OrderedDict[str, HookHandler] = field(default_factory=OrderedDict)
    invoked: int = 0

class Hooks:
    Interface.default("Hooks", "aiko_services.main.hook.HooksImpl")

    @abstractmethod
    def add_hook(self, hook_name):
        pass

    @abstractmethod
    def add_hook_handler(self, hook_name, hook_function, hook_options=None):
        pass

    @abstractmethod
    def get_hook(self, hook_name):
        pass

    @abstractmethod
    def get_hooks(self):
        pass

    @abstractmethod
    def remove_hook(self, hook_name):
        pass

    @abstractmethod
    def remove_hook_handler(self, hook_name, hook_function):
        pass

    @abstractmethod
    def run_hook(self, hook_name):
        pass

    @abstractmethod
    def set_hook_enabled(self, hook_name, enabled_flag):
        pass

class HooksImpl(Hooks):
    hooks: Dict[str, Hook] = {}

    def add_hook(self, hook_name):
        if not self.get_hook(hook_name):
            self.get_hooks()[hook_name] = Hook(hook_name)

    def add_hook_handler(self, hook_name, hook_function, hook_options=None):
        hook = self.get_hook(hook_name)
        if not hook:
            raise RuntimeError(f"Hook {hook_name}: Does not exist")
        hook_options = hook_options if hook_options else {}
        hook_handler = HookHandler(hook_function, hook_options)
        hook.handlers[hook_handler.hash] = hook_handler
        hook.enabled = len(hook.handlers) > 0

    def get_hook(self, hook_name):
        if hook_name in HooksImpl.hooks:
            return HooksImpl.hooks[hook_name]
        else:
            return None

    def get_hooks(self):
        return HooksImpl.hooks

    def remove_hook(self, hook_name):
        hook = self.get_hook(hook_name)
        if not hook:
            raise RuntimeError(f"Hook {hook_name}: Does not exist")
        del self.get_hooks()[hook_name]

    def remove_hook_handler(self, hook_name, hook_function, hook_options=None):
        hook = self.get_hook(hook_name)
        if not hook:
            raise RuntimeError(f"Hook {hook_name}: Does not exist")
        hook_options = hook_options if hook_options else {}
        hook_handler = HookHandler(hook_function, hook_options)
        del hook.handlers[hook_handler.hash]
        hook.enabled = len(hook.handlers) > 0

    def run_hook(self, hook_name, variables=None):
        hook = self.get_hook(hook_name)
        if hook and hook.enabled:
            component = self
            logger = self.logger if hasattr(component, "logger") else None
            if not variables:
                variables = {}
            elif callable(variables):
                variables = variables()

            hook.invoked += 1
            for hook_handler in hook.handlers.values():
                options = hook_handler.options
                hook_handler.function(
                    hook_name, component, logger, variables, options)

    def set_hook_enabled(self, hook_name, enabled_flag):
        hook = self.get_hook(hook_name)
        if hook:
            hook.enabled = enabled_flag

# --------------------------------------------------------------------------- #

def hook_function(hook_name, component, logger, variables, hook_options=None):
    show = variables
    if hook_options and "show" in hook_options:
        show = {}
        for name_path in hook_options["show"]:
            names = name_path.split(".")
            value = variables

            for name in names:
                if isinstance(value, dict):
                    value = value[name]
                elif is_dataclass(value):
                    value = getattr(value, name, None)

            show[name] = value
    logger.info(f"Hook {hook_name}: {show}")

DEFAULT_HOOK = hook_function

# --------------------------------------------------------------------------- #
