---
title: Component
description: The composition engine — compose_class() and compose_instance()
  build concrete classes from Interface contracts and their registered
  default (or overridden) implementations
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/component.py
related: [design_overview, context, proxy, service, actor, category,
  dependency, lifecycle, pipeline]
version: "0.6"
last_updated: 2026-07-05
---

# Component

## Overview

**Component** provides the machinery for Aiko Services *design by
composition of Interfaces*. An **Interface** is a class containing only
abstract methods — a pure contract. Each Interface registers a *default
implementation* (a class, or a dotted module path to one) via
`Interface.default()`. The two functions in this module,
`compose_class()` and `compose_instance()`, then assemble a concrete
class at runtime by grafting the implementation methods for every
Interface in a class's ancestry onto a single dynamically created
subclass — affectionately called the *FrankensteinClass* in the source.

This is the mechanism by which every [Service](service.md),
[Actor](actor.md), [Pipeline](pipeline.md) and
[Category](category.md) instance comes to life. It works hand-in-hand
with [Context](context.md), which supplies the `Interface` base class,
the implementation registry and the single-`context`-argument
constructor convention.

**Why you'd use it**: to define a component's API as a contract that is
independent of any one implementation — so the implementation can be
swapped (per composition, without editing the Interface) for testing,
for alternative transports, or for application-specific behaviour:

```python
from abc import abstractmethod
from aiko_services.main import *

class Example(Interface):
    Interface.default("Example", "__main__.ExampleImpl")

    @abstractmethod
    def method_0(self): pass

class ExampleImpl(Example):
    def __init__(self, context, parameter):
        print(f"ExampleImpl.__init__({parameter})")

    def method_0(self):
        print("ExampleImpl.method_0()")

init_args = service_args("example")
init_args["parameter"] = "value"
example = compose_instance(ExampleImpl, init_args)
example.method_0()
```

(The usage comment at the top of the source shows `server_args()`; the
actual factory in `context.py` is `service_args()` — used here.)

## For application developers

### Command-line usage

Component has no CLI of its own — it is a library module exercised by
every composed component. To see it in action, run any of the
`src/aiko_services/examples/aloha_honua/` examples (for instance
`./aloha_honua_0.py`, whose last lines are exactly the
`actor_args()` / `compose_instance()` idiom), or any framework tool such
as `aiko_registrar` or `aiko_dashboard`.

### Public API

```python
__all__ = ["compose_class", "compose_instance"]
```

| Function | Effect |
|----------|--------|
| `compose_class(impl_seed_class, impl_overrides=None)` | Build and return `(FrankensteinClass, implementations_loaded)` — a concrete subclass of `impl_seed_class` with all Interface implementations applied, plus the dictionary of loaded implementation classes |
| `compose_instance(impl_seed_class, init_args, impl_overrides=None)` | Call `compose_class()`, record the loaded implementations on `init_args["context"]`, then instantiate: `frankenstein_class(**init_args)` |

- **`impl_seed_class`** is the implementation class you are composing,
  e.g. `CategoryImpl` or an application class such as `AlohaHonua`. Its
  ancestry (`__mro__`) is a hierarchy of pure Interfaces, each of which
  has (usually) registered a default implementation.
- **`init_args`** is a dictionary of constructor keyword arguments. It
  *must* contain a `"context"` entry — produced by the
  [Context](context.md) factories `service_args()`, `actor_args()`,
  `pipeline_element_args()` or `pipeline_args()`. Extra keys become
  extra `__init__()` keyword arguments (like `parameter` above).
- **`impl_overrides`** maps Interface names to replacement
  implementations, overriding the `Interface.default()` registrations
  for this composition only:

```python
frankenstein_class, impls = compose_class(
    CategoryImpl, impl_overrides={"Actor": "my_module.MyActorImpl"})
```

Implementation values may be either a class reference or a string
`"module.path.ClassName"`; strings are loaded lazily with
`load_module()` at composition time, so default implementations can be
declared without importing them.

The standard idiom, verbatim from
`src/aiko_services/examples/aloha_honua/aloha_honua_0.py`:

```python
import aiko_services as aiko

class AlohaHonua(aiko.Actor):
    def __init__(self, context):
        context.call_init(self, "Actor", context)
        ...

init_args = aiko.actor_args("aloha_honua")
aloha_honua = aiko.compose_instance(AlohaHonua, init_args)
aiko.process.run()
```

If any Interface in the seed class's ancestry has neither a default nor
an override implementation, `compose_class()` raises
`ValueError("Unimplemented interfaces: ...")`. If a *non*-Interface
ancestor (a class with concrete methods) shares its name with a
registered implementation, it is skipped with a printed warning.

There is no wire protocol: composition is an entirely in-process,
construction-time mechanism. The composed instance's remote face is
provided by [Service](service.md) / [Actor](actor.md) and
[Proxy](proxy.md).

## For framework developers (internals)

### Design

