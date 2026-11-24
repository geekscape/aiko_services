---
title: "ADR-029 — Unreliable links are crossed by StoreForward, and the edge never depends on a remote broker (P13)"
description: Mints P13. Data that crosses a link that is not always available
  goes through StoreForward. An edge process does its work with no remote MQTT
  server, Registrar or other remote service. Records the remote Stream protocol
  over MQTT as a known gap, and the coherent StoreForward layer under remote
  Streams as deferred amendment DA-6
type: adr
audience: [project-lead, architects, developers, ai-coding-agents]
status: normative
ste: adapted
related: [ReadMe, ../p_00_DesignPrinciples, ../p_01_PrinciplesGovernance,
  ../p_02_CandidatePrinciples, ../../documentation/concepts/store_forward,
  ../../documentation/concepts/pipeline, ../../documentation/concepts/lease]
last_updated: 2026-11-24
---

# ADR-029 — Unreliable links are crossed by StoreForward, and the edge never depends on a remote broker (P13)

**Accepted 2026-11-24.** Directed and approved by the project lead in a working session (G2).
The number is claimed in this change.

## Context

Aiko Services targets edge networks, where partitions and lossy links are normal (P4). P1
states that delivery is at-most-once. Neither principle says what a deployment must do when
data must cross such a link and must not be lost.

Remote PipelineElements (`PipelineRemote` in `main/pipeline.py`), remote Streams and the
remote Stream protocol run over MQTT and the Registrar. The remote Stream protocol is the
frame sequences, the Stream states and the function calls between Pipelines. It was not
designed as a protocol. It has no specification, and no tests of link failure. Production
deployments used it across WAN links before that work was done. In one of these deployments,
the edge Pipelines sent their data to a cloud database. They used a remote PipelineElement,
over an MQTT server in the cloud. Each outage of the link or of that server was an outage of the
data path. The design gave no recovery and no guarantee. This deployment shape is a design
and deployment error, and not an operations fault.

The framework now has a mechanism that is better for this case. The `SegmentStoreForward`
Actor (`main/store_forward/`) takes custody of segments across an unreliable link. The sender
keeps a segment on disk until the receiver has verified its sha256. A transfer resumes from
the byte where it stopped. The edge role is a client that polls, so it needs no inbound port.
The `store_forward://` elements (`elements/media/store_forward_base.py`) connect it to
Pipelines. A writer element puts frames into segments in the outbox. A reader element takes
segments from the inbox in sequence order. A commit element moves each segment to `done/`
after the elements before it have applied it. Both the Actor and the Pipelines run with no
MQTT server (`process.run(mqtt_connection_required=False)`, PR #164).

End-to-end tests ran in 2026-11 with the two Actors, a writer Pipeline and a reader Pipeline
on one host, as separate processes, with faults injected. The link was down before the
send, and the link dropped during an upload. Segments arrived out of order, each Pipeline
crashed, the database stopped, and a segment was delivered twice. The tests
found two faults in the reader. An out-of-order arrival lost data, and an idle reader stopped
when its Stream lease expired. Both faults were in new code that had unit tests. This is the
evidence that robustness must be shown by tests of link failure, and not assumed.

## Decision

1. **Adopt P13** in `p_00_DesignPrinciples.md`, in Tier 2 (architecture). The full wording is
   there. In summary:
   - Data that crosses a link that is not always available goes through StoreForward.
   - An edge process does its work with no remote MQTT server, remote Registrar or other
     remote service.
   - A broker and Registrar local to the site are for discovery and visibility. The data path
     never needs them across the link.
   - Documentation, examples and release notes claim only the delivery and robustness that
     tests of link failure have shown.

2. **StoreForward is a layer, not one transport.** The layer has its own protocol: segments,
   a sequence for each writer, segment states, and commit and acknowledgment messages. The
   transport below it is chosen for the link: pull (HTTP, available now) or push (MQTT with
   persistent sessions and acknowledgments, planned). The dataflow elements are above it, so
   a Pipeline gets durability with no change to its shape (P8).

3. **The remote Stream protocol over MQTT is a known gap, not a sanctioned path across
   unreliable links.** Remote Streams have at-most-once delivery (P1), and a Stream is
   destroyed when its lease expires. The framework makes no promise of robustness for them.

4. **DA-6, critically important: one coherent design.** Remote PipelineElements and remote
   Streams are carried over the StoreForward layer. The layer has a pull transport and a push
   transport. A conformance suite of link-failure tests applies to each implementation. At
   least four implementations show the range: text over HTTP, video over HTTP, one push
   transport, and one remote PipelineElement over StoreForward. Per G3, DA-6 is promoted into
   P13 only when the source, tests, documentation and examples comply.

5. **Exception.** Data whose loss is acceptable can use a remote Stream or MQTT directly
   across an unreliable link. The design document must record that choice and why. Examples
   are live telemetry, a live view and a Dashboard.

## In-play assessment (G3)

New code can comply today. `SegmentStoreForward` and the `store_forward://` text elements are
on master, and the video writer element exists. An edge process can run with no MQTT server.

Known violations, to enumerate and schedule:

- `PipelineRemote` and the remote Stream protocol, which have no StoreForward option. This is
  the subject of DA-6.
- The `pipeline_remote.json` example and the remote PipelineElement documentation, which do
  not say that the path is at-most-once and for reliable links only.
- `SegmentStoreForward` keeps its offers, its `/out` cursor and its pending acknowledgments in
  memory (`documentation/concepts/store_forward.md`, "Current limitations"). Persistent state
  is item 1 of its roadmap.
- No test of StoreForward has run on a real WAN link, on Windows, or for longer than some
  minutes.

## Consequences

- Reviews cite P13 for a design or deployment in which an edge process needs a remote broker.
  They also cite it when data crosses an unreliable link without StoreForward.
- New edge deployments use StoreForward for their data path. A local broker and Registrar are
  optional, for visibility.
- Robustness is a claim that tests support, and not a property of the framework. Until DA-6 is
  promoted, documentation calls StoreForward work in progress, and says which failures its
  tests cover.
- The private DA register needs an entry for DA-6 that matches this record.

## Evidence (G5)

- P1 amendment (2026-07-07): delivery is at-most-once. P4: partitions and lossy links are
  normal. P9: no mandatory cloud services in `runtime/`.
- Candidate CP-A (command, then observe) and CP-F (in-band control, out-of-band bulk data),
  in `p_02_CandidatePrinciples.md`. StoreForward agrees with both: segments move out of band,
  and the outcome is observed.
- `documentation/concepts/store_forward.md` and `documentation/elements/media/store_forward_base.md`.
- PR #164 (the text elements and an Actor that runs with no MQTT server) and PR #165.
- The production deployment and the end-to-end fault tests described in the Context section
  (2026-11).
