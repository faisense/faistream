"""Service configuration.

    streams:
      door:
        source: rtsp://admin:secret@192.168.1.21/Streaming/Channels/101
        backup: yard           # optional: another stream's name, or a source
        fps: 15                # optional cap
      yard:
        source: rtsp://admin:secret@192.168.1.22/profile2/media.smp
      replay:
        source: ./recordings/lobby.mp4   # any source: RTSP URL, file, device, synthetic://
    network: true              # optional: also share frames with other machines

``cameras`` is accepted as another name for ``streams``, and ``${VAR}`` /
``${VAR:-default}`` are expanded from the environment.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

import yaml
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

DEFAULT_PORT = 7300

StreamName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")]
Target = str | int
# ${VAR} or ${VAR:-default}: expanded from the environment when the config is read.
ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_SIZE = re.compile(r"^(\d+)x(\d+)$")
_BRANCH = re.compile(r"^(str|int|float|bool|list\[.*\]|tuple\[.*\]|function-.*|\[key\])$")


class ConfigError(ValueError):
    """The configuration is invalid; the message is meant for humans."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StreamConfig(_Model):
    source: Target  # an RTSP/HTTP URL, file, device number, GStreamer pipeline or synthetic://
    backup: Target | list[Target] | None = None
    fps: float | None = Field(default=None, gt=0)
    size: tuple[int, int] | None = None
    open_timeout: float = Field(default=5.0, gt=0)
    read_timeout: float = Field(default=5.0, gt=0)
    rtsp_transport: Literal["auto", "tcp", "udp"] = "auto"
    paused: bool = False  # not streaming until set back to false

    @field_validator("size", mode="before")
    @classmethod
    def _parse_size(cls, value: Any) -> Any:
        if isinstance(value, str):
            match = _SIZE.match(value.strip().lower())
            if not match:
                raise ValueError("expected WIDTHxHEIGHT, e.g. 1280x720")
            return int(match[1]), int(match[2])
        return value

    @field_validator("size")
    @classmethod
    def _positive_size(cls, value: tuple[int, int] | None) -> tuple[int, int] | None:
        if value is not None and min(value) <= 0:
            raise ValueError("width and height must be positive")
        return value

    @property
    def primary(self) -> Target:
        return self.source

    @property
    def backups(self) -> list[Target]:
        items = self.backup if isinstance(self.backup, list) else [self.backup]
        return [b for b in items if b is not None]

    @property
    def sources(self) -> list[Target]:
        """This stream's sources, with backups given as camera names left unresolved."""
        return [self.primary, *self.backups]


class NetworkConfig(_Model):
    codec: Literal["jpeg", "raw", "zstd"] = "jpeg"
    quality: int = Field(default=85, ge=1, le=100, description="JPEG quality")
    level: int = Field(default=3, ge=1, le=22, description="zstd level")
    bind: str = "0.0.0.0"


class ServiceConfig(_Model):
    streams: dict[StreamName, StreamConfig] = Field(
        default_factory=dict, validation_alias=AliasChoices("cameras", "streams")
    )
    network: NetworkConfig | None = None
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    slots: int = Field(default=4, ge=2, le=64, description="shared-memory frames per stream")

    @field_validator("network", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> Any:
        if value is True:
            return {}
        if value is False:
            return None
        return value

    @model_validator(mode="after")
    def _backups_exist(self) -> ServiceConfig:
        for name, stream in self.streams.items():
            if name in stream.backups:
                raise ValueError(f"camera {name!r} can't be its own backup")
        return self

    @property
    def control_host(self) -> str:
        return self.network.bind if self.network else "127.0.0.1"

    def sources_for(self, name: str) -> list[Target]:
        """A stream's sources; a backup that names another camera uses that camera's stream."""
        stream = self.streams[name]
        backups = [
            self.streams[b].primary if isinstance(b, str) and b in self.streams else b
            for b in stream.backups
        ]
        return [stream.primary, *backups]


M = TypeVar("M", bound=BaseModel)


def validate(model: type[M], data: Any) -> M:
    """``data`` as ``model``, with ``${VAR}`` expanded. Problems are reported per setting,
    like ``streams.door.fps: Input should be greater than 0``."""
    try:
        return model.model_validate(expand_env(data or {}))
    except ValidationError as exc:
        raise ConfigError("invalid configuration:\n" + _format_errors(exc)) from None


def parse_config(data: Any) -> ServiceConfig:
    return validate(ServiceConfig, data)


def _format_errors(exc: ValidationError) -> str:
    # Group by location, hiding pydantic's union-branch names (".str", ".int", ...).
    grouped: dict[str, list[str]] = {}
    for err in exc.errors():
        parts = [str(p) for p in err["loc"] if not _BRANCH.match(str(p))]
        message = err["msg"].removeprefix("Value error, ")
        grouped.setdefault(".".join(parts) or "(root)", []).append(message)
    lines: list[str] = []
    prefix = "Input should be a valid "
    for where, messages in grouped.items():
        if len(messages) > 1 and all(m.startswith(prefix) for m in messages):
            kinds = " or ".join(m.removeprefix(prefix) for m in messages)
            messages = [prefix + kinds]
        lines.extend(f"  {where}: {message}" for message in dict.fromkeys(messages))
    return "\n".join(lines)


def load_config(path: str | Path, overrides: dict[str, Any] | None = None) -> ServiceConfig:
    """The config file at ``path``; ``overrides`` (from the command line) win over it."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} should contain settings like 'streams:'")
    return parse_config({**data, **(overrides or {})})


def expand_env(data: Any, environ: dict[str, str] | None = None) -> Any:
    """Expand ``${VAR}`` / ``${VAR:-default}`` in every string of a parsed document."""
    env = os.environ if environ is None else environ
    missing: set[str] = set()

    def substitute(match: re.Match[str]) -> str:
        name, default = match[1], match[2]
        if name in env:
            return env[name]
        if default is not None:
            return default
        missing.add(name)
        return match[0]

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            return ENV_REFERENCE.sub(substitute, node)
        if isinstance(node, dict):
            return {key: walk(value) for key, value in node.items()}
        if isinstance(node, list):
            return [walk(value) for value in node]
        return node

    result = walk(data)
    if missing:
        raise ConfigError(f"environment variables not set: {', '.join(sorted(missing))}")
    return result
