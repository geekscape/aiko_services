#!/usr/bin/env python3
#
# Aiko Services: Daemon Supervisor for launchd (macOS)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Renders a DaemonDefinition as a launchd property list, and installs it as a
# user agent in ~/Library/LaunchAgents, which needs no root.
#
# A user agent starts when the user logs in, not when the host starts.
# A system daemon (/Library/LaunchDaemons) starts earlier, but needs root
# and a different owner, so it is a "To Do" below.
#
# Differences from systemd, which the DaemonDefinition can't hide ...
# - "user" is the account that loads the agent, so the field is not used
# - "after" and "wants" have no equivalent: launchd starts an agent when
#   it is loaded, and KeepAlive restarts it
#
# To Do
# ~~~~~
# * A "--daemon" option for /Library/LaunchDaemons, which starts before
#   a user logs in
# * Map "after" to a launchd dependency, if a useful equivalent is found

import os
from pathlib import Path
from xml.sax.saxutils import escape

from aiko_services.main.daemon_supervisor.daemon_supervisor import DaemonSupervisor, run_command

__all__ = ["LaunchdDaemonSupervisorImpl"]

AGENT_DIRECTORY = "~/Library/LaunchAgents"
LABEL_PREFIX = "io.aiko_services"

class LaunchdDaemonSupervisorImpl(DaemonSupervisor):
    """launchd on macOS: a user agent in ~/Library/LaunchAgents"""

    platform = "launchd"

    def __init__(self, context, agent_directory=AGENT_DIRECTORY, **_):
        self.agent_directory = agent_directory

    def _label(self, spec):
        return f"{LABEL_PREFIX}.{spec.name}"

    def pathname(self, spec):
        directory = Path(self.agent_directory).expanduser()
        return directory / f"{self._label(spec)}.plist"

    def render(self, spec):
        arguments = "\n".join(
            f"      <string>{escape(argument)}</string>"
            for argument in spec.command_line())
        environment = "\n".join(
            f"      <key>{escape(name)}</key>"
            f"<string>{escape(str(value))}</string>"
            for name, value in spec.environment.items())

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
            '<plist version="1.0">',
            "<dict>",
            f"  <!-- {escape(spec.description)} -->",
            "  <!-- Rendered by aiko_supervisor.  Change the DaemonDefinition and",
            "       render again, rather than this file -->",
            "  <key>Label</key>",
            f"  <string>{escape(self._label(spec))}</string>",
            "  <key>ProgramArguments</key>",
            "  <array>",
            arguments,
            "  </array>"
        ]
        if spec.working_directory:
            lines += [
                "  <key>WorkingDirectory</key>",
                f"  <string>{escape(spec.working_directory)}</string>"
            ]
        if spec.environment:
            lines += [
                "  <key>EnvironmentVariables</key>", "  <dict>", environment,
                "  </dict>"
            ]
        lines += ["  <key>RunAtLoad</key>", "  <true/>"]
        if spec.restart == "always":
            lines += ["  <key>KeepAlive</key>", "  <true/>"]
        elif spec.restart == "on-failure":
            lines += [
                "  <key>KeepAlive</key>", "  <dict>",
                "    <key>SuccessfulExit</key><false/>", "  </dict>"
            ]
        lines += [
            "  <key>ThrottleInterval</key>",
            f"  <integer>{spec.restart_seconds}</integer>",
            "  <key>ExitTimeOut</key>",
            f"  <integer>{spec.stop_timeout_seconds}</integer>",
            "</dict>",
            "</plist>",
            ""
        ]
        return "\n".join(lines)

    def _domain_target(self, spec):
        return f"gui/{os.getuid()}/{self._label(spec)}"

    def install(self, spec, enable=True):
        pathname = self.pathname(spec)
        pathname.parent.mkdir(parents=True, exist_ok=True)
        pathname.write_text(self.render(spec))
        if enable:
            run_command(
                ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(pathname)])
        return pathname

    def uninstall(self, spec):
        run_command(["launchctl", "bootout", self._domain_target(spec)])
        pathname = self.pathname(spec)
        if pathname.exists():
            pathname.unlink()
        return pathname

    def start(self, spec):
        return run_command(["launchctl", "kickstart", self._domain_target(spec)])

    def stop(self, spec):
        return run_command(["launchctl", "bootout", self._domain_target(spec)])

    def status(self, spec):
        return run_command(["launchctl", "print", self._domain_target(spec)])

# --------------------------------------------------------------------------- #
