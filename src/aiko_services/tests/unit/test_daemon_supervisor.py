# Usage
# ~~~~~
# pytest [-s] unit/test_supervisor.py
#
# Unit tests for the Daemon Supervisor (main/daemon_supervisor/): one DaemonDefinition,
# rendered as a systemd unit or a launchd agent.  render() and pathname()
# are pure functions, so they are tested directly.  install(), start(),
# stop() and status() change the host or run a platform command, so they
# are not tested here: they are exercised by hand, see
# documentation/concepts/process_manager.md
#
# The stop timeout matters more than it looks: the operating system must
# wait longer than the ProcessManager waits for its own processes, or the
# ProcessManager is killed while its processes are still stopping.  There
# is a negative test for that (ADR-014).

import pytest

import aiko_services as aiko
from aiko_services.main.daemon_supervisor import (
    GRACE_TIME, DaemonDefinition, DaemonSupervisorNotSupported, LaunchdDaemonSupervisorImpl,
    SystemdDaemonSupervisorImpl, UnsupportedDaemonSupervisorImpl, choose_daemon_supervisor,
    daemon_supervisor_args,
)

def make_spec(**parameters):
    return DaemonDefinition.for_process_manager(
        name="aiko01",
        definition_pathname="/home/claude/aiko01.json",
        executable="/home/claude/venvs/venv_3.13/bin/aiko_process",
        user="claude",
        working_directory="/home/claude",
        environment={"AIKO_MQTT_HOST": "localhost"},
        **parameters)

def make_supervisor(impl, **parameters):
    return aiko.compose_instance(impl, daemon_supervisor_args(**parameters))

# The DaemonDefinition ----------------------------------------------------------- #

def test_spec_builds_the_process_manager_command_line():
    assert make_spec().command_line() == [
        "/home/claude/venvs/venv_3.13/bin/aiko_process",
        "run", "--name", "aiko01", "/home/claude/aiko01.json"
    ]

def test_spec_stop_timeout_allows_for_the_grace_time():
    """The operating system must wait longer than the ProcessManager"""

    assert make_spec(grace_time=10).stop_timeout_seconds > 10

def test_spec_rejects_a_stop_timeout_that_is_too_short():
    with pytest.raises(ValueError) as error:
        DaemonDefinition(name="aiko01", stop_timeout_seconds=GRACE_TIME)
    assert "killed before they stop" in str(error.value)

def test_spec_rejects_an_unknown_restart_policy():
    with pytest.raises(ValueError) as error:
        DaemonDefinition(name="aiko01", restart="sometimes")
    assert "restart must be" in str(error.value)

def test_spec_rejects_an_empty_name():
    with pytest.raises(ValueError) as error:
        DaemonDefinition(name="")
    assert "name is necessary" in str(error.value)

def test_spec_sets_python_unbuffered():
    """Python buffers stdout when it is a pipe, which is what a service
    gets: without this the log stays in the buffer and looks silent"""

    assert make_spec().environment["PYTHONUNBUFFERED"] == "1"
    assert make_spec().environment["AIKO_MQTT_HOST"] == "localhost"

def test_spec_with_environment_adds_variables():
    spec = make_spec().with_environment(AIKO_NAMESPACE="test")
    assert spec.environment == {
        "PYTHONUNBUFFERED": "1", "AIKO_MQTT_HOST": "localhost",
        "AIKO_NAMESPACE": "test"}

# systemd ------------------------------------------------------------------ #

def test_systemd_pathname():
    supervisor = make_supervisor(SystemdDaemonSupervisorImpl)
    assert str(supervisor.pathname(make_spec())) ==  \
        "/etc/systemd/system/aiko01.service"

