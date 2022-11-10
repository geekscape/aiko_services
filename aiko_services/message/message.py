# To Do
# ~~~~~
# - Implement disconnect() and support for "with" statement ?
# - Implement statistics measurements, e.g performance

import abc
from typing import Any, List

__all__ = ["Message"]

class Message(abc.ABC):
    def __init__(
        self: Any,
        message_handler: Any = None,
        topics_subscribe: Any = None,
        topic_lwt: str = None,
        payload_lwt: str = None,
        retain_lwt: bool = False
        ) -> None:

        pass

    def publish(
        self: Any,
        topic: str,
        payload: Any,
        retain: bool = False,
        wait: bool = False
        ) -> None:

        raise NotImplementedError("Message.publish()")

    def set_last_will_and_testament(
        self: Any,
        topic_lwt: str = None,
        payload_lwt: str = "(absent)",
        retain_lwt: bool = False
        ) -> None:

        raise NotImplementedError("Message.set_last_will_and_testament()")

    def subscribe(self: Any, topics: Any) -> None:
        raise NotImplementedError("Message.subscribe()")

    def unsubscribe(self: Any, topics: Any) -> None:
        raise NotImplementedError("Message.unsubscribe()")
