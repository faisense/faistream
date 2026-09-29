# faistream

**Decode a camera once. Share its frames with every consumer.**

faistream is a small pub/sub service for video frames, built for edge devices. It reads and
decodes each camera once, and any number of consumers (detectors, recorders, dashboards)
subscribe to it by name. On the same machine frames are shared through shared memory
(1–2 ms from capture to consumer, 52 bytes on the socket). Other machines receive them
over TCP.

```python
import faistream

for frame in faistream.subscribe("front-door"):
    detections = model(frame.image)   # numpy array, always the newest frame
```

Want to add and watch cameras from a web page? faicam does that on top of faistream.

## Why

When several programs need the same camera, each one usually opens its own RTSP
connection. That causes three problems:

- **IP cameras allow only a few concurrent sessions.** The third consumer is refused.
- **Every connection decodes the video again.** On a CPU-only device, decoding is the most
  expensive step.
- **A slow consumer falls behind real time.** Frames queue up, so a detector ends up
  analysing video from several seconds ago.

faistream opens each camera once, decodes each frame once, and publishes only the latest
frame. A slow consumer skips frames instead of queueing them, so it always works on the
newest image and never slows the camera or the other consumers down.

## Quick start

```bash
pip install "faistream[opencv]"
faistream serve rtsp://admin:secret@192.168.1.21/stream1 --name door
```

Then, in as many programs as you like:

```python
import faistream

with faistream.subscribe("door") as sub:
    for frame in sub:
        frame.image          # (H, W, 3) uint8, BGR
        frame.seq            # frame counter; gaps mean frames were skipped
        frame.age_ms()       # time since capture
        sub.stats            # received, skipped, fps, bytes
```

From another machine (start the service with `--network`, or `network: true` in the config):

```python
for frame in faistream.subscribe("door", host="192.168.1.50"):
    ...
```

For several cameras, list them in `faistream.yaml` and run `faistream serve`.
`faistream ls` shows each stream's state, frame rate and subscribers, and
`faistream view door` opens a live window. No camera at hand? `faistream demo` runs a
synthetic one.

## How it works

Step-by-step diagrams of the whole system, the per-frame loop and the code layout are in
[docs/architecture.md](docs/architecture.md).

```mermaid
flowchart LR
    subgraph service["faistream serve (one process)"]
        direction LR
        S1["RTSP / file / USB /<br/>GStreamer source"] --> W["stream thread<br/>decode once · fps cap · resize<br/>reconnect · failover"]
        W --> L["shared-memory ring<br/>+ 36 B notification"]
        W --> N["TCP publisher<br/>JPEG / raw / zstd"]
        C["control port :7300<br/>ls · status · find stream by name"]
    end
    L -->|zero copy| A["detector"]
    L -->|zero copy| B["recorder"]
    N -->|network| R["dashboard on<br/>another machine"]
    C -.->|"subscribe('name')"| A & B & R
```

- **One thread per stream** reads the source, applies the optional fps cap and resize, and
  publishes each frame to its outputs. If the source fails, the thread reconnects with
  exponential backoff and switches to the backup sources. It switches back once the primary
  recovers.
- **Local output:** each frame is written into a shared-memory ring. A ZeroMQ PUB socket
  on loopback then sends a 36-byte header meaning "frame N is ready". Subscribers read the
  pixels directly from shared memory.
- **Network output** (optional): frames are encoded once and published over TCP.
- **Control port:** clients find streams by name through it, so nobody configures ports.
  If the service restarts, subscribers reconnect by themselves.

Programs can also run the service themselves (`faistream.Service`), change its streams
while it runs (`apply`), and read each stream's status and subscribers (`describe`,
`audience`). That is how faicam manages cameras from its web page.

## Configuration

```yaml
streams:
  door:
    source: rtsp://admin:${DOOR_PASS}@192.168.1.21/Streaming/Channels/101
    backup: yard               # another stream's name, or a source
    fps: 15                    # optional cap
  yard:
    source: rtsp://192.168.1.22/live/main
  replay:
    source: /recordings/lobby.mp4   # a file, RTSP URL, USB camera, GStreamer pipeline, ...
network: true                  # optional: also share frames with other machines
```

