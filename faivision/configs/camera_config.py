import os
import yaml
from enum import Enum

from faivision.configs.config import Config
from faivision.camio.ip import IP  # Assuming your IP class is in utils.ip or adjust import
from faivision.camio.camera_state import CameraState  # Assuming you have CameraState enum


class CamerasConfig(Config):

    @staticmethod
    def _compile(args):
        """
        Convert raw dict/list from YAML into dict[ip_str, CameraObject].
        """
        cameras = {}
        for cam_dict in args:
            ip_obj = IP(cam_dict["ip"])
            # Convert status string to CameraState enum if needed
            status = cam_dict.get("status")
            if status and isinstance(status, str):
                status = CameraState[status.upper()]
            cam_dict["ip"] = ip_obj
            cam_dict["status"] = status
            cameras[ip_obj.get_ip()] = cam_dict
        return cameras

    @staticmethod
    def _decompile(args):
        """
        Convert dict[ip_str, CameraObject] back to list of dicts
        for serialization to YAML.
        """
        camera_list = []
        for ip_str, cam in args.items():
            cam_dict = cam.copy()
            # Convert IP object back to string
            if isinstance(cam_dict.get("ip"), IP):
                cam_dict["ip"] = cam_dict["ip"].get_ip()
            # Convert CameraState enum back to string
            if isinstance(cam_dict.get("status"), CameraState):
                cam_dict["status"] = cam_dict["status"].name
            camera_list.append(cam_dict)
        return camera_list

    @staticmethod
    def generate_template(filename):
        """
        Create a YAML file with example cameras.
        Return compiled cameras dict[ip_str, CameraObject].
        """
        if os.path.exists(f"{filename}.yaml"):
            raise FileExistsError(f"{filename}.yaml already exists.")

        example = [
            {
                "id": "cam01",
                "ip": "192.168.1.101",
                "username": "admin",
                "password": "admin123",
                "name": "Front Door",
                "resolution": [1920, 1080],
                "status": "ONLINE",
                "fps": 30,
                "url": "rtsp://192.168.1.101:554/stream1",
                "streams_limit": 2
            },
            {
                "id": "cam02",
                "ip": "192.168.1.102",
                "username": "user2",
                "password": "pass456",
                "name": "Backyard",
                "resolution": [1280, 720],
                "status": "OFFLINE",
                "fps": 25,
                "url": "rtsp://192.168.1.102:554/stream2",
                "streams_limit": 1
            },
            {
                "id": "cam03",
                "ip": "10.0.0.15",
                "username": "guest",
                "password": "guest",
                "name": "Garage",
                "resolution": [640, 480],
                "status": "MAINTENANCE",
                "fps": 15,
                "url": "rtsp://10.0.0.15:554/stream",
                "streams_limit": 3
            }
        ]

        with open(f"{filename}.yaml", mode="x") as f:
            yaml.dump(example, f)

        return CamerasConfig._compile(example)
