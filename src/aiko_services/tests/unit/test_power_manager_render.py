# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_render.py
#
# Unit tests for the files that the operating system must hold
# (actors/power_manager/render.py).
#
# render() is pure, so most of these compare text.  The shutdown hook is
# different: it is a shell script whose one job is to do nothing on a
# restart, so the tests **run it**, with a stub pin utility that records its
# arguments.  A test that only read the script would pass while the script
# was wrong.

import os
import shutil
import stat
import subprocess

import pytest

from aiko_services.actors.power_manager import (
    ARTIFACTS, GRANT_PATH, HOOK_PATH, InstallRefused, RELEASE_ACTIONS,
    UNIT_PATH, install, paths, render, verify,
)

def stub_tool(directory, record):
    """A stand-in for the pin utility: it appends its arguments to a file"""

    path = directory / "pinctrl"
    path.write_text(f'#!/bin/sh\necho "$@" >> "{record}"\n')
    path.chmod(0o755)
    return str(path)

def run_hook(tmp_path, action, delay=0):
    """Render the hook, run it for one action, and return what the pin
    utility was asked to do"""

    record = tmp_path / "calls"
    tool = stub_tool(tmp_path, record)
    hook = tmp_path / "aiko_power_off"
    hook.write_text(render("hook", pinctrl=tool, delay=delay))
    hook.chmod(0o755)
    subprocess.run(["sh", str(hook), action], check=True, timeout=30)
    return record.read_text().splitlines() if record.exists() else []

def unit_commands(text):
    """The unit's commands, in the order systemd runs them, with the
    directive and any "-" stripped.  A oneshot cannot be run here, so the
    order is read from the text: that order is the whole claim, because a
    sound before the hold would tell an operator the opposite of the truth"""

    commands = []
    for line in text.splitlines():
        for directive in ("ExecStart=", "ExecStartPost="):
            if line.startswith(directive):
                commands.append(line[len(directive):].lstrip("-"))
    return commands

# What there is ------------------------------------------------------------ #

def test_three_artifacts_and_no_more():
    assert ARTIFACTS == ("unit", "hook", "grant")

def test_an_unknown_artifact_raises():
    with pytest.raises(ValueError, match="unknown artifact"):
        render("initrd")

def test_rendering_changes_nothing(tmp_path):
    before = sorted(os.listdir(tmp_path))
    render("unit")
    render("hook")
    render("grant", account="someone")
    assert sorted(os.listdir(tmp_path)) == before

# The start-up unit -------------------------------------------------------- #

def test_the_unit_is_a_oneshot_that_exits():
    """The pin keeps its state after the process exits, which is the whole
    mechanism (ADR-028 decision 5)"""

    text = render("unit")
    assert "Type=oneshot" in text
    assert "op dh" in text

def test_the_unit_names_the_hold_line():
    assert "set 5 op dh" in render("unit", hold_gpio=5)

def test_the_unit_can_name_another_line():
    assert "set 17 op dh" in render("unit", hold_gpio=17)

def test_the_unit_points_at_the_record_of_its_reason():
    assert "ADR-028" in render("unit")

def test_the_unit_sounds_the_booted_pattern(tmp_path):
    """The sound the lead asked for: an operator holding a soft power button
    needs to hear that the hold is on, and therefore that the button can be
    released.  No Actor can say it, because it is wanted seconds before
    Aiko Services starts"""

    commands = unit_commands(render("unit", hold_gpio=5, buzzer_gpio=4))
    assert "/usr/bin/pinctrl set 4 op dh" in commands

def test_the_unit_sounds_the_pattern_only_after_the_hold_is_on():
    """The order is the meaning.  A chirp before the hold would tell an
    operator to let go while the power is still theirs to hold"""

    commands = unit_commands(render("unit", hold_gpio=5, buzzer_gpio=4))
    hold = commands.index("/usr/bin/pinctrl set 5 op dh")
    first_sound = next(index for index, command in enumerate(commands)
        if "set 4" in command)
    assert hold < first_sound

def test_the_unit_plays_the_pattern_from_the_table():
    """signal.py holds the durations, and the unit renders them, so a new
    pattern stays one table entry (ADR-028 decision 3)"""

    from aiko_services.actors.power_manager.signal import PATTERNS

    commands = unit_commands(render("unit"))
    waits = [command for command in commands if "sleep" in command]
    assert [command.split()[-1] for command in waits] == \
        [str(seconds) for seconds in PATTERNS["booted"]]

def test_the_unit_leaves_the_buzzer_line_low():
    """Whatever the pattern ends on, the line does not stay driven: a buzzer
    left on is a host that sounds broken from the moment it is up"""

    assert unit_commands(render("unit", buzzer_gpio=4))[-1] == \
        "/usr/bin/pinctrl set 4 op dl"

