# HyperSpace example

## Overview

HyperSpace organizes [Services](../../main/service.py) as a distributed
[hyperlinked](https://en.wikipedia.org/wiki/Hyperlink) graph,
which is backed by the local file-system for persistent storage

HyperSpace enables the interconnection and navigation of a distributed system
of Services, Actors, Agents and Pipelines, as if they were (highly dynamic)
Web pages

## Instructions

- Install Aiko Services and activate the Python virtual environment ...
  see [instructions](../../../../ReadMe.md#installation), which enables
  the `aiko_hyperspace` command

- Change the current working directory to this HyperSpace example directory

```
$ cd src/aiko_services/examples/hyperspace
```
- Initialize this prexisting (via GitHub) HyperSpace example local file-system storage

```
$ aiko_hyperspace initialize
```
- Show the `aiko_hyperspace` command help and the `ls` sub-command help

```
$ aiko_hyperspace --help
Usage: aiko_hyperspace [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  initialize  Initialize HyperSpace: .root and storage/
  ln          Create new link to an existing node or category
  ls          List nodes (files) and categories (directories)
  ls_storage  List node storage/tracked_paths and linked nodes
  mk          Create a node (file)
  mkdir       Create a category (directory)
  rm          Remove a node or category

$ aiko_hyperspace ls --help
Usage: aiko_hyperspace ls [OPTIONS] [PATH]

  List nodes (files) and categories (directories)

Options:
  -l, --long_format  Long format with hash identifiers
  -n, --node_count   Show category's node count
  -r, --recursive    Recursive listing
  --help             Show this message and exit.
```
- Show the HyperSpace nodes (files) and categories (directories) ...
  along with their [unique identifiers](https://en.wikipedia.org/wiki/Unique_identifier)

```
$ aiko_hyperspace ls -l -n -r
8e/14/68/53/d2/05  devices/
b1/c8/8a/11/cf/ce  federation/
41/b7/28/9e/9d/4d    local/
80/8a/15/6a/5f/35  locations/
67/ad/58/46/43/92    home/
5b/07/c7/a1/74/e4  services/
8a/bb/6c/a7/5b/ef    hyperspace/
fa/9d/cb/77/69/32    mosquitto
a1/40/6b/c4/3f/7a    process_manager/ (1)
2c/3e/18/a4/11/2a    recorder
6c/07/82/14/a4/76    registrar
71/bf/ee/ee/a6/25    storage_manager/
```
