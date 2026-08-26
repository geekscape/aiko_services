---
title: CLAUDE.md / AGENTS.md — Aiko Services
description: Drop-in context for AI coding assistants, including the
  "Conventions an agent must follow" and known sharp edges; derived from the
  v0.6 source review
type: agent-context
audience: [ai-coding-agents]
status: operational
ste: adapted
related: [a_00_ArchitectureReview_2026-06, p_00_DesignPrinciples]
last_updated: 2026-07-31
---

# CLAUDE.md / AGENTS.md — Aiko Services

> Drop-in context for AI coding assistants (Claude Code, Gemini Code, OpenAI Codex, Goose).
> This document comes from a source review of `aiko_services` v0.6 (`2026-06-08_a`). Keep this
> file short and truthful. It is the highest-leverage context that an agent receives. When in
> doubt, the source in `src/aiko_services/main/` is authoritative.

## What this project is

Aiko Services is a distributed, embedded framework that unifies AI/ML agent + multimedia dataflow
pipelines, media streaming, IoT, and robotics (ROS2-adjacent) on one message substrate. Services
discover each other through a Registrar. They communicate by **one-way S-expression messages over
MQTT** (no return values across the wire). Shared state is **eventually consistent**
(ECProducer/ECConsumer).

Processing topology is **declarative data** (pipeline graph definitions) that a Pipeline runtime
executes. The framework runs from Raspberry-Pi-class edge devices up to servers. It is
**language-agnostic at the wire-protocol level** (Python here, MicroPython in `aiko_engine_mp`),
and is Apache-2.0.

## Core mental model (do not violate)

- **Asynchronous by protocol, not by language.** The framework uses **no Python `async`/`await`**
  and does not need it. A remote method call is a published S-expression message that returns
  nothing. Do **not** add `async def` to framework interfaces. Do **not** add methods that
  return values across the wire. (Application code *may* use `async` internally, but the framework
  does not depend on it.)
- **Everything is a Service.** Registrar, ProcessManager, Dashboard, Storage, transports — all are
  ordinary Services/Actors. There is no privileged management plane. To add new infrastructure,
  write Services. Do not add special cases to the core.
- **Design by composition of interfaces.** `compose_instance` binds named implementations behind
  abstract `Interface` classes and assembles behavior from them — not deep inheritance. New
  behavior = a new Interface or a method on one, with a registered `…Impl`.
- **Topology is data.** Pipelines are JSON definitions with an S-expression `graph`. The runtime
  interprets them. Prefer to change behavior with definitions, not with imperative wiring.
- **Discovery over configuration.** Find Services by `ServiceFilter` (protocol/name/tags/owner),
  never by hard-coded host/topic strings.

## Repository map (what to read first)

```
src/aiko_services/
  main/                      # FRAMEWORK CORE — start here
    context.py               # Interface base + Context + *_args() factories (composition foundation)
    component.py             # compose_class / compose_instance (the composition engine)
    service.py               # Service interface + ServiceFields/Filter/TopicPath
    actor.py                 # Actor interface + mailbox dispatch (message -> method)
    pipeline.py              # Pipeline + PipelineElement + graph execution (largest file)
    stream.py                # Stream, Frame, StreamEvent
    share.py                 # ECProducer / ECConsumer (eventually-consistent state)
    discovery.py             # get_service_proxy, do_command, do_request (remote calls)
    proxy.py                 # ProxyAllMethods (wrapt) — universal method interception
    registrar.py             # discovery authority    process_manager.py  # process spawn/monitor
    lifecycle.py             # LifeCycleManager/Client    lease.py  hook.py  event.py  process.py
    category.py hyperspace.py storage/ transport/ message/ utilities/ dashboard.py
  elements/                  # PipelineElement LIBRARY — how to build processing nodes
    media/ (image_io, video_io, audio_io, text_io, webcam_io)  control/ observe/ utilities/
  examples/                  # HOW TO USE — read these to learn idioms
    aloha_honua/             # ← simplest Actor (start here)
    pipeline/                # ← simplest Pipelines + pipeline_*.json definitions
  tests/unit/                # test_context, test_hook, test_pipeline_graph, test_stream_*
```

Concept-level documentation for every module above lives in `documentation/concepts/` — one OKF
document per concept (see its `ReadMe.md` index). The PipelineElement library has one document
per module in `documentation/elements/` (control/gstreamer/media/observe/utilities). Each
elements package index maps the example PipelineDefinitions to elements. The example
applications have one document per module in `documentation/examples/` (aloha_honua through
xgo_robot, one package index each). Read the relevant document before the source. Each document
separates implemented behavior from planned behavior.

