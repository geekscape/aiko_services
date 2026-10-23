"""Aiko Services: the Aiko Dashboard, and the Dashboard pages of the
framework's own Services.

A page for one Service is a plug-in: a module with a module-level
"plugins" dictionary, keyed by the Service name or by the protocol type.
"plugins.py" is the default registry, which "aiko_dashboard" loads when
no "--plugin" is given.

The names below are the plug-in interface, so a plug-in imports them from
this package rather than from the application module:

    from aiko_services.actors.dashboard import LogUI, ServiceFrame

"main" is deliberately not re-exported here: the console script names the
application module, "actors.dashboard.dashboard:main", so that the click
group and this package do not compete for one name.
"""

from aiko_services.actors.dashboard.frames import (  # noqa: F401
    FrameCommon, LogUI, ServiceFrame,
)
# LogLevelPopupMenu asks DashboardFrame for the singleton, so it lives with
# the application.  A plug-in does not need to know that
from aiko_services.actors.dashboard.dashboard import (  # noqa: F401
    LogLevelPopupMenu,
)

__all__ = ["FrameCommon", "LogLevelPopupMenu", "LogUI", "ServiceFrame"]
