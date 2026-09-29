import threading
import time
from collections.abc import Callable

import numpy as np
import pytest

from faistream.streaming.sources import SourceError
from faistream.streaming.worker import Backoff, RateLimiter, State, StreamWorker

FAST = Backoff(initial=0.01, maximum=0.05)


class FakeSource:
    """Scriptable source: fails the first ``fail_opens`` opens (or all, if None-reachable),
    then delivers ``frames`` frames per connection before failing."""

    def __init__(
        self,
        label: str,
        *,
        fail_opens: int = 0,
        frames: int | None = None,
        reachable: bool = True,
        value: int = 1,
    ) -> None:
        self.description = label
        self.fail_opens = fail_opens
        self.frames = frames
        self.reachable = reachable
        self.value = value
        self.opens = 0
        self._left: int | None = None
        self._image = np.full((4, 6, 3), value, np.uint8)

    def open(self) -> None:
        self.opens += 1
        if not self.reachable or self.opens <= self.fail_opens:
            raise SourceError(f"{self.description} unreachable")
        self._left = self.frames

    def grab(self) -> bool:
        time.sleep(0.001)
        if self._left is not None:
            if self._left == 0:
                return False
            self._left -= 1
        return True

    def retrieve(self) -> np.ndarray:
        return self._image

    def close(self) -> None:
        pass


class Collector:
    clients = 1

    def __init__(self) -> None:
        self.frames: list[tuple[int, int]] = []  # (seq, pixel value)

    def wants_frames(self) -> bool:
        return True

    def publish(self, image: np.ndarray, seq: int, timestamp_ns: int) -> None:
        self.frames.append((seq, int(image[0, 0, 0])))

    def close(self) -> None:
        pass


def wait_for(condition: Callable[[], bool], timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.005)


def run(worker: StreamWorker) -> StreamWorker:
    worker.start()
    return worker


def stop(worker: StreamWorker) -> None:
    worker.stop()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert worker.status().state is State.STOPPED


def test_publishes_in_order() -> None:
    out = Collector()
    worker = run(StreamWorker("cam", [FakeSource("primary")], [out], backoff=FAST))
    wait_for(lambda: len(out.frames) >= 20)
    status = worker.status()
    stop(worker)
    seqs = [seq for seq, _ in out.frames]
    assert seqs == list(range(1, len(seqs) + 1))
    assert status.state is State.STREAMING and status.fps > 0
    assert (status.width, status.height) == (6, 4)


def test_fails_over_to_backup() -> None:
    out = Collector()
    primary = FakeSource("primary", reachable=False, value=1)
    backup = FakeSource("backup", value=2)
    worker = run(StreamWorker("cam", [primary, backup], [out], backoff=FAST))
    wait_for(lambda: len(out.frames) >= 5)
    status = worker.status()
    stop(worker)
    assert status.on_backup and status.source == "backup"
    assert {value for _, value in out.frames} == {2}


def test_fails_back_to_primary() -> None:
    out = Collector()
    primary = FakeSource("primary", fail_opens=1, value=1)  # down at start, then recovers
    backup = FakeSource("backup", value=2)
    worker = run(
        StreamWorker("cam", [primary, backup], [out], backoff=FAST, failback_interval=0.05)
    )
    wait_for(lambda: bool(out.frames) and out.frames[-1][1] == 1)
    status = worker.status()
    stop(worker)
    assert not status.on_backup
    values = [value for _, value in out.frames]
    assert values[0] == 2 and values[-1] == 1
    seqs = [seq for seq, _ in out.frames]
    assert seqs == sorted(seqs), "sequence keeps increasing across source switches"


def test_reconnects_after_stream_ends() -> None:
    out = Collector()
    source = FakeSource("primary", frames=3)
    worker = run(StreamWorker("cam", [source], [out], backoff=FAST))
    wait_for(lambda: len(out.frames) >= 7)
    status = worker.status()
    stop(worker)
    assert status.reconnects >= 2
    assert source.opens >= 3


def test_stops_promptly_while_backing_off() -> None:
    worker = run(
        StreamWorker(
            "cam",
            [FakeSource("x", reachable=False)],
            [Collector()],
            backoff=Backoff(initial=10, maximum=10),
        )
    )
    wait_for(lambda: worker.status().error is not None)
    started = time.monotonic()
    stop(worker)
    assert time.monotonic() - started < 1


def test_broken_output_does_not_stop_stream() -> None:
    class Broken(Collector):
        def publish(self, image: np.ndarray, seq: int, timestamp_ns: int) -> None:
            raise RuntimeError("boom")

    good = Collector()
    worker = run(StreamWorker("cam", [FakeSource("p")], [Broken(), good], backoff=FAST))
    wait_for(lambda: len(good.frames) >= 10)
    stop(worker)


