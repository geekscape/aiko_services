# Usage
# ~~~~~
# pytest [-s] unit/test_context.py
# pytest [-s] unit/test_context.py::test_actor_args
#
# test_actor_args()
# - Create initial "actor_args" for creating Actors via composition
#
# To Do
# ~~~~~
# - Check all "context.py" init_args convenience functions
# - Check using all "init_args" for creating Instances via composition

import aiko_services as aiko

ACTOR_NAME = "Alice"
TRANSPORT = "mqtt"

# init_args{
#     "context": ContextService(
#         name="Name",
#         implementations=None,
#         parameters={},
#         protocol="*",
#         tags=[],
#         transport="mqtt")
# }

def actor_args(name):
    return aiko.actor_args(name)

def test_actor_args():
    init_args = actor_args(ACTOR_NAME)
    assert init_args is not None
    assert "context" in init_args

    context = init_args["context"]
    assert isinstance(context, aiko.ContextService)
    assert context.name == ACTOR_NAME
    assert context.implementations is None
    assert context.parameters == {}
    assert context.protocol == "*"
    assert context.tags == []
    assert context.transport == TRANSPORT

def test_actor_args_defaults_not_shared():
    # Regression: with tags/parameters omitted, each context must receive
    # its own copy — add_tags() on one Service (e.g. ECProducer's
    # "ec=true") must never pollute the module-level defaults

    context_a = actor_args("Alice")["context"]
    context_b = actor_args("Bob")["context"]
    context_a.tags.append("ec=true")
    context_a.parameters["key"] = "value"
    assert context_b.tags == []
    assert context_b.parameters == {}
    assert aiko.actor_args("Carol")["context"].tags == []
