---
title: Actors index
description: Index of the actors tier — packages of Actors built on the
  framework core, each with its own protocol; the display:0 protocol design
  and evaluation is the first
type: index
audience: [developers, end-users]
status: draft
ste: adapted
source:
  - src/aiko_services/actors
related: [actor, service]
version: "0.8-dev"
last_updated: 2026-09-27
---

# Actors index

The actors tier, `src/aiko_services/actors/`, holds packages of Actors
built on the framework core. Each package has its own protocol. The
packages ship in the wheel. They are designs and evaluations, not
examples: the examples live in `src/aiko_services/examples/`.

Navigation: [documentation map](../ReadMe.md) ·
[concepts guide](../concepts/ReadMe.md) ·
[examples index](../examples/ReadMe.md)

## Packages

| Package | Summary |
|---------|---------|
| [display/](display/ReadMe.md) | The `display:0` protocol: a remote display as an Actor, with an SSD1306 OLED as the reference device, emulated outputs, applets, a keys console, a Dashboard page, a test guide and unit tests |
