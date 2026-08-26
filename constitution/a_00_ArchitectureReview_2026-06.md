---
title: Aiko Services — Architecture & SDLC Review (v0.6, June 2026)
description: Senior-architect review of v0.6 (~23,000 LOC), continuing the
  February 2026 review; all findings re-derived from current source
type: analysis
audience: [project-lead, architects]
status: informational
ste: false
related: [g_03_AgentContext]
last_updated: 2026-06-15
---

# Aiko Services — Architecture & SDLC Review (v0.6, June 2026)

**Reviewer stance:** senior software architect / engineer, SDLC lens.
**Subject:** `aiko_services` `version = 0.6`, `__id__ = 2026-06-08_a`, reviewed from the uploaded
`master` tarball (~23,000 LOC across 113 Python files). Apache-2.0, author Andy Gelme / Geekscape.
**Continues** the February 2026 review; all findings below are re-derived from the current source,
not memory. Where a claim could not be verified in-tree it is marked **[unverified]**.

---

## 1. Executive summary

Aiko Services is a small, conceptually dense distributed-systems framework whose architecture is
unusually coherent: a single set of primitives (Services discovered via a Registrar, one-way
S-expression messages over MQTT, eventually-consistent shared state, declarative dataflow graphs)
is reused everywhere, including by the framework's own infrastructure. The composition mechanism
(`compose_instance`) and the interface model (`context.Interface`) are the cleverest and most
load-bearing parts of the codebase, and they are sound.

The framework is **production-real but pre-1.0 in its engineering scaffolding**. The gap between
the quality of the *design* and the maturity of the *SDLC apparatus* (tests, CI, type coverage,
formal spec) is the central finding of this review. For a project whose stated ambition is to
become a multi-language standard, that apparatus — not the architecture — is now the binding
constraint.