| Key | Default | Description |
|---|---|---|
| `streams.<name>.source` | | An RTSP/HTTP URL, file path, device index (`0`), GStreamer pipeline, or `synthetic://WxH@FPS` |
| `streams.<name>.backup` | none | Another stream's name or a source (or a list), used while this one is offline |
| `streams.<name>.fps` | source rate | Frame-rate cap. Dropped frames are never converted to pixels |
| `streams.<name>.size` | source size | Resize to `WIDTHxHEIGHT` |
| `streams.<name>.rtsp_transport` | `auto` | RTSP over `tcp` or `udp`. `auto` tries TCP first and falls back to UDP |
| `streams.<name>.open_timeout` / `read_timeout` | `5` / `5` | Seconds before a connection attempt or a silent stream counts as failed |
| `streams.<name>.paused` | `false` | Not streaming until set back to `false` |
| `network` | off | `true`, or `{codec: jpeg\|raw\|zstd, quality: 85, level: 3, bind: 0.0.0.0}` |
| `port` | `7300` | Control port. Network streams use the next free ports (`7301`, …) |
| `slots` | `4` | Frames kept in shared memory per stream |

`cameras` works as another name for `streams`. `${VAR}` and `${VAR:-default}` are read from
the environment, so passwords can stay out of the file. Invalid settings are reported per
field, for example `streams.door.fps: Input should be greater than 0`. See
[`configs/example.yaml`](configs/example.yaml) for every option.

**TCP or UDP from the camera?** Leave `rtsp_transport` on `auto` (TCP first) unless a camera
only streams over UDP or you want slightly lower latency on a clean wired network. UDP has no
flow control: if a device decodes too slowly, or packets are lost, frames turn smeared or grey
until the next keyframe, and detectors can misfire on those. TCP slows the camera down instead
of losing data.

## Performance

`faistream bench` starts the service, runs subscribers in separate processes and measures
delivered fps, capture-to-consumer latency, CPU on both sides and bytes per frame. All
results are from an Apple M5 (10 cores), macOS 26.2, Python 3.12 and OpenCV 5.0. "service
CPU" is a percentage of one core and includes reading the source.

### Transports

This test uses a synthetic 30 fps camera to see how each transport scales with more
subscribers.

**1280x720 @ 30 fps source**

| transport | subs | fps/sub | latency p50 | p95 | service CPU | CPU/sub | wire/frame | skipped |
|---|---|---|---|---|---|---|---|---|
| shm | 1 | 30.0 | 0.93 ms | 1.18 ms | 2% | 2% | 52 B | 0 |
| shm | 4 | 30.0 | 1.19 ms | 1.44 ms | 3% | 2% | 52 B | 0 |
| shm | 8 | 30.0 | 1.51 ms | 2.08 ms | 3% | 3% | 52 B | 0 |
| raw | 1 | 30.0 | 1.92 ms | 2.25 ms | 6% | 5% | 2.64 MB | 0 |
| raw | 4 | 30.0 | 3.16 ms | 4.62 ms | 13% | 4% | 2.64 MB | 0 |
| raw | 8 | 30.0 | 4.49 ms | 7.13 ms | 20% | 4% | 2.64 MB | 0 |
| jpeg | 1 | 30.0 | 8.66 ms | 11.04 ms | 15% | 11% | 123.6 KB | 0 |
| jpeg | 4 | 30.0 | 8.04 ms | 11.65 ms | 14% | 12% | 123.6 KB | 0 |
| jpeg | 8 | 30.0 | 7.05 ms | 10.53 ms | 11% | 11% | 123.6 KB | 0 |

**1920x1080 @ 30 fps source**

| transport | subs | fps/sub | latency p50 | p95 | service CPU | CPU/sub | wire/frame | skipped |
|---|---|---|---|---|---|---|---|---|
| shm | 1 | 30.0 | 1.71 ms | 1.96 ms | 4% | 2% | 52 B | 0 |
| shm | 4 | 30.0 | 1.71 ms | 2.60 ms | 4% | 3% | 52 B | 0 |
| shm | 8 | 30.0 | 2.55 ms | 3.54 ms | 5% | 4% | 52 B | 0 |
| raw | 1 | 30.0 | 2.98 ms | 4.10 ms | 10% | 7% | 5.93 MB | 0 |
| raw | 4 | 30.0 | 5.08 ms | 7.49 ms | 17% | 6% | 5.93 MB | 0 |
| raw | 8 | 30.0 | 8.05 ms | 9.48 ms | 25% | 4% | 5.93 MB | 0 |
| jpeg | 1 | 30.0 | 9.82 ms | 10.35 ms | 14% | 15% | 272.0 KB | 0 |
| jpeg | 4 | 30.0 | 9.96 ms | 10.53 ms | 15% | 15% | 271.9 KB | 0 |
| jpeg | 8 | 30.0 | 10.35 ms | 11.22 ms | 15% | 17% | 271.9 KB | 0 |

### Codecs on real footage