def test_a_silent_buzzer_never_fails_the_unit():
    """Every sound line is "-" prefixed.  The unit's job is the hold, and a
    buzzer that is absent or broken must not report the hold as failed"""

    for line in render("unit").splitlines():
        if line.startswith("ExecStartPost="):
            assert line.startswith("ExecStartPost=-"), line

def test_the_unit_can_name_another_buzzer_line():
    assert "set 23 op dh" in render("unit", buzzer_gpio=23)

def test_the_sound_costs_the_boot_only_the_pattern():
    """What the start-up pays for the sound.  The unit is ordered before
    multi-user.target, so this delay is real, and it is bounded by the
    table rather than by anything else"""

    from aiko_services.actors.power_manager.signal import pattern_seconds

    commands = unit_commands(render("unit"))
    waits = sum(float(command.split()[-1])
        for command in commands if "sleep" in command)
    assert round(waits, 3) == pattern_seconds("booted")
    assert waits < 1.0

# The shutdown hook -------------------------------------------------------- #

def test_the_hook_releases_the_hold_on_a_power_off(tmp_path):
    calls = run_hook(tmp_path, "poweroff")
    assert "set 5 op dl" in calls

def test_the_hook_releases_the_hold_on_a_halt(tmp_path):
    assert "set 5 op dl" in run_hook(tmp_path, "halt")

def test_the_hook_does_nothing_on_a_restart(tmp_path):
    """The fault that the learning script had.  A release on a restart stops
    an undocked host that is trying to come back (the plan's S3)"""

    assert run_hook(tmp_path, "reboot") == []

def test_the_hook_does_nothing_on_a_kexec(tmp_path):
    assert run_hook(tmp_path, "kexec") == []

def test_the_hook_does_nothing_for_an_action_it_does_not_know(tmp_path):
    assert run_hook(tmp_path, "something-new") == []

def test_the_hook_sounds_three_chirps_before_the_release(tmp_path):
    calls = run_hook(tmp_path, "poweroff")
    assert len([call for call in calls if call == "set 4 op dh"]) == 3
    assert calls.index("set 5 op dl") == len(calls) - 1

def test_the_hook_leaves_the_buzzer_off(tmp_path):
    calls = run_hook(tmp_path, "poweroff")
    buzzer = [call for call in calls if call.startswith("set 4")]
    assert buzzer[-1] == "set 4 op dl"

def test_the_hook_waits_before_the_release():
    """The kernel needs time to finish after the hook returns, and the wait
    is never zero in what is installed"""

    assert "sleep 2.0" in render("hook")

def test_every_command_in_the_hook_is_an_absolute_path():
    """The hook runs when almost nothing else does.  "sleep" is a program
    and not a shell built-in, so a bare name would depend on a PATH that
    the shutdown environment may not have set"""

    for line in render("hook").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("set "):
            continue
        if line in ("case \"$1\" in", "esac", "*) exit 0 ;;") or  \
            line.endswith(") ;;"):
            continue
        assert line.startswith("/"), line

def test_the_hook_waits_with_an_absolute_sleep():
    assert "/usr/bin/sleep 2.0" in render("hook")

def test_the_hook_can_name_another_sleep():
    assert "/bin/sleep 2.0" in render("hook", sleep="/bin/sleep")

def test_the_hook_names_only_the_actions_that_stop_the_host():
    text = render("hook")
    for action in RELEASE_ACTIONS:
        assert action in text
    assert "reboot)" not in text

# The grant ---------------------------------------------------------------- #

def test_the_grant_needs_an_account():
    with pytest.raises(ValueError, match="account"):
        render("grant")

def test_the_grant_names_the_account_it_was_given():
    assert render("grant", account="some_account").count("some_account") == 2

def test_the_grant_holds_two_commands_and_no_more():
    lines = [line for line in render("grant", account="pi").splitlines()
        if line and not line.startswith("#")]
    assert len(lines) == 2

def test_the_grant_uses_absolute_paths():
    for line in render("grant", account="pi").splitlines():
        if "NOPASSWD" in line:
            command = line.split("NOPASSWD:")[1].strip()
            assert command.startswith("/"), command

def test_the_grant_holds_no_wildcard():
    """A wildcard in a mount command grants far more than one mount point"""

    for line in render("grant", account="pi").splitlines():
        if "NOPASSWD" in line:
            assert "*" not in line

def test_the_grant_never_grants_everything():
    text = render("grant", account="pi")
    assert "NOPASSWD: ALL" not in text
    assert "ALL=(ALL) ALL" not in text

