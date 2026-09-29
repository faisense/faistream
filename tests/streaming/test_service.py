import json
import multiprocessing as mp
import time
from collections.abc import Iterator
from typing import Any

import pytest

import faistream
from faistream import Service, ServiceUnavailable, StreamNotFound, Subscriber, parse_config
from faistream.streaming.service import ServiceError, shm_name
from faistream.transport.shm import ShmRingReader
from tests.helpers import free_port_block


def make_config(port: int, **extra: Any) -> faistream.config.ServiceConfig:
    return parse_config(
        {
            "streams": {
                "cam": {"source": "synthetic://64x48@100"},
                "yard": {"source": "synthetic://32x16@100"},
            },
            "port": port,
            **extra,
        }
    )


@pytest.fixture
def port() -> int:
    return free_port_block()


@pytest.fixture
def service(port: int) -> Iterator[Service]:
    svc = Service(make_config(port, network={"codec": "raw", "bind": "127.0.0.1"}))
    svc.start()
    yield svc
    svc.stop()


def test_local_subscribe(service: Service, port: int) -> None:
    with faistream.subscribe("cam", port=port, wait=5) as sub:
        frames = [sub.recv(timeout=5) for _ in range(5)]
    assert all(f.image.shape == (48, 64, 3) for f in frames)
    seqs = [f.seq for f in frames]
    assert seqs == sorted(seqs) and len(set(seqs)) == 5
    assert frames[-1].age_ms() < 1000
    assert frames[0].image.flags.writeable


def test_zero_copy_subscribe(service: Service, port: int) -> None:
    with faistream.subscribe("yard", port=port, copy=False, wait=5) as sub:
        frame = sub.recv(timeout=5)
        assert frame.image.shape == (16, 32, 3)
        assert not frame.image.flags.writeable


def test_network_subscribe(service: Service, port: int) -> None:
    info = {s["name"]: s for s in faistream.list_streams(port=port)}
    with Subscriber(f"tcp://127.0.0.1:{info['yard']['network_port']}") as sub:
        frame = sub.recv(timeout=5)
    assert frame.image.shape == (16, 32, 3)


def test_many_subscribers(service: Service, port: int) -> None:
    subs = [faistream.subscribe("cam", port=port, wait=5) for _ in range(4)]
    try:
        for sub in subs:
            sub.recv(timeout=5)
        time.sleep(0.1)
        cam = next(s for s in faistream.list_streams(port=port) if s["name"] == "cam")
        assert cam["clients"] == 4
        assert cam["state"] == "streaming" and cam["fps"] > 0
    finally:
        for sub in subs:
            sub.close()


def test_idle_stream_does_not_publish(service: Service, port: int) -> None:
    time.sleep(0.3)
    streams = {s["name"]: s for s in faistream.list_streams(port=port)}
    assert streams["cam"]["seq"] <= 1  # only the first frame, to learn the shape
    assert streams["cam"]["fps"] > 0  # the source is still being read


def test_unknown_stream(service: Service, port: int) -> None:
    with pytest.raises(StreamNotFound, match="available: cam, yard"):
        faistream.subscribe("nope", port=port, wait=0)


def test_no_service(port: int) -> None:
    with pytest.raises(ServiceUnavailable):
        faistream.subscribe("cam", port=port, wait=0)


def test_port_in_use(service: Service, port: int) -> None:
    with pytest.raises(ServiceError, match="another faistream service"):
        Service(make_config(port)).start()


def test_control_rejects_bad_requests(service: Service, port: int) -> None:
    import zmq

    from faistream.client import _socket

    req = _socket(zmq.REQ)
    req.setsockopt(zmq.LINGER, 0)
    req.connect(f"tcp://127.0.0.1:{port}")
    try:
        req.send(b"not json")
        assert req.poll(2000)
        assert json.loads(req.recv())["ok"] is False
    finally:
        req.close()


def test_stop_releases_shared_memory(port: int) -> None:
    svc = Service(make_config(port))
    svc.start()
    with faistream.subscribe("cam", port=port, wait=5) as sub:
        sub.recv(timeout=5)
    svc.stop()
    with pytest.raises(FileNotFoundError):
        ShmRingReader(shm_name(port, "cam"))


