import time
from time import sleep

import cv2
import numpy as np
import zmq
from shared_memory_dict import SharedMemoryDict
import zstandard as zstd
from faivision.camio.ip import IP
from faivision.camio.camera_state import CameraState
from multiprocessing import Process
from faivision.messaging_system import Publisher

class ZMQCamera:
    def __init__(
        self,
        camera_id: str,
        ip: str,
        username: str,
        password: str,
        port: int,
        url: str,
        desc: str,
        resolution: tuple[int, int],
        fps: int,
        timeout: int,
        publisher_info,
        status: CameraState = CameraState.OFFLINE,
        streams_limit: int = 1,
        is_backup=False
    ):
        self._capture = None
        self.camera_id = camera_id
        self._ip = IP(ip)
        self._username = username
        self._password = password
        self._port = port
        self._url = url
        self.desc = desc
        self._resolution = resolution
        self._fps = fps
        self._timeout = timeout
        self._status = status if isinstance(status, CameraState) else CameraState[status.upper()]
        self._streams_limit = streams_limit
        self.publisher_info = publisher_info
        self.process = Process(target=self._read_frame,kwargs={**self.publisher_info,'cam_name':self.camera_id})
        self.is_backup = is_backup

    def __str__(self):
        attr = [
            f"id: {self.camera_id}",
            f"ip: {self._ip.get_ip()}",
            f"username: {self._username}",
            f"password: {self._password}",
            f"port: {self._port}",
            f"url: {self._url}",
            f"desc: {self.desc}",
            f"resolution: [{self._resolution[0]}, {self._resolution[1]}]",
            f"fps: {self._fps}",
            f"timeout: {self._timeout}",
            f"status: {self._status.name}",
            f"streams_limit: {self._streams_limit}",
        ]
        return "\n".join(attr)

    def __repr__(self):
        attr = [
            f"id: {self.camera_id}",
            f"ip: {self._ip.get_ip()}",
            f"username: {self._username}",
            f"password: {self._password}",
            f"port: {self._port}",
            f"url: {self._url}",
            f"desc: {self.desc}",
            f"resolution: [{self._resolution[0]}, {self._resolution[1]}]",
            f"fps: {self._fps}",
            f"timeout: {self._timeout}",
            f"status: {self._status.name}",
            f"streams_limit: {self._streams_limit}",
        ]
        return "Camera_object(" + ", ".join(attr) + ")"

    def props_to_dict(self):
        return {
            "camera_id": self.camera_id,
            "ip": self._ip.get_ip(),
            "username": self._username,
            "password": self._password,
            "port": self._port,
            "url": self._url,
            "desc": self.desc,
            "resolution": list(self._resolution),
            "fps": self._fps,
            "timeout": self._timeout,
            "status": self._status.name,
            "streams_limit": self._streams_limit,
        }

    def get_ip(self):
        return self._ip.get_ip()

    def test_connection(self):
        cap = cv2.VideoCapture(self._url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self._timeout)

        if not cap.isOpened():
            return False

        ret, _ = cap.read()
        cap.release()

        return ret

    def _start_capture(self):
        if self._capture is None:
            print("initlizing new cap")
            self._capture = cv2.VideoCapture(self._url)
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._resolution[0])
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._resolution[1])
            self._capture.set(cv2.CAP_PROP_FPS, self._fps)










    def stop_capture(self):
        print("stop capture triggered.")
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            return CameraState.OFFLINE


    def _read_frame(self,interface,port,n_threads,protocol,cam_name):



        publisher = None
        shared_state_dict = SharedMemoryDict(name='cameras_state', size=1024)
        backup_allowed_state = SharedMemoryDict(name='backup_state', size=1024)
        cctx = zstd.ZstdCompressor()
        shared_state_dict[self.camera_id] = CameraState.ONLINE

        self._start_capture()
        while True:

            if self.is_backup:
                while not backup_allowed_state[self.camera_id]:
                    if publisher:
                        publisher.get_socket().close(0)
                        publisher.context.term()
                        publisher = None
            else:
                print("cameras states: ", shared_state_dict)
                print("backup states: ", backup_allowed_state)


            if self._capture:
                t1 = time.time()
                ret, frame = self._capture.read()
                t2 = time.time()

                if (t2 - t1) >= 30:
                    frame = None
                if frame is not None:
                    try:
                        shared_state_dict[cam_name] = CameraState.ONLINE

                        if publisher is None:
                            publisher = Publisher(interface,port,n_threads,protocol)


                        publisher.get_socket().send(cctx.compress(frame.tobytes()))
                    except zmq.error.ZMQError:
                        sleep(1)
                        print("catch triggered")
                else:
                    shared_state_dict[cam_name] = CameraState.OFFLINE
                    if publisher:
                        publisher.get_socket().close(0)
                        publisher.context.term()
                        publisher = None


                    self.stop_capture()
                    self._start_capture()

                if not self.is_backup:
                    print("continue")

    @property
    def resolution(self):
        return self._resolution