---
title: Context
description: The single constructor argument for composed components — a
  dataclass hierarchy carrying name, implementations and Service fields,
  plus the Interface base class and its default-implementation registry
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/context.py
related: [design_overview, component, proxy, service, actor,
  pipeline, pipeline_element, parameters]
version: "0.6"
last_updated: 2026-07-05
---

# Context

## Overview

A **Context** is the single argument passed to every composed
component's constructor. It is an extensible dataclass that bundles the
common variable fields — name, implementations, parameters, protocol,
tags, transport, and (for Pipelines) definitions — so that
`__init__(self, context)` stays stable as the framework evolves,
protecting application code from constructor-signature churn.

The same module also defines the **`Interface`** base class — the root
of every Aiko Services contract — and its class-level
default-implementation registry (`Interface.default()`), which the
[Component](component.md) composition engine consumes. Context and
Component are two halves of one mechanism: Component builds the
composed class; Context carries its construction data and drives
once-only cooperative initialisation via `call_init()`.

Do not confuse this module with
`src/aiko_services/main/utilities/context.py`, whose `ContextManager` /
`get_context()` hold the process-wide `aiko` and `message` references —
a different concept documented separately.

**Why you'd use it**: every component you write starts with a Context.
The `*_args()` factories create one wrapped in an `init_args`
dictionary, ready for `compose_instance()`:

```python
import aiko_services as aiko

class Example(aiko.Actor):
    def __init__(self, context):
        context.call_init(self, "Actor", context)

init_args = aiko.actor_args("example")
example = aiko.compose_instance(Example, init_args)
aiko.process.run()
```

## For application developers

### Command-line usage

Context has no CLI of its own — it is a construction-time data
structure. It is exercised by every example and tool; the unit test can
be run directly:

```bash
cd src/aiko_services/tests
pytest [-s] unit/test_context.py
pytest [-s] unit/test_context.py::test_actor_args
```

### Public API

**The dataclass hierarchy** (each level adds fields):

| Class | Adds fields | Used by |
|-------|-------------|---------|
| `Context` | `name`, `implementations` | Plain composed classes |
| `ContextService(Context)` | `parameters`, `protocol`, `tags`, `transport` | [Service](service.md) *and* [Actor](actor.md) (same structure) |
| `ContextPipelineElement(ContextService)` | `definition`, `pipeline` | [Pipeline element](pipeline_element.md) |
| `ContextPipeline(ContextPipelineElement)` | `definition_pathname`, `graph_path` | [Pipeline](pipeline.md) |

Accessors: `get_name()`, `get_parameters()`, `get_protocol()`,
`get_tags()`, `get_transport()`, `set_protocol()`,
`get_definition()`, `get_pipeline()`, `get_definition_pathname()`,
`get_graph_path()`.

**The `init_args` factories** — each returns `{"context": <Context>}`,
ready for `compose_instance()`; add further constructor keyword
arguments as extra dictionary entries:

```python
context_args()
service_args(name, implementations=None,
    parameters=None, protocol=None, tags=None, transport=None)
actor_args(...)                  # identical fields to service_args()
pipeline_element_args(..., definition=None, pipeline=None)
pipeline_args(..., definition_pathname=None, graph_path=None)
```

Defaults (applied in `__post_init__` when a field is `None`):
`parameters={}`, `protocol="*"`, `tags=[]`, `transport="mqtt"`,
`definition=""`, `definition_pathname=""`. The Service `name` must be a
non-empty string or `ValueError` is raised;
`ContextPipelineElement` lower-cases the name.

**Composition support** — the methods the
[Component](component.md) machinery and composed `__init__()` methods
use:

| Operation | Effect |
|-----------|--------|
| `call_init(caller, implementation_name, context, **kwargs)` | Call the named implementation's `__init__(caller, context, **kwargs)` — once only per name per Context |
| `get_implementation(name)` | Return the loaded implementation class registered under `name` |
| `get_implementations()` / `set_implementations(dict)` | Whole-registry access (used by `compose_instance()`) |
| `set_implementation(name, implementation)` | Register a single implementation |
| `is_initialized(name)` / `set_initialized(name)` | The once-only guard behind `call_init()` |

**The `Interface` classes:**

```python
class Interface(ABC):
    context = Context()                      # class-level, shared

    @classmethod
    def default(cls, implementation_name, implementation): ...

    @classmethod
    def get_implementations(cls): ...

class ServiceProtocolInterface(Interface):
    """Interface marker represents an Aiko Service implementing a protocol"""
```

`Interface.default("Actor", "aiko_services.main.actor.ActorImpl")` is
the idiom every Interface uses to bind its default implementation; the
binding runs at class-definition (import) time, so importing
`aiko_services.main` populates the registry for the whole framework.
Note that `Interface.context` is a *single shared* Context — the
registry is global across all Interfaces (see
[Component](component.md) for the consequences).

