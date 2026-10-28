#!/usr/bin/env python3
#
# Aiko Services: Daemon Supervisor for systemd (Linux)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Renders a DaemonDefinition as a systemd unit, and installs it as a system
# service, so that it starts when the host starts.
#
# The unit is written to /etc/systemd/system/, which needs root.  Run
# "aiko_supervisor install" with sudo, or use "render" and copy the unit
# yourself.
#
# To Do
# ~~~~~
# * A "--user" option, for a systemd user service: no root, but it stops
#   when the user logs out, unless "loginctl enable-linger" is used

from pathlib import Path

from aiko_services.main.daemon_supervisor.daemon_supervisor import DaemonSupervisor, run_command

__all__ = ["SystemdDaemonSupervisorImpl"]

UNIT_DIRECTORY = "/etc/systemd/system"

class SystemdDaemonSupervisorImpl(DaemonSupervisor):
    """systemd on Linux: a system service in /etc/systemd/system"""

    platform = "systemd"

    def __init__(self, context, unit_directory=UNIT_DIRECTORY, **_):
        self.unit_directory = unit_directory

    def _unit_name(self, spec):
        return f"{spec.name}.service"

    def pathname(self, spec):
        return Path(self.unit_directory) / self._unit_name(spec)

    def render(self, spec):
        lines = [
            f"# {spec.description}",
            "#",
            "# Rendered by aiko_supervisor.  Change the DaemonDefinition and render",
            "# again, rather than this file",
            "",
            "[Unit]",
            f"Description={spec.description}"
        ]
        if spec.after:
            lines.append(f"After={' '.join(spec.after)}")
        if spec.wants:
            lines.append(f"Wants={' '.join(spec.wants)}")
        lines += ["", "[Service]", "Type=simple"]
        if spec.user:
            lines.append(f"User={spec.user}")
        if spec.working_directory:
            lines.append(f"WorkingDirectory={spec.working_directory}")
        for name, value in spec.environment.items():
            lines.append(f"Environment={name}={value}")
        lines += [
            f"ExecStart={' '.join(spec.command_line())}",
            f"KillSignal={spec.stop_signal}",
            f"TimeoutStopSec={spec.stop_timeout_seconds}",
            f"Restart={spec.restart}",
            f"RestartSec={spec.restart_seconds}",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            ""
        ]
        return "\n".join(lines)

    def install(self, spec, enable=True):
        pathname = self.pathname(spec)
        pathname.parent.mkdir(parents=True, exist_ok=True)
        pathname.write_text(self.render(spec))
        run_command(["systemctl", "daemon-reload"])
        if enable:
            run_command(["systemctl", "enable", self._unit_name(spec)])
        return pathname

    def uninstall(self, spec):
        unit_name = self._unit_name(spec)
        run_command(["systemctl", "disable", "--now", unit_name])
        pathname = self.pathname(spec)
        if pathname.exists():
            pathname.unlink()
        run_command(["systemctl", "daemon-reload"])
        return pathname

    def start(self, spec):
        return run_command(["systemctl", "start", self._unit_name(spec)])

    def stop(self, spec):
        return run_command(["systemctl", "stop", self._unit_name(spec)])

    def status(self, spec):
        return run_command(
            ["systemctl", "status", "--no-pager", self._unit_name(spec)])

# --------------------------------------------------------------------------- #
