# Example
# ~~~~~~~
# from aiko_services import *
# test_actor = actor.TestActor("TestActor")
# test_actor.initialize()
# event.loop()
#
# from aiko_services import *
# test_actor = actor.TestActor("TestActor")
# test_actor_proxy = proxy.ProxyAllMethods("ProxyTest", test_actor, Actor.proxy_post_message)
# test_actor_proxy.initialize()
# event.loop()
#
# Design
# ~~~~~~
# Is a LifeCycleClient (can be standalone)
# Has [Leases], MailBox (ordered, priority) --> Messages
#
# Message --> Actor --> Mailbox --> Event loop --> Message (optional)
# StateChange external --> Message --> Actor --> Mailbox --> Event loop
# StateChange internal --> Priority Mailbox --> Event loop
#
# To Do
# ~~~~~
# - State Machine ...
#   - Turn "self.running" into "self.state"
#   - Turn "self._is_running()" into "self._get_state()"
#   - Stop Actor by changing "self.state" to "STOP"
#   - Hard terminate Actor using "self._terminate()"
#
# - function() > Remote Actor >  Message > Mailbox > Event loop > function()
# - Wrapper for function tracing (enter:count, exit:time+average)
# - Optionally add Leases to Messages ... what does this mean ?
#   - Lease UUID used later: complete, delete, update (extend)
#   - Message response required ?
#   - Hold onto resources, e.g entry in a list / dictionary ?
#   - LifeCycle: still alive (state change)
#
# - Carefully rename all "function" to either "function" or "method"
# - Consider whether to make Actor an interface (with an implementation)
# - Actor(): "__init__()": Add "uuid" to "name" (for non-singletons) ?
#
# - Distributed: single process, pyro5, MQTT, Ray
#   - As an AikoService
# - Eventual consistency: add, update (dictionary only), remove
# - Logging: Distributed collection and distribution --> Kafka ?
# - Multiple threads and multithreading support
# - State Machine

from aiko_services import *
from aiko_services.utilities import *

__all__ = ["Actor", "TestActor"]

_LOGGER = aiko.logger(__name__)

class LifeCycleClient:  # Interface
    pass

class Message:
    def __init__(self, target_object, command, arguments, target_function=None):
        self.target_object = target_object
        self.command = command
        self.arguments = arguments
        self.target_function = target_function

    def __repr__(self):
        return f"Message: {self.command}({str(self.arguments)[1:-1]})"

    def invoke(self):
    #   _LOGGER.debug(f"### Invoke: {self} ###")
        target_function = self.target_function
        if not target_function:
            try:
                target_function = self.target_object.__getattribute__(
                    self.command)
            except AttributeError:
                pass

        diagnostic = None
        if target_function is None:
            diagnostic = f"{self}: Function not found in: {self.target_object}"
        else:
            if callable(target_function):
                try:
                    target_function(*self.arguments)
                except TypeError as type_error:
                    diagnostic = f"{self}: {type_error}"
            else:
                diagnostic = f"{self}: isn't callable"
        if diagnostic:
            _LOGGER.error(diagnostic)
        #   raise RuntimeError(diagnostic)

class Topic:
    # Application topics
    IN = "in"
    OUT = "out"

    # Framework topics
    CONTROL = "control"
    STATE = "state"

    topics = [CONTROL, STATE, IN, OUT]

    def __init__(self, topic_name):  # TODO: implement user defined topics
        self.topic_name = topic_name

class Actor(LifeCycleClient):  # Base class
    @classmethod
    def proxy_post_message(
        cls, proxy_name, actual_object, actual_function, *args, **kwargs):

        command = actual_function.__name__
        control_command = command.startswith(f"{Topic.CONTROL}_")
        topic = Topic.CONTROL if control_command else Topic.IN

        actual_object._post_message(
            topic, command, args, target_function=actual_function)

    def __init__(self, actor_name):
        self.actor_name = actor_name
        self.running = False
        # First mailbox added has priority handling for all posted messages
        for topic in [Topic.CONTROL, Topic.IN]:
            mailbox_name = self._actor_mailbox_name(topic)
            event.add_mailbox_handler(self._mailbox_handler, mailbox_name)

    def _actor_mailbox_name(self, topic):
        return f"{self.actor_name}/{topic}"

    def _is_running(self):
        return self.running

    def _mailbox_handler(self, topic, message, time_posted):
        message.invoke()

    def _run(self):
        self.running = True
        event.loop()
        self.running = False

    def _post_message(self, topic, command, args, target_function=None):
        target_object = self
        message = Message(
            target_object, command, args, target_function=target_function)
        event.mailbox_put(self._actor_mailbox_name(topic), message)

    def __repr__(self):
        return f"[{self.__module__}.{type(self).__name__} " \
               f"object at {hex(id(self))}]"

    def _stop(self):
        event.terminate()

class TestActor(Actor):  # class
    def __init__(self, actor_name):
        super().__init__(actor_name)
        self.test_count = None

    def initialize(self):
        self.control_test(0)
        self.test(1)
        self.test(2)
        self.control_test(3)
        self.test_count = 4

    def _mailbox_handler(self, topic, message, time_posted):
        print(f"Actor.handle(): {time_posted%100:07.3f}, " \
              f"{topic}: {message.command}{message.arguments}")
        super()._mailbox_handler(topic, message, time_posted)

        if topic == self._actor_mailbox_name(Topic.IN):
            if self.test_count and self.test_count <= 5:
                self.control_test(self.test_count)
                self.test_count += 1

    def control_test(self, value):
        print(f"TestActor: control_test({value})")

    def test(self, value):
        print(f"TestActor: test({value})")