def test_systemd_render():
    supervisor = make_supervisor(SystemdDaemonSupervisorImpl)
    unit = supervisor.render(make_spec())

    assert "[Unit]" in unit and "[Service]" in unit and "[Install]" in unit
    assert "After=network-online.target" in unit
    assert "User=claude" in unit
    assert "WorkingDirectory=/home/claude" in unit
    assert "Environment=AIKO_MQTT_HOST=localhost" in unit
    assert "ExecStart=/home/claude/venvs/venv_3.13/bin/aiko_process run " \
        "--name aiko01 /home/claude/aiko01.json" in unit
    assert "KillSignal=SIGTERM" in unit
    assert f"TimeoutStopSec={GRACE_TIME + 25}" in unit
    assert "Restart=always" in unit
    assert "WantedBy=multi-user.target" in unit

def test_systemd_render_omits_what_is_not_set():
    supervisor = make_supervisor(SystemdDaemonSupervisorImpl)
    unit = supervisor.render(DaemonDefinition(name="aiko01", after=(), wants=()))

    assert "User=" not in unit
    assert "WorkingDirectory=" not in unit
    assert "After=" not in unit
    assert "Wants=" not in unit

# launchd ------------------------------------------------------------------ #

def test_launchd_pathname():
    supervisor = make_supervisor(
        LaunchdDaemonSupervisorImpl, agent_directory="/tmp/LaunchAgents")
    assert str(supervisor.pathname(make_spec())) ==  \
        "/tmp/LaunchAgents/io.aiko_services.aiko01.plist"

def test_launchd_render():
    supervisor = make_supervisor(LaunchdDaemonSupervisorImpl)
    plist = supervisor.render(make_spec())

    assert plist.startswith('<?xml version="1.0"')
    assert "<key>Label</key>" in plist
    assert "<string>io.aiko_services.aiko01</string>" in plist
    assert "<string>run</string>" in plist
    assert "<string>/home/claude/aiko01.json</string>" in plist
    assert "<key>AIKO_MQTT_HOST</key><string>localhost</string>" in plist
    assert "<key>RunAtLoad</key>" in plist
    assert "<key>KeepAlive</key>" in plist
    assert f"<integer>{GRACE_TIME + 25}</integer>" in plist

def test_launchd_render_escapes_xml():
    """A definition pathname is not trusted to be XML-safe"""

    supervisor = make_supervisor(LaunchdDaemonSupervisorImpl)
    spec = DaemonDefinition.for_process_manager(
        name="aiko01", definition_pathname="/tmp/a&b.json")
    plist = supervisor.render(spec)

    assert "<string>/tmp/a&amp;b.json</string>" in plist
    assert "a&b.json" not in plist

def test_launchd_restart_on_failure_uses_a_dictionary():
    supervisor = make_supervisor(LaunchdDaemonSupervisorImpl)
    plist = supervisor.render(make_spec(restart="on-failure"))
    assert "<key>SuccessfulExit</key><false/>" in plist

# Choosing a DaemonSupervisor ------------------------------------------------------ #

def test_choose_daemon_supervisor_by_platform():
    assert isinstance(choose_daemon_supervisor("systemd"), SystemdDaemonSupervisorImpl)
    assert isinstance(choose_daemon_supervisor("launchd"), LaunchdDaemonSupervisorImpl)

def test_choose_daemon_supervisor_rejects_an_unknown_platform():
    with pytest.raises(ValueError) as error:
        choose_daemon_supervisor("upstart")
    assert "Unknown platform" in str(error.value)

def test_unsupported_supervisor_reports_the_platform():
    supervisor = choose_daemon_supervisor("unsupported")
    with pytest.raises(DaemonSupervisorNotSupported) as error:
        supervisor.render(make_spec())
    assert "No DaemonSupervisor for platform" in str(error.value)

def test_unsupported_supervisor_refuses_every_function():
    supervisor = make_supervisor(UnsupportedDaemonSupervisorImpl)
    spec = make_spec()
    for call in [
        lambda: supervisor.pathname(spec), lambda: supervisor.install(spec),
        lambda: supervisor.uninstall(spec), lambda: supervisor.start(spec),
        lambda: supervisor.stop(spec), lambda: supervisor.status(spec)]:
        with pytest.raises(DaemonSupervisorNotSupported):
            call()