def test_max_fps_caps_output() -> None:
    out = Collector()
    worker = run(StreamWorker("cam", [FakeSource("p")], [out], max_fps=20, backoff=FAST))
    time.sleep(0.5)
    stop(worker)
    assert 7 <= len(out.frames) <= 12


@pytest.mark.parametrize(
    ("camera_fps", "cap", "expected"), [(30, 15, 15), (25, 15, 15), (10, 15, 10)]
)
def test_rate_limiter(camera_fps: float, cap: float, expected: float) -> None:
    limiter = RateLimiter(cap)
    rng = np.random.default_rng(0)
    times = np.arange(0, 10, 1 / camera_fps) + rng.normal(0, 0.002, int(10 * camera_fps))
    kept = sum(limiter.ready(t) for t in np.sort(times))
    assert kept / 10 == pytest.approx(expected, rel=0.1)
    assert kept / 10 <= cap * 1.01


def test_resize() -> None:
    pytest.importorskip("cv2")
    out: list[tuple[int, ...]] = []

    class Shapes(Collector):
        def publish(self, image: np.ndarray, seq: int, timestamp_ns: int) -> None:
            out.append(image.shape)

    worker = run(StreamWorker("cam", [FakeSource("p")], [Shapes()], size=(3, 2), backoff=FAST))
    wait_for(lambda: len(out) >= 3)
    stop(worker)
    assert set(out) == {(2, 3, 3)}


def test_requires_a_source() -> None:
    with pytest.raises(ValueError):
        StreamWorker("cam", [], [])


def test_threads_do_not_leak() -> None:
    before = threading.active_count()
    worker = run(
        StreamWorker(
            "cam",
            [FakeSource("p", fail_opens=1), FakeSource("b")],
            [Collector()],
            backoff=FAST,
            failback_interval=0.01,
        )
    )
    time.sleep(0.2)
    stop(worker)
    time.sleep(0.05)
    assert threading.active_count() <= before


def test_idle_stream_skips_retrieve() -> None:
    class Idle(Collector):
        clients = 0

        def wants_frames(self) -> bool:
            return False

    class Counting(FakeSource):
        retrieves = 0

        def retrieve(self) -> np.ndarray:
            self.retrieves += 1
            return super().retrieve()

    source = Counting("p")
    out = Idle()
    worker = run(StreamWorker("cam", [source], [out], backoff=FAST))
    wait_for(lambda: worker.status().fps > 0)
    stop(worker)
    assert source.retrieves == 1, "only the first frame is decoded, to learn the shape"
    assert len(out.frames) == 1


def test_paused_stream_never_connects() -> None:
    source = FakeSource("camera")
    worker = run(StreamWorker("cam", [source], [Collector()], backoff=FAST, paused=True))
    wait_for(lambda: worker.status().state is State.PAUSED)
    time.sleep(0.2)
    assert source.opens == 0  # the camera is left alone while paused
    stop(worker)


def test_health_counters() -> None:
    class Idle(Collector):
        clients = 0

        def wants_frames(self) -> bool:
            return False

    watched = run(StreamWorker("cam", [FakeSource("p")], [Collector()], max_fps=50, backoff=FAST))
    idle = run(StreamWorker("idle", [FakeSource("p")], [Idle()], backoff=FAST))
    wait_for(lambda: watched.status().frames_capped > 20 and idle.status().frames_unwatched > 20)
    time.sleep(0.1)
    status = watched.status()
    stop(watched)
    stop(idle)
    assert status.online_seconds > 0 and status.seq > 0
    assert status.cpu_seconds > 0 and status.work_ms >= 0
    assert status.last_frame_age is not None and status.last_frame_age < 1
    assert status.frames_unwatched == 0  # someone was watching
    assert status.backup_seconds == 0


def test_time_on_backup_is_counted() -> None:
    primary = FakeSource("primary", reachable=False)
    worker = run(StreamWorker("cam", [primary, FakeSource("backup")], [Collector()], backoff=FAST))
    wait_for(lambda: worker.status().on_backup)
    time.sleep(0.2)
    status = worker.status()
    stop(worker)
    assert status.backup_seconds >= 0.1
    assert worker.status().backup_seconds >= status.backup_seconds  # kept after it stops


class Polled(Collector):
    polls = 0

    def wants_frames(self) -> bool:
        self.polls += 1
        return True


@pytest.mark.parametrize("paused", [True, False])
def test_viewers_stay_current_while_paused_or_offline(paused: bool) -> None:
    """Who is connected keeps updating when no frames flow (for the stats page)."""
    out = Polled()
    source = FakeSource("camera", reachable=paused)  # not paused: the camera is offline
    worker = run(StreamWorker("cam", [source], [out], backoff=Backoff(0.5, 0.5), paused=paused))
    wait_for(lambda: out.polls >= 2)
    stop(worker)
