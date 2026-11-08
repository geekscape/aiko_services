# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_log.py
#
# Unit tests for PowerLog (actors/power_manager/log.py): one JSON object for
# each sample, one to a line, in a file for each UTC day.
#
# Three properties are the reason for the form, and each one has a test.  A
# partial last line costs one line and not the file.  A column that is
# absent is still there as null.  And a log that cannot be written returns
# False rather than stopping the Actor that reads the battery.

import json
from datetime import datetime, timezone

from aiko_services.actors.power_manager import PowerLog, PowerReading

READING = PowerReading(
    device="pmm", battery_volts=10.047, battery_amps=1.106, battery_watts=11.65, battery_pack_celsius=27.0
)


def lines_of(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_the_day_file_is_named_for_the_utc_day(tmp_path):
    log = PowerLog(tmp_path)
    when = datetime(2026, 11, 5, 23, 30, tzinfo=timezone.utc)
    assert log.path_for(when).name == "2026-11-05.jsonl"


def test_nothing_is_made_until_the_first_line(tmp_path):
    directory = tmp_path / "power_log"
    PowerLog(directory)
    assert not directory.exists()


def test_one_line_for_one_reading(tmp_path):
    log = PowerLog(tmp_path)
    assert log.write(READING) is True
    log.close()
    records = lines_of(log.path_for())
    assert len(records) == 1
    assert records[0]["battery_volts"] == 10.047


def test_extra_is_merged_into_the_line(tmp_path):
    log = PowerLog(tmp_path)
    log.write(READING, extra={"policy": "advisory", "period_s": 5.0})
    log.close()
    assert lines_of(log.path_for())[0]["policy"] == "advisory"


def test_an_absent_column_is_present_as_null(tmp_path):
    log = PowerLog(tmp_path)
    log.write(READING)
    log.close()
    record = lines_of(log.path_for())[0]
    assert "supply_volts" in record and record["supply_volts"] is None


def test_lines_append_and_are_counted(tmp_path):
    log = PowerLog(tmp_path)
    for _ in range(3):
        log.write(READING)
    log.close()
    assert log.lines == 3
    assert len(lines_of(log.path_for())) == 3


def test_a_partial_last_line_costs_one_line(tmp_path):
    """What a power cut in the middle of a write leaves behind"""

    log = PowerLog(tmp_path)
    log.write(READING)
    log.write(READING)
    log.close()
    path = log.path_for()
    text = path.read_text()
    path.write_text(text[:-12])  # Cut the last line short
    good = []
    for line in path.read_text().splitlines():
        try:
            good.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    assert len(good) == 1


def test_a_log_that_cannot_be_written_returns_false(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory")
    log = PowerLog(blocker / "inside")
    assert log.write(READING) is False
    assert log.last_error


def test_prune_does_nothing_without_keep_days(tmp_path):
    log = PowerLog(tmp_path)
    log.write(READING)
    log.close()
    assert log.prune() == []


def test_prune_removes_the_oldest_days(tmp_path):
    log = PowerLog(tmp_path, keep_days=2)
    for day in ("2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"):
        (tmp_path / f"{day}.jsonl").write_text("{}\n")
    assert log.prune() == ["2026-11-01.jsonl", "2026-11-02.jsonl"]
    assert sorted(path.name for path in tmp_path.glob("*.jsonl")) == ["2026-11-03.jsonl", "2026-11-04.jsonl"]


def test_prune_with_no_directory_is_not_an_error(tmp_path):
    assert PowerLog(tmp_path / "absent", keep_days=1).prune() == []


def test_close_then_write_opens_the_file_again(tmp_path):
    log = PowerLog(tmp_path)
    log.write(READING)
    log.close()
    assert log.write(READING) is True
    log.close()
    assert len(lines_of(log.path_for())) == 2


# --------------------------------------------------------------------------- #
