"""Subscribing to streams.

    import faistream

    for frame in faistream.subscribe("front-door"):                  # same host: shared memory
        ...
    for frame in faistream.subscribe("front-door", host="10.0.0.5"): # remote: TCP
        ...

Subscribers always get the latest frame: if they are slower than the stream,
older frames are skipped (counted in ``stats.skipped``), never queued.
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np
import zmq

from faistream.config import DEFAULT_PORT
from faistream.transport.codecs import Decoder
from faistream.transport.protocol import HEADER_SIZE, Codec, Frame, Header
from faistream.transport.shm import ShmRingReader

log = logging.getLogger(__name__)

_LOCAL_HOSTS = {None, "", "localhost", "127.0.0.1", "::1"}


def _socket(kind: int) -> zmq.Socket[bytes]:
    context: zmq.Context[zmq.Socket[bytes]] = zmq.Context.instance()
    return context.socket(kind)


class ServiceUnavailable(ConnectionError):
    """No faistream service answered on the control port."""


class StreamNotFound(LookupError):
    pass


def list_streams(
    host: str | None = None, port: int = DEFAULT_PORT, timeout: float = 2.0
) -> list[dict[str, Any]]:
    """Ask a service for the status of all its streams."""
    socket = _socket(zmq.REQ)
    socket.setsockopt(zmq.LINGER, 0)
    address = f"tcp://{host or '127.0.0.1'}:{port}"
    try:
        socket.connect(address)
        socket.send(json.dumps({"cmd": "streams"}).encode())
        if not socket.poll(int(timeout * 1000)):
            raise ServiceUnavailable(f"no faistream service answered at {address}")
        reply = json.loads(socket.recv())
    finally:
        socket.close()
    if not reply.get("ok"):
        raise ServiceUnavailable(f"service at {address} returned an error: {reply.get('error')}")
    return list(reply["streams"])


def resolve(
    stream: str, host: str | None = None, port: int = DEFAULT_PORT, timeout: float = 2.0
) -> str:
    """Return the endpoint to subscribe to for ``stream``."""
    streams = {s["name"]: s for s in list_streams(host, port, timeout)}
    if stream not in streams:
        available = ", ".join(sorted(streams)) or "none"
        raise StreamNotFound(f"no stream named {stream!r} (available: {available})")
    info = streams[stream]
    if host in _LOCAL_HOSTS:
        return str(info["local"])
    if info["network_port"] is None:
        raise StreamNotFound(
            f"stream {stream!r} is not shared over the network; enable 'network' on the service"
        )
    return f"tcp://{host}:{info['network_port']}"


def subscribe(
    stream: str,
    host: str | None = None,
    port: int = DEFAULT_PORT,
    *,
    copy: bool = True,
    wait: float | None = None,
) -> Subscriber:
    """Subscribe to a stream by name.

    Uses shared memory when ``host`` is local and TCP otherwise. If the service
    is not up yet, retries for ``wait`` seconds (``None``: forever). The
    subscriber re-resolves the stream on its own if the service restarts.
    """
    deadline = None if wait is None else time.monotonic() + wait
    announced = False
    while True:
        try:
            endpoint = resolve(stream, host, port)
            break
        except (ServiceUnavailable, StreamNotFound) as exc:
            if deadline is not None and time.monotonic() >= deadline:
                raise
            if not announced:
                log.warning("%s; waiting...", exc)
                announced = True
            time.sleep(1.0)
    return Subscriber(
        endpoint, copy=copy, resolver=lambda: resolve(stream, host, port, timeout=0.5)
    )


@dataclass
class Stats:
    received: int = 0
    skipped: int = 0
    fps: float = 0.0
    bytes: int = 0  # received on the socket (for shared memory: just the notifications)


class Subscriber:
    """Low-level subscriber for a known endpoint. Prefer :func:`subscribe`.

    With ``copy=False`` shared-memory frames are read-only views that stay valid
    for a few frame intervals; RAW/ZSTD network frames are always read-only.
    Call ``frame.image.copy()`` before drawing on them.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        copy: bool = True,
        resolver: Callable[[], str] | None = None,
        resolve_after: float = 2.0,
    ) -> None:
        self.endpoint = endpoint
        self.stats = Stats()
        self._copy = copy
        self._resolver = resolver
        self._resolve_after = resolve_after
        self._decoder = Decoder()
        self._reader: ShmRingReader | None = None
        self._last: tuple[int, int] | None = None  # (epoch, seq)
        self._times: deque[float] = deque(maxlen=30)
        self._socket = self._connect(endpoint)

    def _connect(self, endpoint: str) -> zmq.Socket[bytes]:
        socket = _socket(zmq.SUB)
        socket.setsockopt(zmq.CONFLATE, 1)
        socket.setsockopt(zmq.LINGER, 0)
        socket.setsockopt(zmq.SUBSCRIBE, b"")
        socket.connect(endpoint)
        return socket

    def recv(self, timeout: float | None = None) -> Frame:
        """Wait for the next frame. Raises ``TimeoutError`` after ``timeout`` seconds."""
        deadline = None if timeout is None else time.monotonic() + timeout
        quiet_since = time.monotonic()
        while True:
            wait_ms = (
                250
                if deadline is None
                else max(0, min(250, int((deadline - time.monotonic()) * 1000)))
            )
            if self._socket.poll(wait_ms):
                message = self._socket.recv(copy=False)
                self.stats.bytes += len(message.buffer)
                frame = self._handle(message)
                if frame is not None:
                    return frame
                quiet_since = time.monotonic()
                continue
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                raise TimeoutError(f"no frame from {self.endpoint} within {timeout}s")
            if self._resolver is not None and now - quiet_since >= self._resolve_after:
                quiet_since = now
                self._reresolve()

    def __iter__(self) -> Iterator[Frame]:
        while True:
            yield self.recv()

    def close(self) -> None:
        self._socket.close()
        if self._reader is not None:
            self._reader.close()
            self._reader = None

    def __enter__(self) -> Subscriber:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _handle(self, message: zmq.Frame) -> Frame | None:
        buffer = message.buffer
        header = Header.unpack(buffer)
        payload = buffer[HEADER_SIZE:]
        self._count_gap(header)
        if header.codec is Codec.SHM:
            image = self._read_shm(header, bytes(payload).decode())
            if image is None:  # overwritten before we got to it
                self.stats.skipped += 1
                return None
        else:
            image = self._decoder.decode(header, payload)
        self._count_received()
        return Frame(image, header.seq, header.timestamp_ns, header.epoch)

    def _read_shm(self, header: Header, name: str) -> np.ndarray | None:
        reader = self._reader
        if reader is None or reader.name != name or reader.epoch != header.epoch:
            if reader is not None:
                reader.close()
            try:
                reader = self._reader = ShmRingReader(name)
            except FileNotFoundError:
                self._reader = None
                return None
            if reader.epoch != header.epoch:
                return None  # the ring was re-created after this notification
        return reader.read(header.seq, copy=self._copy)

    def _count_gap(self, header: Header) -> None:
        last = self._last
        if last is not None and last[0] == header.epoch and header.seq > last[1]:
            self.stats.skipped += header.seq - last[1] - 1
        self._last = (header.epoch, header.seq)

    def _count_received(self) -> None:
        stats = self.stats
        stats.received += 1
        now = time.monotonic()
        self._times.append(now)
        if len(self._times) > 1:
            stats.fps = round((len(self._times) - 1) / (self._times[-1] - self._times[0]), 1)

    def _reresolve(self) -> None:
        assert self._resolver is not None
        try:
            endpoint = self._resolver()
        except (ServiceUnavailable, StreamNotFound):
            return
        if endpoint != self.endpoint:
            log.info("stream moved to %s; reconnecting", endpoint)
            self._socket.close()
            self._socket = self._connect(endpoint)
            self.endpoint = endpoint
