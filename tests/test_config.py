from pathlib import Path

import pytest

from faistream.config import ConfigError, expand_env, load_config, parse_config


def test_minimal_config() -> None:
    config = parse_config({"streams": {"cam": {"source": "rtsp://h/s"}}})
    stream = config.streams["cam"]
    assert stream.sources == ["rtsp://h/s"]
    assert stream.fps is None and stream.size is None
    assert config.network is None
    assert config.control_host == "127.0.0.1"


def test_full_config() -> None:
    config = parse_config(
        {
            "streams": {
                "front-door": {
                    "source": "rtsp://a/s",
                    "backup": ["rtsp://b/s", 0],
                    "fps": 15,
                    "size": "1280x720",
                }
            },
            "network": {"codec": "zstd", "level": 3},
            "port": 8000,
        }
    )
    stream = config.streams["front-door"]
    assert stream.sources == ["rtsp://a/s", "rtsp://b/s", 0]
    assert stream.size == (1280, 720)
    assert config.network is not None and config.network.codec == "zstd"
    assert config.control_host == "0.0.0.0"


def test_rtsp_transport() -> None:
    config = parse_config({"streams": {"c": {"source": "rtsp://h/s", "rtsp_transport": "udp"}}})
    assert config.streams["c"].rtsp_transport == "udp"
    assert parse_config({"streams": {"c": {"source": 0}}}).streams["c"].rtsp_transport == "auto"
    with pytest.raises(ConfigError, match="rtsp_transport"):
        parse_config({"streams": {"c": {"source": 0, "rtsp_transport": "quic"}}})


def test_network_flag() -> None:
    config = parse_config({"streams": {"c": {"source": 0}}, "network": True})
    assert config.network is not None and config.network.codec == "jpeg"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"streams": {"c": {"source": 0, "fps": 0}}}, "streams.c.fps"),
        ({"streams": {"c": {"source": 0, "size": "big"}}}, "WIDTHxHEIGHT"),
        ({"streams": {"c": {"source": 0, "colour": "red"}}}, "streams.c.colour"),
        ({"streams": {"bad name": {"source": 0}}}, "bad name"),
        ({"streams": {"c": {"source": 0}}, "network": {"codec": "h264"}}, "network.codec"),
    ],
)
def test_errors_are_readable(data: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigError, match="invalid configuration") as info:
        parse_config(data)
    assert message in str(info.value)


def test_expand_env() -> None:
    env = {"USER": "admin", "PASS": "p@ss"}
    data = {"url": "rtsp://${USER}:${PASS}@h/${PATH_PART:-main}", "n": 3, "l": ["${USER}"]}
    assert expand_env(data, env) == {"url": "rtsp://admin:p@ss@h/main", "n": 3, "l": ["admin"]}


def test_expand_env_reports_all_missing() -> None:
    with pytest.raises(ConfigError, match="A, B"):
        expand_env({"x": "${B}${A}"}, {})


def test_load_config_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAM_PASS", "secret")
    path = tmp_path / "cameras.yaml"
    path.write_text("streams:\n  cam:\n    source: rtsp://u:${CAM_PASS}@h/s\n")
    assert load_config(path).streams["cam"].source == "rtsp://u:secret@h/s"


def test_load_config_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("streams: [unclosed")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(bad)


def test_backup_cannot_be_itself() -> None:
    with pytest.raises(ConfigError, match="own backup"):
        parse_config({"cameras": {"a": {"source": "synthetic://64x48", "backup": "a"}}})
