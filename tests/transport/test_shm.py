import multiprocessing as mp
import secrets
from collections.abc import Iterator
from multiprocessing import shared_memory

import numpy as np
import pytest

from faistream.transport.shm import ShmRingReader, ShmRingWriter


@pytest.fixture
def name() -> Iterator[str]:
    # Short and unique: macOS limits shared-memory names to 31 characters.
    yield f"fvt_{secrets.token_hex(4)}"


def frame(value: int, shape: tuple[int, ...] = (4, 6, 3)) -> np.ndarray:
    return np.full(shape, value, np.uint8)


def test_round_trip(name: str) -> None:
    writer = ShmRingWriter(name, slots=3)
    writer.write(frame(1), seq=1, timestamp_ns=10)
    reader = ShmRingReader(name)
    try:
        assert reader.epoch == writer.epoch
        assert reader.shape == (4, 6, 3)
        out = reader.read(1)
        assert out is not None
        np.testing.assert_array_equal(out, frame(1))
        assert out.flags.writeable
    finally:
        reader.close()
        writer.close()


def test_overwritten_slot_is_skipped(name: str) -> None:
    writer = ShmRingWriter(name, slots=2)
    for seq in range(1, 4):  # seq 3 overwrites seq 1's slot
        writer.write(frame(seq), seq, 0)
    reader = ShmRingReader(name)
    try:
        assert reader.read(1) is None
        assert reader.read(2) is not None
        out = reader.read(3)
        assert out is not None and out[0, 0, 0] == 3
    finally:
        reader.close()
        writer.close()


def test_zero_copy_view(name: str) -> None:
    writer = ShmRingWriter(name, slots=2)
    writer.write(frame(5), 1, 0)
    reader = ShmRingReader(name)
    try:
        view = reader.read(1, copy=False)
        assert view is not None and not view.flags.writeable
        assert reader.is_current(1)
        writer.write(frame(6), 2, 0)
        writer.write(frame(7), 3, 0)  # wraps onto seq 1's slot
        assert not reader.is_current(1)
        del view
    finally:
        reader.close()
        writer.close()


def test_shape_change_creates_new_epoch(name: str) -> None:
    writer = ShmRingWriter(name)
    writer.write(frame(1), 1, 0)
    first = writer.epoch
    writer.write(frame(2, (8, 8, 3)), 2, 0)
    reader = ShmRingReader(name)
    try:
        assert writer.epoch != first
        assert reader.shape == (8, 8, 3)
    finally:
        reader.close()
        writer.close()


def test_close_unlinks(name: str) -> None:
    writer = ShmRingWriter(name)
    writer.write(frame(1), 1, 0)
    writer.close()
    with pytest.raises(FileNotFoundError):
        ShmRingReader(name)


def test_replaces_stale_segment(name: str) -> None:
    # Simulate a writer that crashed without unlinking.
    stale = shared_memory.SharedMemory(name=name, create=True, size=128)
    stale.close()
    writer = ShmRingWriter(name)
    writer.write(frame(1), 1, 0)
    reader = ShmRingReader(name)
    try:
        assert reader.read(1) is not None
    finally:
        reader.close()
        writer.close()


def _read_in_child(name: str, seq: int, queue: "mp.Queue[int]") -> None:
    reader = ShmRingReader(name)
    out = reader.read(seq)
    queue.put(-1 if out is None else int(out.sum()))
    reader.close()


def test_reader_process_exit_does_not_unlink(name: str) -> None:
    writer = ShmRingWriter(name)
    writer.write(frame(2), 1, 0)
    ctx = mp.get_context("spawn")
    queue: mp.Queue[int] = ctx.Queue()
    child = ctx.Process(target=_read_in_child, args=(name, 1, queue))
    child.start()
    child.join(timeout=30)
    try:
        assert queue.get(timeout=5) == frame(2).sum()
        # The segment must survive the reader process exiting.
        reader = ShmRingReader(name)
        reader.close()
    finally:
        writer.close()