def test_the_grant_lines_come_from_the_granted_command_vectors():
    """sudo matches a command and its arguments literally, so whatever runs
    them must use the same vectors.  One source of truth, or the grant and
    the caller drift apart"""

    from aiko_services.actors.power_manager.render import granted_commands

    text = render("grant", account="pi")
    for command in granted_commands():
        assert " ".join(command) in text

def test_the_remount_avoids_a_comma():
    """A comma separates commands in a sudoers file.  "-o remount,ro" needs
    an escape, and an escape that a later edit drops turns one command into
    two"""

    for line in render("grant", account="pi").splitlines():
        if "NOPASSWD" in line:
            assert "," not in line

def test_the_grant_can_name_another_mount_point():
    text = render("grant", account="pi", mount_point="/data")
    assert "remount -o ro /data" in text

# Installing --------------------------------------------------------------- #

def test_installing_writes_the_text(tmp_path):
    path = tmp_path / "unit"
    install("unit", render("unit"), path=str(path))
    assert path.read_text() == render("unit")

def test_the_unit_is_readable_and_the_hook_is_executable(tmp_path):
    unit, hook = tmp_path / "unit", tmp_path / "hook"
    install("unit", render("unit"), path=str(unit))
    install("hook", render("hook"), path=str(hook))
    assert stat.S_IMODE(unit.stat().st_mode) == 0o644
    assert stat.S_IMODE(hook.stat().st_mode) == 0o755

def test_the_grant_is_installed_at_0440(tmp_path):
    path = tmp_path / "grant"
    install("grant", render("grant", account="pi"), path=str(path))
    assert stat.S_IMODE(path.stat().st_mode) == 0o440

def test_nothing_is_left_behind_by_an_install(tmp_path):
    """The write is atomic, so no temporary file survives it"""

    install("unit", render("unit"), path=str(tmp_path / "unit"))
    assert sorted(os.listdir(tmp_path)) == ["unit"]

def test_an_empty_artifact_is_refused(tmp_path):
    with pytest.raises(InstallRefused, match="did not validate"):
        install("unit", "   ", path=str(tmp_path / "unit"))

def test_a_grant_that_grants_everything_is_refused(tmp_path):
    with pytest.raises(InstallRefused, match="more than the two"):
        install("grant", "pi ALL=(ALL) NOPASSWD: ALL\n",
            path=str(tmp_path / "grant"))

@pytest.mark.skipif(
    not (shutil.which("visudo") or os.access("/usr/sbin/visudo", os.X_OK)),
    reason="visudo is not installed here")
def test_a_malformed_grant_is_refused(tmp_path):
    """A malformed file in the sudoers directory denies every account the
    privilege to repair it, and a host with no console cannot be repaired"""

    with pytest.raises(InstallRefused):
        install("grant", "this is not sudoers syntax at all\n",
            path=str(tmp_path / "grant"))

def test_a_valid_grant_passes_the_check(tmp_path):
    path = tmp_path / "grant"
    install("grant", render("grant", account="root"), path=str(path))
    assert path.exists()

def test_a_directory_that_does_not_exist_is_refused(tmp_path):
    with pytest.raises(InstallRefused, match="does not exist"):
        install("unit", render("unit"),
            path=str(tmp_path / "absent" / "unit"))

def test_installing_an_unknown_artifact_raises(tmp_path):
    with pytest.raises(ValueError):
        install("initrd", "text", path=str(tmp_path / "x"))

# Verifying ---------------------------------------------------------------- #

def test_verify_reports_every_artifact():
    assert sorted(verify()) == ["grant", "hook", "unit"]

def test_verify_reports_what_is_absent(tmp_path):
    where = {name: str(tmp_path / name) for name in ARTIFACTS}
    assert set(verify(where).values()) == {"missing"}

def test_verify_reports_what_is_there(tmp_path):
    where = {name: str(tmp_path / name) for name in ARTIFACTS}
    (tmp_path / "hook").write_text("#!/bin/sh\n")
    states = verify(where)
    assert states["hook"] == "installed"
    assert states["unit"] == "missing"

def test_verify_uses_nothing_that_it_reports(tmp_path):
    """It reads, and never runs the hook or the utility"""

    where = {name: str(tmp_path / name) for name in ARTIFACTS}
    (tmp_path / "hook").write_text("#!/bin/sh\nexit 3\n")
    (tmp_path / "hook").chmod(0o755)
    assert verify(where)["hook"] == "installed"

def test_the_default_paths_are_where_the_operating_system_looks():
    where = paths()
    assert where["unit"] == UNIT_PATH
    assert where["hook"] == HOOK_PATH
    assert where["grant"] == GRANT_PATH
    assert where["hook"].startswith("/usr/lib/systemd/system-shutdown/")

# --------------------------------------------------------------------------- #
