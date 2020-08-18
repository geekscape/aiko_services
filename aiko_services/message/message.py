# To Do
# ~~~~~
# - Add close(), subscribe()
# - Implement statistics measurements, e.g performance
# - Implement destructor ?

import abc
from typing import Any

__all__ = ["Message"]


class Message(abc.ABC):
    def __init__(
        self, message_handler: Any = None, topics_subscribe: Any = None, lwt_topic: str = None, lwt_retain: bool = False
    ) -> None:
        pass

    def loop_start(self: Any) -> None:
        raise NotImplementedError("Message.loop_start()")

    def publish(self: Any, topic: Any, payload: Any, wait: bool = False) -> None:
        raise NotImplementedError("Message.publish()")