## How to build the two things you will build most

### A basic Actor (pattern from `examples/aloha_honua/`)

```python
import aiko_services as aiko

class AlohaHonua(aiko.Actor):
    def __init__(self, context):
        context.call_init(self, "Actor", context)   # cooperative init — ALWAYS do this

    def aloha(self, name):                            # becomes remotely callable: (aloha Pele)
        self.logger.info(f"Aloha {name} !")

# start it:
init_args = aiko.actor_args("aloha_honua")
aloha = aiko.compose_instance(AlohaHonua, init_args)
aiko.process.run()
```
Remote call from elsewhere: discover + invoke through a proxy (fire-and-forget):
```python
aiko.do_command(
    AlohaHonua,
    aiko.ServiceFilter("*", "aloha_honua", "*", "*", "*", "*"),
    lambda a: a.aloha("Pele"),
    terminate=True)
aiko.process.run()
```
Request/response (reply through message, not a return value): use `aiko.do_request(...)` with a
response topic and a `response_handler` (see `aloha_honua_3.py`).

### A basic PipelineElement (pattern from `examples/pipeline/elements.py`)

```python
from typing import Tuple
import aiko_services as aiko

class PE_Add(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("add:0")                       # protocol id for discovery
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, i) -> Tuple[aiko.StreamEvent, dict]:
        constant, _ = self.get_parameter("constant", default=1)
        return aiko.StreamEvent.OKAY, {"i": int(i) + int(constant)}   # local return to runtime
```
Stream lifecycle methods, when needed: `start_stream(self, stream, stream_id)` and
`stop_stream(self, stream, stream_id)`. Generate frames with
`self.create_frames(stream, self.frame_generator, rate=...)`. Expose state through `self.share[k] = v`.

### A Pipeline definition (JSON; topology-as-data)

```json
{ "version": 0, "name": "p_example", "runtime": "python",
  "graph": [ "(PE_IN PE_TEXT PE_OUT)" ],
  "elements": [
    { "name": "PE_IN",
      "input":  [{ "name": "in_a",   "type": "string" }],
      "output": [{ "name": "text_b", "type": "string" }],
      "deploy": { "local": { "module": "aiko_services.examples.pipeline.elements",
                             "class_name": "PE_IN" } } }
  ] }
```
Run: `aiko_pipeline create pipeline_example.json -s 1 -p limit 1000 -p rate 1`. To drive a
stream, publish these S-expressions: `(create_stream 1)`, `(process_frame (stream_id: 1) (a: 0))`,
`(destroy_stream 1)`.

### Hooks (AOP — pattern from `tests/unit/test_hook.py`)

```python
self.add_hook(HOOK_NAME)                              # framework declares a hook point
self.add_hook_handler(HOOK_NAME, self.hook_handler)  # developer attaches a handler
self.run_hook(HOOK_NAME, lambda: {"k": v})           # framework fires it
# handler signature: handler(name, component, logger, variables, options)
```

## Conventions an agent must follow

- **Naming:** always write "Aiko Services" in full — never abbreviate to "Aiko". Other Aiko
  sub-system and application concepts exist (for example, Aiko Engine and Aiko Chat), often in
  other Git repositories. As a result, the bare "Aiko" is ambiguous.
- **ReadMe files:** always name them `ReadMe.md` (CamelCase style), not `README.md`.
- **STE:** for plans, documentation, commit messages and release notes, use ASD-STE100
  Simplified Technical English (STE). Write at the level that the document's `ste:`
  front-matter field declares (`full | adapted | false`). New documents get their default
  level per the project STE profile [Privately maintained]. The profile
  carries the global switch, the rules digest, the Aiko Services technical-word register and
  the swap list. The dictionary is the local licensed PDF
  `documentation/z_asd-ste100-issue-9.pdf` (gitignored — never commit it and never quote it <!-- future-ref-ok: never-commit instruction for a local-only licensed file -->
  at length). Use American English spelling throughout (STE rule 1.14). Note that
  `remove` ≠ `destroy` in Aiko Services APIs and prose. The correct name is always
  "ASD-STE100" (not "ASR-STE100"). Verify with the gate, never from memory:
  `python3 documentation/tools/asd_ste100_lint.py <file>` must read zero on all seven
  counts before you set `ste: adapted`. Read the `I` advisory line first, because a
  swap-list word that is also a code span usually names a real command.
