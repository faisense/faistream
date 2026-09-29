"""Record a stream to MP4 files, starting a new file every N minutes.

python examples/record.py front-door --minutes 10 --out recordings/
"""

import argparse
import time
from pathlib import Path

import cv2

import faistream

parser = argparse.ArgumentParser()
parser.add_argument("stream")
parser.add_argument("--host")
parser.add_argument("--out", type=Path, default=Path("recordings"))
parser.add_argument("--minutes", type=float, default=10)
parser.add_argument("--fps", type=float, default=15, help="frame rate written to the file")
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)

writer = None
started = 0.0
with faistream.subscribe(args.stream, host=args.host) as sub:
    try:
        for frame in sub:
            if writer is None or time.monotonic() - started > args.minutes * 60:
                if writer is not None:
                    writer.release()
                path = args.out / f"{args.stream}-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
                height, width = frame.image.shape[:2]
                writer = cv2.VideoWriter(
                    str(path), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (width, height)
                )
                started = time.monotonic()
                print(f"recording to {path}")
            writer.write(frame.image)
    except KeyboardInterrupt:
        pass
    finally:
        if writer is not None:
            writer.release()
