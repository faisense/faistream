"""Frame encoders/decoders for network transports.

Optional dependencies are imported lazily so a subscriber that only receives
RAW or SHM frames needs nothing beyond numpy and pyzmq.
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from faistream._deps import import_cv2, import_zstd
from faistream.transport.protocol import Codec, Header, ProtocolError

Buffer = bytes | memoryview


class Encoder(Protocol):
    codec: Codec

    def encode(self, image: np.ndarray) -> Buffer: ...


class RawEncoder:
    codec = Codec.RAW

    def encode(self, image: np.ndarray) -> Buffer:
        return memoryview(np.ascontiguousarray(image)).cast("B")


class JpegEncoder:
    codec = Codec.JPEG

    def __init__(self, quality: int = 85) -> None:
        self._cv2 = import_cv2("the JPEG codec")
        self._params = [self._cv2.IMWRITE_JPEG_QUALITY, quality]

    def encode(self, image: np.ndarray) -> Buffer:
        ok, buf = self._cv2.imencode(".jpg", image, self._params)
        if not ok:
            raise ValueError("JPEG encoding failed")
        return memoryview(buf).cast("B")


class ZstdEncoder:
    codec = Codec.ZSTD

    def __init__(self, level: int = 3) -> None:
        zstd = import_zstd()
        self._compressor = zstd.ZstdCompressor(level=level)

    def encode(self, image: np.ndarray) -> Buffer:
        return self._compressor.compress(np.ascontiguousarray(image))  # type: ignore[no-any-return]


def make_encoder(codec: Codec, *, quality: int = 85, level: int = 3) -> Encoder:
    if codec is Codec.RAW:
        return RawEncoder()
    if codec is Codec.JPEG:
        return JpegEncoder(quality)
    if codec is Codec.ZSTD:
        return ZstdEncoder(level)
    raise ValueError(f"{codec.name} is not a network codec")


class Decoder:
    """Decodes RAW/JPEG/ZSTD payloads. Heavy codec state is created on first use.

    RAW and ZSTD results are read-only views over the received buffer; call
    ``.copy()`` before drawing on them.
    """

    def __init__(self) -> None:
        self._cv2: Any = None
        self._zstd: Any = None

    def decode(self, header: Header, payload: Buffer) -> np.ndarray:
        if header.codec is Codec.RAW:
            data: Buffer = payload
        elif header.codec is Codec.ZSTD:
            if self._zstd is None:
                self._zstd = import_zstd().ZstdDecompressor()
            data = self._zstd.decompress(payload, max_output_size=header.nbytes)
        elif header.codec is Codec.JPEG:
            if self._cv2 is None:
                self._cv2 = import_cv2("the JPEG codec")
            flag = self._cv2.IMREAD_GRAYSCALE if header.channels == 1 else self._cv2.IMREAD_COLOR
            image = self._cv2.imdecode(np.frombuffer(payload, np.uint8), flag)
            if image is None:
                raise ProtocolError("JPEG decoding failed")
            return image  # type: ignore[no-any-return]
        else:
            raise ProtocolError(f"cannot decode {header.codec.name} payload")

        if len(data) != header.nbytes:
            raise ProtocolError(f"payload is {len(data)} bytes, header says {header.nbytes}")
        return np.frombuffer(data, np.uint8).reshape(header.shape)
