
import cv2
import zmq
import numpy as np
import time
import json
from ultralytics.models.yolo import YOLO
import supervision as sv
import zstandard as zstd
import json
class Subscriber:
    def __init__(self,interface,port,n_threads=1,protocol="tcp"):


        self._context = zmq.Context(n_threads)

        self._socket = self._context.socket(zmq.SocketType.SUB)
        self._socket.setsockopt(zmq.CONFLATE,1)

        self._socket.connect(f"{protocol}://{interface}:{port}")
        self._socket.subscribe("".encode())

    def get_socket(self):
        return self._socket


class FrameGrabber:
    def __init__(self, cam_resolution: tuple[int, int], interface, port, n_threads=1, protocol="tcp"):
        self.subscriber = Subscriber(interface, port, n_threads, protocol)
        self.cam_resolution = cam_resolution
        self.dctx = zstd.ZstdDecompressor()

    def execute(self, *args):
        bytes_frame = self.dctx.decompress(self.subscriber.get_socket().recv(0, copy=True))
        frame = np.frombuffer(bytes_frame, dtype=np.uint8).reshape((*self.cam_resolution, 3))

        return frame

class CamStateGrabber:
    def __init__(self,interface, port, n_threads=1, protocol="tcp"):
        self.subscriber = Subscriber(interface, port, n_threads, protocol)

    def execute(self):
        return json.loads(self.subscriber.get_socket().recv(0,copy=True))



if __name__ == '__main__':
    cameras_states_grabber = CamStateGrabber('192.168.126.240',6000,1,'tcp')
    
    frame_grabber = FrameGrabber((1080,1920),"192.168.126.240",5555,1,"tcp")
    model = YOLO()
    bounding_box_annotator = sv.BoxAnnotator()
    label_annotator = sv.LabelAnnotator()
    print("started")
    while True:
        while True:
            t1 = time.time()
            frame = frame_grabber.execute()
            print("i recived the frame")
            output = model.predict(frame, conf=0.6, verbose=False)[0]
            print(cameras_states_grabber.execute())
            detections = sv.Detections.from_ultralytics(output)

            labels = [
                model.model.names[class_id]
                for class_id
                in detections.class_id
            ]
            annotated_image = bounding_box_annotator.annotate(
                scene=frame, detections=detections)

            annotated_image = label_annotator.annotate(
                scene=annotated_image, detections=detections, labels=labels)
            t2 = time.time()
            print(f" elapsed time: {(t2 - t1) * 1000} milliseconds")
            cv2.imshow("cam", annotated_image)
            key = cv2.waitKey(1)
            if key != -1 and chr(key) == "q":
                break
