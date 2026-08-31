---
title: Tutorial 0 — Building an Aiko Application on the Constitution
description: Set up a new Aiko Application so the Constitution steers your AI coding agent — two starting shapes (Pipeline or Actor), the prompt, and the Agents.md seed
type: guide
audience: [application-developers, ai-coding-agents]
status: operational
ste: adapted
last_updated: 2026-08-31
---

# Tutorial 0 — Building an Aiko Application on the Constitution

The zeroth tutorial: read this before
[Using the public Constitution](using_the_public_constitution.md) and
[Using a private Constitution](using_a_private_constitution.md). It covers one thing: **setting up a new
Aiko Application so that the Aiko Services Constitution works FOR you**.
The result: a robust, secure, diagnosable, high-performance application
that interoperates with Aiko Services and every other Aiko Application.
You (and your AI coding agent, especially when vibe coding) get this by
default rather than by luck.

The trick: you never *enforce* the Constitution yourself. You point your
AI coding agent at it once, and the principles do the steering.

## Step 0 — Choose your starting shape: Pipeline or Actor

There are two reasonable ways to start, and both end at the same place.

| | **(1) Pipeline** — start here if unsure | **(2) Actor** |
|---|---|---|
| What it is | A declarative dataflow graph (P8): data "Frames" flow through connected **PipelineElements**, each doing one step | A long-lived distributed service (P2): a mailbox that receives one-way messages and owns its state |
| Runs as | **One process. No MQTT broker, no Registrar, no Dashboard needed** to begin | Distributed from birth — needs a broker + Registrar |
| You write | A small JSON definition + (optionally) your own elements — many exist **off-the-shelf** in `src/aiko_services/elements/` (media, control, observe, utilities) | A Python class with methods that become remotely callable |
| Best first fit | Processing anything step-by-step: media, ML inference, sensor data, text | Services that talk to each other: chat, robots, coordinators |
| Working example | `src/aiko_services/examples/pipeline/` (`pipeline_example.json` + `elements.py`) | `src/aiko_services/examples/aloha_honua/` (four files, graded) |

