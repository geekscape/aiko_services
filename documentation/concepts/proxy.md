---
title: Proxy
description: Transparent method interception — ProxyAllMethods wraps an
  object so every public method call is routed through a proxy function,
  the seed of Aspect Oriented Programming and remote invocation
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/proxy.py
related: [design_overview, component, context, actor, service,
  discovery, transport, message, recorder]
version: "0.6"
last_updated: 2026-07-05
---

# Proxy

## Overview

**Proxy** provides transparent method interception: `ProxyAllMethods`
wraps any object so that every public method call is routed through a
single *proxy function*, which can log the call, time it, check access
— or, most importantly for Aiko Services, turn it into a message posted
to a remote [Actor](actor.md). It is the Aspect Oriented Programming
(AOP) seed of the framework, complementing
[Component](component.md): composition assembles *what* an object does,
a Proxy intercepts *how its methods are invoked*.

The wrapper is built on the `wrapt` package's `ObjectProxy`
(dependency pinned as `wrapt~=1.16.0`), so anything not explicitly
intercepted transparently falls through to the wrapped object.

**Why you'd use it**: to trace every call into a component without
touching its code —

```python
from aiko_services.main.proxy import ProxyAllMethods, proxy_trace, Example
example_proxy = ProxyAllMethods("Example", Example("v0"), proxy_trace)
example_proxy.function_0("value_0", argument_1="value_1")
# ### Enter: Example.function_0('value_0',) {'argument_1': 'value_1'} ###
#            Example.function_0(value_0, value_1)
# ### Exit:  Example.function_0 ###
```

— or, with `ActorImpl.proxy_post_message` as the proxy function, to
turn local method calls into Actor mailbox messages (shown as
"Example 3" in the `actor.py` source header; currently illustrative
rather than the wired-in remote path — see roadmap).

## For application developers

### Command-line usage

Proxy has no CLI of its own — it is a library module. The in-module
`Example` class supports the interactive snippet above; the framework
behaviour it foreshadows (transparent remote invocation) is exercised
through the [discovery](discovery.md) tools and any remote Actor
example, e.g. `src/aiko_services/examples/aloha_honua/aloha_honua_1.py`.

### Public API

```python
__all__ = ["is_callable", "ProxyAllMethods", "proxy_trace"]
```

| Name | Effect |
|------|--------|
| `ProxyAllMethods(proxy_name, actual_object, proxy_function, attribute_filter=ismethod, ignore_prefix="_")` | Wrap `actual_object`; every attribute selected by `attribute_filter` whose name does not start with `ignore_prefix` is replaced by a closure that invokes `proxy_function` |
| `proxy_trace(...)` | Ready-made proxy function: print `### Enter ...` / `### Exit ...` around the call and pass the result through |
| `is_callable(attribute)` | `True` for a plain function or a bound method |

**The proxy-function contract.** A proxy function receives the full
call context and decides whether/how to invoke the real method:

```python
def proxy_function(proxy_name, actual_object, actual_function,
    actual_function_name, *args, **kwargs):
    ...
    return actual_function(*args, **kwargs)   # or not: e.g. post a message
```

`proxy_trace` calls straight through. By contrast,
`ActorImpl.proxy_post_message` (in `actor.py`) *never* calls the target
directly — it posts `(command, args)` to the Actor's `control` or `in`
mailbox topic, which is the shape of asynchronous and remote
invocation:

```
 caller                    ProxyAllMethods            proxy_function
   │ proxy.method_0(args)        │                         │
   │────────────────────────────►│ closure for "method_0"  │
   │                             │────────────────────────►│
   │                             │      trace / time / check / ...
   │                             │   then EITHER call actual_function
   │                             │   OR post (method_0 args) as a message
   │◄────────────────────────────│◄────────────────────────│
```

Proxy itself defines no wire protocol; when the proxy function posts
messages, the format is the [Actor](actor.md) /
[message](message.md) command form, e.g. `(aloha Pele)`.

## For framework developers (internals)

### Design

```
                ProxyAllMethods(wrapt.ObjectProxy)
                ┌────────────────────────────────────┐
 caller ───────►│ method_0 ─► closure ─► proxy_function(
                │ method_1 ─► closure ─►   proxy_name, actual_object,
                │   ...        (per       actual_function, name,
                │              method)    *args, **kwargs)
                │                                    │
                │ everything else falls through      ▼
                └───────────────►  actual_object.method(...)
                                   (or a posted message instead)
```

