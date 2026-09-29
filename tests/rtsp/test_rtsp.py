"""Integration tests against a real RTSP server that only accepts UDP.

Forcing UDP must deliver frames and forcing TCP must be refused, which proves
``rtsp_transport`` really selects the transport. Needs no camera:

    docker compose -f tests/rtsp/compose.yml run --rm --build tests
"""

import os
import time

import pytest

import faistream
from faistream.streaming.sources import RtspTransport, SourceError, make_source
from tests.helpers import free_port_block

URL = os.environ.get("FAISTREAM_TEST_RTSP_UDP_ONLY", "")

pytestmark = pytest.mark.skipif(
    not URL, reason="set FAISTREAM_TEST_RTSP_UDP_ONLY (see tests/rtsp/compose.yml)"
)


@pytest.fixture(scope="module", autouse=True)
def stream_ready() -> None:
    """The server's test stream starts a few seconds after the container."""
    deadline = time.monotonic() + 60
    while True:
        source = make_source(URL, rtsp_transport="udp", open_timeout=3, read_timeout=3)
        try:
            source.open()
            source.close()
            return
        except SourceError:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)


def read_frames(transport: RtspTransport, count: int = 10) -> tuple[int, ...]:
    source = make_source(URL, rtsp_transport=transport, open_timeout=4, read_timeout=4)
    source.open()
    try:
        for _ in range(count):
            assert source.grab()
        return source.retrieve().shape
    finally:
        source.close()


def test_forced_udp_delivers_frames() -> None:
    assert read_frames("udp") == (720, 1280, 3)


def test_forced_tcp_is_refused_by_udp_only_server() -> None:
    with pytest.raises(SourceError):
        read_frames("tcp")


def test_auto_falls_back_to_udp() -> None:
    assert read_frames("auto") == (720, 1280, 3)


def test_service_streams_rtsp_over_udp() -> None:
    port = free_port_block()
    config = faistream.parse_config(
        {"streams": {"cam": {"source": URL, "rtsp_transport": "udp"}}, "port": port}
    )
    service = faistream.Service(config)
    service.start()
    try:
        with faistream.subscribe("cam", port=port, wait=10) as sub:
            frames = [sub.recv(timeout=15) for _ in range(5)]
        assert all(f.image.shape == (720, 1280, 3) for f in frames)
    finally:
        service.stop()
