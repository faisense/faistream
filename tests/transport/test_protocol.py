import numpy as np
import pytest

from faistream.transport.codecs import Decoder, make_encoder
from faistream.transport.protocol import HEADER_SIZE, Codec, Header, ProtocolError


def test_header_round_trip() -> None:
    header = Header(
        Codec.JPEG, epoch=7, seq=2**40, timestamp_ns=123, height=720, width=1280, channels=3
    )
    packed = header.pack()
    assert len(packed) == HEADER_SIZE
    assert Header.unpack(packed) == header


def test_header_shape() -> None:
    assert Header(Codec.RAW, 0, 1, 0, 4, 6, 3).shape == (4, 6, 3)
    assert Header(Codec.RAW, 0, 1, 0, 4, 6, 1).shape == (4, 6)


@pytest.mark.parametrize(
    "data",
    [b"", b"XX" + bytes(HEADER_SIZE), bytes(HEADER_SIZE)],
    ids=["short", "bad-magic", "zeros"],
)
def test_header_rejects_garbage(data: bytes) -> None:
    with pytest.raises(ProtocolError):
        Header.unpack(data)


def test_header_rejects_unknown_codec() -> None:
    packed = bytearray(Header(Codec.RAW, 0, 1, 0, 1, 1, 1).pack())
    packed[3] = 99
    with pytest.raises(ProtocolError, match="codec"):
        Header.unpack(bytes(packed))


@pytest.mark.parametrize("codec", [Codec.RAW, Codec.ZSTD])
@pytest.mark.parametrize("shape", [(48, 64, 3), (48, 64)])
def test_lossless_codecs(codec: Codec, shape: tuple[int, ...]) -> None:
    if codec is Codec.ZSTD:
        pytest.importorskip("zstandard")
    image = np.random.default_rng(0).integers(0, 255, shape, dtype=np.uint8)
    header = Header.for_image(image, codec, epoch=1, seq=1, ts=0)
    payload = make_encoder(codec).encode(image)
    np.testing.assert_array_equal(Decoder().decode(header, payload), image)


def test_jpeg_codec_is_close() -> None:
    pytest.importorskip("cv2")
    image = np.full((48, 64, 3), 120, np.uint8)
    header = Header.for_image(image, Codec.JPEG, epoch=1, seq=1, ts=0)
    decoded = Decoder().decode(header, make_encoder(Codec.JPEG, quality=90).encode(image))
    assert decoded.shape == image.shape
    assert np.abs(decoded.astype(int) - image).max() <= 3


def test_decoder_rejects_size_mismatch() -> None:
    header = Header(Codec.RAW, 0, 1, 0, height=2, width=2, channels=3)
    with pytest.raises(ProtocolError, match="bytes"):
        Decoder().decode(header, b"\x00" * 5)


def test_shm_is_not_a_network_codec() -> None:
    with pytest.raises(ValueError):
        make_encoder(Codec.SHM)
