"""Wire format shared by every transport.

Each published message is a single ZeroMQ frame: a fixed 36-byte header followed
by the payload. It is deliberately single-part because ZMQ_CONFLATE (keep only
the latest message) does not support multipart messages.

Header layout (little-endian):

    magic      2s   b"FV"
    version    u8
    codec      u8   Codec
    epoch      u32  random per publisher session; changes on restart / shape change
    seq        u64  frame counter; starts at 1 when the stream (re)starts, always with a new epoch
    timestamp  i64  capture time, ns since the Unix epoch
    height     u32
    width      u32
    channels   u8
    (pad)      3x
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

MAGIC = b"FV"
VERSION = 1

_HEADER = struct.Struct("<2sBBIQqIIB3x")
HEADER_SIZE = _HEADER.size


class Codec(IntEnum):
    RAW = 0
    JPEG = 1
    ZSTD = 2
    SHM = 3  # payload is the name of a shared-memory ring; pixels live there


class ProtocolError(ValueError):
    """Raised when a message is not a valid faistream frame."""


@dataclass(frozen=True, slots=True)
class Header:
    codec: Codec
    epoch: int
    seq: int
    timestamp_ns: int
    height: int
    width: int
    channels: int

    @property
    def shape(self) -> tuple[int, ...]:
        if self.channels == 1:
            return (self.height, self.width)
        return (self.height, self.width, self.channels)

    @property
    def nbytes(self) -> int:
        return self.height * self.width * self.channels

    def pack(self) -> bytes:
        return _HEADER.pack(
            MAGIC,
            VERSION,
            self.codec,
            self.epoch,
            self.seq,
            self.timestamp_ns,
            self.height,
            self.width,
            self.channels,
        )

    @classmethod
    def unpack(cls, data: bytes | memoryview) -> Header:
        if len(data) < HEADER_SIZE:
            raise ProtocolError(f"message too short: {len(data)} bytes")
        magic, version, codec, epoch, seq, ts, h, w, c = _HEADER.unpack_from(data)
        if magic != MAGIC:
            raise ProtocolError(f"bad magic {magic!r}")
        if version != VERSION:
            raise ProtocolError(f"unsupported protocol version {version}")
        try:
            codec = Codec(codec)
        except ValueError:
            raise ProtocolError(f"unknown codec {codec}") from None
        return cls(codec, epoch, seq, ts, h, w, c)

    @classmethod
    def for_image(cls, image: np.ndarray, codec: Codec, epoch: int, seq: int, ts: int) -> Header:
        h, w = image.shape[:2]
        c = 1 if image.ndim == 2 else image.shape[2]
        return cls(codec, epoch, seq, ts, h, w, c)


@dataclass(frozen=True, slots=True)
class Frame:
    """A decoded frame as seen by a subscriber."""

    image: np.ndarray
    seq: int
    timestamp_ns: int
    epoch: int

    def age_ms(self) -> float:
        """Milliseconds since capture. Only meaningful when clocks are shared (same host)."""
        return (time.time_ns() - self.timestamp_ns) / 1e6
