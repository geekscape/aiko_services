# Usage
# ~~~~~
# from aiko_services.main.utilities import *
#
# with ContextManager({}) as context:
#     print(context.aiko, context.message)
#
# context = ContextManager({})
# print(context.aiko)
# context.aiko["a"] = 1
#
# context = get_context()
# print(context.aiko)
#
# To Do
# ~~~~~
# - Thread local context example

# This import allows us to specify the class itself as return type,
# e.g def activate(self) -> ContextManager

from typing import Any

__all__ = ["ContextManager", "get_context"]

_CONTEXT = None


class ContextManager:
    def __init__(self, aiko: Any = None, message: Any = None) -> None:
        self.aiko = aiko
        self.message = message
        self.activate()

    def activate(self) -> "ContextManager":
        # pylint: disable=global-statement
        global _CONTEXT
        _CONTEXT = self
        return self

    def __enter__(self) -> "ContextManager":
        return self.activate()

    def __exit__(self, *args: Any) -> None:
        pass


def get_context() -> Any:
    # pylint: disable=global-statement
    global _CONTEXT
    return _CONTEXT
