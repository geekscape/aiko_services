---
title: Configuration utility
description: Environment-driven discovery of the MQTT server, namespace and
  process identity — hostname, username, PID — used to bootstrap every
  Aiko Services process
type: concept
audience: [developers]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/main/utilities/configuration.py
related: [design_overview, logger]
version: "0.6"
last_updated: 2026-09-28
---

# Configuration utility

## Overview

Source code: [`src/aiko_services/main/utilities/configuration.py`](../../../src/aiko_services/main/utilities/configuration.py)

The configuration utility answers the first questions every Aiko Services
process asks at start-up: *which MQTT server, which namespace, and who am
I?* It reads `AIKO_*` environment variables, probes candidate MQTT
hosts, and derives process identity (hostname, username, PID). All of
these are plain functions with no framework dependencies. Thus the
[Process](../design_overview.md) bootstrap and the
[Logger](logger.md) can use them before anything else exists.

**Why to use it**: point a whole terminal session of Aiko Services
tools at a different broker and namespace without touching any code:

```bash
export AIKO_NAMESPACE=test
export AIKO_MQTT_HOST=broker.example.com
export AIKO_MQTT_PORT=1883
aiko_registrar    # every topic now starts with "test/"
```

## For application developers

### Command-line usage

There is no CLI. Every Aiko Services process exercises the module
indirectly at import time. For example `aiko_registrar`,
`aiko_dashboard` and `aiko_pipeline` all resolve their MQTT server and
topic namespace through it.

Recognized environment variables:

```bash
AIKO_NAMESPACE=test       # default "aiko"
AIKO_MQTT_HOST=localhost
AIKO_MQTT_PORT=1883       # or 1884 (websockets), 9883 (TLS), 9884 (WSS)
AIKO_MQTT_TLS=true        # if unset, TLS is inferred from AIKO_USERNAME
AIKO_MQTT_TRANSPORT=tcp   # or "websockets"
AIKO_USERNAME=username    # setting a username enables TLS by default
AIKO_PASSWORD=password
```

### Public API

| Function | Effect |
|----------|--------|
| `get_mqtt_configuration(tls_enabled=None)` | Full connection tuple `(server_up, host, port, transport, username, password, tls_enabled, address)` |
| `get_mqtt_host()` | Probe candidates, return `(server_up, host, port)` |
| `get_mqtt_host_address()` | Probe candidates, return `(server_up, host, port, address)`: the IP address that answered, or `None` |
| `get_mqtt_port()` | `AIKO_MQTT_PORT` or 1883 |
| `get_namespace()` / `get_namespace_prefix()` | `AIKO_NAMESPACE` (default `aiko`); prefix is the part up to and including `:` when present |
| `get_hostname()` | Short hostname — strips `.local`, abbreviates AWS EC2 names |
| `get_username()` / `get_pid()` | Process identity strings |
| `create_password(length=32)` | Random hex token (`length` is bytes, so 32 → 64 hex characters) |

`get_mqtt_host()` tries, in order: `AIKO_MQTT_HOST`, the (currently empty)
hard-coded `_AIKO_MQTT_HOSTS` list, then `localhost`. For each host, it
resolves the name one time. Then it tries the IPv4 addresses before the
IPv6 addresses, with a TCP connect of 2 s at most for each
(`_MQTT_PROBE_TIMEOUT`). It logs a WARNING for each address that fails,
and an INFO line for the address that answers.

A host name can resolve to an IPv6 address that is not routable from
the client. For example, on macOS, a `.local` name can resolve to the
IPv6 unique local address of a Linux SBC. The MQTT client then connects
to the address that answered, not to the name (see
[Message](../message.md)). To select an address yourself, set
`AIKO_MQTT_HOST` to an IPv4 literal.

Real call sites:

```python
# src/aiko_services/main/message/mqtt.py — connect or fail loudly
mqtt_configuration = get_mqtt_configuration()
server_up = mqtt_configuration[0]
...
if not server_up:
    raise SystemError(f"Couldn't connect to MQTT server {self.mqtt_info}")

# src/aiko_services/main/process.py — every Service topic path
topic_path_process = f"{get_namespace()}/{get_hostname()}/{get_pid()}"
```

Other users include `dashboard.py` (shows "MQTT SERVER UNAVAILABLE"),
`registrar.py` (wildcard state topic) and `hyperspace.py` /
`storage_file.py` (hostname-derived default Service names).

## For framework developers (internals)

### Design

```
   AIKO_* environment variables
              │
              ▼
   ┌────────────────────────┐ TCP probe, IPv4 ┌────────────┐
   │ get_mqtt_configuration │────────────────►│ MQTT server│
   │ get_namespace/hostname │  first, 2 s max └────────────┘
   │ get_username/pid       │
   └────────────────────────┘
        used by: process.py, message/mqtt.py, dashboard.py, ...
```

Deliberately dependency-free (stdlib plus [Logger](logger.md)) so it can
run before the framework initializes. TLS policy: explicit
`AIKO_MQTT_TLS` wins. Otherwise TLS is enabled exactly when a username is
configured.

### Implementation notes

- **Import-time side effect**: the module computes the UDP-bootstrap
  `RESPONSE` string at import, and that calls `_get_lan_ip_address()`.
  This can open a UDP socket toward `8.8.8.8` to learn the LAN IP
  address.
- `bootstrap_start()` / `bootstrap_thread()` implement a UDP
  broadcast-request / unicast-reply responder (port 4149) so devices
  without DNS/mDNS can find the MQTT server. It is implemented but not in
  `__all__` and currently has **no callers** in the code base.
- `_resolve_mqtt_host()` fails fast on connection-refused. Each TCP
  connect has a 2 s limit. Thus a host that is switched off costs 2 s
  for each address, not the operating system's timeout (about 75 s on
  macOS). The "timeout after N seconds" WARNING gives the total
  time for one host.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| *module* `configuration` | Resolve MQTT server, namespace and process identity from environment; probe candidate hosts; UDP bootstrap responder (unused) | [Logger](logger.md) (warnings); `message/mqtt.py`, `process.py` (main consumers) |

## Current limitations and roadmap

From the source `To Do` list:

- Replace the hard-coded (empty) `_AIKO_MQTT_HOSTS` list with an
  environment variable
- Move discovery and bootstrap functions into `message/discovery.py`.
  Implement discovery of the default MQTT hostname and namespace
  (including a `Namespace` class)
- `tests/unit/test_configuration.py` covers the address order, the
  timeouts, an unknown name, a literal address and the configuration
  tuple, with fake sockets. The header's other cases (no
  `AIKO_MQTT_HOST`, a host without a server) have no tests yet

## Related concepts

- [Design overview](../design_overview.md) — where process bootstrap fits
- [Logger](logger.md) — consumes `AIKO_LOG_*` variables the same way, and
  is this module's only internal dependency
