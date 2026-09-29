"""faistream: decode a camera once, share its frames with many consumers."""

from faistream.client import (
    ServiceUnavailable,
    StreamNotFound,
    Subscriber,
    list_streams,
    subscribe,
)
from faistream.config import ConfigError, load_config, parse_config
from faistream.streaming.service import Service
from faistream.transport.protocol import Frame

__version__ = "0.1.0"

__all__ = [
    "ConfigError",
    "Frame",
    "Service",
    "ServiceUnavailable",
    "StreamNotFound",
    "Subscriber",
    "__version__",
    "list_streams",
    "load_config",
    "parse_config",
    "subscribe",
]
