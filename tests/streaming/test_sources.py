import os
import time
from pathlib import Path

import numpy as np
import pytest

from faistream.streaming.sources import (
    OpenCVSource,
    Pacer,
    SourceError,
    SyntheticSource,
    _ffmpeg_options,
    capture_options,
    make_source,
    redact,
)

CAPTURE_OPTIONS = "OPENCV_FFMPEG_CAPTURE_OPTIONS"


def test_make_source_dispatch() -> None:
    synthetic = make_source("synthetic://320x240@30")
    assert isinstance(synthetic, SyntheticSource)
    assert (synthetic.width, synthetic.height, synthetic.fps) == (320, 240, 30)
    assert isinstance(make_source("synthetic://64x64"), SyntheticSource)
    device = make_source("0")
    assert isinstance(device, OpenCVSource) and device.target == 0
    assert isinstance(make_source("rtsp://cam/stream"), OpenCVSource)


def test_make_source_rejects_bad_synthetic() -> None:
    with pytest.raises(ValueError, match="synthetic"):
        make_source("synthetic://big")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("rtsp://admin:s3cret@10.0.0.2:554/s1", "rtsp://admin:***@10.0.0.2:554/s1"),
        ("rtsp://10.0.0.2/s1", "rtsp://10.0.0.2/s1"),
        ("/videos/a.mp4", "/videos/a.mp4"),
        (0, "0"),
    ],
)
def test_redact(url: str | int, expected: str) -> None:
    assert redact(url) == expected


def test_source_description_is_redacted() -> None:
    assert "s3cret" not in make_source("rtsp://u:s3cret@host/x").description


def test_synthetic_frames_change() -> None:
    source = SyntheticSource(64, 48, fps=1000)
    source.open()
    assert source.grab()
    first = source.retrieve().copy()
    assert source.grab()
    second = source.retrieve()
    assert first.shape == (48, 64, 3) and first.dtype == np.uint8
    assert not np.array_equal(first, second)


def test_pacer_limits_rate() -> None:
    pacer = Pacer(fps=100)
    start = time.monotonic()
    for _ in range(11):
        pacer.wait()
    assert time.monotonic() - start >= 0.09


@pytest.fixture
def video_file(tmp_path: Path) -> Path:
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 200, (64, 48))
    for i in range(3):
        writer.write(np.full((48, 64, 3), i * 60, np.uint8))
    writer.release()
    return path


def test_file_source_loops(video_file: Path) -> None:
    source = make_source(str(video_file))
    source.open()
    try:
        for _ in range(7):  # more frames than the file has
            assert source.grab()
            assert source.retrieve().shape == (48, 64, 3)
    finally:
        source.close()


def test_file_source_reuses_buffer(video_file: Path) -> None:
    source = make_source(str(video_file))
    source.open()
    try:
        source.grab()
        first = source.retrieve()
        source.grab()
        assert source.retrieve() is first
    finally:
        source.close()


def test_missing_file_raises() -> None:
    pytest.importorskip("cv2")
    with pytest.raises(SourceError, match="not found"):
        make_source("/nope/missing.mp4").open()


def test_unreachable_stream_raises_within_timeout() -> None:
    pytest.importorskip("cv2")
    source = make_source("rtsp://127.0.0.1:1/none", open_timeout=1)
    start = time.monotonic()
    with pytest.raises(SourceError):
        source.open()
    assert time.monotonic() - start < 5


def test_capture_options() -> None:
    assert capture_options(None, "auto") is None
    assert capture_options("probesize;32", "auto") == "probesize;32"
    assert capture_options(None, "udp") == "rtsp_transport;udp"
    assert capture_options("probesize;32", "tcp") == "probesize;32|rtsp_transport;tcp"


def test_ffmpeg_options_are_scoped_and_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CAPTURE_OPTIONS, "probesize;32")  # the user's own options are kept
    with _ffmpeg_options("udp"):
        assert os.environ[CAPTURE_OPTIONS] == "probesize;32|rtsp_transport;udp"
    assert os.environ[CAPTURE_OPTIONS] == "probesize;32"

    monkeypatch.delenv(CAPTURE_OPTIONS)
    with _ffmpeg_options("tcp"):
        assert os.environ[CAPTURE_OPTIONS] == "rtsp_transport;tcp"
    assert CAPTURE_OPTIONS not in os.environ


def test_ffmpeg_options_restored_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CAPTURE_OPTIONS, raising=False)
    with pytest.raises(RuntimeError), _ffmpeg_options("udp"):
        raise RuntimeError("open failed")
    assert CAPTURE_OPTIONS not in os.environ


def test_rtsp_transport_only_applies_to_rtsp() -> None:
    def transport(target: str) -> str:
        return OpenCVSource(target, rtsp_transport="udp").rtsp_transport

    assert transport("rtsp://h/s") == "udp"
    assert transport("rtsps://h/s") == "udp"
    assert transport("http://h/s") == "auto"
    assert transport("/v.mp4") == "auto"


def test_home_folder_is_expanded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    source = make_source("~/Movies/s1.mp4")
    assert isinstance(source, OpenCVSource) and source.target == str(tmp_path / "Movies/s1.mp4")


def test_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from faistream.streaming.sources import missing_file

    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "there.mp4").write_bytes(b"")
    assert missing_file("~/there.mp4") is None
    assert missing_file("~/gone.mp4") == str(tmp_path / "gone.mp4")
    for not_a_file in ("rtsp://h/s", "0", 0, "synthetic://64x48", "videotestsrc ! appsink"):
        assert missing_file(not_a_file) is None
