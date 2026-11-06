"""Aiko Services: the Aiko Dashboard, and the Dashboard pages of the
framework's own Services.

A page for one Service is a plug-in: a module with a module-level
"plugins" dictionary, keyed by the Service name or by the protocol type.
"plugins.py" is the default registry, which "aiko_dashboard" loads when
no "--plugin" is given.

The names below are the plug-in interface, so a plug-in imports them from
this package rather than from the application module:

    from aiko_services.ide.tui.dashboard import LogUI, ServiceFrame

"FormFrame" is a dialogue of more than one field, because a PopUpDialog
takes its height from its text and silently clips a Layout that does not
fit.  "ListRequest" sends a "(list ...)" and collects the response.

"main" is deliberately not re-exported here: the console script names the
application module, "ide.tui.dashboard.dashboard:main", so that the click
group and this package do not compete for one name.
"""

from aiko_services.ide.tui.dashboard.frames import (  # noqa: F401
    Field, FormFrame, FrameCommon, ListRequest, LogUI, ServiceFrame,
    choice_field, display_value, radio_field, set_display_utc, text_field,
)
# LogLevelPopupMenu asks DashboardFrame for the singleton, so it lives with
# the application.  A plug-in does not need to know that
from aiko_services.ide.tui.dashboard.dashboard import (  # noqa: F401
    LogLevelPopupMenu,
)

__all__ = [
    "Field", "FormFrame", "FrameCommon", "ListRequest", "LogLevelPopupMenu",
    "LogUI", "ServiceFrame", "choice_field", "display_value",
    "radio_field", "set_display_utc", "text_field",
]