def test_subscriber_survives_service_restart(port: int) -> None:
    first = Service(make_config(port))
    first.start()
    sub = faistream.subscribe("cam", port=port, wait=5)
    try:
        before = sub.recv(timeout=5)
        first.stop()
        second = Service(make_config(port))
        second.start()
        try:
            # A frame sent just before the restart may still be delivered; the
            # new service's frames must follow.
            deadline = time.monotonic() + 10
            while sub.recv(timeout=10).epoch == before.epoch:
                assert time.monotonic() < deadline
        finally:
            second.stop()
    finally:
        sub.close()


def _subscribe_in_child(port: int, queue: "mp.Queue[tuple[int, tuple[int, ...]]]") -> None:
    with faistream.subscribe("cam", port=port, wait=5) as sub:
        frames = [sub.recv(timeout=5) for _ in range(3)]
    queue.put((len(frames), frames[-1].image.shape))


def test_subscriber_in_another_process(service: Service, port: int) -> None:
    ctx = mp.get_context("spawn")
    queue: mp.Queue[tuple[int, tuple[int, ...]]] = ctx.Queue()
    child = ctx.Process(target=_subscribe_in_child, args=(port, queue))
    child.start()
    child.join(timeout=30)
    assert child.exitcode == 0
    assert queue.get(timeout=5) == (3, (48, 64, 3))


def test_apply_adds_changes_and_removes_streams(port: int) -> None:
    svc = Service(make_config(port))
    svc.start()
    try:
        with faistream.subscribe("yard", port=port, wait=5) as yard:
            first = yard.recv(timeout=5)
            changed = parse_config(
                {
                    "streams": {
                        "cam": {"source": "synthetic://64x48@100", "fps": 10},  # changed
                        "yard": {"source": "synthetic://32x16@100"},  # unchanged
                        "new": {"source": "synthetic://16x16@100"},  # added
                    },
                    "port": port,
                }
            )
            svc.apply(changed)
            names = {s["name"] for s in faistream.list_streams(port=port)}
            assert names == {"cam", "yard", "new"}
            # The unchanged stream kept running: same session, no gap in frames.
            after = yard.recv(timeout=5)
            assert after.epoch == first.epoch
        with faistream.subscribe("new", port=port, wait=5) as new:
            assert new.recv(timeout=5).image.shape == (16, 16, 3)

        svc.apply(
            parse_config({"streams": {"yard": {"source": "synthetic://32x16@100"}}, "port": port})
        )
        assert [s["name"] for s in faistream.list_streams(port=port)] == ["yard"]
    finally:
        svc.stop()


def test_apply_refuses_network_changes(port: int) -> None:
    svc = Service(make_config(port))
    svc.start()
    try:
        with pytest.raises(ServiceError, match="restart"):
            svc.apply(make_config(port, network=True))
    finally:
        svc.stop()


def test_audience_lists_who_is_connected(service: Service, port: int) -> None:
    info = {s["name"]: s for s in faistream.list_streams(port=port)}
    local = faistream.subscribe("cam", port=port, wait=5)
    remote = Subscriber(f"tcp://127.0.0.1:{info['cam']['network_port']}")
    try:
        local.recv(timeout=5)
        remote.recv(timeout=5)
        time.sleep(0.1)
        cam = service.audience()["cam"]
        assert cam["local"] == 1
        [(address, since)] = cam["network"]
        assert address == "127.0.0.1" and time.time() - since < 10
        assert cam["network_bytes"] >= 64 * 48 * 3  # at least one raw frame
    finally:
        local.close()
        remote.close()
    time.sleep(0.2)
    deadline = time.monotonic() + 3
    while service.audience()["cam"]["network"] and time.monotonic() < deadline:
        time.sleep(0.05)
    assert service.audience()["cam"]["network"] == []
    # viewers' addresses stay off the control port
    assert all("network" not in stream for stream in faistream.list_streams(port=port))


def test_private_subscribers_are_not_programs(service: Service, port: int) -> None:
    endpoint = service.private_endpoint("cam")
    assert endpoint is not None and endpoint != service.describe()[0]["local"]
    with Subscriber(endpoint) as private:
        private.recv(timeout=5)  # frames flow as usual
        time.sleep(0.1)
        cam = next(s for s in faistream.list_streams(port=port) if s["name"] == "cam")
        assert cam["clients"] == 1
        assert service.audience()["cam"]["local"] == 0
