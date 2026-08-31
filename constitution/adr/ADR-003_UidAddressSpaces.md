---
title: "ADR-003 — HyperSpace/Storage UID address-space allocation"
description: Reserves 48-bit UID address spaces MAC-style — leading nibble 0
  for Aiko Services development (sub-classed by governance tier), leading
  nibble f for future development, all other leading nibbles for third
  parties — and defines the class-octet / identity-octets split
type: adr
audience: [project-lead, architects, developers, ai-coding-agents]
status: normative
ste: adapted
related: [ReadMe, ../p_00_DesignPrinciples]
last_updated: 2026-09-01
---

# ADR-003 — HyperSpace/Storage UID address-space allocation

## Context

HyperSpace/Storage entry UIDs gain a third generation mode: (1) random,
(2) predictable one-up integers for debugging, (3) caller-specified. A
caller-specified storage identity can equal a registry identity, for
example a Nomic(Law) rule number. Caller-specified UIDs need an allocation policy:
who may mint what, and how third-party entries stay collision-free from
constitutional ones. The proven model is the IEEE MAC address registry —
an authority prefix plus a device identity.

## Decision

**Core scheme.** UIDs are 48 bits, written as six colon-separated octets
(`hh:hh:hh:hh:hh:hh`). Three allocation modes exist — random, automatic
one-up, and specified. The leading nibble allocates the address space,
and each space carries its own **default mode**:

| Leading nibble | Space | Use | Default mode |
|---|---|---|---|
| `0` | **Aiko Services development** | Constitutional and framework entries, sub-classed by governance tier (immutable / core / epochal) | **specified** |
| `1`–`e` | **Third parties** | Free for external use — self-minted; a prefix registry may follow when element packaging lands | **random** |
| `f` | **Aiko Services future** | Reserved for future development and other purposes | **specified** |

The defaults are themselves a guard: nothing lands in a reserved space by
accident, because reserved spaces are never randomly minted by default —
entering them takes a deliberate, specified act. Automatic one-up remains
available in every space as an explicit debugging configuration.

**Extension scheme (longer UIDs).** An Aiko Application may adopt any UID
definition its needs dictate: a longer hexadecimal number, RFC 9562 UUIDs
(UUIDv7 timestamp+random, UUIDv4 random, or any of the eight defined
versions), or any byte encoding of any length. Two rules bind every
extension:

1. **The core scheme is a subset of any extended scheme.** The 48-bit
   allocation above stays valid and meaningful inside the longer format.
2. **Embedding is left-justified, space-padded.** A core UID extends by
   prepending it — core octets at the most-significant end — with the
   padding fill **matching the space marker**: a `0`-space core UID pads
   the remainder with `0` nibbles, and an `f`-space core UID pads with
   `f` nibbles. The leading-nibble classification therefore survives
   extension unchanged. The two reserved spaces occupy the extremes of
   any extended number space. Aiko Services development sits at the very
   bottom, Aiko Services future at the very top, and third parties in
   the broad middle.

*Discriminator note.* Third-party UUIDs of standard versions can begin
with a reserved nibble by their own rules (a contemporary UUIDv7's
leading timestamp bits begin with `0` for the current era, and one
eighth of UUIDv4s begin with `0` or `f` by chance). The test for an
extended Aiko-space UID therefore has two halves. The leading nibble
must be **reserved**, AND the padding tail beyond the core 48 bits must
be **uniformly that space's fill** (all-`0` for the `0` space, all-`f`
for the `f` space). A standard UUIDv4/v7 meets both halves with
probability ≈ 2^-80, negligible by construction. Range classification
in extended schemes always tests both halves of this condition. A store declares its UID scheme in its
configuration (CP-G: a scheme change is a versioned change), and
validation is per scheme.

**Class–identity split (the OUI lesson).** Within a reserved space, the
**high octet carries the class** (space nibble + tier sub-class) and the
**low octets carry the stable identity number**. The identity octets are
frozen — never renumbered, never reused (the registry discipline). A
transmutation (a tier change) rewrites only the class octet. The identity
number persists, and the registry records both forms of the succession.
Identity therefore never depends on class, and class is always mechanically
readable from the address.

**Enforcement.** Caller-specified UIDs are validated against this
allocation: duplicate UIDs are rejected, and a proposer may mint only
within the ranges its declared authority allows. The gate checks
allocation by range comparison at stage 2. The machine constitution
declares per-proposer `uid_ranges`.

## Consequences

- Constitutional entries and third-party entries cannot collide by
  construction. 14/16 of the space belongs to third parties, and each
  reserved space still holds 2^44 identities.
- Governance class is visible in the address itself. Tooling, the gate
  and the committed storage tree can classify an entry without a lookup.
  A CI lint can verify that constitutional entries sit in their range.
- Anti-wireheading gains an addressing form: an entry claiming a
  `0`-space UID is refused unless the gate minted it.
- Transmutation does not break the frozen-identifier rule, because
  identity lives in the low octets only.
- Third-party self-minting is collision-safe today (random within 44+
  bits). A vendor prefix registry, when the shareable-element ecosystem
  needs one, extends this table rather than replacing it.

## Evidence trail

Storage UID mode 3 (E1 plan revision 11) and the address-space reservation
directed by the project lead (2026-08-27). Precedents: IEEE OUI/EUI-48
allocation, RFC 1918 reserved ranges, RFC 4122 variant/version bits. P10
(stand on established theory), P8 (identity as declarative data), registry
discipline (t_03 — registries own numbers, and identifiers are frozen).
