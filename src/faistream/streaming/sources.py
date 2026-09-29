"""Frame sources, all created from a single string.

    rtsp://user:pass@host/stream   network stream (FFmpeg, with open/read timeouts;
                                   RTSP over TCP or UDP, see ``rtsp_transport``)
    /path/to/video.mp4             file, played at its native fps and looped
    0                              local camera index
    "v4l2src ! ... ! appsink"      GStreamer pipeline (hardware decode on Jetson/Pi)
    synthetic://640x480@15         generated test pattern, no hardware or OpenCV needed

Sources split reading into ``grab`` (advance the stream) and ``retrieve``
(produce pixels) so frames dropped by an fps cap skip the colour conversion.
``retrieve`` may reuse its output buffer: the array is only valid until the
next call.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal, Protocol
from urllib.parse import quote, unquote, urlsplit

import numpy as np

from faistream._deps import import_cv2

_NETWORK_SCHEMES = {"rtsp", "rtsps", "rtmp", "http", "https", "udp", "tcp", "srt"}
_SYNTHETIC = re.compile(r"^synthetic://(\d+)x(\d+)(?:@(\d+(?:\.\d+)?))?$")
_RTSP_SCHEMES = {"rtsp", "rtsps"}

RtspTransport = Literal["auto", "tcp", "udp"]
"""How RTSP media travels. ``auto`` is OpenCV's default: try TCP, fall back to UDP."""


class SourceError(RuntimeError):
    """A source could not be opened or stopped delivering frames."""


class Source(Protocol):
    description: str

    def open(self) -> None: ...
    def grab(self) -> bool: ...
    def retrieve(self) -> np.ndarray: ...
    def close(self) -> None: ...


def make_source(
    target: str | int,
    *,
    open_timeout: float = 5.0,
    read_timeout: float = 5.0,
    rtsp_transport: RtspTransport = "auto",
) -> Source:
    """Build (but do not open) the source described by ``target``."""
    if isinstance(target, str):
        target = target.strip()
        if target.startswith("synthetic://"):
            match = _SYNTHETIC.match(target)
            if not match:
                raise ValueError(f"expected synthetic://WIDTHxHEIGHT[@FPS], got {target!r}")
            w, h, fps = match.groups()
            return SyntheticSource(int(w), int(h), float(fps or 15))
        if target.isdigit():
            target = int(target)
        elif target.startswith("~"):
            target = os.path.expanduser(target)
    return OpenCVSource(
        target, open_timeout=open_timeout, read_timeout=read_timeout, rtsp_transport=rtsp_transport
    )


def missing_file(target: str | int) -> str | None:
    """If ``target`` names a local file that doesn't exist, its full path; otherwise None."""
    if isinstance(target, int):
        return None
    target = target.strip()
    if (
        target.isdigit()
        or target.startswith("synthetic://")
        or "!" in target  # GStreamer pipeline
        or urlsplit(target).scheme in _NETWORK_SCHEMES
    ):
        return None
    path = os.path.abspath(os.path.expanduser(target))
    return None if os.path.exists(path) else path


def is_stream_address(target: str | int) -> bool:
    return isinstance(target, str) and urlsplit(target.strip()).scheme in _NETWORK_SCHEMES


def split_credentials(url: str) -> tuple[str, str, str]:
    """``rtsp://user:pass@host/x`` -> (``rtsp://host/x``, user, pass), unescaped."""
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url, "", ""
    host = parts.netloc.rsplit("@", 1)[1]
    return (
        parts._replace(netloc=host).geturl(),
        unquote(parts.username or ""),
        unquote(parts.password or ""),
    )


def add_credentials(url: str, username: str, password: str) -> str:
    """Put a username and password into a stream address, escaping special characters."""
    base, _, _ = split_credentials(url)
    if not username and not password:
        return base
    parts = urlsplit(base)

    def escape(text: str) -> str:  # keep ${VAR} references readable for the config loader
        return (
            text
            if re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*(:-[^}]*)?\}", text)
            else quote(text, safe="")
        )

    auth = escape(username) + (f":{escape(password)}" if password else "")
    return parts._replace(netloc=f"{auth}@{parts.netloc}").geturl()


def redact(target: str | int) -> str:
    """Hide the password in a URL so it can be logged."""
    text = str(target)
    parts = urlsplit(text)
    if parts.password:
        netloc = parts.netloc.replace(f":{parts.password}@", ":***@", 1)
        return parts._replace(netloc=netloc).geturl()
    return text


_CAPTURE_OPTIONS = "OPENCV_FFMPEG_CAPTURE_OPTIONS"
_capture_options_lock = threading.Lock()
_transport_forced = False  # set once any source forces an RTSP transport


def capture_options(base: str | None, rtsp_transport: RtspTransport) -> str | None:
    """The ``OPENCV_FFMPEG_CAPTURE_OPTIONS`` value (``key;value|key;value``) for one open."""
    if rtsp_transport == "auto":
        return base
    option = f"rtsp_transport;{rtsp_transport}"
    return f"{base}|{option}" if base else option


