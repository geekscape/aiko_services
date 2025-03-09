# Investigate Behaviour Trees !
#
# For simple operational FSMs, name the machine states using descriptive
# adjectives that directly correspond to the state transition operations,
# i.e use the past tense of the transitive verb for each state transition
# operation, e.g pending, running, success, error

import os
import traceback
from transitions import Machine
from transitions.core import MachineError

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = ["StateMachineOld"]

_AIKO_LOG_LEVEL_STATE = os.environ.get("AIKO_LOG_LEVEL_STATE", "INFO")
_LOGGER = aiko.logger(__name__, log_level=_AIKO_LOG_LEVEL_STATE)

class StateMachineOld(object):
    def __init__(self, model):
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
            if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
                _LOGGER.debug(f"transition start: state={self.get_state()}, action={action}")
            self.state_machine.dispatch(action, parameters=parameters)
            if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
                _LOGGER.debug(f"transition finish: state={self.get_state()}")

        except AttributeError:
            failure = True
            known_action = next((item for item in self.model.transitions if item["trigger"] == action), False)
            if known_action:
                _LOGGER.critical(f"exception: {traceback.format_exc()}")
            else:
                _LOGGER.critical(f"unknown action: {action}")

        except MachineError as machine_error:
            failure = True
            _LOGGER.critical(machine_error)

        except Exception as exception:
            failure = True
            _LOGGER.critical(f"failure during transition: Exception: {traceback.format_exc()}")

        if failure:
            raise SystemExit(f"Fatal error: StateMachineOld: state={self.get_state()}, action={action}")
