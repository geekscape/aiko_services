# Aiko Services StoreForward: partial directory and the final move, no Flask
#
# The helpers are module-level functions of store_forward_http.py, which
# imports without Flask.  The cross-file-system case (os.replace raises
# EXDEV) is reproduced by a wrapped os.replace that fails on demand.
#
#   pytest [-s] unit/test_store_forward_partial.py

import errno
import os

import pytest

from aiko_services.main.store_forward.store_forward_message import (
    PARTIAL_DIRECTORY, partial_path
)
from aiko_services.main.store_forward.store_forward_http import (
    _finish_download, _partial_paths
)

DATA = b"segment-bytes-" * 50

# --------------------------------------------------------------------------- #

def _replace_raising(monkeypatch, *errnos):
    """os.replace raising OSError(errnos[i]) on call i, recording the
    (source, target) of every call"""

    real_replace = os.replace
    calls = []

    def replace(source, target):
        calls.append((source, target))
        if len(calls) <= len(errnos):
            code = errnos[len(calls) - 1]
            raise OSError(code, os.strerror(code), source)
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)
    return calls

def _part(tmp_path):
    inbox = tmp_path / "in"
    parts = tmp_path / "parts"
    inbox.mkdir()
    parts.mkdir()
    part = parts / "0123abcd.part"
    meta = parts / "0123abcd.meta"
    part.write_bytes(DATA)
    meta.write_text('{"name": "a.mp4"}')
    return inbox, part, meta

# --------------------------------------------------------------------------- #

def test_partial_path_default_and_explicit(tmp_path, monkeypatch):
    inbox = tmp_path / "in"
    default = os.path.join(os.path.realpath(inbox), PARTIAL_DIRECTORY)
    assert partial_path(inbox) == default
    assert partial_path(inbox, "") == default
    assert partial_path(inbox, None) == default
    monkeypatch.setenv("HOME", str(tmp_path))
    assert partial_path(inbox, "~/state/parts")  \
        == os.path.realpath(tmp_path / "state" / "parts")

def test_partial_paths_creates_directory(tmp_path):
    parts = tmp_path / "parts"
    part, meta = _partial_paths(str(parts), "0123abcd")
    assert parts.is_dir()
    assert part == str(parts / "0123abcd.part")
    assert meta == str(parts / "0123abcd.meta")

def test_finish_download_same_file_system(tmp_path):
    inbox, part, meta = _part(tmp_path)
    path = _finish_download(str(inbox), "a.mp4", str(part), str(meta))
    assert os.path.realpath(path) == os.path.realpath(inbox / "a.mp4")
    assert os.listdir(inbox) == ["a.mp4"]
    assert (inbox / "a.mp4").read_bytes() == DATA
    assert not part.exists() and not meta.exists()

def test_finish_download_exdev_copies_through_temporary(tmp_path, monkeypatch):
    inbox, part, meta = _part(tmp_path)
    calls = _replace_raising(monkeypatch, errno.EXDEV)
    path = _finish_download(str(inbox), "a.mp4", str(part), str(meta))
    assert (inbox / "a.mp4").read_bytes() == DATA
    assert os.listdir(inbox) == ["a.mp4"]          # no .a.mp4.part left
    assert not part.exists() and not meta.exists()
    assert len(calls) == 2
    assert calls[1] == (str(inbox / ".a.mp4.part"), path)

def test_finish_download_exdev_copy_failure_leaves_nothing(
    tmp_path, monkeypatch):

    inbox, part, meta = _part(tmp_path)
    _replace_raising(monkeypatch, errno.EXDEV, errno.ENOSPC)
    with pytest.raises(OSError) as raised:
        _finish_download(str(inbox), "a.mp4", str(part), str(meta))
    assert raised.value.errno == errno.ENOSPC
    assert os.listdir(inbox) == []                  # temporary removed
    assert part.exists() and meta.exists()          # the caller discards

def test_finish_download_other_error_propagates(tmp_path, monkeypatch):
    inbox, part, meta = _part(tmp_path)
    calls = _replace_raising(monkeypatch, errno.EACCES)
    with pytest.raises(OSError) as raised:
        _finish_download(str(inbox), "a.mp4", str(part), str(meta))
    assert raised.value.errno == errno.EACCES
    assert len(calls) == 1                          # no copy attempted
    assert os.listdir(inbox) == []
    assert part.exists() and meta.exists()
