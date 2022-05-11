# To Do
# ~~~~~
# - Implement disconnect() and support for "with" statement ?
# - Implement subscribe() and track subscriptions for reconnecting
# - Implement statistics measurements, e.g performance

import abc
from typing import Any

__all__ = ["Message"]

class Message(abc.ABC):
    def __init__(
        self,
        message_handler: Any = None,
        topics_subscribe: Any = None,
        lwt_topic: str = None,
        lwt_payload: str =None,
        lwt_retain: bool = False
        ) -> None:

        pass

    def publish(
        self: Any,
        topic: Any,
        payload: Any,
        retain: bool = False,
        wait: bool = False
        ) -> None:

        raise NotImplementedError("Message.publish()")

    def set_last_will_and_testament(
        self: Any,
        lwt_topic: str = None,
        lwt_retain: bool = False
        ) -> None:

        raise NotImplementedError("Message.set_last_will_and_testament()")
