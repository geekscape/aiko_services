---
title: Network utility
description: Discover which TCP/UDP ports are in use on this host and find
  a free port in a given range — used by DataSchemes that open sockets
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/network.py
related: [design_overview, scheme]
version: "0.6"
last_updated: 2026-07-05
---

# Network utility

## Overview

The network utility answers two local-host questions: *which network
ports are already in use?* and *what is a free port I can bind?* It is a
thin layer over `psutil.net_connections()` with no Aiko Services
dependencies, exported via `utilities/__init__.py` as
`get_network_port_free` and `get_network_ports_used`.

**Why you'd use it**: a [DataScheme](../scheme.md) or server component
that must bind a listening socket without a hard-coded port. The ZMQ
DataScheme does exactly this when a `zmq://host:0` URL asks for "any
free port":

```python
# src/aiko_services/elements/media/scheme_zmq.py
from aiko_services.main.utilities import get_network_port_free
port = get_network_port_free(port_range)   # e.g. [6502, 6510] or [0, 0]
```

## For application developers

### Command-line usage

There is no console script; running the module directly lists every TCP
and UDP port currently in use:

```bash
cd src/aiko_services/main/utilities
./network.py
# TCP port:    88
# TCP port:  1883
# ...
# UDP port:  5353
# ...
```

### Public API

```python
__all__ = ["get_network_port_free", "get_network_ports_used"]

DYNAMIC_PORTS = [49152, 65535]  # IANA dynamic / private port range

def get_network_port_free(port_range=DYNAMIC_PORTS, type="tcp")
def get_network_ports_used()  # --> (tcp_used_ports, udp_used_ports)
```

- `get_network_ports_used()` returns two sorted, de-duplicated lists of
  port numbers: TCP ports in `LISTEN` state and UDP (datagram) ports.
- `get_network_port_free(port_range, type)` returns the first port in
  `port_range` (inclusive) not currently used, or `None` when the whole
  range is occupied. Passing `port_range=[0, 0]` selects the default
  `DYNAMIC_PORTS` range — this is the convention DataScheme URLs use for
  "any port". `type` must be `"tcp"` or `"udp"`, otherwise `KeyError`
  is raised.

Examples:

```python
from aiko_services.main.utilities import *

tcp_used, udp_used = get_network_ports_used()
port = get_network_port_free()                 # first free dynamic port
port = get_network_port_free([6502, 6510])     # first free in 6502..6510
port = get_network_port_free([0, 0], "udp")    # dynamic range, UDP
```

## For framework developers (internals)

### Design

```
  get_network_port_free(range, type)
        │
        ▼
  get_network_ports_used() ──► psutil.net_connections("inet")
        │                        ├─ TCP: status == CONN_LISTEN
        │                        └─ UDP: type == SOCK_DGRAM
        ▼
  linear walk of the sorted used-port list within range
```

The free-port scan is check-then-use, not bind-then-return: it walks the
sorted used-port list, advancing past each collision, and stops at the
first gap. This is simple and dependency-free, but inherently racy — see
limitations.

### Implementation notes

- The scan relies on `get_network_ports_used()` returning **sorted**
  lists (it does — both are `sorted(set(...))`).
- Only TCP sockets in `LISTEN` state count as "used"; a TCP port held by
  an established outbound connection is considered free.
- `psutil.net_connections()` may require elevated privileges on some
  platforms (notably macOS) to see other processes' sockets; with
  restricted visibility the "free" answer can be optimistic.
- The `type` parameter name shadows the Python built-in `type` — safe
  here, but keep it in mind when editing.

### CRC card

The module is purely functions; one row describes the module itself:

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `network` (module) | Enumerate in-use TCP/UDP ports; find the first free port in a range (with `[0, 0]` meaning the IANA dynamic range) | `psutil` (socket enumeration); [DataScheme](../scheme.md) implementations, e.g. `scheme_zmq.py` |

## Current limitations and roadmap

The source has no `To Do` list. Observed limitations:

- **TOCTOU race**: the returned port can be taken by another process
  before the caller binds it; there is no reserve-and-hand-over option
- Returns `None` on exhaustion rather than raising — callers must check
- No IPv4/IPv6 distinction and no per-interface filtering; all `inet`
  connections are pooled
- No unit tests anywhere in the repository exercise this module

## Related concepts

- [DataScheme](../scheme.md) — the main consumer, for `zmq://` style URLs
  that need a free port
- [Configuration utility](configuration.md) — the other "environment
  discovery" helper (MQTT host/port, namespace)
