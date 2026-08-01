---
title: Utility elements
description: The Expression PipelineElement and the expression-evaluation
  helpers — the define, delete and rename commands change Frame swag values
  from S-expression parameters, plus the all_outputs() pass-through helper
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/utilities/elements.py
  - src/aiko_services/elements/utilities/pipelines/pipeline_expression.json
related: [pipeline_element, pipeline, parameters, stream]
version: "0.6"
last_updated: 2026-08-01
---

# Utility elements

## Overview

The utility elements module gives the **Expression**
[PipelineElement](../../concepts/pipeline_element.md) and the expression
evaluator behind it. Expression modifies the Frame's swag — the
accumulated `process_frame()` input and output arguments (see
[Stream](../../concepts/stream.md)) — driven entirely by
[parameters](../../concepts/parameters.md), through three commands:

- `define` — set swag values from expressions: `"((a 0) (b b+1.0))"`
- `delete` — remove swag values: `"(s)"`
- `rename` — rename swag values: `"((b c))"`

The module also exports the evaluator functions `evaluate()`,
`evaluate_condition()` and `evaluate_define()`. The Loop element of the
[control elements](../control/elements.md) reuses them. The module also
exports the `all_outputs()` helper. Pass-through elements use that
helper to forward their declared outputs from the swag. Expression
itself and the [observe elements](../observe/elements.md) are such
elements.

**Why to use it**: to adapt data between elements, and to write no new
Python element. It injects constants, computes derived values, and drops
or renames fields. Thus one element's outputs match the next element's
inputs:

```bash
cd src/aiko_services/elements/utilities
aiko_pipeline create pipelines/pipeline_expression.json -fd "()" -ll debug
# ... inspect_0<*:0> a: 0, b: 1.0, s: hello
# ... inspect_1<*:0> a: 1, c: 2.0, d: {…}, l: […]   (s deleted, b→c)
```

## For application developers

### Command-line usage

Utility elements have no CLI of their own. They are hosted by the
`aiko_pipeline` CLI (see [Pipeline](../../concepts/pipeline.md)). From
the usage header of `elements.py`:

```bash
cd src/aiko_services/elements/utilities
aiko_pipeline create pipelines/pipeline_expression.json -fd "()" -ll debug
```

The commands are ordinary element parameters, so they can also be set
per-Stream or overridden live from the command line:

```bash
aiko_pipeline update p_expression -s 1 -fd "()" \
    -p Expression_0.define "((a 10) (s 'aloha'))"
```

### Public API

```python
from aiko_services.elements.utilities import (
    all_outputs, evaluate, evaluate_condition, evaluate_define, Expression)
```

**`Expression(aiko.PipelineElement)`** — protocol `expression:0`.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `define` | *(optional)* | `"((argument_0 expression_0) (argument_1 expression_1) ...)"` — evaluate each expression against the swag and store it under the argument name |
| `delete` | *(optional)* | `"(argument_0 argument_1 ...)"` — remove each named value from the swag (missing names ignored) |
| `rename` | *(optional)* | `"((from_0 to_0) (from_1 to_1) ...)"` — rename swag entries (missing names ignored) |

- Frame contract: `input: []`. `output` declares the swag names the
  element forwards (through `all_outputs()`), with their types — for example, in
  `pipeline_expression.json`, `Expression_1` outputs
  `a: int`, `c: float`, `d: dict`, `l: [int]`.
- Commands are applied in the fixed order `define`, `delete`, `rename`
  each Frame, regardless of parameter order.
- Returns `StreamEvent.OKAY` with the declared outputs. A declared
  output name absent from the swag raises `KeyError` (no graceful
  diagnostic yet).

**Expression grammar** (from the source comments):

```
expression: expression_0 operator expression_1 ...
expression: integer, float, string, list, dictionary, argument_name
operator:   + - * / < <= > >=
```

Evaluation rules of `evaluate(expression, arguments)`:

- An argument (swag) name evaluates to its current value. Bare digits
  become `int` / `float`. Quoted or identifier-like text becomes a
  string. `[...]` literals become Python lists.
- Binary operators split on the first operator found. `+` also
  concatenates lists, and mixed number/string `+` concatenates as a
  string. Division by zero raises `ValueError`.
- Anything unrecognized is returned unchanged as a string (there is no
  error for a malformed expression).
- Note: the `>` and `<=` operators are currently unreliable — see
  Current limitations and roadmap.

**Helper functions:**

