"""The streaming service: one worker per stream plus a small control port.

The control port (REQ/REP, JSON) is how clients find streams by name, so users
never deal with ports: ``{"cmd": "streams"}`` returns every stream's status and
where to subscribe to it.

Streams can be added, changed and removed while the service runs (``apply``);
only the streams that changed restart.
"""

from __future__ import annotations

import hashlib
import json
import logging
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import zmq

from faistream.config import ServiceConfig
from faistream.streaming.outputs import LocalOutput, NetworkOutput
from faistream.streaming.sources import Source, make_source
from faistream.streaming.worker import Output, StreamWorker
from faistream.transport.codecs import make_encoder
from faistream.transport.protocol import Codec
from faistream.transport.shm import unlink

log = logging.getLogger(__name__)

CONTROL_VERSION = 1
SourceFactory = Callable[..., Source]


class ServiceError(RuntimeError):
    pass


class Companion(Protocol):
    """Something that runs alongside the service, like a web server embedding it."""

    def start(self) -> None: ...
    def stop(self) -> None: ...


def shm_name(port: int, stream: str) -> str:
    # Short (macOS allows 31 chars) and unique per service instance, since only
    # one service can hold a given control port.
    return f"fs{port}_{hashlib.sha1(stream.encode()).hexdigest()[:8]}"


@dataclass
class _Stream:
    worker: StreamWorker
    local: LocalOutput
    network: NetworkOutput | None
    shm: str
    grace: float  # how long a stop may take: the source's open + read timeouts

    def describe(self) -> dict[str, Any]:
        return {
            **self.worker.status().to_dict(),
            "local": self.local.endpoint,
            "network_port": self.network.port if self.network else None,
        }

    def audience(self) -> dict[str, Any]:
        network = self.network
        return {
            "local": self.local.programs,
            "network": network.peers if network else [],
            "network_bytes": network.bytes_sent if network else 0,
        }


