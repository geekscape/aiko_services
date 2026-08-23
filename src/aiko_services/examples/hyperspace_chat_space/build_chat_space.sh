#!/bin/zsh
#
# Build the "chat_space" HyperSpace used by Aiko Chat, from an empty directory.
#
# Every command runs in bootstrap mode (-b), directly against the file-system,
# so no MQTT broker, Registrar or Storage Service is required.
#
# Usage
# ~~~~~
#   ./build_chat_space.sh [TARGET_DIRECTORY]    # default: ./chat_space
#
# The result is the Category structure that ChatServer expects, where
# "chat_server.py" reads its channel list:
#
#     self.hyperspace = aiko.HyperSpaceImpl.create_hyperspace("chat_space")
#     self.channels   = self.hyperspace.share["entries"]["channels"]
#
# To Do
# ~~~~~
# - Persist each Dependency's ServiceFilter. Storage writes a 0-byte file for
#   a Dependency, so protocol, transport, owner and tags do not survive a
#   restart and "list" reports "*" for every one of them.
# - "link" into a Dependency raises out of click, rather than reporting that
#   an Entry path cannot descend through a leaf.

set -e

TARGET=${1:-chat_space}

# Predictable incrementing UIDs, so a second run is comparable with the first.
export STORAGE_RANDOM_UID=False

mkdir -p $TARGET
cd $TARGET

# Create "_hyperspace_/" (the content-addressed store) and the ".root"
# symbolic link, which every Entry resolves its own links through.
aiko_storage_file initialize

# Categories are directories. Each one is minted under a UID in the store,
# then linked into the graph under its human-readable name.
aiko_storage_file create channels -b
aiko_storage_file create agents   -b

# Dependencies are files. Each channel is a Service reference, and a channel
# name is also the MQTT topic suffix ChatREPL subscribes to:
#   f"{chat_server_topic_path}/{channel}"
aiko_storage_file add channels/general  -b
aiko_storage_file add channels/robotics -b

# An Agent, in its own Category.
aiko_storage_file add agents/nickba -b

# The same Entry, linked into a second Category. This mints no UID and copies
# no content: one Entry, two paths, which is what makes the structure a graph
# rather than a tree.
aiko_storage_file link channels/nickba agents/nickba -b

echo "\n--- The graph: 6 names ---"
aiko_storage_file list -r -b

echo "\n--- The store: 5 Entries, because nickba is linked twice ---"
aiko_storage_file dump -b
