# HyperSpace example: chat_space

Builds the HyperSpace that [Aiko Chat](https://github.com/geekscape/aiko_chat)
uses, from an empty directory, with one command per concept.

`ChatServer` creates this HyperSpace by name and reads its channel list
out of the graph ...

```python
self.hyperspace = aiko.HyperSpaceImpl.create_hyperspace("chat_space")
self.channels   = self.hyperspace.share["entries"]["channels"]
```

## Run it

Every command uses `-b` (`--bootstrap`), which operates directly on the
file-system. No MQTT broker, Registrar or Storage Service is required.

```
$ ./build_chat_space.sh
```

The result ...

```
--- The graph: 6 names ---
agents/
  nickba
channels/
  general
  nickba
  robotics

--- The store: 5 Entries, because nickba is linked twice ---
00/00/00/00/00/00  channels
00/00/00/00/00/01  agents
00/00/00/00/00/02  general
00/00/00/00/00/03  robotics
00/00/00/00/00/04  nickba
```

## What the two listings show

`list` walks the symbolic links, so it reports the graph: six names.
`dump` reads `_hyperspace_/tracked_paths`, so it reports the store: five
Entries. The difference is `nickba`, which is linked from both `agents`
and `channels`.

That is the property which lets one Service belong to several Categories
at once. `link` creates one symbolic link. It mints no UID and copies no
content, so a second membership costs a link and nothing else.

On disk ...

| Concept    | File-system            |
|------------|------------------------|
| Category   | directory              |
| Dependency | file                   |
| Entry name | symbolic link to a UID |
| The store  | `_hyperspace_/`        |
| The index  | `tracked_paths`        |

## Remove and the reference count

Remove one of two links and the Entry survives, because the other link
still reaches it. Remove the last link and Storage reclaims the Entry
and its line in `tracked_paths`.

```
$ cd chat_space
$ aiko_storage_file remove channels/nickba -b   # agents/nickba survives
$ aiko_storage_file remove agents/nickba   -b   # the Entry is reclaimed
```

## To Do

- Persist each Dependency's ServiceFilter. Storage writes a 0-byte file
  for a Dependency, so protocol, transport, owner and tags do not survive
  a restart, and `list` reports `*` for every one of them.
- `link` into a Dependency raises out of `click`. An Entry path cannot
  descend through a leaf, and the command must report that.
- Write `tracked_paths` with one terminator. `add` and `create` end the
  file with a newline. `remove` rewrites it without one.
