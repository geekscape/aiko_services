---
title: LRUCache utility
description: A minimal fixed-size least-recently-used cache built on
  OrderedDict, used for log records, audio clips and frame diagnostics
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/lru_cache.py
related: [design_overview]
version: "0.6"
last_updated: 2026-07-05
---

# LRUCache utility

## Overview

`LRUCache` is a small fixed-capacity key/value cache with
least-recently-used eviction: when a `put()` pushes the cache past its
size, the entry that has gone longest without a `get()` or `put()` is
dropped. Aiko Services uses it wherever "keep the most recent N things"
is the right memory policy — recent log records in the Recorder, cached
speech audio, recent frames for Pipeline debugging.

**Why you'd use it**: bound memory while keeping hot entries:

```python
from aiko_services.main.utilities import LRUCache

cache = LRUCache(size=2)
cache.put("key_0", "value_0")
cache.put("key_1", "value_1")
cache.put("key_2", "value_2")   # evicts "key_0" (least recently used)
cache.get("key_0")              # None
cache.get("key_1")              # "value_1" (now most recently used)
"key_1" in cache                # True (via key iteration)
```

## For application developers

### Command-line usage

There is no CLI; the module is exercised by `aiko_recorder` (recent log
records) and by Pipelines with frame diagnostics enabled.

### Public API

```python
class LRUCache:
    LRUCache(size)
    get(key)         # value, or None on miss; refreshes recency
    put(key, value)  # insert/replace; refreshes recency; may evict
    get_list()       # values, least- to most-recently used
    __len__, __iter__ (over keys, which also enables "key in cache")
```

Real call sites:

```python
# src/aiko_services/main/recorder.py — most recent log records
self.lru_cache = LRUCache(_LRU_CACHE_SIZE)

# src/aiko_services/examples/speech/speech_elements.py — audio cache
self._lru_cache = LRUCache(AUDIO_CACHE_SIZE)

# src/aiko_services/main/pipeline.py — recent frames for DEBUG
self.DEBUG[stream_id]["frames_lru"] = LRUCache(size=8)
```

## For framework developers (internals)

### Design

```
   LRUCache(size=3)                    OrderedDict (all ops O(1))
   least recent ── key_a ─ key_b ─ key_c ── most recent
                     ▲                        ▲
        popitem(last=False) on overflow    move_to_end() on get/put
```

A thin veneer over `collections.OrderedDict`: recency is the dict's
insertion order, refreshed with `move_to_end()` and trimmed with
`popitem(last=False)`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `LRUCache` | Bound the collection to `size` entries; evict least recently used; report values in recency order | `collections.OrderedDict`; `recorder.py`, `pipeline.py`, speech elements (users) |

## Current limitations and roadmap

The source has no `To Do` list; observed limitations:

- A miss returns `None`, indistinguishable from a stored `None` value
- Not thread-safe — callers sharing a cache across threads must guard it
  (e.g. with the [Lock](lock.md) utility)
- Membership tests (`in`) fall back to key iteration (O(n)); no
  `__contains__` — and note that `in` does **not** refresh recency
- No unit tests anywhere in the repository
- The source usage header shows `import lru_cache`; in practice import
  from `aiko_services.main.utilities`

## Related concepts

- [Lock](lock.md) — pair with LRUCache for multi-threaded use
- [Design overview](../design_overview.md) — the Recorder, its main
  framework consumer
