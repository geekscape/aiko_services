---
title: Parser utility (S-expressions)
description: The S-expression generate()/parse() pair that defines the wire
  format of every Aiko Services message — lists, dictionaries, canonical
  length-prefixed symbols and the "0:" None sentinel
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/parser.py
related: [design_overview, service, actor, share, registrar, graph]
version: "0.6"
last_updated: 2026-07-05
---

# Parser utility (S-expressions)

## Overview

The parser utility implements the **wire format of every Aiko Services
message**: an S-expression of the shape `(command parameter ...)`.
`generate()` turns a Python command and parameters into an S-expression
payload string; `parse()` turns a payload string back into a
`(command, parameters)` pair. The two functions are designed to be each
other's inverse:

```
parse(generate(command, parameters)) --> command, parameters
generate(parse("(s expression)"))    --> "(s expression)"
```

Every [Service](../service.md) function call that travels over MQTT — an
[Actor](../actor.md) command on `topic_in`, a [Registrar](../registrar.md)
add/remove, an [ECProducer/ECConsumer](../share.md) update — is one of
these S-expressions. That makes this small module the single most
load-bearing utility in Aiko Services: the payload grammar described here
is the public contract between all processes.

**Why you'd use it**: any time you handle a raw MQTT payload or build one.
For example, `ActorImpl._topic_in_handler()` dispatches every incoming
message with one call:

```python
from aiko_services.main.utilities import generate, parse

command, parameters = parse(payload_in)   # "(control log DEBUG)" -->
                                          # "control", ["log", "DEBUG"]
payload_out = generate("invoke", ["item_1", ["item_2a", "item_2b"]])
                                          # "(invoke item_1 (item_2a item_2b))"
```

## For application developers

### Command-line usage

There is no console script; running the module directly executes a
round-trip self-test over a range of example payloads:

```bash
cd src/aiko_services/main/utilities
./parser.py
# (a 0: b) --> command: a, parameters: [None, 'b']
# a, [None, 'b'] --> payload: (a 0: b)
# ...
```

### Public API

```python
__all__ = ["generate", "parse", "parse_float", "parse_int", "parse_number"]

def generate(command: str, parameters: Union[Dict, List, Tuple]) -> str
def parse(payload: str, car_cdr=True, dictionaries_flag=True)
def parse_float(payload: str, default: float=0.0) -> float
def parse_int(payload: str, default: int=0) -> int
def parse_number(payload: str, default: int=0)       # int, else float
```

**Generating.** `generate()` prepends `command` to the parameters
(a dict is flattened to `keyword: value` pairs first) and renders the
whole expression recursively:

```python
generate("add", ["topic", "protocol", "owner", ["a=b", "c=d"]])
# "(add topic protocol owner (a=b c=d))"

generate("topic", {"a": 1, "b": [1, 2]})
# "(topic a: 1 b: (1 2))"

generate("cmd", ["has space", "", None, ["x", "y"]])
# '(cmd 9:has space "" 0: (x y))'
```

Rendering rules, in order:

