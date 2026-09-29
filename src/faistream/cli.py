"""Command line: ``faistream serve | ls | view | demo | bench``."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from faistream import __version__
from faistream.client import ServiceUnavailable, StreamNotFound, list_streams, subscribe
from faistream.config import DEFAULT_PORT, ConfigError, ServiceConfig, load_config, parse_config
from faistream.streaming.service import Service, ServiceError

log = logging.getLogger("faistream")

DEFAULT_CONFIG = "faistream.yaml"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # Exit cleanly on SIGTERM (docker stop, systemd), also when running as PID 1,
    # which otherwise ignores it. `serve` installs its own graceful handler.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return int(args.run(args) or 0)
    except KeyboardInterrupt:
        return 130
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ServiceUnavailable as exc:
        print(f"error: {exc}\nhint: start one with `faistream serve`", file=sys.stderr)
        return 1
    except (ServiceError, StreamNotFound, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="faistream",
        description="Decode a camera once, share its frames with many consumers.",
    )
    parser.add_argument("--version", action="version", version=f"faistream {__version__}")
    parser.add_argument(
        "--log-level", default="info", choices=["debug", "info", "warning", "error"]
    )
    commands = parser.add_subparsers(title="commands", required=True, metavar="COMMAND")

    serve = commands.add_parser(
        "serve",
        help="run the streaming service",
        description="Run the service from a YAML config, or share a single source directly.",
        epilog="examples:\n  faistream serve faistream.yaml\n"
        "  faistream serve rtsp://user:pass@10.0.0.5/stream1 --name door --fps 15",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    serve.add_argument(
        "target",
        nargs="?",
        default=DEFAULT_CONFIG,
        help=f"config file (default: {DEFAULT_CONFIG}) or a source",
    )
    serve.add_argument("--name", default="camera", help="stream name when serving a single source")
    serve.add_argument("--fps", type=float, help="cap the frame rate (single source)")
    serve.add_argument("--size", help="resize to WIDTHxHEIGHT (single source)")
    serve.add_argument(
        "--rtsp-transport",
        choices=["auto", "tcp", "udp"],
        help="RTSP over tcp or udp (default: auto, TCP first)",
    )
    serve.add_argument("--network", action="store_true", help="also share over TCP (JPEG)")
    serve.add_argument("--port", type=int, help=f"control port (default {DEFAULT_PORT})")
    serve.set_defaults(run=_serve)

    ls = commands.add_parser("ls", help="list streams and their status")
    _add_target(ls)
    ls.add_argument("-w", "--watch", action="store_true", help="refresh every second")
    ls.set_defaults(run=_ls)

    view = commands.add_parser("view", help="watch a stream (window, or stats if headless)")
    view.add_argument("stream")
    _add_target(view)
    view.add_argument(
        "--stats", action="store_true", help="print stats instead of opening a window"
    )
    view.set_defaults(run=_view)

    demo = commands.add_parser(
        "demo", help="serve a synthetic camera and view it; no hardware needed"
    )
    demo.add_argument("--size", default="640x480")
    demo.add_argument("--fps", type=float, default=30)
    demo.add_argument("--port", type=int, default=DEFAULT_PORT)
    demo.set_defaults(run=_demo)

    bench = commands.add_parser(
        "bench",
        help="measure transports and codecs on this machine",
        description="Measure latency, CPU and bytes per frame for each transport. Compression "
        "depends on the scene, so benchmark codecs with your own camera (--source).",
        epilog="examples:\n  faistream bench\n"
        "  faistream bench --source rtsp://user:pass@cam/stream1 --transports jpeg zstd:3 zstd:5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    bench.add_argument("--stream", help=f"a stream from {DEFAULT_CONFIG}, by name")
    bench.add_argument("--source", help="camera URL, file or device (default: synthetic)")
    bench.add_argument("--size", help="frame size; synthetic default 1280x720, else resize to")
    bench.add_argument("--fps", type=float, help="synthetic default 30, else a cap")
    bench.add_argument(
        "--rtsp-transport",
        default="auto",
        choices=["auto", "tcp", "udp"],
        help="RTSP over tcp or udp (default: auto, TCP first)",
    )
    bench.add_argument("--subscribers", type=int, nargs="+", default=[1, 4])
    bench.add_argument("--seconds", type=float, default=5)
    bench.add_argument(
        "--transports",
        nargs="+",
        default=["shm", "raw", "jpeg", "zstd"],
        type=_transport,
        metavar="T",
        help="shm, raw, jpeg[:QUALITY], zstd[:LEVEL] (default: shm raw jpeg zstd)",
    )
    bench.add_argument("--markdown", action="store_true", help="print a Markdown table")
    bench.set_defaults(run=_bench)
    return parser


def _add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", help="service host (default: this machine)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)


# -- commands ------------------------------------------------------------


def _serve(args: argparse.Namespace) -> None:
    service = Service(_serve_config(args))
    service.serve_forever(_Banner(service))


class _Banner:
    """Says, once everything has started, how to use the streams."""

    def __init__(self, service: Service):
        self.service = service

    def start(self) -> None:
        names = list(self.service.config.streams)
        plural = "s" if len(names) != 1 else ""
        example = names[0] if names else "name"
        print(
            f"\nfaistream is running with {len(names)} stream{plural}.\n"
            f"Programs subscribe with faistream.subscribe({example!r}); "
            "check them with `faistream ls`.\n"
            "Press Ctrl+C to stop.\n",
            flush=True,
        )

    def stop(self) -> None:
        pass


def _serve_config(args: argparse.Namespace) -> ServiceConfig:
    target: str = args.target
    overrides: dict[str, Any] = {}
    if args.port:
        overrides["port"] = args.port
    if args.network:
        overrides["network"] = True
    if target.endswith((".yaml", ".yml")):
        if args.fps or args.size or args.rtsp_transport or args.name != "camera":
            raise ConfigError(
                "--name/--fps/--size/--rtsp-transport apply to a single source; "
                "set them in the config file"
            )
        return load_config(target, overrides)
    stream: dict[str, Any] = {"source": target}
    if args.fps:
        stream["fps"] = args.fps
    if args.size:
        stream["size"] = args.size
    if args.rtsp_transport:
        stream["rtsp_transport"] = args.rtsp_transport
    return parse_config({"streams": {args.name: stream}, **overrides})


def _ls(args: argparse.Namespace) -> None:
    while True:
        table = _format_streams(list_streams(args.host, args.port))
        if not args.watch:
            print(table)
            return
        print("\033[H\033[J" + table, flush=True)  # clear screen, redraw
        time.sleep(1)


def _format_streams(streams: list[dict[str, Any]]) -> str:
    rows = [["STREAM", "STATE", "SOURCE", "FPS", "SIZE", "CLIENTS", "RECONNECTS"]]
    for s in streams:
        source = _shorten(s["source"]) + (" (backup)" if s["on_backup"] else "")
        if s["state"] != "streaming" and s["error"]:
            source = s["error"]
        size = f"{s['width']}x{s['height']}" if s["width"] else "-"
        rows.append(
            [
                s["name"],
                s["state"],
                source,
                f"{s['fps']:.1f}",
                size,
                str(s["clients"]),
                str(s["reconnects"]),
            ]
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)).rstrip()
        for row in rows
    )


def _shorten(text: str, width: int = 48) -> str:
    if len(text) <= width:
        return text
    keep = (width - 1) // 2
    return f"{text[:keep]}…{text[-keep:]}"


def _view(args: argparse.Namespace) -> None:
    view(args.stream, args.host, args.port, stats_only=args.stats)


def view(stream: str, host: str | None, port: int, *, stats_only: bool = False) -> None:
    """Show a stream in a window; fall back to printing stats without a GUI."""
    cv2 = None if stats_only else _gui_cv2()
    with subscribe(stream, host, port) as sub:
        if cv2 is None and not stats_only:
            print("no GUI available (headless OpenCV?); printing stats instead.", flush=True)
        last_print = 0.0
        for frame in sub:
            s = sub.stats
            stats = f"{stream}  {s.fps:.1f} fps  age {frame.age_ms():.1f} ms  skipped {s.skipped}"
            if cv2 is None:
                if time.monotonic() - last_print >= 1:
                    last_print = time.monotonic()
                    print(stats, flush=True)
                continue
            image = frame.image if frame.image.flags.writeable else frame.image.copy()
            cv2.putText(
                image, stats, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA
            )
            cv2.putText(
                image,
                stats,
                (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.imshow(stream, image)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27) or cv2.getWindowProperty(stream, cv2.WND_PROP_VISIBLE) < 1:
                break
        if cv2 is not None:
            cv2.destroyAllWindows()


def _gui_cv2() -> Any:
    try:
        import cv2

        cv2.namedWindow("faistream-probe", cv2.WINDOW_AUTOSIZE)
        cv2.destroyWindow("faistream-probe")
        return cv2
    except Exception:
        return None


def _demo(args: argparse.Namespace) -> None:
    config = parse_config(
        {
            "streams": {"demo": {"source": f"synthetic://{args.size}@{args.fps:g}"}},
            "port": args.port,
        }
    )
    service = Service(config)
    service.start()
    print(
        "Serving a synthetic camera as stream 'demo'. In another terminal, try:\n"
        f"  faistream ls{_port_flag(args.port)}\n  faistream view demo{_port_flag(args.port)}\n"
        "Close the window or press q to stop."
    )
    try:
        view("demo", None, args.port)
    finally:
        service.stop()


def _port_flag(port: int) -> str:
    return "" if port == DEFAULT_PORT else f" --port {port}"


def _transport(spec: str) -> str:
    from faistream.bench import parse_transport

    try:
        parse_transport(spec)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None
    return spec


def _bench(args: argparse.Namespace) -> None:
    from faistream.bench import run

    if args.stream:
        if not Path(DEFAULT_CONFIG).exists():
            raise ConfigError(
                f"{DEFAULT_CONFIG} isn't in this folder. Run this where you run "
                "`faistream serve`, or use --source."
            )
        streams = load_config(DEFAULT_CONFIG).streams
        if args.stream not in streams:
            names = ", ".join(streams) or "none"
            raise ConfigError(
                f"no stream named {args.stream!r} in {DEFAULT_CONFIG} (have: {names})"
            )
        stream = streams[args.stream]
        args.source, args.rtsp_transport = stream.primary, stream.rtsp_transport
    if not args.source:
        args.size = args.size or "1280x720"
        args.fps = args.fps or 30
    run(args)


if __name__ == "__main__":
    sys.exit(main())