There is no wire protocol: Context is purely in-process. The `protocol`
*field* it carries is the [Service](service.md) protocol identifier
used for discovery — data, not behaviour.

## For framework developers (internals)

### Design

```
 Context ─────────────── name, implementations
    └── ContextService ─ parameters, protocol, tags, transport
           └── ContextPipelineElement ─ definition, pipeline
                  └── ContextPipeline ─ definition_pathname, graph_path

 One Context instance per composed component instance:
   *_args(name) ─► {"context": ContextService(...)}
   compose_instance() ─► context.set_implementations({...})
   Seed.__init__(self, context)
     └─ context.call_init(self, "Actor", context)
          └─ ActorImpl.__init__(self, context)
               └─ context.call_init(self, "Service", context, ...)
                    └─ ServiceImpl.__init__(self, context)
   (each implementation initialised exactly once)
```

Key design points:

- **One argument, forever.** Constructors take `(self, context)` plus
  optional keyword arguments; new framework fields are added to the
  Context dataclasses, not to constructor signatures.
- **Cooperative diamond-safe initialisation.** `call_init()` calls the
  implementation class's `__init__` as an *unbound* function with the
  composed instance as `self` — all state lands on the one object —
  and records `initialized_<Name>` on the Context so diamonds in the
  Interface hierarchy (e.g. Category → Actor → Service and
  Category → Dependency) initialise each implementation exactly once.
- **Two registries, two lifetimes.** The class-level
  `Interface.context` holds *default* bindings (name → class or dotted
  path, process-wide); the per-instance Context holds the *loaded*
  implementation classes actually chosen for that composition
  (installed by `compose_instance()`).

### Implementation notes

- The `initialized_<Name>` flags are dynamic attributes on the Context
  instance, which means a Context — and therefore an `init_args`
  dictionary — is **single-use**: passing the same `init_args` to a
  second `compose_instance()` would make `call_init()` silently skip
  the `__init__` chain. Create fresh `*_args()` per instance.
- `get_implementation(name)` returns the implementation *class* (not an
  instance); callers such as `CategoryImpl` use it to delegate, e.g.
  `context.get_implementation("Dependency").is_type(self, ...)`.
- `__post_init__` normalises `None` fields to the module defaults and
  validates the Service name; subclasses chain with
  `super().__post_init__()`.
- `__all__` in this module is written as a *set* literal, not a list —
  functional for `import *`, but unordered and unconventional.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Context` (dataclass) | Carry `name` and implementations; drive once-only cooperative init via `call_init()`; per-instance implementation lookup | [Component](component.md) (`compose_instance()` installs implementations); every composed `__init__()` |
| `ContextService` / `ContextPipelineElement` / `ContextPipeline` | Extend Context with Service, PipelineElement and Pipeline fields; validate and default them in `__post_init__` | [Service](service.md), [Actor](actor.md), [Pipeline element](pipeline_element.md), [Pipeline](pipeline.md) |
| `Interface` (ABC) | Root of all contracts; hold the shared default-implementation registry; `default()` / `get_implementations()` | All Interface hierarchies; [Component](component.md) (registry consumer) |
| `ServiceProtocolInterface` | Marker: "this Interface represents an Aiko Services Service implementing a protocol" | [Service](service.md); excluded from Component's implemented-check |
| `context_args()` ... `pipeline_args()` (module functions) | Build the `init_args` dictionary with the right Context subclass | Application code; examples; tests |

## Current limitations and roadmap

From the source `To Do` list — highlights:

- **FIX:** `service_args()` should include `owner`
  (needed by `hyperspace.py:run_command()`) and `register_service`
  (needed by `storage_file.py`)
- Provide `get_parameter()` / `set_parameter()` (reusing existing code),
  and `add_tags()` / `remove_tags()` — with tags possibly becoming a
  dictionary internally
- Use `__file__` instead of `__name__` (with a `__file__` → `__name__`
  helper) to avoid `"__main__."` implementation paths
- Consider `protocol` revision versus source-code file version, with a
  convenience function to create source-code versions automatically
- Provide custom `__repr__()` / `__str__()`
- Test coverage: `tests/unit/test_context.py` covers only
  `actor_args()`; its own To Do lists checking all `*_args()`
  convenience functions and using each `init_args` to create instances
  via composition

## Related concepts

- [Design overview](design_overview.md)
- [Component](component.md) — consumes the registry and installs loaded
  implementations into the Context
- [Proxy](proxy.md) — method interception around composed instances
- [Service](service.md) and [Actor](actor.md) — constructed from
  `ContextService`
- [Pipeline](pipeline.md) and
  [Pipeline element](pipeline_element.md) — constructed from the
  extended Context subclasses
- [Parameters](parameters.md) — the `parameters` field carried by
  `ContextService`