| Function | Role |
|----------|------|
| `all_outputs(pipeline_element, stream)` | Build the `process_frame()` output dict by looking up each name in `pipeline_element.definition.output` in the current Frame's swag |
| `evaluate(expression, arguments={})` | Recursively evaluate one expression string against an arguments dictionary |
| `evaluate_condition(expressions, swag, logger=None)` | Evaluate a parsed list of single-expression lists; `True` only if every result is truthy (used by Loop's `condition`) |
| `evaluate_define(expressions, swag, logger=None, name="Define")` | Evaluate a parsed list of `(name expression)` pairs and assign the results into the swag |

`evaluate_condition()` and `evaluate_define()` take the *parsed* form.
Callers first apply `aiko_services.main.utilities.parse(text,
car_cdr=False)`. Both functions mutate the parsed structure in place, so
parse it again on each use.

## For framework developers (internals)

### Design

```
   parameters                                     Frame swag
   "define": "((a 0) (b b+1.0))" ─ parse() ─┐    {a: …, b: …}
   "delete": "(s)"                          ├─►  define / delete /
   "rename": "((b c))"                      ┘    rename in place
                                                     │
   definition.output  ──────────── all_outputs() ◄───┘
   [{name, type}, …]               forwarded outputs
```

- Expression is a *data-shaping* element: like Loop and Inspect it
  declares `input: []` and works on
  `stream.frames[stream.frame_id].swag` directly, so it can touch any
  value in the Frame without graph rewiring. The `output` list is the
  only declared contract.
- The evaluator is a small recursive-descent interpreter over strings.
  It has no AST and no operator precedence. The *first* operator that a
  regular expression matches splits the string. Each side is then
  evaluated recursively. `parse_number()` (from
  `aiko_services.main.utilities`) coerces operands to numbers where
  possible.
- Keeping the evaluator as module functions (not methods) is deliberate:
  the [control elements](../control/elements.md) Loop reuses
  `evaluate_condition()` / `evaluate_define()`, and future elements can
  do the same.

### Implementation notes

- The operator regular expression is
  `(\+|\-|\*|/|\<|\<=|/>|\>=)`. Because alternation is first-match,
  `\<` shadows `\<=`, and the `=` leaks into the right operand. Plain
  `>` appears only in the suspect `/>` alternative. Thus `<`, `>=` and
  the arithmetic operators work, while `<=` and bare `>` do not.
  `/>` looks like a typo for `\>`.
- List literals are converted with Python `eval()` — do not feed
  Expression parameters from untrusted input until this is replaced.
- Operator matching uses `re.search` over the whole expression, so
  operand strings that contain `-`, `/` and other operators (dates, paths) will be
  split as arithmetic.
- `evaluate_condition()` returns `all(results)`, so an empty or
  non-list `expressions` value is vacuously `True` — a Loop `condition`
  of `"()"` never terminates.
- The module `__all__` misspells `evaluate_condition` as
  `"evaluate_conition"`, which breaks `from ... import *` (the package
  `__init__.py` imports the names explicitly, so it is unaffected).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Expression` | Resolve `define` / `delete` / `rename` [parameters](../../concepts/parameters.md) each Frame; parse and apply them to the Frame swag in fixed order; forward declared outputs | [PipelineElement](../../concepts/pipeline_element.md) (contract); [Stream](../../concepts/stream.md) `Frame.swag`; `parse()` (S-expression parser); `evaluate_define()` / `all_outputs()` (module helpers); [observe elements](../observe/elements.md) `Inspect` (typical companion in graphs) |
| *(module functions)* `all_outputs`, `evaluate`, `evaluate_condition`, `evaluate_define` | Shared expression evaluation and output forwarding for any PipelineElement | [Control elements](../control/elements.md) `Loop`; [observe elements](../observe/elements.md) `Inspect` / `Metrics`; `parse_number()` (`aiko_services.main.utilities`) |

## Current limitations and roadmap

From the source To Do list:

- Expression evaluation support for dictionary or list access
  (`variable[1]`, `variable[index]`) — needs parser improvement for
  `list[index]`
- An extensible list of functions, for example, `random()`, stack `push()` /
  `pop()` — needs parser improvement for function calls
- Common system calls, for example, `/proc`, filesystem, network
- Update Pipeline Stream Event → State. Implement a StateMachine
- Alter Pipeline Graph control flow: conditionals

Additional observed limitations (implemented behavior):

- Operator gaps: `<=` and bare `>` do not evaluate correctly (regular
  expression alternation order and the suspect `/>` alternative — see
  Implementation notes). The grammar comment advertises all of
  `< <= > >=`.
- `__all__` typo `"evaluate_conition"` breaks wildcard imports.
- `eval()` on `[...]` literals is an arbitrary-code-execution risk for
  untrusted PipelineDefinitions or live parameter updates.
- Malformed expressions fall through silently as strings (the
  `ValueError` raise is commented out). There is no expression
  validation at Pipeline start-up.
- `all_outputs()` raises a bare `KeyError` when a declared output is
  missing from the swag.
- No unit tests cover `evaluate()` and friends — a natural first target,
  since they are pure functions.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  Expression implements
- [Pipeline](../../concepts/pipeline.md) — hosts the graph. Planned
  control-flow conditionals would land here
- [Parameters](../../concepts/parameters.md) — how `define` / `delete` /
  `rename` are declared, overridden and resolved
- [Stream](../../concepts/stream.md) — the Frame swag that Expression
  reshapes
- [Control elements](../control/elements.md) — Loop, built on this
  module's evaluator
- [Observe elements](../observe/elements.md) — Inspect / Metrics, users
  of `all_outputs()` and companions in the example Pipeline
