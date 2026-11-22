#!/usr/bin/env bash
#
# Run a command again each time it exits, after a pause.
#
# Usage: respawn.sh SECONDS COMMAND [ARGUMENT ...]
#
# The ProcessManager does not yet relaunch a process that exits: its
# "--watchdog" option is recorded, not acted on, and systemd restarts only
# the ProcessManager itself.  This wrapper keeps one process running until
# the ProcessManager stops it.  SIGTERM or SIGINT is passed to the command,
# then the wrapper exits.

set -u
if [ $# -lt 2 ]; then
    echo "Usage: respawn.sh SECONDS COMMAND [ARGUMENT ...]" >&2
    exit 2
fi
pause=$1
shift

child=0
stop() {
    if [ "$child" -ne 0 ]; then
        kill -TERM "$child" 2>/dev/null
        wait "$child" 2>/dev/null
    fi
    exit 0
}
trap stop TERM INT

while true; do
    "$@" &
    child=$!
    wait "$child"
    status=$?
    child=0
    echo "respawn.sh: \"$*\" exited, status $status: restart in $pause s" >&2
    sleep "$pause" &
    child=$!
    wait "$child"
    child=0
done
