"""Run YOLO object detection on a stream.

Start several of these (or mix with record.py) on the same stream: the camera is
still decoded only once.

    pip install ultralytics
    python examples/detect.py front-door
    python examples/detect.py front-door --host 192.168.1.50   # from another machine
"""

import argparse

import cv2
from ultralytics import YOLO

import faistream

parser = argparse.ArgumentParser()
parser.add_argument("stream")
parser.add_argument("--host")
parser.add_argument("--model", default="yolo11n.pt")
args = parser.parse_args()

model = YOLO(args.model)

with faistream.subscribe(args.stream, host=args.host) as sub:
    for frame in sub:
        result = model.predict(frame.image, conf=0.5, verbose=False)[0]
        annotated = result.plot()  # draws on a copy
        cv2.putText(
            annotated,
            f"{sub.stats.fps:.1f} fps, skipped {sub.stats.skipped}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )
        cv2.imshow(f"detect: {args.stream}", annotated)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
