"""Lazy imports for optional dependencies, with install hints."""

from __future__ import annotations

import os
from typing import Any


def import_cv2(feature: str) -> Any:
    # OpenCV and FFmpeg log every failed connection attempt to stderr; the
    # service reports those itself. Set these variables to see them anyway.
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")
    try:
        import cv2
    except ImportError:
        raise ImportError(
            f"OpenCV is required for {feature}: pip install 'faistream[opencv]' "
            "(or use your platform's OpenCV build)"
        ) from None
    return cv2


def import_zstd() -> Any:
    try:
        import zstandard
    except ImportError:
        raise ImportError("the zstd codec requires: pip install 'faistream[zstd]'") from None
    return zstandard
