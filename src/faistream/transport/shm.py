"""Shared-memory ring buffer for same-host, zero-codec frame sharing.

The writer owns one POSIX shared-memory segment per stream:

    [ control block, 64 B ][ slot metadata, 16 B x slots ][ slot 0 ][ slot 1 ] ...

Frames are written round-robin (slot = seq % slots). The writer never waits for
readers: a slow reader simply finds its slot overwritten and skips that frame,
which is the same "latest frame wins" contract as ZMQ_CONFLATE.

Readers learn about new frames from a ZeroMQ notification (see ``outputs.py``)
rather than by polling. The notification is sent after the slot is written, and
the kernel hand-off of that message orders the writer's stores before the
reader's loads, so readers never observe a frame that has not been fully
written.

Overwrites during a read are detected with a per-slot sequence check before and
after copying (a seqlock). That check is reliable while a reader finishes its
copy within ``slots - 1`` frame intervals, which is several orders of magnitude
more than a memcpy takes; raise ``slots`` if consumers hold zero-copy views for
long.
"""

from __future__ import annotations

import secrets
import struct
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from multiprocessing import shared_memory

import numpy as np

_MAGIC = b"FVSM"
_VERSION = 1
_CONTROL = struct.Struct("<4sIIIIIIQ")  # magic, version, epoch, slots, h, w, c, slot_bytes
_CONTROL_SIZE = 64
_META_SIZE = 16  # per slot: seq (i64), timestamp_ns (i64)
_ALIGN = 64
_WRITING = -1


def _align(n: int) -> int:
    return (n + _ALIGN - 1) // _ALIGN * _ALIGN


def _data_offset(slots: int) -> int:
    return _align(_CONTROL_SIZE + slots * _META_SIZE)


_tracker_lock = threading.Lock()


@contextmanager
def _untracked() -> Iterator[None]:
    """Keep multiprocessing's resource tracker out of segments we only attach to.

    Before Python 3.13 attaching registers the segment with the tracker, which
    then unlinks it when *this* process exits, although it belongs to the writer.
    """
    if sys.version_info >= (3, 13) or sys.platform == "win32":
        yield
        return
    from multiprocessing import resource_tracker

    with _tracker_lock:
        register, unregister = resource_tracker.register, resource_tracker.unregister
        resource_tracker.register = resource_tracker.unregister = lambda *args, **kw: None
        try:
            yield
        finally:
            resource_tracker.register, resource_tracker.unregister = register, unregister


def _attach(name: str) -> shared_memory.SharedMemory:
    if sys.version_info >= (3, 13):
        return shared_memory.SharedMemory(name=name, track=False)
    with _untracked():
        return shared_memory.SharedMemory(name=name)


def _buf(shm: shared_memory.SharedMemory) -> memoryview:
    buf = shm.buf
    if buf is None:
        raise ValueError(f"shared memory {shm.name!r} is closed")
    return buf


class _Ring:
    """Numpy views over a mapped ring segment."""

    def __init__(self, shm: shared_memory.SharedMemory, slots: int, shape: tuple[int, ...]):
        self.shm = shm
        self.slots = slots
        self.shape = shape
        self.meta = np.ndarray((slots, 2), np.int64, buffer=shm.buf, offset=_CONTROL_SIZE)
        nbytes = int(np.prod(shape))
        slot_bytes = _align(nbytes)
        base = _data_offset(slots)
        self.data = [
            np.ndarray(shape, np.uint8, buffer=shm.buf, offset=base + i * slot_bytes)
            for i in range(slots)
        ]

    def close(self) -> None:
        del self.meta, self.data
        # BufferError: a caller still holds a zero-copy view; the mapping is
        # released when that view is garbage collected.
        with suppress(BufferError):
            self.shm.close()


class ShmRingWriter:
    """Creates and writes a ring. Re-creates it (new epoch) if the frame shape changes."""

    def __init__(self, name: str, slots: int = 4) -> None:
        if slots < 2:
            raise ValueError("a ring needs at least 2 slots")
        self.name = name
        self.slots = slots
        self.epoch = 0
        self._ring: _Ring | None = None

    def write(self, image: np.ndarray, seq: int, timestamp_ns: int) -> None:
        if self._ring is None or self._ring.shape != image.shape:
            self._create(image.shape)
        assert self._ring is not None
        i = seq % self.slots
        meta = self._ring.meta
        meta[i, 0] = _WRITING
        np.copyto(self._ring.data[i], image, casting="no")
        meta[i, 1] = timestamp_ns
        meta[i, 0] = seq

    def close(self) -> None:
        if self._ring is not None:
            shm = self._ring.shm
            self._ring.close()
            shm.unlink()
            self._ring = None

    def _create(self, shape: tuple[int, ...]) -> None:
        self.close()
        unlink(self.name)  # left behind by a writer that crashed
        h, w = shape[:2]
        c = 1 if len(shape) == 2 else shape[2]
        slot_bytes = _align(h * w * c)
        size = _data_offset(self.slots) + self.slots * slot_bytes
        with _tracker_lock:
            shm = shared_memory.SharedMemory(name=self.name, create=True, size=size)
        self.epoch = secrets.randbits(32)
        _CONTROL.pack_into(
            _buf(shm), 0, _MAGIC, _VERSION, self.epoch, self.slots, h, w, c, slot_bytes
        )
        self._ring = _Ring(shm, self.slots, tuple(shape))
        self._ring.meta[:, 0] = _WRITING


class ShmRingReader:
    """Attaches to a writer's ring by name and reads validated frames."""

    def __init__(self, name: str) -> None:
        shm = _attach(name)
        try:
            magic, version, epoch, slots, h, w, c, _ = _CONTROL.unpack_from(_buf(shm), 0)
            if magic != _MAGIC or version != _VERSION:
                raise ValueError(f"shared memory {name!r} is not a faistream ring")
        except Exception:
            shm.close()
            raise
        self.name = name
        self.epoch: int = epoch
        shape = (h, w) if c == 1 else (h, w, c)
        self._ring = _Ring(shm, slots, shape)

    @property
    def shape(self) -> tuple[int, ...]:
        return self._ring.shape

    def read(self, seq: int, *, copy: bool = True) -> np.ndarray | None:
        """Return frame ``seq``, or None if it was already overwritten.

        With ``copy=False`` the result is a read-only view into shared memory that
        stays valid until the writer wraps around; check with ``is_current``.
        """
        i = seq % self._ring.slots
        meta = self._ring.meta
        if meta[i, 0] != seq:
            return None
        view = self._ring.data[i]
        if copy:
            out = view.copy()
            if meta[i, 0] != seq:
                return None
            return out
        out = view.view()
        out.flags.writeable = False
        return out

    def is_current(self, seq: int) -> bool:
        return bool(self._ring.meta[seq % self._ring.slots, 0] == seq)

    def close(self) -> None:
        self._ring.close()


def unlink(name: str) -> None:
    """Remove a ring segment by name, if it exists."""
    try:
        stale = _attach(name)
    except FileNotFoundError:
        return
    stale.close()
    with _untracked():
        stale.unlink()
