# Usage
# ~~~~~
# pytest [-s] unit/test_hook.py
# pytest [-s] unit/test_hook.py::test_hook
#
# test_hook() performs ...
# - Add Hook used within the Framework "component" code
# - Add HookHandler created by the third-party developer
# - Run Hook --> HookHandlers
# - Remove HookHandler
# - Remove Hook
#
# Where "# by framework" is code inserted into the Aiko Services framework
# Where "# by developer" is code that utilizes that framework hook
#
# To Do
# ~~~~~
# - None, yet !

import aiko_services as aiko

HOOK_NAME = "HookTest.test_hook:0"

class HookTest(aiko.Actor):  # primarily acts as a Framework component
    def __init__(self, context):
        context.get_implementation("Actor").__init__(self, context)

    def hook_check(self):
        hook_count_base = len(self.get_hooks())
        self.variable_0 = 1
        self.variable_1 = "test"

        self.add_hook(HOOK_NAME)                                 # by framework
        hooks = self.get_hooks()
        assert len(hooks) == hook_count_base + 1

        self.add_hook_handler(HOOK_NAME, self.hook_handler)      # by developer
        hook_test = self.get_hook(HOOK_NAME)
        hook_test_handlers = hook_test.handlers
        assert len(hook_test_handlers) == 1

        self.run_hook(HOOK_NAME, lambda: {                       # by framework
            "variable_0": self.variable_0,
            "variable_1": self.variable_1})

        self.remove_hook_handler(HOOK_NAME, self.hook_handler)   # by developer
        assert len(hook_test_handlers) == 0

        self.remove_hook(HOOK_NAME)                              # by framework
        assert len(hooks) == hook_count_base

        aiko.process.terminate()  # TODO: Improve Aiko Services Process exit

    def hook_handler(self, name, component, logger, variables, options):
        assert name == HOOK_NAME                                 # by developer
        assert component == self
        assert logger is not None
        assert variables["variable_0"] == component.variable_0
        assert variables["variable_1"] == component.variable_1
        assert options == {}

def test_hook():                                                 # by developer
    init_args = aiko.actor_args("test_hook")
    hook_test = aiko.compose_instance(HookTest, init_args)
    aiko.event.add_timer_handler(hook_test.hook_check, 0.0)
    aiko.process.run(mqtt_connection_required=False)