Key design points:

- **Interception by instance attribute, not subclassing.** At
  construction, `getmembers(actual_object, attribute_filter)`
  enumerates the object's bound methods; each public one gets a closure
  set *on the proxy instance*. Attribute lookup finds the closure
  before `wrapt` delegates, so intercepted calls never reach the
  wrapped object unless the proxy function forwards them.
- **Everything else is transparent.** State access, un-intercepted
  attributes, `isinstance()` behaviour — all delegate to the wrapped
  object via `wrapt.ObjectProxy`.
- **The intercept policy is a plain function**, so the same mechanism
  serves tracing, timing, security checks and remote invocation — the
  AOP intercepts listed in the roadmap.
- **Direction of travel:** the source To Do and `discovery.py` To Do
  both point at consolidating this module with the hand-rolled
  lightweight proxies in `discovery.py` (`_make_service_proxy()` /
  `get_service_proxy()`) and `transport/transport_mqtt.py`
  (`make_proxy_mqtt()`), which currently build remote-call proxies
  without `ProxyAllMethods`.

### Implementation notes

- Default `attribute_filter=ismethod` intercepts only *bound methods*
  of the instance; pass a different predicate (e.g. `is_callable`) to
  widen the net.
- Default `ignore_prefix="_"` skips private *and* dunder methods —
  which is also what keeps the proxy's own plumbing safe. Pass
  `ignore_prefix=None` to intercept everything the filter matches.
- Each closure captures `(actual_function, name)` via the
  `make_closure()` factory — the classic loop-variable-capture pitfall
  is deliberately avoided.
- `__repr__` is overridden to identify the proxy object itself;
  otherwise `wrapt` would delegate `repr()` to the wrapped object.
- `ProxyAllMethods` is exported from `aiko_services.main`, but nothing
  in the live framework call path constructs one today: `actor.py`
  references it only in a commented header example, and the remote
  invocation path uses `discovery.py`'s own proxies. Treat this module
  as implemented-and-available, with framework integration pending.
- The commented-out `@proxy` decorator sketch at the bottom of the file
  documents the intended decorator form and its open problem: the
  decorator must return a factory that creates proxy *instances*, not a
  single wrapped instance.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ProxyAllMethods` (wrapt.ObjectProxy) | Enumerate the wrapped object's public methods; install per-method closures routing calls to the proxy function; delegate everything else transparently | `wrapt.ObjectProxy` (base); any proxy function (`proxy_trace`, `ActorImpl.proxy_post_message`); the wrapped object |
| `proxy_trace` (function) | Reference proxy function: print Enter/Exit around a pass-through call | `ProxyAllMethods` |
| `Example` | In-module demonstration target for the usage example | `ProxyAllMethods`, `proxy_trace` |

## Current limitations and roadmap

From the source `To Do` list — highlights (all currently unimplemented):

- Proxy only *specified* functions — select by `[Interface]`, wildcard
  match lists and wildcard ignore lists. (The To Do says "see
  MATCH_STRING (below)", but no `MATCH_STRING` exists in the file —
  a stale reference.)
- Support multiple proxy functions per Proxy object
  (`proxy_function` → `[proxy_function]`)
- `@proxy` and `@remote_proxy` decorators (a non-working sketch is
  commented out at the end of the source)
- Aspect Oriented Programming intercepts: logging (flight
  [recorder](recorder.md), tracing for diagnosis), remote function
  call, security access, timing (performance)
- Consolidation with `discovery.py` / `transport_mqtt.py` proxies (per
  the `discovery.py` To Do), so remote Service proxies and
  `ProxyAllMethods` share one mechanism
- No unit tests exercise this module

## Related concepts

- [Design overview](design_overview.md)
- [Component](component.md) — composes behaviour; Proxy intercepts its
  invocation
- [Context](context.md) — construction data for the composed objects a
  Proxy wraps
- [Actor](actor.md) — `ActorImpl.proxy_post_message` turns intercepted
  calls into mailbox messages
- [Discovery](discovery.md) — today's remote Service proxies
  (`get_service_proxy()`), the planned consolidation target
- [Transport](transport.md) and [Message](message.md) — how posted
  proxy calls travel
- [Recorder](recorder.md) — the flight-recorder intercept on the AOP
  roadmap