- **Concepts documentation:** every document in `documentation/concepts/` follows the section
  structure that [t_00_OkfConceptTemplate.md](t_00_OkfConceptTemplate.md) defines. The order is:
  Overview, then application-developer sections (Command-line usage, Public API), then
  framework-developer sections (Design, Implementation notes, CRC card), then roadmap and
  related concepts.
- A new constructor takes a single `context` argument. Call `context.call_init(self,
  "<Interface>", context)` first. Use `aiko.actor_args(name)` / `aiko.pipeline_element_args(name)`
  / `aiko.pipeline_args(name)` to build it. When a class needs no constructor arguments beyond
  `context` and no explicit chaining, you can omit the `__init__` entirely (ADR-021,
  implemented 2026-07-13). Then `compose_class()` synthesizes it, and a `PROTOCOL` class
  attribute replaces `context.set_protocol(...)`. An explicit `__init__` always wins — learn
  the explicit form first.
- New public framework APIs follow the Interface composition pattern. As an alternative, they
  carry an ADR-022 categorized-exemption header note. There are three exemption categories:
  value/data type, presentation/CLI shell, and bootstrap before composition.
  the public-API composition rollout [Privately maintained] governs the migration across existing
  code — check its §2 before you restructure any `main/` module.
- Public APIs carry Python docstrings per e_10 §3. An Interface method documents its
  contract in four parts: one summary line, the arguments, the wire form
  `(method arg …)` and the reply-to/shared-state convention. Match the existing style of
  `lifecycle.py`. Add docstrings to any public API that you touch.
- **P12 (ADR-023):** never `eval`/`exec`/pickle bus-derived input — safe parsers only. Coerce
  and validate parameters at the boundary. Mobile LISP/predicate expressions run only in the
  sandboxed predicate language (item 06). Until that sandbox exists, refuse mobile code
  (hard-coded filters only). New exposure surfaces (gateways, dispatch) are deny-all by
  default, per method, seeded by the composed Interface declarations. An isolated
  development deployment may run allow-all (explicit config, advertised, never the shipped
  default, never on externally-reachable surfaces). But the no-unguarded-`eval()` rule holds
  in every mode: never add an eval code path for dev convenience.
- Public method names become wire commands. Keep them S-expression-friendly (positional args, or
  a single trailing dict). Do **not** use return values to send data across the wire.
- Discover with `ServiceFilter(topic_path, name, protocol, transport, owner, tags)` (six fields,
  `"*"` = wildcard). Never hard-code peer topics.
- Set a protocol id in elements/services (`context.set_protocol("name:0")`) so discovery and future
  MCP exposure work.
- Run and stop through `aiko.process.run()` / the event loop. Never block the event-loop thread
  (push long work onto a mailbox/worker).
- Tests use `aiko.process.run(mqtt_connection_required=False)` to run without a broker.

## Commands

```
pip install -e .                      # dev install (hatchling backend)
pytest                                # unit tests (src/aiko_services/tests)
flake8 . --select=E9,F63,F7,F82       # critical lint (matches CI)
scripts/system_start.sh               # start mosquitto + Aiko Registrar (see scripts/)
aiko_registrar  aiko_dashboard  aiko_pipeline  aiko_process  aiko_hyperspace   # console entry points
```

## Known gaps / sharp edges (so agents do not trip on them or "fix" them wrongly)

- **No MCP code and no `Agent` interface yet** — both are greenfield. If a task asks you to add
  them, treat them as new design, not modification.
- **`ECProducer`/`ECConsumer` are plain classes, not Interfaces** — a standing P7 violation
  that awaits normalization (the composition rollout §2.1 [Privately maintained], ADR-022). Do not assume that an
  interface exists yet. Do not add one unplanned — follow e_10.
- **Several Interfaces are empty markers** — `Registrar`, `Recorder` and `TransportMQTT`
  declare no abstract methods. `RegistrarImpl._topic_in_handler()` hand-parses the Registrar
  wire commands (`add`/`remove`/`share`/`history`). Do not assume that an Interface declares
  the contract — read the Impl (contract promotion: e_10 §2.2/§2.3/§2.13).
- **`HooksImpl` keeps its `hooks` dict as a class-level attribute and has no `__init__`** —
  every composed Service in the process shares the hook state. When you add a hook on one
  component, you add it to all. This is a latent aliasing bug. The fix is e_10 §2.4. Also,
  `HooksImpl.run_hook(self, hook_name, variables=None)` is wider than the abstract
  `run_hook(self, hook_name)` declaration.
