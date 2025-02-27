# Description
# ~~~~~~~~~~~
# Distributed Service based on the Actor Nodel
# - https://en.wikipedia.org/wiki/Actor_model
#
# Example 1
# ~~~~~~~~~
# from abc import abstractmethod
# from aiko_services.main import *
#
# class ActorTest(Actor):
#     Interface.default("ActorTest", "__main__.ActorTestImpl")
#
#     @abstractmethod
#     def test(self):
#         pass
#
# class ActorTestImpl(ActorTest):
#     def __init__(self, context):
#         context.get_implementation("Actor").__init__(self, context)
#
#     def test(self):
#         print("ActorTestImpl.test() invoked")
#
# protocol = f"{SERVICE_PROTOCOL_AIKO}/actor_test:0"
# init_args = actor_args("actor_test", protocol=protocol)
# actor_test = compose_instance(ActorTestImpl, init_args)
# actor_test.test()
# aiko.process.run()
#
# Example 2
# ~~~~~~~~~
# from aiko_services.main import *
# actor_test = actor.ActorTest("ActorTest")
# actor_test.initialize()
# aiko.process.run()
#
# Example 3
# ~~~~~~~~~
# from aiko_services.main import *
# actor_test = actor.ActorTest("ActorTest")
# actor_test_proxy = proxy.ProxyAllMethods(
#    "ProxyTest", actor_test, Actor.proxy_post_message)
# actor_test_proxy.initialize()
# aiko.process.run()
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
# - If default ActorImpl is too heavy, then create lightweight ActorCoreImpl
#
# * Provide "priority" mailbox for internal requirements, e.g
#   - If an Exception is raised during initialization / setup,
#     then post a "(raise_exception exception)" message to the mailbox
#
# * Support multiple Actors per process, e.g Pipeline --> PipelineElements
#   * Specify framework generated unique Actor name as ...
#         Fully Qualified Name: (actortype namespace/host/pid/sid)
#         Short Name: actortype/pid/sid  # for human input and display
#     - Allow multiple Actors in the same process to share ECConsumer instance
#       - Must support Pipeline --> PipelineElements in the same process !
#         All would share ECConsumers for ServiceDiscovery and LifeCycleClient
#
# - State Machine ...
#   - Consolidate  self.share["lifecycle"] and self.share["running"]
#     - into self.share["state"] ?
#   - Turn "self.is_running()" into "self.get_state()"
#   - Stop Actor by changing "self.share" to "STOP"
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

from abc import abstractmethod
import os
import queue
import time
import traceback

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = [
    "Actor", "ActorImpl", "ActorTest", "ActorTestImpl", "ActorTopic",
    "ACTOR_HOOK_MESSAGE_CALL", "ACTOR_HOOK_MESSAGE_IN"
]

_AIKO_LOG_LEVEL_ACTOR = os.environ.get("AIKO_LOG_LEVEL_ACTOR", "INFO")
_LOGGER = aiko.logger(__name__, log_level=_AIKO_LOG_LEVEL_ACTOR)

ACTOR_HOOK_MESSAGE_CALL = "actor.message_call:"
_ACTOR_HOOK_MESSAGE_CALL = ACTOR_HOOK_MESSAGE_CALL+"0"
ACTOR_HOOK_MESSAGE_IN = "actor.message_in:"
_ACTOR_HOOK_MESSAGE_IN = ACTOR_HOOK_MESSAGE_IN+"0"

class Message:
    def __init__(self, target_object, command, arguments, target_function=None):
        self.target_object = target_object
        self.command = command
        self.arguments = arguments
        self.target_function = target_function

    def __repr__(self):
        return f"Message: {self.command}({str(self.arguments)[1:-1]})"

    def invoke(self):
        if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
            _LOGGER.debug(f"Message.invoke(): {self}")
        target_function = self.target_function
        if not target_function:
            try:
                target_function = self.target_object.__getattribute__(
                    self.command)
            except AttributeError:
                pass

        diagnostic = None
        stack_traceback = None

        if target_function is None:
            try:
                target_object_name = self.target_object.__class__.__name__
            except Exception:
                target_object_name = str(self.target_object)
            diagnostic = f"{self}: Function not found in: {target_object_name}"
        else:
            if callable(target_function):
            # TODO: Catching all TypeError hides problems in "target_function"
            #       Must only catch TypeError problems in this actor code below
            #       For the specific argument TypeErrors and nothing else
                try:
                    target_function(*self.arguments)
                except TypeError as type_error:
                    diagnostic = f"Message.invoke: {self.command} {self.arguments}"
                    stack_traceback = traceback.format_exc()
            else:
                diagnostic = f"{self}: isn't callable"
        if diagnostic:
            if stack_traceback:
                _LOGGER.error(stack_traceback)
                raise SystemExit(f"SystemExit: actor.py: {diagnostic}")
            else:
                _LOGGER.error(diagnostic)

class ActorTopic:
    # Application topics
    IN = "in"
    OUT = "out"

    # Framework topics
    CONTROL = "control"
    STATE = "state"

    topics = [CONTROL, STATE, IN, OUT]

    def __init__(self, topic_name):  # TODO: Implement user defined topics
        self.topic_name = topic_name

