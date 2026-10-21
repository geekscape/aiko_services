# Aiko Services: Daemon Supervisor
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Start Aiko Services when the operating system starts.  The operating
# system starts one process for each host, the ProcessManager, and the
# ProcessManager definition file starts everything else.
#
# One DaemonDefinition, several renderers: a systemd unit on Linux, a launchd
# agent on macOS.  render() changes nothing, install() changes the host.
#
# Usage: aiko_supervisor --help  (see cli.py)

from aiko_services.main.daemon_supervisor.daemon_supervisor import (  # noqa: F401
    GRACE_TIME, STOP_TIMEOUT_MARGIN, DaemonDefinition, DaemonSupervisor,
    DaemonSupervisorNotSupported, UnsupportedDaemonSupervisorImpl, choose_daemon_supervisor,
    daemon_supervisor_args,
)
from aiko_services.main.daemon_supervisor.launchd import (  # noqa: F401
    LaunchdDaemonSupervisorImpl,
)
from aiko_services.main.daemon_supervisor.systemd import (  # noqa: F401
    SystemdDaemonSupervisorImpl,
)

__all__ = [
    "GRACE_TIME", "STOP_TIMEOUT_MARGIN",
    "DaemonDefinition", "DaemonSupervisor", "DaemonSupervisorNotSupported", "LaunchdDaemonSupervisorImpl",
    "SystemdDaemonSupervisorImpl", "UnsupportedDaemonSupervisorImpl", "choose_daemon_supervisor",
    "daemon_supervisor_args",
]
