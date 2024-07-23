# These class definitions exist to workaround a short-coming in the
# PipelineElement Definition for "deploy":"remote" PipelineElements

from aiko_services.examples.pipeline.elements import PE_Add

# pipeline_small_*.json
class PE_A0(PE_Add): pass
class PE_B0(PE_Add): pass
class PE_C0(PE_Add): pass

# pipeline_large_*.json
class PE_000(PE_Add): pass
class PE_010(PE_Add): pass
class PE_020(PE_Add): pass
class PE_030(PE_Add): pass
class PE_040(PE_Add): pass
class PE_050(PE_Add): pass
class PE_060(PE_Add): pass
class PE_070(PE_Add): pass
class PE_080(PE_Add): pass
class PE_090(PE_Add): pass