class Actor(Service):
    Interface.default("Actor", "aiko_services.main.actor.ActorImpl")

    @abstractmethod
    def run(self, mqtt_connection_required=True):
        pass

class ActorImpl(Actor):
    @classmethod
    def proxy_post_message(
        cls, proxy_name, actual_object, actual_function, *args, **kwargs):

        command = actual_function.__name__
        control_command = command.startswith(f"{ActorTopic.CONTROL}_")
        topic = ActorTopic.CONTROL if control_command else ActorTopic.IN

        actual_object._post_message(
            topic, command, args, target_function=actual_function)

    def __init__(self, context):
        context.get_implementation("Service").__init__(self, context)
        if not hasattr(self, "logger"):
            self.logger = aiko.logger(context.name)

        self.add_hook(_ACTOR_HOOK_MESSAGE_CALL)
        self.add_hook(_ACTOR_HOOK_MESSAGE_IN)

        self.share = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(self.logger),
            "running": False  # TODO: Consolidate into self.share ?
        }
        self.ec_producer = ECProducer(self, self.share)
        self.ec_producer.add_handler(self.ec_producer_change_handler)

        self.delayed_message_queue = queue.Queue()
        # First mailbox added has priority handling for all posted messages
        for topic in [ActorTopic.CONTROL, ActorTopic.IN]:
            mailbox_name = self._actor_mailbox_name(topic)
            event.add_mailbox_handler(self._mailbox_handler, mailbox_name)
        # TODO: Optionally, binary=True ?
        self.add_message_handler(self._topic_in_handler, self.topic_in)

    def _actor_mailbox_name(self, topic):
        return f"{self.name}/{self.service_id}/{topic}"

    def _mailbox_handler(self, topic, message, time_posted):
        self.run_hook(_ACTOR_HOOK_MESSAGE_CALL, lambda: {
            "topic": topic, "message": message, "time_posted": time_posted})

        message.invoke()

    def _topic_in_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
    #   if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
    #       _LOGGER.debug(
    #           f"{self.name}: topic_in_handler(): {command}:{parameters}"
    #       )
        self._post_message(ActorTopic.IN, command, parameters)

    def _post_message(
        self, topic, command, args, delay=None, target_function=None):

        self.run_hook(_ACTOR_HOOK_MESSAGE_IN, lambda: {
            "topic": topic, "command": command, "args": args,
            "delay": delay, "target_function": target_function})

        target_object = self
        message = Message(
            target_object, command, args, target_function=target_function)

        if not delay:
            event.mailbox_put(self._actor_mailbox_name(topic), message)
        else:
            delay_time = time.monotonic() + delay
            delayed_message = (delay_time, topic, message)
            self.delayed_message_queue.put(delayed_message, block=False)
            if self.delayed_message_queue.qsize() == 1:
                event.add_timer_handler(
                    self._post_delayed_message_handler, delay)

    def _post_delayed_message_handler(self):
        while self.delayed_message_queue.qsize() > 0:
            delayed_message = self.delayed_message_queue.get()
            delayed_time = delayed_message[0]
            topic = delayed_message[1]
            message = delayed_message[2]
            event.mailbox_put(self._actor_mailbox_name(topic), message)
        event.remove_timer_handler(self._post_delayed_message_handler)

    def __repr__(self):
        return f"[{self.__module__}.{type(self).__name__} " \
               f"object at {hex(id(self))}]"

    def ec_producer_change_handler(self, command, item_name, item_value):
    #   if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
    #       _LOGGER.debug(f"ECProducer: {command} {item_name} {item_value}")
        if item_name == "log_level":
            try:
                self.logger.setLevel(str(item_value).upper())
            except ValueError:
                pass

    def is_running(self):
        return self.share["running"]

# TODO: Refactor this method into "service.py"
    def run(self, mqtt_connection_required=True):
        self.share["running"] = True
        try:
            aiko.process.run(mqtt_connection_required=mqtt_connection_required)
        except Exception as exception:
        #   _LOGGER.error(f"Exception caught in {self.__class__.__name__}: {type(exception).__name__}: {exception}")
            _LOGGER.error(traceback.format_exc())
            raise exception
        self.share["running"] = False

    def set_log_level(self, level):  # Override to set subclass _LOGGER level
        pass

class ActorTest(Actor):  # TODO: Move into "../examples/"
    Interface.default("ActorTest", "aiko_services.main.actor.ActorTestImpl")

    __test__ = False  # Stop PyTest from collecting and instantiating this class

    @abstractmethod
    def initialize(self):
        pass

    @abstractmethod
    def control_test(self, value):
        pass

    @abstractmethod
    def test(self, value):
        pass

class ActorTestImpl(ActorTest):  # TODO: Move into "../examples/" showing hooks
    def __init__(self, context):
        context.get_implementation("Actor").__init__(self, context)
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

        if topic == self._actor_mailbox_name(ActorTopic.IN):
            if self.test_count and self.test_count <= 5:
                self.control_test(self.test_count)
                self.test_count += 1

    def control_test(self, value):
        print(f"ActorTest: control_test({value})")

    def test(self, value):
        print(f"ActorTest: test({value})")