- **`transport/transport_mqtt.py:ActorDiscovery.get_actor_mqtt()` unconditionally raises**
  `Exception("Broken: get_actor_mqtt()")` — use `discovery.get_service_proxy()` instead. The
  duplicate discovery classes merge in e_10 §2.5.
- **`Castaway.__init__` silently drops the `mqtt_state_handler` parameter** that
  `Message.__init__` declares — code that passes it behaves differently with and without a
  broker.
- **Two proxy mechanisms** (`proxy.py` and `discovery.get_service_proxy`) — their
  consolidation is pending.
- **`discovery.do_command/do_request` lack timeouts** — with a missing responder, the call
  waits forever. Add timeouts when you build on these paths.
- **Actor dispatch catches broad exceptions** — do not rely on exception propagation from
  message handlers.
- **Type hints are partial** — add them when you touch a file. Never remove the `async`-free
  property of the framework.
- **Pipeline port types are declared but not validated at construction** — validate them if you
  add graph-construction logic.
- **PipelineDefinition validation is toothless** — `parse_pipeline_definition()` discards the
  avro `validate()` boolean (avro returns False, it does not raise). Thus invalid definitions
  pass silently. The schema also restricts parameter values to bool/int/null/string, yet
  shipped examples use floats.
- **`process.py remove_message_handler()` is broken for binary topics** — the binary branch
  removes from the *wildcard* list (`del list[str]` → TypeError). Two reviews found this bug
  independently. Do not build on it until it is fixed.
- **`process.py` Service ids can collide** — `remove_service()` decrements `service_count`,
  and `add_service()` uses that count to mint the next id. Thus add→remove→add reuses the id
  and topic path of a live Service.
- **`process.py topic_matcher()` is narrower than MQTT wildcard semantics** — `#` matches
  exactly one extra level, and `+` compares only the first and last tokens (`a/+/c` also
  matches `a/x/y/c`). Subscriptions use real MQTT semantics. Thus dispatch can drop
  deliveries or over-match them.
- **`Stream.set_state()` can downgrade ERROR to RUN** — the `if / if-else` chain makes the
  do-not-downgrade guards ineffective (the correct form is `if/elif`).
- **Never write `self.share[…]` directly** — always use `ec_producer.update()`. Direct writes
  (`ActorImpl.run()` "running", `PipelineImpl.set_parameter()`) are invisible to remote
  observers and the Dashboard.
- **ECProducer incremental updates are f-string-built, not `generate()`-encoded** — values
  that contain spaces or nesting do not round-trip. Snapshot and incremental encodings can
  disagree for the same value.
- **`event.py remove_timer_handler()` can remove the wrong timer** when one function backs
  several timers — use distinct bound methods per timer (Lease uses this pattern).
- **Registrar election is fragile under partition** (stale retained `(primary found …)`,
  simultaneous self-promotion). Also, registrar timestamps use `time.monotonic()` — this
  value is meaningless across hosts.
- **Placeholders, not bugs to "fix" casually**: `utilities/metrics.py` does not compile.
  `utilities/probe.py` is a zero-byte file. The `utilities/thread.py` ThreadManager is
  implemented but unwired (ProcessManager carries the `TODO: Use ThreadManager`).
- **`elements/gstreamer/utilities.py` ships a live `breakpoint()`** (in the misnamed
  `has_h263_support()`). The link-failure paths in `video_stream_reader.py` raise `NameError`
  instead of an error report. Do not assume that the GStreamer error paths work.
- **`elements/utilities/elements.py` uses `eval()`** to convert list literals in Expression
  `define` parameters. Treat PipelineDefinition parameters as a code-execution surface until
  a replacement lands (for example, `ast.literal_eval`). Its comparison-operator regex also
  breaks `<=` and `>`.
- **PipelineElement parameters arrive uncoerced** — CLI/JSON strings stay strings (`"false"` is
  truthy, `"2"` breaks `%`). Also, `get_parameter()` keys are case-sensitive (committed
  pipelines use UPPERCASE keys as an undocumented disable trick). Coerce and validate in
  every element.
- **Several committed example PipelineDefinitions cannot load as-is** — do not treat them as
  regression baselines. `colab_ds_pipeline_0.json` deploys from the nonexistent module
  `aiko_services.elements.colab.elements`. `pipeline_encode.json` deploys from the nonexistent
  `...pipeline.test_elements`. `pipeline_transcription.json` names an undefined `PE_Speaker`.
  Every speech microphone/speaker JSON deploys classes from the disabled (string-quoted)
  legacy block in `audio_io.py`. A definition-validation test can catch all of these problems.
