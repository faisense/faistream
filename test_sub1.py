
import cv2
import zmq
import numpy as np
import time
from ultralytics.models.yolo import YOLO
import supervision as sv
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

    def execute(self, *args):
        frame_bytes = self.subscriber.get_socket().recv(0, copy=True)
        frame = np.frombuffer(frame_bytes, dtype=np.uint8).reshape((*self.cam_resolution, 3))


        return cv2.resize(frame, (640, 640))


if __name__ == '__main__':
    frame_grabber = FrameGrabber((1080,1920),"192.168.126.240",5555,1,"tcp")
    model = YOLO()
    bounding_box_annotator = sv.BoxAnnotator()
    label_annotator = sv.LabelAnnotator()
    while True:
        while True:
            t1 = time.time()
            frame = frame_grabber.execute()

            output = model.predict(frame, conf=0.6, verbose=False)[0]

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