**The difference in one breath:** a Pipeline says *what flows through
what*, as data. An Actor says *who can be told what*, as a service. And
the secret that makes the choice low-stakes: **a PipelineElement IS an
Actor/Service under the hood**. A Pipeline that starts life in one quiet
process becomes discoverable, observable and distributed later, just by
adding the broker. Your element code does not change. Start simple —
distribution is a deployment decision, not a rewrite (P8's whole point).

## Step 1 — Create the application repo and install the framework

```bash
mkdir my_app && cd my_app && git init
python3 -m venv venv && source venv/bin/activate
pip install aiko_services

# Alongside (for examples, elements and docs to learn from):
git clone https://github.com/geekscape/aiko_services.git ~/aiko_services
```

## Step 2 — Seed `Agents.md` (and the `CLAUDE.md` softlink)

This is the highest-leverage file in your repo: every AI coding session
loads it automatically. Copy, then adapt the first paragraph:

```markdown
# MyApp: Agent instructions

MyApp is an Aiko Application built ON the Aiko Services framework
(github.com/geekscape/aiko_services). It is bound by the framework's
Constitution — especially the Design Principles P1–P12 in
`constitution/p_00_DesignPrinciples.md` (adopted by reference,
content as of <TODAY'S DATE>). When a design choice is unclear, decide
by appeal to the principles and cite the P-number.

## The principles, one line each (read p_00 for the real text)

- P1  Asynchronous at the protocol level: one-way messages. Methods
      NEVER return values across the wire. No async/await in
      framework-facing code.
- P2  Everything is an Actor. Share nothing. Never block the
      event-loop thread.
- P3  Request/response is two messages. Observe state via
      ECProducer/ECConsumer — getters do not exist.
- P4  Eventual consistency over consensus.
- P5  Discovery over configuration: find Services via the Registrar
      (ServiceFilter). Never hard-code topics or hosts.
- P6  Everything is a Service — no privileged plane.
- P7  Design by composition of Interfaces, not inheritance.
- P8  Topology is declarative data (PipelineDefinitions), not
      imperative wiring.
- P9  Edge-first frugality: minimal dependencies. Every buffer
      bounded. A Raspberry Pi must be able to run it.
- P10 Elegance is a requirement: the smallest design that composes.
- P12 Guarded by default: never eval/exec/pickle bus input. Public
      APIs are deny-all per method.

## Conventions

- Write "Aiko Services" in full — never bare "Aiko". Name ReadMe files
  `ReadMe.md`, not `README.md`.
- Identifiers: bare identifiers are local to this repo. Framework
  identifiers are cited as "framework P3", "framework ADR-002".
- Learn idioms from the framework's examples, simplest first:
  `examples/pipeline/` (a Pipeline of PipelineElements — start here) and
  `examples/aloha_honua/` (a basic Actor). Reuse off-the-shelf elements
  from `src/aiko_services/elements/` before writing new ones. Concept
  docs: `documentation/concepts/` (read `design_overview.md` first).
- Before claiming done: `pytest` green, and no principle violated —
  in review, cite P-numbers ("rejected: violates P3").

## Commands

    source venv/bin/activate
    aiko_pipeline create <definition>.json -s 1    # run a Pipeline (single process)
    mosquitto & aiko_registrar &                   # only when going distributed
    aiko_dashboard                                 # observe everything (P6)
```

Then make the softlink (edit `Agents.md`, never the link):

```bash
ln -s Agents.md CLAUDE.md
git add Agents.md CLAUDE.md && git commit -m "Seed agent context bound to the Aiko Services Constitution"
```

## Step 3 — The prompt for your AI coding agent

Short version (starting a session):

```text
Read Agents.md, the Aiko Services Design Principles at
https://github.com/geekscape/aiko_services/blob/master/constitution/p_00_DesignPrinciples.md
and the agent conventions at
https://github.com/geekscape/aiko_services/blob/master/constitution/g_03_AgentContext.md.
Build <FEATURE> as an Aiko Services Pipeline of PipelineElements
(reuse off-the-shelf elements where possible), following the
examples/pipeline/ pattern. For a long-lived service, use composed
Actors instead, following examples/aloha_honua/. Comply with P1-P12.
When unsure, decide by the principles and tell me which P-number
decided it.
```

That last clause is the vibe-coding safety net: it makes the agent *show
its constitutional reasoning*, so drift is visible in one line instead of
buried in code.

## Step 4 — Verify the plumbing before building anything

**Path (1), Pipeline — one process, no infrastructure:**

```bash
cd ~/aiko_services
aiko_pipeline create src/aiko_services/examples/pipeline/pipeline_example.json \
    -s 1 -p limit 10 -p rate 1
# Frames flow through the graph and print — the P8 dataflow model,
# alive on your desk, with nothing else running.
```

**Path (2), Actor — distributed, three commands of infrastructure:**

```bash
mosquitto &
aiko_registrar &
python -m aiko_services.examples.aloha_honua.aloha_honua &
aiko_dashboard        # you should SEE your Actor — that is P6 working
```

Either success is your interoperability floor. And remember the
convergence: run path (1) today, add path (2)'s broker + Registrar
whenever you want the same Pipeline discoverable and observable across
machines — no rewrite.

## Step 5 — As the application grows (three habits, one sentence each)

1. **Cite P-numbers in every review** — cheapest quality gate that exists.
2. **When a framework rule chafes, do not work around it**: comply, or
   raise it upstream as a proposal ([Using the public Constitution](using_the_public_constitution.md), Lane B/C) — never a
   quiet local exception.
3. **When your app develops its own recurring design rules**, give it a
   tiny constitution of its own: application principles (AP-1, AP-2 …)
   in your repo, beneath the framework's. Adopt the framework rules by
   reference, with a pinned date. The Aiko SDLC application is the worked
   example of this pattern. Start that file the second time you repeat a
   design argument, not before.

## Why this works (one paragraph, then go build)

The Design Principles encode the failure modes that AI coding agents
reliably produce: blocking getters, async creep, unbounded buffers, eval
on input, hard-coded topics. Each one is a short prohibition with a
reason. Loading them into every session turns your coding agent from a
generator of plausible code into a generator of *conformant* code. The
Pipeline console (then later the Dashboard) makes conformance visible at
runtime.
Setup is ten minutes. The payoff is every session afterward.
