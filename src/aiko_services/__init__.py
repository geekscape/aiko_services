import aiko_services.main

__version__ = "0.8-dev"
__id__ = "2026-07-25_a"

from aiko_services.main import *
aiko.id = __id__        # aiko = main.process.ProcessData
process = aiko.process