@contextmanager
def _ffmpeg_options(rtsp_transport: RtspTransport) -> Iterator[None]:
    """Apply FFmpeg options to the capture opened inside this block.

    OpenCV takes them from a process-wide environment variable, read when a
    capture opens, so the variable is changed only for that call and under a
    lock. Processes where no source forces a transport never take the lock.
    """
    if rtsp_transport == "auto" and not _transport_forced:
        yield
        return
    with _capture_options_lock:
        base = os.environ.get(_CAPTURE_OPTIONS)  # the user's own value; we always restore it
        value = capture_options(base, rtsp_transport)
        try:
            if value is None:
                os.environ.pop(_CAPTURE_OPTIONS, None)
            else:
                os.environ[_CAPTURE_OPTIONS] = value
            yield
        finally:
            if base is None:
                os.environ.pop(_CAPTURE_OPTIONS, None)
            else:
                os.environ[_CAPTURE_OPTIONS] = base


class Pacer:
    """Sleeps so that successive ``wait`` calls are ``1 / fps`` apart.

    If the caller falls more than one interval behind, it resynchronises instead
    of bursting to catch up.
    """

    def __init__(self, fps: float) -> None:
        self.interval = 1.0 / fps
        self._next: float | None = None

    def wait(self) -> None:
        now = time.monotonic()
        if self._next is None or now - self._next > self.interval:
            self._next = now
        elif self._next > now:
            time.sleep(self._next - now)
        self._next += self.interval


class OpenCVSource:
    def __init__(
        self,
        target: str | int,
        *,
        open_timeout: float = 5.0,
        read_timeout: float = 5.0,
        rtsp_transport: RtspTransport = "auto",
    ):
        global _transport_forced
        self.target = target
        self.description = redact(target)
        self.open_timeout = open_timeout
        self.read_timeout = read_timeout
        is_rtsp = isinstance(target, str) and urlsplit(target).scheme in _RTSP_SCHEMES
        # Other kinds of source (files, devices, backups of another type) ignore it.
        self.rtsp_transport: RtspTransport = rtsp_transport if is_rtsp else "auto"
        if self.rtsp_transport != "auto":
            _transport_forced = True
        self._cap: Any = None
        self._buf: np.ndarray | None = None
        self._pacer: Pacer | None = None
        self._cv2: Any = None

    def _kind(self) -> str:
        if isinstance(self.target, int):
            return "device"
        if "!" in self.target:
            return "gstreamer"
        if urlsplit(self.target).scheme in _NETWORK_SCHEMES:
            return "network"
        return "file"

    def open(self) -> None:
        cv2 = self._cv2 = import_cv2("video sources")
        kind = self._kind()
        if kind == "file" and not os.path.exists(str(self.target)):
            raise SourceError(f"file not found: {self.target}")
        if kind == "network" and cv2.videoio_registry.hasBackend(cv2.CAP_FFMPEG):
            params = [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                int(self.open_timeout * 1000),
                cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                int(self.read_timeout * 1000),
            ]
            with _ffmpeg_options(self.rtsp_transport):
                cap = cv2.VideoCapture(self.target, cv2.CAP_FFMPEG, params)
        elif kind == "gstreamer":
            cap = cv2.VideoCapture(self.target, cv2.CAP_GSTREAMER)
        else:
            cap = cv2.VideoCapture(self.target)
        if not cap.isOpened():
            cap.release()
            raise SourceError(f"cannot open {self.description}")
        self._cap = cap
        self._pacer = Pacer(cap.get(cv2.CAP_PROP_FPS) or 25.0) if kind == "file" else None

    def grab(self) -> bool:
        if self._cap is None:
            raise SourceError("source is not open")
        if self._pacer is not None:
            self._pacer.wait()
            if not self._cap.grab():  # end of file: loop
                self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, 0)
                return bool(self._cap.grab())
            return True
        return bool(self._cap.grab())

    def retrieve(self) -> np.ndarray:
        ok, image = self._cap.retrieve(self._buf)
        if not ok or image is None:
            raise SourceError(f"failed to decode a frame from {self.description}")
        self._buf = image
        return image  # type: ignore[no-any-return]

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class SyntheticSource:
    """A noisy gradient with a moving square: cheap to generate, realistic to compress."""

    def __init__(self, width: int, height: int, fps: float = 15.0) -> None:
        if width < 16 or height < 16:
            raise ValueError("synthetic frames must be at least 16x16")
        self.width, self.height, self.fps = width, height, fps
        self.description = f"synthetic://{width}x{height}@{fps:g}"
        self._base: np.ndarray | None = None
        self._buf: np.ndarray | None = None
        self._pacer = Pacer(fps)
        self._count = 0

    def open(self) -> None:
        if self._base is None:
            rng = np.random.default_rng(0)
            x = np.linspace(0, 255, self.width, dtype=np.float32)
            y = np.linspace(0, 255, self.height, dtype=np.float32)[:, None]
            base = np.stack(
                [
                    np.broadcast_to(x, (self.height, self.width)),
                    np.broadcast_to(y, (self.height, self.width)),
                    (x + y) / 2,
                ],
                axis=-1,
            )
            base += rng.normal(0, 6, base.shape).astype(np.float32)  # sensor-like noise
            self._base = np.clip(base, 0, 255).astype(np.uint8)
            self._buf = np.empty_like(self._base)

    def grab(self) -> bool:
        if self._base is None:
            raise SourceError("source is not open")
        self._pacer.wait()
        self._count += 1
        return True

    def retrieve(self) -> np.ndarray:
        assert self._base is not None and self._buf is not None
        np.copyto(self._buf, self._base)
        size = min(self.width, self.height) // 6
        x = self._count * 4 % (self.width - size)
        y = self.height // 2 - size // 2
        self._buf[y : y + size, x : x + size] = 255
        return self._buf

    def close(self) -> None:
        pass
