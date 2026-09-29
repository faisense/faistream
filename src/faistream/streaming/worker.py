"""One thread per stream: read a source once, publish every frame to all outputs.

A stream has an ordered list of sources (primary first, then backups). When the
active source fails the worker reconnects, trying sources in priority order with
exponential backoff. While running on a backup it periodically probes the
higher-priority sources in the background and switches back once one is
reachable again.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Protocol

import numpy as np

from faistream._deps import import_cv2
from faistream.streaming.sources import Source, SourceError

log = logging.getLogger(__name__)


class State(str, Enum):
    CONNECTING = "connecting"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass(frozen=True)
class StreamStatus:
    name: str
    state: State
    source: str
    on_backup: bool
    seq: int
    fps: float
    clients: int
    width: int
    height: int
    reconnects: int
    error: str | None
    # health, for status displays
    online_seconds: float = 0.0  # since the current connection started
    backup_seconds: float = 0.0  # total time spent on a backup source
    frames_capped: int = 0  # read, but dropped by the fps limit
    frames_unwatched: int = 0  # read, but not decoded because nobody was watching
    cpu_seconds: float = 0.0  # CPU time used by this stream's thread
    work_ms: float = 0.0  # time to decode, resize and publish one frame (average)
    last_frame_age: float | None = None  # seconds since the last frame was sent

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "state": self.state.value}


class Output(Protocol):
    @property
    def clients(self) -> int: ...
    def wants_frames(self) -> bool: ...
    def publish(self, image: np.ndarray, seq: int, timestamp_ns: int) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class Backoff:
    initial: float = 0.5
    maximum: float = 30.0
    factor: float = 2.0


DEFAULT_BACKOFF = Backoff()


class RateLimiter:
    """Decides which frames to keep to stay at or under ``fps``.

    A quarter-interval of tolerance keeps camera jitter from turning e.g. a
    30 -> 15 fps cap into 10 fps.
    """

    def __init__(self, fps: float) -> None:
        self.interval = 1.0 / fps
        self._due: float | None = None

    def ready(self, now: float) -> bool:
        if self._due is None or now - self._due > self.interval:
            self._due = now  # first frame, or fell behind: resynchronise
        if now < self._due - self.interval / 4:
            return False
        self._due += self.interval
        return True


class StreamWorker(threading.Thread):
    def __init__(
        self,
        name: str,
        sources: Sequence[Source],
        outputs: Sequence[Output],
        *,
        max_fps: float | None = None,
        size: tuple[int, int] | None = None,
        backoff: Backoff = DEFAULT_BACKOFF,
        failback_interval: float = 30.0,
        paused: bool = False,
    ) -> None:
        if not sources:
            raise ValueError("a stream needs at least one source")
        super().__init__(name=f"stream-{name}", daemon=True)
        self.stream_name = name
        self._sources = list(sources)
        self._outputs = list(outputs)
        self._max_fps = max_fps
        self._size = size
        self._backoff = backoff
        self._failback_interval = failback_interval
        self._paused = paused
        self._stopping = threading.Event()
        self._failback_ready = threading.Event()
        self._probe: threading.Thread | None = None
        self._resized: np.ndarray | None = None
        self._broken_outputs: set[int] = set()
        # status (written by this thread only)
        self._state = State.CONNECTING
        self._active = -1
        self._seq = 0
        self._shape: tuple[int, ...] = (0, 0)
        self._reconnects = 0
        self._error: str | None = None
        self._publish_times: deque[float] = deque(maxlen=30)
        self._frames_capped = 0
        self._frames_unwatched = 0
        self._online_since: float | None = None
        self._backup_since: float | None = None
        self._backup_total = 0.0
        self._cpu_seconds = 0.0
        self._work_ms = 0.0
        self._last_frame: float | None = None

    # -- public API ------------------------------------------------------

    def stop(self) -> None:
        self._stopping.set()

    def status(self) -> StreamStatus:
        times = list(self._publish_times)
        fps = 0.0
        if self._state is State.STREAMING and len(times) > 1 and times[-1] > times[0]:
            fps = (len(times) - 1) / (times[-1] - times[0])
        active = self._active
        now = time.monotonic()
        backup_since = self._backup_since
        return StreamStatus(
            name=self.stream_name,
            state=self._state,
            source=self._sources[active].description if active >= 0 else "",
            on_backup=active > 0,
            seq=self._seq,
            fps=round(fps, 1),
            clients=sum(output.clients for output in self._outputs),
            width=self._shape[1],
            height=self._shape[0],
            reconnects=self._reconnects,
            error=self._error,
            online_seconds=round(now - self._online_since, 1) if self._online_since else 0.0,
            backup_seconds=round(
                self._backup_total + (now - backup_since if backup_since else 0), 1
            ),
            frames_capped=self._frames_capped,
            frames_unwatched=self._frames_unwatched,
            cpu_seconds=round(self._cpu_seconds, 3),
            work_ms=round(self._work_ms, 2),
            last_frame_age=round(now - self._last_frame, 1) if self._last_frame else None,
        )

    # -- worker loop -----------------------------------------------------

    def run(self) -> None:
        try:
            if self._paused:  # stopped on purpose: don't even connect to the camera
                self._state = State.PAUSED
                while not self._idle(60):
                    pass
                return
            while not self._stopping.is_set():
                active = self._connect()
                if active is None:
                    break
                self._stream(active)
        finally:
            self._state = State.STOPPED
            self._active = -1

    def _connect(self) -> int | None:
        """Open the highest-priority reachable source; None if stopped first."""
        if self._probe is not None:
            self._probe.join()  # it may be holding one of our sources open
        self._failback_ready.clear()
        delay = self._backoff.initial
        while not self._stopping.is_set():
            for index, source in enumerate(self._sources):
                try:
                    source.open()
                except Exception as exc:
                    self._error = str(exc)
                    log.debug("%s: cannot open %s: %s", self.stream_name, source.description, exc)
                    continue
                self._active, self._error = index, None
                role = "backup" if index else "primary"
                log.info("%s: streaming from %s (%s)", self.stream_name, source.description, role)
                return index
            log.warning(
                "%s: no source reachable (%s); retrying in %.1fs",
                self.stream_name,
                self._error,
                delay,
            )
            if self._idle(delay):
                break
            delay = min(delay * self._backoff.factor, self._backoff.maximum)
        return None

    def _idle(self, seconds: float) -> bool:
        """Wait while no frames flow; True if asked to stop.

        Keeps checking the outputs, so the list of who is connected stays current
        while a camera is paused or offline.
        """
        deadline = time.monotonic() + seconds
        while True:
            for output in self._outputs:
                output.wants_frames()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if self._stopping.wait(min(remaining, 1.0)):
                return True

    def _stream(self, index: int) -> None:
        source = self._sources[index]
        limiter = RateLimiter(self._max_fps) if self._max_fps else None
        next_probe = time.monotonic() + self._failback_interval if index else float("inf")
        self._online_since = time.monotonic()
        self._backup_since = self._online_since if index else None
        try:
            while not self._stopping.is_set():
                if not source.grab():
                    raise SourceError(f"{source.description} stopped delivering frames")
                now = time.monotonic()
                self._cpu_seconds = time.thread_time()
                if now >= next_probe:
                    self._start_probe(index)
                    next_probe = now + self._failback_interval
                if self._failback_ready.is_set():
                    log.info("%s: higher-priority source is back; switching", self.stream_name)
                    return
                if limiter and not limiter.ready(now):
                    self._frames_capped += 1
                    continue  # dropped: skip retrieve() and its colour conversion
                self._publish_times.append(now)
                wanted = [output.wants_frames() for output in self._outputs]  # poll every output
                if not any(wanted) and self._shape != (0, 0):
                    self._frames_unwatched += 1
                    self._state = State.STREAMING
                    continue  # nobody is subscribed: skip decoding to pixels entirely
                self._publish(self._resize(source.retrieve()))
                self._state = State.STREAMING  # from the first frame, so its size is known
                done = time.monotonic()
                self._work_ms += ((done - now) * 1000 - self._work_ms) * 0.1  # moving average
                self._last_frame = done
        except Exception as exc:
            self._error = str(exc)
            self._reconnects += 1
            self._state = State.RECONNECTING
            log.warning("%s: lost %s: %s", self.stream_name, source.description, exc)
        finally:
            source.close()
            self._publish_times.clear()
            self._cpu_seconds = time.thread_time()
            self._online_since = None
            if self._backup_since is not None:
                self._backup_total += time.monotonic() - self._backup_since
                self._backup_since = None
            if self._state is State.STREAMING:
                self._state = State.CONNECTING

    def _publish(self, image: np.ndarray) -> None:
        self._seq += 1
        timestamp_ns = time.time_ns()
        self._shape = image.shape
        for i, output in enumerate(self._outputs):
            try:
                output.publish(image, self._seq, timestamp_ns)
            except Exception:
                if i not in self._broken_outputs:  # log once per output, keep streaming
                    self._broken_outputs.add(i)
                    log.exception("%s: output %d failed", self.stream_name, i)

    def _resize(self, image: np.ndarray) -> np.ndarray:
        if self._size is None or (image.shape[1], image.shape[0]) == self._size:
            return image
        cv2 = import_cv2("resizing")
        self._resized = cv2.resize(
            image, self._size, dst=self._resized, interpolation=cv2.INTER_AREA
        )
        return self._resized

    def _start_probe(self, active: int) -> None:
        if self._probe is not None and self._probe.is_alive():
            return
        candidates = self._sources[:active]

        def probe() -> None:
            for source in candidates:
                try:
                    source.open()
                except Exception:
                    continue
                source.close()
                self._failback_ready.set()
                return

        self._probe = threading.Thread(target=probe, name=f"probe-{self.stream_name}", daemon=True)
        self._probe.start()
