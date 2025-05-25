from urllib.parse import urlparse, urlunparse

import cv2

from faivision.camio.ip import IP


from faivision.camio.ip import IP
from faivision.camio.camera_state import CameraState

class Camera:
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
        status: CameraState = CameraState.OFF,
        streams_limit: int = 1,
    ):
        self.id = camera_id
        self._ip = IP(ip) if not isinstance(ip, IP) else ip
        self.username = username
        self.password = password
        self.port = port
        self.url = url
        self.desc = desc
        self.resolution = resolution
        self.fps = fps
        self.timeout = timeout
        self.status = status if isinstance(status, CameraState) else CameraState[status.upper()]
        self.streams_limit = streams_limit

    def __str__(self):
        lines = [
            f"id: {self.id}",
            f"ip: {self._ip.get_ip()}",
            f"username: {self.username}",
            f"password: {self.password}",
            f"port: {self.port}",
            f"url: {self.url}",
            f"desc: {self.desc}",
            f"resolution: [{self.resolution[0]}, {self.resolution[1]}]",
            f"fps: {self.fps}",
            f"timeout: {self.timeout}",
            f"status: {self.status.name}",
            f"streams_limit: {self.streams_limit}",
        ]
        return "\n".join(lines)

    def props_to_dict(self):
        return {
            "id": self.id,
            "ip": self._ip.get_ip(),
            "username": self.username,
            "password": self.password,
            "port": self.port,
            "url": self.url,
            "desc": self.desc,
            "resolution": list(self.resolution),
            "fps": self.fps,
            "timeout": self.timeout,
            "status": self.status.name,
            "streams_limit": self.streams_limit,
        }

    def get_ip(self):
        return self._ip.get_ip()
    def test_connection(self):
        cap = cv2.VideoCapture(self.url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.timeout)

        if not cap.isOpened():
            return False

        ret, _ = cap.read()
        cap.release()

        return ret

    def start_capture(self):
        pass

    def stop_capture(self):
        pass
