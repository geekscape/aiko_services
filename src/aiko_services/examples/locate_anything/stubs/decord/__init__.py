"""Minimal decord stub for image-only LocateAnything inference.

The Hugging Face processor imports decord at module load time. Real decord has no
PyPI wheel on macOS; this stub is added to sys.path by locate_anything.py.
"""


class VideoReader:
    def __init__(self, *args, **kwargs):
        raise ImportError(
            "decord is not installed; video input is not supported in this environment")

    def get_batch(self, *args, **kwargs):
        raise ImportError(
            "decord is not installed; video input is not supported in this environment")