class Service:
    def __init__(self, config: ServiceConfig, *, source_factory: SourceFactory = make_source):
        self.config = config
        self._source_factory = source_factory
        self._context: zmq.Context[zmq.Socket[bytes]] | None = None
        self._control: zmq.Socket[bytes] | None = None
        self._control_thread: threading.Thread | None = None
        self._streams: dict[str, _Stream] = {}
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        self._stuck = False
        self.started: float | None = None  # time.time() when start() finished

    @property
    def control_endpoint(self) -> str:
        return f"tcp://{self.config.control_host}:{self.config.port}"

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._context = zmq.Context()
        try:
            self._control = self._context.socket(zmq.REP)
            self._control.setsockopt(zmq.LINGER, 0)
            _listen(
                self._control,
                self.control_endpoint,
                "is another faistream service running? Set a different 'port'.",
            )
            # In config order, so network ports are predictable: port+1, port+2, ...
            for name in self.config.streams:
                self._add(name)
        except BaseException:
            for stream in self._streams.values():
                stream.worker.stop()
            self._stop_streams(list(self._streams.values()))
            self._streams.clear()
            self._context.destroy(linger=0)  # closes the control socket too
            self._context = self._control = None
            raise

        self._control_thread = threading.Thread(
            target=self._serve_control, name="control", daemon=True
        )
        self._control_thread.start()
        self.started = time.time()
        log.info(
            "faistream listening on %s with %d stream(s)", self.control_endpoint, len(self._streams)
        )

    def stop(self) -> None:
        self._stopping.set()
        with self._lock:
            streams = list(self._streams.values())
            self._streams.clear()
        self._stop_streams(streams)
        if self._control_thread is not None:
            self._control_thread.join(timeout=2)
        if self._context is not None and not self._stuck:
            self._context.destroy(linger=0)
        log.info("faistream stopped")

    def request_stop(self) -> None:
        """Make ``serve_forever`` return, stopping everything cleanly."""
        self._stopping.set()

    def serve_forever(self, *companions: Companion) -> None:
        """Run, with any companions, until SIGINT/SIGTERM."""
        self.start()
        started: list[Companion] = []
        previous = {
            sig: signal.signal(sig, lambda *_: self._stopping.set())
            for sig in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            for companion in companions:
                companion.start()
                started.append(companion)
            while not self._stopping.wait(0.5):
                pass
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            for companion in reversed(started):
                companion.stop()
            self.stop()

    # -- changing streams while running ------------------------------------

    def apply(self, config: ServiceConfig) -> None:
        """Switch to ``config``: start new streams, stop removed ones, restart changed ones."""
        old = self.config
        if (config.network, config.port, config.slots) != (old.network, old.port, old.slots):
            raise ServiceError("changing network, port or slots needs a restart of faistream")
        with self._lock:
            stale = [
                name
                for name in self._streams
                if name not in config.streams
                or config.streams[name] != old.streams[name]
                or config.sources_for(name) != old.sources_for(name)
            ]
            removed = [self._streams.pop(name) for name in stale]
            self.config = config
        self._stop_streams(removed)
        with self._lock:
            for name in config.streams:
                if name not in self._streams:
                    self._add(name)
        added = sorted(set(config.streams) - set(old.streams))
        gone = sorted(set(old.streams) - set(config.streams))
        restarted = sorted(set(stale) & set(config.streams))
        for label, names in (("added", added), ("removed", gone), ("restarted", restarted)):
            if names:
                log.info("%s: %s", label, ", ".join(names))

    def describe(self) -> list[dict[str, Any]]:
        with self._lock:
            streams = list(self._streams.values())
        return [stream.describe() for stream in streams]

    def audience(self) -> dict[str, dict[str, Any]]:
        """Who is connected to each stream: the number of programs on this machine,
        and each other machine's address and since when. For apps embedding the service; the
        control port doesn't share viewers' addresses."""
        with self._lock:
            streams = dict(self._streams)
        return {name: stream.audience() for name, stream in streams.items()}

    def private_endpoint(self, name: str) -> str | None:
        """Where an app embedding the service subscribes for itself: its subscribers
        aren't counted as programs in ``audience()`` (see outputs.py)."""
        with self._lock:
            stream = self._streams.get(name)
            return stream.local.private_endpoint if stream else None

    # -- internals ---------------------------------------------------------

    def _add(self, name: str) -> None:
        assert self._context is not None
        cfg = self.config.streams[name]
        sources = [
            self._source_factory(
                target,
                open_timeout=cfg.open_timeout,
                read_timeout=cfg.read_timeout,
                rtsp_transport=cfg.rtsp_transport,
            )
            for target in self.config.sources_for(name)
        ]
        remote = self._network_output(name) if self.config.network else None
        try:
            local = LocalOutput(self._context, shm_name(self.config.port, name), self.config.slots)
        except BaseException:
            if remote is not None:
                remote.close()
            raise
        outputs: list[Output] = [local] if remote is None else [local, remote]
        worker = StreamWorker(
            name, sources, outputs, max_fps=cfg.fps, size=cfg.size, paused=cfg.paused
        )
        grace = cfg.open_timeout + cfg.read_timeout
        self._streams[name] = _Stream(
            worker, local, remote, shm_name(self.config.port, name), grace
        )
        worker.start()

    def _network_output(self, name: str) -> NetworkOutput:
        assert self._context is not None and self.config.network is not None
        network = self.config.network
        encoder = make_encoder(
            Codec[network.codec.upper()], quality=network.quality, level=network.level
        )
        # The lowest free port after the control port; clients look it up by name.
        used = {s.network.port for s in self._streams.values() if s.network is not None}
        candidates = [p for p in range(self.config.port + 1, 65536) if p not in used][:100]
        for port in candidates:
            try:
                return NetworkOutput(self._context, f"tcp://{network.bind}:{port}", encoder)
            except zmq.ZMQError:
                continue
        raise ServiceError(
            f"stream {name!r}: no free network port after {self.config.port} on {network.bind}"
        )

    def _stop_streams(self, streams: list[_Stream]) -> None:
        for stream in streams:
            stream.worker.stop()
        for stream in streams:
            if stream.worker.ident is not None:
                stream.worker.join(timeout=stream.grace + 1)
            if stream.worker.is_alive():
                # Still blocked inside the video backend. Its sockets can't be
                # closed from this thread safely; just release the shared memory.
                log.warning("%s: did not stop in time", stream.worker.stream_name)
                unlink(stream.shm)
                self._stuck = True
                continue
            stream.local.close()
            if stream.network:
                stream.network.close()

    def _serve_control(self) -> None:
        assert self._control is not None
        control = self._control
        try:
            while not self._stopping.is_set():
                if not control.poll(200):
                    continue
                raw = control.recv()
                try:
                    request = json.loads(raw)
                    if not isinstance(request, dict) or request.get("cmd") != "streams":
                        raise ValueError('unknown command; expected {"cmd": "streams"}')
                    reply: dict[str, Any] = {
                        "ok": True,
                        "version": CONTROL_VERSION,
                        "streams": self.describe(),
                    }
                except ValueError as exc:
                    reply = {"ok": False, "version": CONTROL_VERSION, "error": str(exc)}
                control.send(json.dumps(reply).encode())
        finally:
            control.close()


def _listen(socket: zmq.Socket[bytes], endpoint: str, hint: str) -> None:
    try:
        socket.bind(endpoint)
    except zmq.ZMQError as exc:
        raise ServiceError(f"cannot listen on {endpoint} ({exc}); {hint}") from None