```
 impl_seed_class (e.g. CategoryImpl)
   │  inherits a pure Interface hierarchy:
   │  Category ─► Actor ─► Service ─► ServiceProtocolInterface
   │                       Dependency ──────────► Interface
   ▼
 impl_seed_class.get_implementations()      Interface.default()
   {"Actor": "...ActorImpl", ...}     ◄──   registry (class-level,
   merged with impl_overrides               shared by all Interfaces)
   ▼
 _keep_specified_implementations()   keep only implementations whose
 _check_interfaces_implemented()     Interface is in the seed's __mro__
   ▼
 _load_implementations()             dotted-path strings ─► classes
   ▼
 class FrankensteinClass(impl_seed_class): pass
   methods grafted by _add_methods()
   __init__ pinned to impl_seed_class.__init__
   __abstractmethods__ recomputed
   ▼
 frankenstein_class(**init_args)  ─►  one composed instance
```

Key design points:

- **Contract and implementation are decoupled per-Interface, not
  per-class.** A composed class is the union of one implementation per
  Interface in its ancestry; each can be independently overridden. This
  is composition *of behaviour into one object* — not delegation to
  held sub-objects — so every grafted method sees the same `self`.
- **The default registry is global.** `Interface.default()` (defined in
  [Context](context.md)) writes into a single class-level `Context`
  shared by *all* Interfaces, so `get_implementations()` on any seed
  class returns the defaults of every Interface imported so far —
  hence the filtering step. The source To Do acknowledges this.
- **One FrankensteinClass per composition.** Each `compose_instance()`
  call builds a fresh subclass; there is no class cache yet (see
  roadmap).
- **Initialisation is cooperative, not automatic.** The composed
  class's `__init__` is the seed class's `__init__`; it is that
  method's job to chain to parent-Interface implementations via
  `context.call_init(self, "Actor", context)` and so on — see
  [Context](context.md) for the diamond-safe once-only semantics.

### Implementation notes

**`_add_methods()` grafting rules.** For every non-dunder function of
every implementation class:

- if the method is absent from the composed class, add it;
- if it is present but abstract, replace it;
- if it is present and concrete, leave it alone.

This lets the seed class (and any concrete ancestor) override methods
supplied by an Interface's implementation.

**Interface detection is heuristic.** `_is_interface()` treats a class
as an Interface when *all* of its inspectable functions are
`@abstractmethod`. Note the vacuous case: a class with *no* Python-level
functions at all (e.g. the marker `ServiceProtocolInterface`, or a class
whose methods are C-implemented) also qualifies. `ABC`, `Interface`,
`ServiceProtocolInterface` and `object` are explicitly excluded from
the "must be implemented" check.

**Abstractness bookkeeping.** After grafting,
`_update_abstractmethods()` recomputes `__abstractmethods__` so that
Python's ABC machinery accepts instantiation. This is a verbatim copy of
the CPython 3.10 `abc.update_abstractmethods()` (the framework predates
a Python ≥ 3.10 floor); it can be replaced by the standard-library
function once the minimum supported Python is 3.10+.

**Implementations end up in two places.** `compose_instance()` calls
`context.set_implementations(implementations_loaded)`, so at
`__init__()` time the instance can retrieve the implementation *class*
for any Interface with `context.get_implementation("Dependency")` —
the delegation idiom used by `CategoryImpl` and others.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `compose_class()` / `compose_instance()` (module functions) | Gather, filter, validate and load implementations; build the composed class; wire loaded implementations into the Context; instantiate | `Interface` / `Context` ([Context](context.md)); `load_module()` (utilities importer); every composable component ([Service](service.md), [Actor](actor.md), [Category](category.md), [Pipeline](pipeline.md), ...) |
| `FrankensteinClass` (dynamic) | Concrete subclass of the seed class carrying the grafted implementation methods; renamed to the seed class's `__name__` | `impl_seed_class` (its base); implementation classes (method donors) |

## Current limitations and roadmap

From the source `To Do` list — highlights:

- **BUG (flagged in source):** is `_check_interfaces_implemented()`
  working correctly? The Interface-detection heuristic
  (`_is_interface()`) is the likely suspect — see Implementation notes
- Support composing a class *once* and reusing it to create multiple
  instances (currently every `compose_instance()` re-composes; note
  also that a `Context` records per-instance `initialized_*` flags, so
  `init_args` must not be reused either — see [Context](context.md))
- `impl_seed_class.get_implementations()` always picks up *all*
  registered Aiko Services Interface default implementations (global
  registry), relying on filtering rather than scoping
- Design a "protocol" (Interface hierarchy) for inbound and outbound
  methods — different Interfaces may optionally have different
  "connection pads"
- The source header's usage example refers to `server_args()`, which
  does not exist — the actual factory is `service_args()`
- No unit tests exercise `compose_class()` / `compose_instance()`
  directly (only `tests/unit/test_context.py` covers the neighbouring
  Context factories)

## Related concepts

- [Design overview](design_overview.md)
- [Context](context.md) — supplies `Interface`, the implementation
  registry, `call_init()` and the `*_args()` constructor factories
- [Proxy](proxy.md) — method interception for composed instances
- [Service](service.md) and [Actor](actor.md) — the principal Interface
  hierarchies that get composed
- [Category](category.md) and [Dependency](dependency.md) — worked
  examples of multi-Interface composition and delegation
- [Pipeline](pipeline.md) and [Pipeline element](pipeline_element.md) —
  composed with the extended `ContextPipeline*` data structures