Three things are worth stating up front because they shape everything else, and all three are
**deliberate and correct**, not deficiencies (per the project's own design intent):

1. **No Python `async`/`await` anywhere in the framework.** Verified: zero `async def` in
   `main/` or `elements/`. Asynchrony is a property of the *distributed protocol* — methods do
   not return values across the wire, interaction is one-way message passing, and consistency is
   eventual. This is the right model for a language-neutral, edge-targeted Actor system, and
   conflating it with language-level concurrency would be a category error.
2. **The framework is not tied to Python.** The wire contract (S-expressions over MQTT, topic
   namespace, EC state protocol) is what matters; Python is one reference implementation, with
   `aiko_engine_mp` (MicroPython/ESP32) as a second, intentionally minimal one.
3. **Application code may still use Python `async`** if it wishes — the framework's single-threaded
   event loop and mailbox model do not forbid it inside user handlers; they simply don't depend
   on it.

The most important *new* observation versus February: there is still **no MCP code anywhere** in
the tree (not even a stub), and **no `Agent` interface** — both are genuinely greenfield, which is
good news for the planned agent/MCP work because there is no legacy to dislodge.

---

## 2. Architecture as built (verified)

### 2.1 The composition core — `context.py` + `component.py`

The foundation is an interface-composition system, not an inheritance hierarchy:

- `Interface(ABC)` carries a class-level `Context()` and a classmethod
  `Interface.default(name, "module.ImplClass")` that registers a *default implementation* for that
  interface in a registry.
- `compose_class(impl_seed_class, impl_overrides)` walks the seed class's MRO, collects every
  ancestor that is a pure interface (all-abstract), looks up each one's registered implementation
  (honouring per-instance overrides), loads those implementation classes, and **grafts their
  methods onto a synthetic `FrankensteinClass`** — replacing abstract methods, preserving concrete
  overrides. `compose_instance` does that and instantiates with a `context` that carries the
  resolved implementation map.
- `Context.call_init(self, "InterfaceName", context)` performs cooperative, once-only
  initialisation of each composed implementation.

This is effectively a **registry-driven trait/mixin system**: behaviour is assembled from
named, independently-substitutable implementations bound behind abstract interfaces. It is the
mechanism that makes "design by composition of interfaces" real, and it is the right substrate for
the eventual MCP tool-surface and for swapping implementations (e.g. a test transport, a lean
embedded Registrar client). It is also the single most subtle piece of the codebase and the least
defended by tests (see §4).

*Observation:* `component.py` itself flags `# BUG: _check_interfaces_implemented() working
correctly ?` and notes that `get_implementations()` "always picks up all the AikoServices
interfaces default implementations." Both are real latent issues in the composition machinery and
deserve targeted unit tests before they bite during the planned refactors.

### 2.2 The interface chain (verified, and it matters)

The actual inheritance among the core interfaces is:

    ServiceProtocolInterface
        └─ Service          (also mixes in Hooks)
            └─ Actor
                └─ PipelineElement
                    └─ Pipeline

with `Category(Actor, Dependency)` and `HyperSpace(Category, Actor)` as further compositions.
**There is no `Agent` interface** in the chain today — confirming that introducing
`Pipeline → PipelineElement → Agent → Actor → Service` is a genuine extension, not a modification.

Two structural notes for the planned work:
- `DataSource` and `DataTarget` (`source_target.py`) inherit from `PipelineElementImpl`
  (the *implementation*), not from the `PipelineElement` *interface*. This is an inheritance-of-
  implementation shortcut that mildly violates the otherwise-clean interface/impl separation, and
  is worth normalising when `elements/` is touched.
- `Pipeline` *is-a* `PipelineElement`, so pipelines nest — the property the "society of agents"
  framing depends on.

### 2.3 Messaging, discovery, and the proxy (verified)

- **Topic structure:** `namespace/host/pid/sid` (`ServiceTopicPath`, four components), with
  per-service `/in`, `/out`, etc. Topics are derived, not hand-configured.
- **Remote invocation:** `get_service_proxy(topic, ProtocolClass)` returns a proxy whose every
  public method serialises `(method_name args...)` to an S-expression and publishes it to
  `{topic}/in` — fire-and-forget, no return value (verified in `discovery.py`). This *is* the
  distributed-async model in code.
- **Request/response** is built from two one-way messages: `do_request(...)` discovers the target,
  invokes it with a reply topic, and collects the reply via a message handler using a
  `DiscoveryResponse`-style `item_count` / `response` convention.
- **Two proxy mechanisms coexist:** `discovery.get_service_proxy` (remote, message-based) and
  `proxy.ProxyAllMethods` (a `wrapt.ObjectProxy` that funnels *all* method calls through a single
  `proxy_function`). The latter's own to-do list explicitly anticipates intercepting "remote
  function call, security access, timing, logging" — i.e. it is the designed foundation for the
  MCP tool surface and the dynamic-proxy-to-external-tools work. `discovery.py` notes the intent to
  **consolidate the two**; doing so should precede the MCP build so there is one proxy story.
- **Actor dispatch:** each Actor has a mailbox per topic; `_topic_in_handler` parses the inbound
  S-expression and dispatches by `getattr(target, command)(*args)`. Unknown commands become logged
  diagnostics rather than crashes; handler exceptions are caught and captured with a traceback.
  This is robust, but the catch is currently broad (the code itself warns that catching all
  `TypeError`/`Exception` "hides problems in target_function") — a correctness sharp edge.

### 2.4 Shared state — `share.py` (verified)

`ECProducer` and `ECConsumer` implement the eventual-consistency state protocol: a producer
publishes a state dictionary and streams incremental updates; a consumer maintains a converging
replica with change handlers; leases (`ECLease(Lease)`) bound liveness. `self.share[key] = value`
in an Actor is the ergonomic surface.

**Catalog gap (important):** `ECProducer`/`ECConsumer` are **plain classes, not `Interface`s**.
Every other major capability (Actor, PipelineElement, Registrar, Storage, Transport…) is an
interface with a registered implementation and is therefore substitutable; EC state is not. Given
that EC state is one of the framework's defining primitives and a natural MCP *resource* surface,
promoting it to an interface (`ECProducerInterface`/`ECConsumerInterface`) would restore
consistency and enable alternative backends. `ECProducer.get()` returns a value, but it is local
in-process state access, not a wire call — so it does not violate the no-return-value protocol
rule.

### 2.5 Big-data path (verified, and a strength worth noting)

The media elements (`elements/media/image_io.py`, `text_io.py`) include `ImageReadZMQ` /
`ImageWriteZMQ` / `TextReadZMQ` etc., and `pyzmq` is a core dependency. So Aiko already
**side-channels bulk/binary data over ZeroMQ** rather than forcing it through S-expressions on
MQTT. This is the correct answer to the serialization-overhead critique that the dora-rs lineage
levels at message-passing middleware (see the comparison document), and it should be made explicit
in the protocol spec rather than left as an element-level convention.

### 2.6 Built-in infrastructure as ordinary Services (verified)

Registrar, ProcessManager, LifeCycleManager/Client, HyperSpace, Storage, Recorder, Dashboard, and
the MQTT transport are all themselves Services/Actors composed through the same mechanism — there
is no privileged management plane. This is the "everything is a Service" property holding in
practice, and it is what will make the planned IDE/observability/MCP layers additive rather than
special-cased.

---

## 3. The Interface catalog (verified, with signatures)

Every type below transitively inherits `context.Interface`. Signatures are the **abstract**
methods (the protocol surface); each interface also has a default `…Impl`. Test/example interfaces
(`ActorTest`, `MQTTTest`, `Example`, `LifeCycleManagerTest`, …) are omitted from the core list.

### Core service & actor layer

**`ServiceProtocolInterface(Interface)`** — marker. "This Service implements a protocol." Basis for
protocol-identified discovery.

**`Service(ServiceProtocolInterface, Hooks)`** — the discoverable unit.
```
add_message_handler(self, message_handler, topic, binary=False)
remove_message_handler(self, message_handler, topic)
registrar_handler_call(self, action, registrar)
set_registrar_handler(self, registrar_handler)
run(self)
stop(self)
add_tags(self, tags)
add_tags_string(self, tags_string)
get_tags_string(self)
```
Owns ServiceFields (name, protocol, transport, owner, tags), topic paths, Registrar
registration/deregistration, and tag-based discoverability. Mixes in `Hooks` (AOP).

**`Actor(Service)`** — a Service with a mailbox; messages dispatch one-at-a-time to methods.
```
run(self, mqtt_connection_required=True)
set_log_level(self, level)
```
(The mailbox/dispatch behaviour lives in `ActorImpl`; the abstract surface is intentionally tiny —
an Actor mostly *is* a Service plus message→method dispatch.)

### Dataflow layer

**`PipelineElement(Actor)`** — a stream-processing node.
```
process_frame(self, stream, **kwargs) -> Tuple[StreamEvent, dict]
start_stream(self, stream, stream_id)
stop_stream(self, stream, stream_id)
create_frame(self, stream, frame_data, frame_id=None, graph_path=None)
create_frames(self, stream, frame_generator, frame_id=FIRST_FRAME_ID, rate=None)
get_parameter(self, name, default=None, required=False, use_pipeline=True)
get_stream(self)
get_variables(self)
my_id(self, all=False)
```
`process_frame` returns `(StreamEvent, dict)` **to the in-process Pipeline runtime** — the
deliberate, documented local exception to "no return values" (the distributed boundary is the
Pipeline Actor, not the element call).

**`Pipeline(PipelineElement)`** — interprets a declarative graph definition.
```
create_stream(self, stream_id, graph_path=None, parameters=None, grace_time=_GRACE_TIME,
              queue_response=None, topic_response=None)
destroy_stream(self, stream_id, graceful=False)
process_frame_response(self, stream, frame_data) -> Tuple[StreamEvent, dict]
set_parameter(self, stream_id, name, value)
set_parameters(self, stream_id, parameters)
parse_pipeline_definition(cls, pipeline_definition_pathname)   # classmethod
```
Definitions are JSON: `version`, `name`, `runtime`, a `graph` of S-expression edge strings (e.g.
`"(PE_IN PE_TEXT PE_OUT)"`), and `elements` with typed `input`/`output` ports and
`deploy.local|remote`. Topology-as-data, in the same S-expression syntax as messages.

### Discovery, registry & grouping

**`Registrar(Service)`** — discovery authority (marker interface; behaviour in `RegistrarImpl`:
add/remove/query of ServiceFields, history, share).

**`Dependency(Interface)`** — typed dependency relation.
```
get_type(self)
is_type(self, type_name)
update(self, entry_name, service=None, service_filter=None,
       lifecycle_manager_url=None, storage_url=None)
```

**`Category(Actor, Dependency)`** — a named grouping/registry of entries.
```
add(self, entry_name, service_filter=None, lifecycle_manager_url=None, storage_url=None)
remove(self, entry_name)
list(self, topic_path_response, entry_name=None, long_format=False,
     recursive=False, entry_records=None)
exit(self)
```

**`HyperSpace(Category, Actor)`** — a navigable space of categories (content-addressed store
backing it on disk).
```
create(self, category_path)
destroy(self, category_path)
dump(self)
```

### Lifecycle & process management

**`LifeCycleManager(ServiceProtocolInterface)`**
```
lcm_create_client(self, parameters=None)
lcm_delete_client(self, client_id)
```
with a private companion interface `LifeCycleManagerPrivate` (`_lcm_create_client`,
`_lcm_delete_client`, `_lcm_get_clients`, `_lcm_get_handshaking_clients`,
`_lcm_lookup_client_state`).

**`LifeCycleClient(ServiceProtocolInterface)`** — marker, with private companion
`LifeCycleClientPrivate` (`_lcc_get_lifecycle_manager_topic`,
`_lcc_lifecycle_manager_change_handler`).

**`ProcessManager(Actor)`** — spawns/monitors OS processes hosting Services.
```
create(self, command, arguments=None, uid=None)
destroy(self, uid, kill=False)
list(self, topic_path_response, uid=None)
dump(self)
exit(self, grace_time=_GRACE_TIME)
```

### Storage & transport

**`Storage(Actor)`** — persistent, file-backed entry store (default impl `StorageFileImpl`).
```
initialize(self, storage_url)
create(self, category_name)
add(self, dependency_name, dependency=None)
update(self, entry_name, service=None, service_filter=None,
       lifecycle_manager_url=None, storage_url=None)
link(self, entry_path_new, entry_path_existing)
list(self, topic_path_response, entry_name=None, long_format=False,
     recursive=False, entry_records=None)
remove(self, entry_name)
destroy(self, entry_name)
dump(self, sort_by_name)
exit(self)
```

**`TransportMQTT(Actor)`** — MQTT transport binding (marker interface; `TransportMQTTImpl`
provides connect/publish/subscribe). The transport abstraction exists, with MQTT as the reference;
a second transport (ZMQ for control, or Zenoh) is a plausible addition behind this seam.

**`Recorder(Service)`** — records message traffic (marker interface; `RecorderImpl`). The seed of
persistence/replay and conformance-trace capture.

### Pipeline element library base

**`DataSource(PipelineElementImpl)`** / **`DataTarget(PipelineElementImpl)`** — base classes for
source/sink elements (stream in / stream out). *Note the inheritance from the Impl, not the
interface — see §2.2.*

### Not yet interfaces (gaps)

- **`ECProducer` / `ECConsumer`** — plain classes; should be interfaces (§2.4).
- **No `Agent` interface** — greenfield.
- **No `MCP` server/client interfaces** — greenfield.
- **No explicit `EventLoop`/`Process` interface** — `process.py` is concrete; fine for now, but
  an interface would help alternative runtimes.

---

## 4. SDLC review and prioritised recommendations

The SDLC gap review (§4) and the prioritised recommendation list (§5) of this analysis
are maintained privately [Reserved for private items]. The load-bearing public facts they
produced are already normative elsewhere: the testing reality and methodology in
e_06_TestingStrategy §9, the agent-facing sharp edges in g_03_AgentContext, the composition
audit in the public-API composition rollout [Privately maintained], and the P12 security posture in
adr/ADR-023_GuardedEvalDefaultDeny.