- A string containing a delimiter — whitespace, `(`, `)` — or *starting
  with* `digits:` is emitted as a **canonical S-expression symbol**,
  prefixed with its byte length: `has space` becomes `9:has space`
  (see [Canonical S-expressions](https://en.wikipedia.org/wiki/Canonical_S-expressions)).
- A dict becomes alternating `keyword:` / value tokens; a list or tuple
  becomes a nested `( ... )`.
- The empty string becomes `""`.
- `None` becomes the sentinel **`0:`** — a zero-length canonical symbol.
  This is how *None* travels inside S-expressions, and why framework
  CLIs such as the [Category](../category.md) `update` command use `0:`
  to mean "leave unchanged".
- Everything else (int, float, bool, ...) is emitted via its `str()` form.

**Parsing.** `parse()` scans the payload character by character,
recursing on `(`, splitting tokens on whitespace, and recognising three
special token forms:

- `LENGTH:DATA` — canonical symbol: the next `LENGTH` characters are one
  token, delimiters included: `parse("(3:a b 3:c d)")` →
  `("a b", ["c d"])`. `0:` yields `None`.
- `'text'` or `"text"` — a quoted string is one token (quotes stripped):
  `parse("('aloha honua')")` → `("aloha honua", [])`. Note that
  *parse* accepts quoted strings but *generate* never emits them — it
  always uses the canonical length prefix — so quoted input does not
  round-trip to identical text (it round-trips to the canonical form).
- `keyword:` — when the first element of a (sub)list ends with `:`, the
  whole list is converted to a dict by `parse_list_to_dict()`:

```python
parse("(a b: 1 c: (d: 1 e: 2))")  # ("a", {"b": "1", "c": {"d": "1", "e": "2"}})
parse("(a (b: ''))")              # ("a", [{"b": ""}])
```

Mixing positional and keyword parameters is illegal and raises
`ValueError`, as does a keyword without a value:

```python
parse("(a b: 1 b)")    # ValueError: ... must have pairs of keywords and values
```

By default the result is split into **car** (the command, first element)
and **cdr** (the parameter list). Two keyword arguments change this:

- `car_cdr=False` returns the single flat list, e.g.
  `parse("(a b)", car_cdr=False)` → `["a", "b"]` — used by
  [Graph](graph.md)`.traverse()` and the Pipeline definition parser.
- `dictionaries_flag=False` suppresses the list-to-dict conversion,
  leaving `keyword:` tokens as plain strings.

**Type fidelity.** Only `None` (as `0:`) survives a round trip with its
type intact. Numbers and booleans are stringified by `generate()` and come
back as strings from `parse()` — `generate("a", [1])` → `"(a 1)"` →
`("a", ["1"])`. That is what `parse_int()`, `parse_float()` and
`parse_number()` are for: tolerant conversions with a default instead of
an exception, e.g. `StreamEvent` handling in `pipeline.py` and parameter
handling in PipelineElements.

**Limits (implemented behaviour):**

- Only complete lists parse: `parse("abc def")` does not return the bare
  atoms (a plain trailing token is appended, but the documented contract
  is "doesn't parse plain symbols, i.e anything not in a (list)").
- A quoted token containing parentheses fails:
  `parse("(c '(this_is_not_a_list)')")`.
- `parse("")` and `parse("()")` both return `("", [])` — callers test for
  a falsy command.

**Real call sites** (both directions of the contract):

```python
# src/aiko_services/main/actor.py — every Actor command arrives here
command, parameters = parse(payload_in)

# src/aiko_services/main/discovery.py — remote proxy invocation
payload = generate(method_name, arguments)
```

Other parse sites: `process.py:on_registrar()`, `registrar.py`
topic handlers, `share.py` (ECProducer/ECConsumer handlers),
`storage.py`. Many payloads elsewhere are still assembled with f-strings
rather than `generate()` — see the roadmap below.

## For framework developers (internals)

### Design

```
   Python values                         wire payload (MQTT)
   ┌──────────────────────┐  generate()  ┌───────────────────────────┐
   │ command: "update"    │ ───────────► │ (update entries.a 9:has   │
   │ parameters:          │              │  space (x y) 0: b: 1)     │
   │  ["entries.a",       │ ◄─────────── └───────────────────────────┘
   │   "has space",       │   parse()      strings, nested lists,
   │   ["x","y"], None,   │                dicts (keyword:), None (0:)
   │   {"b": 1}]          │
   └──────────────────────┘
```

Design points:

- **One grammar, three notations.** Plain symbols, quoted strings and
  canonical `LENGTH:DATA` symbols coexist in the same payload;
  `generate()` normalises everything it emits to plain-or-canonical, so
  the canonical form is the *only* escape mechanism on the wire.
- **The `0:` sentinel is grammar, not convention.** It falls out of the
  canonical symbol rule (a zero-length symbol has no value), and the
  whole framework relies on it — e.g. Category/HyperSpace Entry records
  and "leave unchanged" CLI defaults.
- **Dictionaries are positional pairs.** `(a: 1 b: 2)` is just a list
  whose first token ends in `:`; the dict interpretation happens after
  parsing, in `parse_list_to_dict()`, recursively. This keeps the
  scanner simple but is why positional and keyword parameters cannot mix.
- **car/cdr split at the top.** `parse()` returns
  `(command, parameters)` because virtually every consumer is a message
  dispatcher; the To Do list plans to invert this so `parse()` returns
  the plain tree and a new `parse_payload()` does the split.

### Implementation notes

- `parse()` is a single hand-rolled scanner: an index loop with two
  regex fast-paths tried only at token boundaries —
  `RE_CANONICAL_SYMBOL = ^(\d+):(.+)` (with `re.DOTALL`, so canonical
  data may contain newlines) and `RE_STRING = (['"])(.*?)\1`
  (non-greedy, so quotes cannot be nested or escaped).
- `generate_s_expression()` length-prefixes a string when
  `RE_DELIMITERS = ^\d+:|[\s()]` matches — note the `^\d+:` alternative,
  which protects data that would otherwise *look like* a length prefix.
- The empty-string case is handled by emitting a literal ` ""` separator
  quirk in `generate_s_expression()` (the `character = ' ""'`
  assignment); it round-trips because `RE_STRING` matches `""` as an
  empty token.
- `parse_list_to_dict()` validates pairs strictly (even count, string
  keywords, trailing `:`) and raises `ValueError` — callers that handle
  untrusted payloads should be prepared to catch it.
- `parser_wip*.py` files alongside are work-in-progress scratch versions
  — ignore them; `parser.py` is the module exported via
  `utilities/__init__.py`.

### CRC card

The module is purely functions; one row describes the module itself:

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `parser` (module) | Define the S-expression wire grammar; `generate()` Python values into payloads (canonical escaping, `0:` for None, dict flattening); `parse()` payloads into `(command, parameters)` with dict reconstruction; tolerant numeric conversions (`parse_int/float/number`) | [Service](../service.md) / [Actor](../actor.md) / [Registrar](../registrar.md) / [Share](../share.md) topic handlers (parse); `discovery.py` proxies and [Share](../share.md) (generate); [Graph](graph.md) definitions (`car_cdr=False`) |

## Current limitations and roadmap

From the source `To Do` list — all planned, none implemented:

- Consolidate `generate(command, parameters)` into `generate(tree)` and
  the car/cdr split out of `parse()` into a new
  `parse_payload()` / `generate_payload()` pair, so *any* S-expression
  round-trips, not only `(command ...)` lists
- Provide proper unit tests (there are currently **none** — only the
  `main()` self-test)
- AVRO schema and JSON parsing; consider the `sexpdata` and `hy` /
  `hyrule` Python modules
- Sweep the code base for hand-assembled payloads that should use
  `generate()` — the header names `process.py`
  (`_add_service_to_registrar()`), `recorder.py`, `share.py`
  (`_update_consumers()`) and `transport/transport_mqtt.py` among others

Known behavioural sharp edges (implemented, but easy to trip over):
numbers and booleans do not round-trip typed; quoted strings are
parse-only; quoted tokens cannot contain parentheses; plain symbols
outside a list are unsupported.

## Related concepts

- [Service](../service.md) / [Actor](../actor.md) — every remote function
  call is a parsed S-expression on `topic_in`
- [Share](../share.md) — ECProducer/ECConsumer state updates ride this
  wire format
- [Registrar](../registrar.md) — service (add)/(remove) records
- [Graph](graph.md) — Pipeline graph definitions are parsed with
  `parse(..., car_cdr=False)`
- [Category](../category.md) — documents the `0:` sentinel in Entry
  records and CLI defaults