Compression depends on the scene, so this test uses real CCTV footage: OpenCV's
[`vtest.avi`](https://github.com/opencv/opencv/blob/4.x/samples/data/vtest.avi), a busy,
grainy 768x576 street scene at 10 fps. `jpeg:95` and `zstd:5` set the JPEG quality and the
zstd level.

**vtest.avi (768x576 @ 10 fps)**

| transport | subs | fps/sub | latency p50 | p95 | service CPU | CPU/sub | wire/frame | skipped |
|---|---|---|---|---|---|---|---|---|
| shm | 1 | 10.0 | 0.67 ms | 0.97 ms | 3% | 0% | 52 B | 0 |
| shm | 4 | 10.0 | 0.92 ms | 1.07 ms | 4% | 1% | 52 B | 0 |
| raw | 1 | 10.0 | 1.11 ms | 1.37 ms | 4% | 1% | 1.27 MB | 0 |
| raw | 4 | 10.0 | 1.71 ms | 2.37 ms | 5% | 1% | 1.27 MB | 0 |
| jpeg | 1 | 10.0 | 5.00 ms | 6.08 ms | 6% | 2% | 87.6 KB | 0 |
| jpeg | 4 | 10.0 | 5.61 ms | 6.68 ms | 7% | 3% | 87.6 KB | 0 |
| jpeg:95 | 1 | 10.0 | 6.23 ms | 7.82 ms | 7% | 3% | 151.6 KB | 0 |
| jpeg:95 | 4 | 10.0 | 6.40 ms | 7.85 ms | 7% | 3% | 151.6 KB | 0 |
| zstd:1 | 1 | 10.0 | 8.75 ms | 9.98 ms | 9% | 2% | 971.2 KB | 0 |
| zstd:1 | 4 | 10.0 | 7.46 ms | 10.65 ms | 8% | 2% | 970.9 KB | 0 |
| zstd:3 | 1 | 10.0 | 13.09 ms | 15.39 ms | 14% | 2% | 830.5 KB | 0 |
| zstd:3 | 4 | 10.0 | 13.63 ms | 14.82 ms | 15% | 3% | 830.5 KB | 0 |
| zstd:5 | 1 | 10.0 | 19.57 ms | 24.71 ms | 19% | 2% | 778.9 KB | 0 |
| zstd:5 | 4 | 10.0 | 24.48 ms | 27.25 ms | 23% | 2% | 779.1 KB | 0 |

### What the numbers show

- **Shared memory is the fast path.** It gives about 1–2 ms latency, and the service's CPU
  stays flat no matter how many subscribers are attached, because the frame is written once.
  Each subscriber pays one memcpy.
- **Raw TCP doesn't scale.** At 720p30 each subscriber costs about 80 MB/s (about
  630 Mbit/s), so one remote subscriber nearly fills gigabit Ethernet. The service's CPU
  also grows with each connection.
- **JPEG gives the smallest frames** (15× on the real footage) and is the cheapest to
  encode, but it is lossy. The service encodes each frame once, so its cost doesn't grow
  with more subscribers. It is the default network codec.
- **zstd is lossless, and how well it compresses depends on the scene.** It reaches 1.6× on
  the grainy clip above. On production 1080p IP cameras watching mostly static scenes it
  reduced frames from about 6 MB to 1.5 MB (4×) at levels 3–5. Level 3 is the default:
  level 5 costs about twice the encode time for a few percent more compression, and at
  1080p on a small device that decides whether the stream keeps 30 fps. Use it when
  consumers need exact pixels.

Measure your own cameras, since both the scene and the CPU change the results:

```bash
faistream bench --source rtsp://user:pass@camera/stream1 --transports shm jpeg zstd:3 zstd:5
```

## Design decisions

- **Only the latest frame.** Real-time analytics needs the newest frame, not every frame.
  Publishers use `ZMQ_CONFLATE`, and the shared-memory ring overwrites old slots, so there
  is never a backlog. Skipped frames show up as gaps in `frame.seq` and in
  `stats.skipped`.
- **Pixels travel through shared memory; ZeroMQ only signals.** The writer fills a slot,
  then publishes a notification. Because the notification goes through the kernel, the
  reader can't see a slot before it is fully written. A per-slot sequence check before and
  after each read (a seqlock) catches frames that were overwritten while being read. An
  `epoch` field marks each ring instance, so readers reattach after a restart or a change
  in resolution.
- **Every message is one part with a 36-byte header.** `CONFLATE` doesn't support
  multi-part messages. The header also makes each message self-describing (codec, shape,
  sequence, capture time), so subscribers never need the camera's settings.
- **Threads instead of one process per camera.** OpenCV releases Python's global lock
  while decoding, so streams still decode in parallel. One process uses much less RAM on a
  Raspberry Pi than a Python process per camera. If the process itself crashes, the
  supervisor (systemd or Docker) restarts it.
