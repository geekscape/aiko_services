#!/usr/bin/env python3
#
# Aiko Services: the power log
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# One JSON object for each sample, one to a line, in a file for each UTC
# day: "<directory>/YYYY-MM-DD.jsonl".
#
# The form is chosen for what happens to this file.  A host that loses its
# power in the middle of a write leaves a partial last line, and a reader
# drops one line rather than losing the file.  Any tool reads JSON lines,
# and a column that is absent is still present as null, so a reader does not
# have to guess why.  A day is the rotation, and prune() removes the days
# that are too old to matter.
#
# The writer appends and flushes each line.  A sample is seconds apart, so
# the cost of a flush is nothing, and the value of it is the line that
# survives the power cut that this Actor exists to manage.
#
# To Do
# ~~~~~
# * Write through the Storage Interface, once it has a SQLite3
#   Implementation (ADR-028, the plan's phase 7)

import json
import os
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["PowerLog"]

_SUFFIX = ".jsonl"


class PowerLog:
    """Appends one line for each reading, in a file for each UTC day.

    "directory" is made when the first line is written, and not before: a
    run that logs nothing leaves nothing behind"""

    def __init__(self, directory, keep_days=None):
        self.directory = Path(directory).expanduser()
        self.keep_days = None if keep_days is None else int(keep_days)
        self.lines = 0
        self.last_error = None
        self._path = None
        self._file = None

    def path_for(self, when=None):
        """The file that a reading at "when" belongs in.  "when" defaults to
        now, and it is always read as UTC, so a day does not change with the
        time zone of the host"""

        when = when or datetime.now(timezone.utc)
        return self.directory / f"{when.strftime('%Y-%m-%d')}{_SUFFIX}"

    def write(self, reading, extra=None):
        """One line for "reading", with "extra" merged into it.

        Returns True when the line was written.  An OSError is recorded in
        last_error and returned as False: a log that cannot be written must
        never stop the Actor that reads the battery"""

        record = reading.as_dict()
        if extra:
            record.update(extra)
        try:
            self._open(self.path_for())
            self._file.write(json.dumps(record, sort_keys=True) + "\n")
            self._file.flush()
            self.lines += 1
            return True
        except OSError as error:
            self.last_error = str(error)
            self.close()
            return False

    def prune(self):
        """Remove the day files that are older than "keep_days".  Does
        nothing when keep_days is None.  Returns the names removed"""

        if self.keep_days is None:
            return []
        try:
            names = sorted(path.name for path in self.directory.glob(f"*{_SUFFIX}"))
        except OSError:
            return []
        removed = []
        for name in names[: max(0, len(names) - self.keep_days)]:
            try:
                (self.directory / name).unlink()
                removed.append(name)
            except OSError as error:  # Leave it, and say
                self.last_error = str(error)
        return removed

    def close(self):
        """Close the day file.  The next write opens it again"""

        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
        self._file = None
        self._path = None

    def _open(self, path):
        if self._file is not None and self._path == path:
            return
        self.close()
        os.makedirs(path.parent, exist_ok=True)
        self._file = open(path, "a", encoding="utf-8")
        self._path = path


# --------------------------------------------------------------------------- #
