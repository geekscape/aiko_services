# Camera PipelineElements: machine-vision cameras as DataSources, one
# DataScheme per camera SDK, so a PipelineDefinition selects the camera by
# its DataSource element and "data_sources" URL alone
#
# Every module imports without its camera SDK: the SDK is a guarded import
# and its absence is reported as a diagnostic when the DataScheme is used
#
# Declaration order is based on the dependency on static references
#
# To Do
# ~~~~~
# - None, yet !

from .camera import (
    Camera, CaptureTimeout, CountdownSettle, RateMeter, SettleMonitor,
    auto_expose, parse_bool, parse_frame_rate, parse_resolution,
    parse_settle, plan_resolution, resize_image, share_token, utc_now
)

from .camera_aravis import AravisCamera

from .camera_ids_peak import IdsPeakCamera

from .camera_oak_d import OakDCamera

from .scheme_camera import DataSchemeCamera

from .scheme_depthai import DataSchemeDepthAI

from .scheme_gigev import DataSchemeGigE, select_backend

from .image_dewarp import Dewarper, ImageDewarp, load_calibration

from .depthai_io import VideoReadDepthAI

from .gigev_io import VideoReadGigE
