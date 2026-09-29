"""``faistream bench``: measure each transport on this machine.

For every transport and subscriber count, a service is started (by default with a
synthetic camera, or with ``--source``), subscribers run in separate processes,
and we record delivered fps, capture-to-consumer latency, CPU cost on both sides
and bytes per frame.

Compression depends heavily on the scene, so measure codecs on your own cameras:

    faistream bench --source rtsp://... --transports shm jpeg zstd:1 zstd:3 zstd:5
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import socket
import statistics
import time
from dataclasses import dataclass
from typing import Any

from faistream.config import parse_config
from faistream.streaming.service import Service

_WARMUP = 1.0


@dataclass
class Result:
    transport: str
    subscribers: int
    fps: float
    p50_ms: float
    p95_ms: float
    publisher_cpu: float
    subscriber_cpu: float
    frame_kb: float
    skipped: float


TRANSPORTS = ("shm", "raw", "jpeg", "zstd")


def parse_transport(spec: str) -> tuple[str, dict[str, int]]:
    """``shm``, ``raw``, ``jpeg[:QUALITY]`` or ``zstd[:LEVEL]`` -> (codec, network options)."""
    name, _, param = spec.partition(":")
    if name not in TRANSPORTS:
        raise ValueError(f"unknown transport {spec!r}; expected one of {', '.join(TRANSPORTS)}")
    if not param:
        return name, {}
    key = {"jpeg": "quality", "zstd": "level"}.get(name)
    if key is None or not param.isdigit():
        raise ValueError(f"invalid transport {spec!r}; e.g. jpeg:95 or zstd:5")
    return name, {key: int(param)}


def run(args: argparse.Namespace) -> None:
    stream: dict[str, Any] = {"source": args.source or f"synthetic://{args.size}@{args.fps:g}"}
    if args.source and args.size:
        stream["size"] = args.size
    if args.source and args.fps:
        stream["fps"] = args.fps
    if args.source:
        stream["rtsp_transport"] = args.rtsp_transport
    results = []
    title = ""
    for spec in args.transports:
        if not _available(spec):
            print(f"skipping {spec}: optional dependency not installed")
            continue
        for count in args.subscribers:
            print(f"measuring {spec} with {count} subscriber(s)...", flush=True)
            result, title = _measure(spec, count, stream, args.seconds)
            results.append(result)
    print()
    print(format_results(results, title, markdown=args.markdown))
    if not args.source:
        print(
            "\nnote: synthetic frames are noisier than real video, so codec sizes here are "
            "pessimistic.\nMeasure compression on your own camera with --source."
        )


def _measure(spec: str, count: int, stream: dict[str, Any], seconds: float) -> tuple[Result, str]:
    transport, options = parse_transport(spec)
    port = _free_port()
    config: dict[str, Any] = {"streams": {"bench": stream}, "port": port}
    if transport != "shm":
        config["network"] = {"codec": transport, "bind": "127.0.0.1", **options}
    service = Service(parse_config(config))
    service.start()
    ctx = mp.get_context("spawn")
    queue: mp.Queue[dict[str, Any]] = ctx.Queue()
    try:
        target = None if transport == "shm" else f"tcp://127.0.0.1:{port + 1}"
        procs = [
            ctx.Process(target=_subscriber, args=(port, target, seconds, queue))
            for _ in range(count)
        ]
        for proc in procs:
            proc.start()
        time.sleep(_WARMUP + 0.5)  # let subscribers connect and warm up
        cpu0, t0 = time.process_time(), time.monotonic()
        time.sleep(seconds)
        publisher_cpu = (time.process_time() - cpu0) / (time.monotonic() - t0) * 100
        reports = [queue.get(timeout=seconds + 30) for _ in procs]
        for proc in procs:
            proc.join(timeout=10)
        status = service.describe()[0]
    finally:
        service.stop()
    title = f"{status['source']} ({status['width']}x{status['height']} @ {status['fps']:.0f} fps)"
    latencies = sorted(lat for r in reports for lat in r["latencies"])
    result = Result(
        transport=spec,
        subscribers=count,
        fps=statistics.mean(r["fps"] for r in reports),
        p50_ms=_percentile(latencies, 50),
        p95_ms=_percentile(latencies, 95),
        publisher_cpu=publisher_cpu,
        subscriber_cpu=statistics.mean(r["cpu"] for r in reports),
        frame_kb=statistics.mean(r["bytes"] for r in reports) / 1024,
        skipped=statistics.mean(r["skipped"] for r in reports),
    )
    return result, title


def _subscriber(
    port: int, endpoint: str | None, seconds: float, queue: mp.Queue[dict[str, Any]]
) -> None:
    import faistream
    from faistream.client import Subscriber

    sub = (
        faistream.subscribe("bench", port=port, wait=10)
        if endpoint is None
        else Subscriber(endpoint)
    )
    with sub:
        sub.recv(timeout=10)
        deadline = time.monotonic() + _WARMUP
        while time.monotonic() < deadline:
            sub.recv(timeout=5)
        received0, skipped0, bytes0 = sub.stats.received, sub.stats.skipped, sub.stats.bytes
        latencies: list[float] = []
        cpu0, t0 = time.process_time(), time.monotonic()
        while time.monotonic() - t0 < seconds:
            latencies.append(sub.recv(timeout=5).age_ms())
        elapsed = time.monotonic() - t0
        frames = sub.stats.received - received0
    queue.put(
        {
            "fps": frames / elapsed,
            "latencies": latencies,
            "cpu": (time.process_time() - cpu0) / elapsed * 100,
            "bytes": (sub.stats.bytes - bytes0) / max(frames, 1),
            "skipped": sub.stats.skipped - skipped0,
        }
    )


def format_results(results: list[Result], title: str, *, markdown: bool = False) -> str:
    headers = [
        "transport",
        "subs",
        "fps/sub",
        "latency p50",
        "p95",
        "service CPU",
        "CPU/sub",
        "wire/frame",
        "skipped",
    ]
    rows = [
        [
            r.transport,
            str(r.subscribers),
            f"{r.fps:.1f}",
            f"{r.p50_ms:.2f} ms",
            f"{r.p95_ms:.2f} ms",
            f"{r.publisher_cpu:.0f}%",
            f"{r.subscriber_cpu:.0f}%",
            _size(r.frame_kb),
            f"{r.skipped:.0f}",
        ]
        for r in results
    ]
    if markdown:
        lines = [f"**{title}**", "", "| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        lines += ["| " + " | ".join(row) + " |" for row in rows]
        return "\n".join(lines)
    widths = [max(len(x) for x in col) for col in zip(headers, *rows, strict=True)]
    lines = [title, "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))]
    lines += ["  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) for row in rows]
    return "\n".join(lines)


def _size(kb: float) -> str:
    return (
        f"{kb / 1024:.2f} MB" if kb >= 1024 else f"{kb:.1f} KB" if kb >= 1 else f"{kb * 1024:.0f} B"
    )


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    index = min(len(values) - 1, round(pct / 100 * (len(values) - 1)))
    return values[index]


def _available(spec: str) -> bool:
    module = {"jpeg": "cv2", "zstd": "zstandard"}.get(spec.partition(":")[0])
    if module is None:
        return True
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port
