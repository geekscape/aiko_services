# Used when there is no connected transport layer, e.g no MQTT !

from typing import Any

from aiko_services.main.message import *

__all__ = ["Castaway"]

class Castaway(Message):
    def __init__(
        self: Any,
        message_handler: Any = None,
        topics_subscribe: Any = None,
        topic_lwt: str = None,
        payload_lwt:str = None,
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

        pass

    def set_last_will_and_testament(
        self: Any,
        topic_lwt: str = None,
        payload_lwt: str = "(absent)",
        retain_lwt: bool = False
        ) -> None:

        pass

    def subscribe(self: Any, topics: Any) -> None:
        pass

    def unsubscribe(self: Any, topics: Any, remove=True) -> None:
        pass

# Wilson !
