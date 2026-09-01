---
title: "Aiko Services — Python Reference Implementation: Repository Layout"
description: Target layout for src/aiko_services/, the one-way layering rules
  that make it meaningful, and the migration sequence from the current main/
  package
type: specification
audience: [architects, developers, ai-coding-agents]
status: proposal
ste: adapted
related: [e_00_TransitionPlan, s_00_Specifications]
last_updated: 2026-07-31
---

# Aiko Services — Python Reference Implementation: Repository Layout

**Status:** Proposal. Defines the target layout for `src/aiko_services/`, the layering rules that
make the layout meaningful, and the migration sequence from the current `main/` package.

---

## 1. Layering rule (the layout in one sentence)

Packages form a strict one-way dependency order — each layer imports only from layers above it,
never below, enforced in CI by an import-linter contract:

    runtime  →  actors  →  pipeline  →  agents  →  elements  →  (cli, examples)

`runtime/` is mechanism (no concrete Services). `actors/` is the Actor abstraction plus the
framework's built-in Actors. `pipeline/` is the dataflow engine. `agents/` composes pipelines into
perceive-decide-act Actors. `elements/` is the open-ended library of PipelineElements. `cli/` and
`examples/` consume everything and are imported by nothing.

## 2. Target tree

    src/aiko_services/
        __init__.py                 # public API façade — re-exports the stable surface;
                                    #   "import aiko_services as aiko" continues to work
        main/                       # TEMPORARY compatibility shim (one release cycle):
            __init__.py             #   re-exports from new locations + DeprecationWarning
        runtime/
            __init__.py
            AGENTS.md               # package context: responsibility, invariants, forbidden deps
            process.py              # Process singleton, bootstrap, run/terminate
            event.py                # event loop: mailboxes, timers, queues
            component.py            # Interface base + composition machinery (see 04-…)
            service.py              # Service interface, ServiceFields, topic derivation
            share.py                # ECProducer / ECConsumer
            lease.py
            lifecycle.py            # LifeCycleManager/Client mechanism (interfaces + impl)
            state.py                # StateMachine utility
            connection.py           # connection state model
            proxy.py                # remote invocation proxies (do_command, …)
            message/                # S-expression parse/generate, topic path construction
            transport/
                __init__.py         # Transport interface (transport-neutral)
                mqtt.py             # reference transport
            utilities/              # parser, logger, importer, … (no framework imports)
        actors/
            __init__.py
            AGENTS.md
            actor.py                # Actor interface + ActorImpl (mailbox dispatch)
            registrar.py
            process_manager.py
            recorder.py
            dashboard/              # observer UI (optional-dependency group)
        pipeline/
            __init__.py
            AGENTS.md
            pipeline.py             # Pipeline Actor, PipelineDefinition loading, graph
            element.py              # PipelineElement interface + base impl
            stream.py               # Stream, Frame, stream events
            schema.py               # NEW: definition JSON schema + I/O type validation
        agents/
            __init__.py
            AGENTS.md
            agent.py                # Agent composition (Actor + Pipeline host + policy)
            mcp/                    # MCP Server/Client bridge
        elements/
            __init__.py
            AGENTS.md
            media/                  # image/video/audio/webcam I/O, codecs…
            ml/                     # inference elements
            utilities/              # general-purpose elements
        cli/
            __init__.py             # aiko_dashboard, aiko_pipeline, aiko_registrar entry points
    docs/
        specifications/             # normative: protocol, runtime, actors, pipeline, agents
        adr/                        # ADR-NNN…, append-only
        interfaces/CATALOG.md       # generated + human-curated interface catalog
    tests/
        conformance/                # golden protocol traces + replay harness (language-neutral)
        unit/                       # mirrors src layout
        integration/
    AGENTS.md                       # root agent context (CLAUDE.md symlinks here)
    examples/                       # executable specifications, one concept each, run in CI

## 3. The two judgment calls (decided here, flagged for your veto)

**Where does `actor.py` live?** You said "Services / Actors split out into `actors/`." Taken
literally that could include `service.py`. I propose the line differently: **`Service` stays in
`runtime/`, `Actor` moves to `actors/`.** Reasoning: the runtime cannot function without the
Service abstraction — registration, topics, discovery are bootstrap mechanism, and the Registrar
protocol has no meaning without ServiceFields. The Actor (mailbox semantics) is the first thing
*built on* the runtime. Put it in `actors/` alongside the built-in Actors, and that package
reads as "the Actor model layer": the abstraction at the top of the file list, and the Actors
of the framework below it.

You can instead keep only concrete Actors in `actors/` and keep the abstraction in `runtime/`.
That migration is one file-move different. But then the package boundary teaches nothing, and
packages are now agent context units.

One wrinkle: the Registrar moves to `actors/` yet bootstrap (`runtime/process.py`) must find it.
The runtime should depend on the *Registrar protocol* (§1.4 of the specifications — topic names
and message forms, which live in `runtime/message/`), never on the Registrar *implementation*.
That keeps the layering honest and matches the language-agnostic claim: the runtime must work
against a Rust registrar anyway.

**One package or two for dataflow?** I propose `pipeline/` (engine) and `agents/` (compositions
that include MCP) as separate layers, not one package. Pipelines are useful without any agent
semantics (pure media streaming). Also, `agents/` is where most new, fast-moving, spec-first
work will occur. To keep the two apart protects the stable engine from churn, and it gives
agents a sandbox with a clear scope.

## 4. Migration sequence (Phase 3 of the transition plan)

Each step is a separate PR by an AI agent. The full test + conformance suite gates each step.
The shim keeps the `aiko_services.main.*` imports operational through all the steps:

1. **Scaffold:** create empty `runtime/ actors/ pipeline/ agents/` packages, the root `__init__.py`
   façade, and the `main/` shim machinery. Zero behavior change.
2. **Leaves first:** move `utilities/` and `message/` into `runtime/` (they import nothing else).
3. **Mechanism core:** move `event`, `process`, `component`, `state`, `lease`, `connection`.
4. **Service layer:** move `service`, `share`, `proxy`, `lifecycle`, `transport/`.
5. **Actor split:** move `actor.py` to `actors/`. Move `registrar`, `process_manager`,
   `recorder` and `dashboard` to `actors/`. Introduce the protocol/implementation seam from §3.
6. **Dataflow:** move `pipeline` and `stream` (+ new `element.py`, `schema.py` split) to
   `pipeline/`. Update the imports of `elements/` and `examples/`.
7. **Enforce:** turn on the import-linter layering contract and the interface-drift check. The
   layout is now load-bearing.
8. **(Next release) remove the `main/` shim.**

Steps 2–6 are mechanical and are ideal early multi-agent tasks. Step 5 contains the only real
design work (the registrar seam) and needs your review.
