import argparse
from pathlib import Path

import pytest

from faistream.cli import _format_streams, _serve_config, _shorten, main
from faistream.config import ConfigError


def serve_args(target: str, **overrides: object) -> argparse.Namespace:
    defaults = {
        "name": "camera",
        "fps": None,
        "size": None,
        "rtsp_transport": None,
        "network": False,
        "port": None,
    }
    return argparse.Namespace(target=target, **{**defaults, **overrides})


def test_serve_single_source() -> None:
    config = _serve_config(
        serve_args("rtsp://h/s", name="door", fps=15, size="640x360", network=True)
    )
    stream = config.streams["door"]
    assert stream.source == "rtsp://h/s" and stream.fps == 15 and stream.size == (640, 360)
    assert config.network is not None


def test_serve_single_source_over_udp() -> None:
    config = _serve_config(serve_args("rtsp://h/s", rtsp_transport="udp"))
    assert config.streams["camera"].rtsp_transport == "udp"


def test_serve_config_file_with_overrides(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("streams:\n  cam:\n    source: synthetic://64x48\n")
    config = _serve_config(serve_args(str(path), port=9000, network=True))
    assert config.port == 9000 and config.network is not None
    assert _serve_config(serve_args(str(path))).port == 7300


def test_serve_config_file_rejects_single_source_flags(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("streams:\n  cam:\n    source: synthetic://64x48\n")
    with pytest.raises(ConfigError, match="single source"):
        _serve_config(serve_args(str(path), fps=5))


def test_format_streams() -> None:
    table = _format_streams(
        [
            {
                "name": "door",
                "state": "streaming",
                "source": "rtsp://u:***@h/s",
                "on_backup": True,
                "fps": 14.96,
                "width": 1280,
                "height": 720,
                "clients": 3,
                "reconnects": 1,
                "error": None,
            },
            {
                "name": "yard",
                "state": "reconnecting",
                "source": "",
                "on_backup": False,
                "fps": 0.0,
                "width": 0,
                "height": 0,
                "clients": 0,
                "reconnects": 4,
                "error": "timeout",
            },
        ]
    )
    header, door, yard = table.splitlines()
    assert header.split() == ["STREAM", "STATE", "SOURCE", "FPS", "SIZE", "CLIENTS", "RECONNECTS"]
    assert "(backup)" in door and "15.0" in door and "1280x720" in door
    assert "timeout" in yard and " - " in yard


def test_shorten() -> None:
    assert _shorten("short") == "short"
    long = "/very/long/path/" + "x" * 80 + "/clip.mp4"
    short = _shorten(long)
    assert len(short) <= 48 and short.endswith("clip.mp4") and "…" in short


def test_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("cameras: [unclosed")
    assert main(["serve", str(bad)]) == 2
    assert main(["ls", "--port", "1"]) == 1
    err = capsys.readouterr().err
    assert "not valid YAML" in err and "faistream serve" in err


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("shm", ("shm", {})),
        ("jpeg:95", ("jpeg", {"quality": 95})),
        ("zstd:5", ("zstd", {"level": 5})),
    ],
)
def test_parse_transport(spec: str, expected: tuple[str, dict[str, int]]) -> None:
    from faistream.bench import parse_transport

    assert parse_transport(spec) == expected


@pytest.mark.parametrize("spec", ["h264", "shm:3", "zstd:max"])
def test_bench_rejects_bad_transport(spec: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["bench", "--transports", spec])
    assert "transport" in capsys.readouterr().err


def test_sigterm_exits_cleanly() -> None:
    # Containers and systemd stop commands with SIGTERM; `view` must exit 0, not hang.
    import signal
    import subprocess
    import sys
    import time

    from tests.helpers import free_port_block

    port = free_port_block(1)  # nothing listens: `view` keeps waiting for the service
    proc = subprocess.Popen(
        [sys.executable, "-m", "faistream", "view", "cam", "--stats", "--port", str(port)],
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=10) == 0
