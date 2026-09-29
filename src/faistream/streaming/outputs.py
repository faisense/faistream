"""Where a stream's frames go.

Both outputs publish on a ZeroMQ PUB socket with CONFLATE (latest frame only)
and track connected subscribers through the socket monitor, so a stream nobody
is watching costs no copying or encoding.

- ``LocalOutput``: pixels go into a shared-memory ring; the socket (loopback
  only) carries just a 36-byte "frame N is ready" header. Zero codec cost.
- ``NetworkOutput``: pixels are encoded (JPEG by default) and sent over TCP.
"""

from __future__ import annotations

import os
import secrets
import socket
import time

import numpy as np
import zmq
from zmq.utils.monitor import recv_monitor_message

from faistream.transport.codecs import Encoder
from faistream.transport.protocol import Codec, Header
from faistream.transport.shm import ShmRingWriter


class _PubSocket:
    def __init__(self, context: zmq.Context[zmq.Socket[bytes]], endpoint: str) -> None:
        self.socket = context.socket(zmq.PUB)
        self.socket.setsockopt(zmq.CONFLATE, 1)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.bind(endpoint)
        self.endpoint = self.socket.getsockopt_string(zmq.LAST_ENDPOINT)
        self._monitor = self.socket.get_monitor_socket(zmq.EVENT_ACCEPTED | zmq.EVENT_DISCONNECTED)
        self.clients = 0
        # connection -> (address, connected at, the endpoint it came in on). Replaced,
        # never changed in place, so other threads can read it.
        self.peers: dict[int, tuple[str, float, str]] = {}
        self.bytes_sent = 0

    @property
    def port(self) -> int:
        return int(self.endpoint.rsplit(":", 1)[1])

    def bind(self, endpoint: str) -> str:
        """Also listen on ``endpoint``; returns the address it got."""
        self.socket.bind(endpoint)
        return self.socket.getsockopt_string(zmq.LAST_ENDPOINT)

    def poll_clients(self) -> int:
        while self._monitor.poll(0):
            message = recv_monitor_message(self._monitor)
            event, fd = message["event"], int(message["value"])  # the value is the connection's fd
            if event == zmq.EVENT_ACCEPTED:
                peer = (_peer_address(fd), time.time(), message["endpoint"].decode())
                self.peers = {**self.peers, fd: peer}
            elif event == zmq.EVENT_DISCONNECTED:
                self.peers = {key: peer for key, peer in self.peers.items() if key != fd}
            self.clients = len(self.peers)
        return self.clients

    def send(self, header: Header, payload: bytes | memoryview) -> None:
        message = b"".join((header.pack(), payload))
        self.socket.send(message, zmq.NOBLOCK)
        self.bytes_sent += len(message) * self.clients

    def close(self) -> None:
        self.socket.disable_monitor()
        self._monitor.close()
        self.socket.close()


def _peer_address(fd: int) -> str:
    """The IP address at the other end of a connection ZeroMQ accepted."""
    try:
        conn = socket.socket(fileno=os.dup(fd))
    except OSError:  # already closed, or not a plain socket (Windows)
        return "unknown"
    with conn:
        try:
            address = str(conn.getpeername()[0])
        except OSError:
            return "unknown"
    return address.removeprefix("::ffff:")  # IPv4 seen through an IPv6 socket


class LocalOutput:
    def __init__(self, context: zmq.Context[zmq.Socket[bytes]], shm_name: str, slots: int = 4):
        self._ring = ShmRingWriter(shm_name, slots)
        self._name = shm_name.encode()
        self._pub = _PubSocket(context, "tcp://127.0.0.1:*")
        # An app embedding the service (like a web page) subscribes on a port of its own,
        # so its own viewers are never counted as programs watching.
        self.private_endpoint = self._pub.bind("tcp://127.0.0.1:*")

    @property
    def endpoint(self) -> str:
        return self._pub.endpoint

    @property
    def clients(self) -> int:
        return self._pub.clients

    @property
    def programs(self) -> int:
        """Subscribers on this machine, not counting the private endpoint's."""
        return sum(peer[2] != self.private_endpoint for peer in self._pub.peers.values())

    def wants_frames(self) -> bool:
        return self._pub.poll_clients() > 0

    def publish(self, image: np.ndarray, seq: int, timestamp_ns: int) -> None:
        if not self._pub.clients:
            return
        self._ring.write(image, seq, timestamp_ns)
        header = Header.for_image(image, Codec.SHM, self._ring.epoch, seq, timestamp_ns)
        self._pub.send(header, self._name)

    def close(self) -> None:
        self._pub.close()
        self._ring.close()


class NetworkOutput:
    def __init__(self, context: zmq.Context[zmq.Socket[bytes]], endpoint: str, encoder: Encoder):
        self._encoder = encoder
        self._epoch = secrets.randbits(32)
        self._pub = _PubSocket(context, endpoint)

    @property
    def port(self) -> int:
        return self._pub.port

    @property
    def clients(self) -> int:
        return self._pub.clients

    @property
    def peers(self) -> list[tuple[str, float]]:
        """Each connected machine's IP address and when it connected (``time.time()``)."""
        return [(address, since) for address, since, _ in self._pub.peers.values()]

    @property
    def bytes_sent(self) -> int:
        return self._pub.bytes_sent

    def wants_frames(self) -> bool:
        return self._pub.poll_clients() > 0

    def publish(self, image: np.ndarray, seq: int, timestamp_ns: int) -> None:
        if not self._pub.clients:
            return
        header = Header.for_image(image, self._encoder.codec, self._epoch, seq, timestamp_ns)
        self._pub.send(header, self._encoder.encode(image))

    def close(self) -> None:
        self._pub.close()
