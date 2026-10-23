import aiko_services.main

__version__ = "0.8-dev"
__id__ = "2026-10-22_a"

from aiko_services.main import *
aiko.id = __id__        # aiko = main.process.ProcessData
process = aiko.process

# The Dashboard lives in the actors tier (s_01_RepositoryLayout), so the
# plug-in interface is re-exported here, in the facade, and not by
# "main/__init__.py".  A plug-in keeps using "aiko.ServiceFrame", and
# "main" does not import "actors"
from aiko_services.actors.dashboard import (  # noqa: E402, F401
    FrameCommon, LogLevelPopupMenu, LogUI, ServiceFrame,
)
