import traceback
from transitions import Machine
from transitions.core import MachineError

from aiko_services.utilities import *

__all__ = ["StateMachine"]

class StateMachine(object):
    def __init__(self, model):
        self.logger = logger.get_logger(__name__)  # don't use aiko.logger
        self.model = model
        self.state_machine = Machine(
            model=self.model,
            states=model.states,
            transitions=model.transitions,
            initial="start",
            send_event=True
        )

    def get_state(self):
        return self.model.state

    def transition(self, action, parameters):
        failure = False
        try:
            self.logger.debug(f"transition start: state={self.get_state()}, action={action}")
            self.state_machine.dispatch(action, parameters=parameters)
            self.logger.debug(f"transition finish: state={self.get_state()}")

        except AttributeError:
            failure = True
            known_action = next((item for item in self.model.transitions if item["trigger"] == action), False)
            if known_action:
                self.logger.critical(f"exception: {traceback.format_exc()}")
            else:
                self.logger.critical(f"unknown action: {action}")

        except MachineError as machine_error:
            failure = True
            self.logger.critical(machine_error)

        except Exception as exception:
            failure = True
            self.logger.critical(f"failure during transition: Exception: {traceback.format_exc()}")

        if failure:
            raise SystemExit(f"Fatal error: StateMachine: state={self.get_state()}, action={action}")