- **Unwatched streams cost almost nothing.** The ZeroMQ socket monitor counts
  subscribers. With none connected, the service keeps reading the source (so the camera
  connection stays alive) but skips converting frames to pixels, copying and encoding.
  Frames dropped by the fps cap skip that conversion too.
- **Failover is part of each stream.** Sources are an ordered list. While running on a
  backup, the worker checks the primary in the background and switches back. Consumers
  notice nothing: `seq` keeps increasing.
- **Long runs don't wrap or grow.** `seq` is a 64-bit counter, which at 30 fps lasts
  billions of years, and `stats` are Python integers with no upper limit. faistream's own
  memory use is fixed: each stream keeps `slots` frames in shared memory, and fps figures
  average the last 30 frames. `seq` restarts at 1 only when a stream restarts, and then
  under a new `epoch`, so subscribers don't count the jump as skipped frames.
- **Streams change while the service runs.** `Service.apply` starts new streams, stops
  removed ones and restarts only the ones that changed, so the other streams and their
  subscribers are never interrupted. Ports and network sharing only take effect at start.
- **OpenCV is optional.** Jetson and Raspberry Pi images often ship an OpenCV built with
  hardware decoding, which a pip wheel would override, so it isn't a hard dependency.
  Subscribers that read shared memory, raw or zstd frames don't need OpenCV at all. CI
  runs the tests without OpenCV to keep that true.

## Deployment

Run the image with your config mounted at `/config/config.yaml`:

```bash
docker build -t faistream .
docker run --rm -v ./faistream.yaml:/config/config.yaml -p 7300-7310:7300-7310 faistream
```

The published ports are for other machines, so they only matter with `network: true` in the
config. The image is built for `linux/amd64` and `linux/arm64`, runs as the user `faistream`
(uid 1000), and checks itself every 10 seconds with `faistream ls`.

To see both transports working without a camera, run the demo in
[`docker-compose.yml`](docker-compose.yml):

```bash
docker compose up --build
```

| Container | What it does |
|---|---|
| `streamd` | the service, streaming a synthetic 1280x720 camera ([`configs/demo.yaml`](configs/demo.yaml)) |
| `local-consumer` | reads the stream through shared memory, like a program on the same device, and prints stats |
| `remote-consumer` | receives it as JPEG over TCP, like another machine, and prints stats |

A consumer container that reads shared memory must share the service's IPC namespace
(`ipc: "service:streamd"`) and run as the same user, as `local-consumer` does. Without
Docker, run `faistream serve` under systemd with `Restart=always`. It shuts down cleanly on
SIGTERM and releases its shared memory.

## Examples

- [`examples/detect.py`](examples/detect.py): YOLO object detection on a stream
- [`examples/record.py`](examples/record.py): record a stream to rotating MP4 files

Run several at once on one stream; the camera is still decoded once.

## Limitations and roadmap

- Network ports have no authentication or encryption yet (ZeroMQ CURVE is planned).
  Network sharing is off by default, and without it the control port listens only on
  localhost.
- Shared-memory consumers must be on the same host and run as the same user as the
  service.
- Backups are cold standby: a backup camera is only connected while it's in use.
- Frames received with `subscribe(..., copy=False)` are views into shared memory. They
  stay valid for `slots - 1` frame intervals, so increase `slots` if you hold them longer.
- `frame.age_ms()` assumes the publisher and subscriber share a clock (the same host).
- Tested on Linux and macOS. Windows is untested.
- Runs lasting days haven't been tested yet, so memory use inside OpenCV/FFmpeg over that
  time is unmeasured.

## Development

```bash
uv sync --all-extras
uv run pytest            # unit and end-to-end tests, no camera needed (RTSP tests skip)
uv run ruff check . && uv run ruff format --check . && uv run mypy src tests

# RTSP tests against a real server (mediamtx) that only accepts UDP: forcing UDP must
# work, forcing TCP must be refused, auto must fall back. Docker, no camera needed.
docker compose -f tests/rtsp/compose.yml run --rm --build tests
```

```text
src/faistream/
  cli.py           faistream serve | ls | view | demo | bench
  config.py        YAML config, ${ENV} expansion, readable errors
  client.py        subscribe(), Subscriber
  bench.py         the transport and codec benchmark
  streaming/       the service: read each source once, share every frame
    sources.py       RTSP, files, devices, GStreamer, synthetic
    worker.py        one per stream: fps cap, resize, reconnect, failover
    outputs.py       local (shared memory) and network publishers, who's connected
    service.py       streams and the control port; applies changes while running
  transport/       the frame format, shared with subscribers
    protocol.py      36-byte frame header, Frame
    codecs.py        raw / JPEG / zstd
    shm.py           shared-memory ring buffer (seqlock, epochs)
tests/             mirrors src/faistream: streaming/ transport/, plus rtsp/
```

## License

MIT