- **`examples/colab/elements.py:53` uses a PEP 701 nested-quote f-string.** An import of the
  colab package is a `SyntaxError` below Python 3.12. This break contradicts the repo
  claim of Python 3.9.7+ support. The file also keeps ChatGPT citation artifacts
  (`:contentReference[oaicite:N]`) in comments.
- **`examples/xgo_robot/` is largely mocked** — every actuator call carries a `# MOCK` comment
  (xgolib blocks all threads). `RobotCore._run()` has a loop-body indentation bug that
  busy-spins and ignores `sleep_period` (xgo_robot.py:210-219). The video publisher and
  subscriber topic pair disagree (`{namespace}/video` compared with
  `{namespace}/{robot_name}/video`).
- **Examples stop Actors with a raised `SystemExit` inside handlers** — `ku()` in aloha_honua
  2/3, and the spoken "terminate" kill switch in `PE_WhisperX.process_frame()`
  (speech_elements.py:258). This stop is abrupt, with no lifecycle transition. Do not copy
  the pattern.
- **`examples/pipeline` PE_DataDecode calls `np.load(..., allow_pickle=True)` on frame data**
  (elements.py:237) — a second code-execution surface alongside the Expression `eval()`.
  Treat inter-Pipeline frame payloads as untrusted.

---

# PRD (condensed) — for spec-driven / Spec-Kit workflows

**Product:** Aiko Services — distributed embedded framework for AI/ML + media + IoT + robotics.

**Users:** edge/robotics/AIoT developers, commercial teams that build cloud+edge AI products, a
small OSS community, and AI coding assistants that operate the codebase.

**Problem:** existing stacks force a choice between datacenter-shaped distributed systems (heavy,
RPC-with-futures, cloud-assumed) and embedded/robotics middleware (DDS complexity, poor
WAN/wireless behavior). None unify agents + dataflow + IoT + robotics on one edge-frugal,
language-neutral, observable substrate.

**Solution / value:** one set of primitives — discovery, one-way messaging, eventually-consistent
state, declarative dataflow, composition of interfaces. The primitives are reused everywhere,
deployable on a Pi, and implementable in any language at the wire level.

**Differentiators:** (1) declarative topology *as data on the same message substrate that the
actors inhabit* (homoiconic — this property enables governed runtime self-modification). (2) An
integrated four-domain fabric (agents/IoT/robotics/media). (3) Protocol-level asynchrony →
genuine language-agnosticism. (4) Edge frugality.

**Non-goals:** datacenter-only scale-out, language-locked APIs, synchronous RPC semantics, and a
heavy management plane.

**Top requirements (current):** R1 reliable discovery & registration. R2 one-way messaging +
reply-through-message. R3 EC shared state with leases. R4 declarative pipelines with typed ports.
R5 lifecycle/process management. R6 composition/interface substitutability. R7 edge-frugal
footprint. R8 multi-language wire protocol.

**Quality gates (target, mostly not yet met — see review):** conformance golden traces, CI
matrix + integration, typed public API, formal protocol spec, pipeline schema validation, and
protocol-level security.

# Spec-Kit seed — interface-first specification index

Treat each core Interface as a spec unit (the signature is the contract, and the behavior is
normative prose + a golden trace). Priority order for the specs:

1. **Wire protocol** (S-expr grammar with the ZMQ binary side-channel, topic namespace
   `namespace/host/pid/sid`, Registrar add/remove/query, EC snapshot+update, lease grant/extend/
   expire, lifecycle handshake).
2. **`Service` / `Actor`** (registration, mailbox dispatch `(command args) -> getattr`, control
   verbs, tags).
3. **`PipelineElement` / `Pipeline`** (stream lifecycle, `process_frame -> (StreamEvent, dict)`,
   definition JSON schema with typed-port validation).
4. **`Registrar`, `ProcessManager`, `LifeCycleManager/Client`, `Storage`, `TransportMQTT`,
   `Category`, `HyperSpace`, `Dependency`, `Recorder`** (each: abstract surface + message sequences).
5. **To-be-designed:** `ECProducerInterface`/`ECConsumerInterface`, `Agent`, `McpGateway`/
   `McpClient`.

Each spec unit must state these five items:

- The protocol id and version
- The methods (one-way, unless a declared reply interface exists)
- The exposed EC state keys
- The failure behavior
- A conformance trace fixture
