import os
import yaml

from faivision.configs.config import Config
from faivision.camio.camera_state import CameraState
from faivision.camio.camera import Camera


class CamerasConfig(Config):
    @staticmethod
    def _create_camera_from_dict(cam_dict):
        return Camera(
            camera_id=cam_dict['camera_id'],
            ip=cam_dict['ip'],
            username=cam_dict.get('username', ''),
            password=cam_dict.get('password', ''),
            port=cam_dict.get('port', 554),
            url=cam_dict.get('url', ''),
            desc=cam_dict.get('desc', ''),
            resolution=tuple(cam_dict.get('resolution', (0, 0))),
            fps=cam_dict.get('fps', 0),
            timeout=cam_dict.get('timeout', 2),
            status=CameraState[cam_dict.get('status', 'OFFLINE').upper()] if 'status' in cam_dict else CameraState.OFFLINE,
            streams_limit=cam_dict.get('streams_limit', 1),
        )

    @staticmethod
    def _compile(args):
        cameras_list = args.get('cameras', [])
        cameras_dict = {}
        for cam_dict in cameras_list:
            camera = CamerasConfig._create_camera_from_dict(cam_dict)
            cameras_dict[camera.camera_id] = camera

        args.clear()
        args.update(cameras_dict)

    @staticmethod
    def _decompile(args):
        args_list = []
        for cam in args.values():
            args_list.append(cam.props_to_dict())
        args.clear()
        args['cameras'] = args_list

    @classmethod
    def to_yaml(cls, filename, args):
        # args: dict where key=ip string, value=Camera object
        cameras_list = [cam.props_to_dict() for cam in args.values()]
        yaml_dict = {'cameras': cameras_list}

        if os.path.exists(f"{filename}.yaml"):
            raise FileExistsError(f"{filename}.yaml already exists!")

        with open(f"{filename}.yaml", "x") as f:
            yaml.dump(yaml_dict, f)

    @staticmethod
    def generate_template(filename):
        args = {
            'cameras': [
                {
                    'camera_id': 'cam01',
                    'ip': '192.168.0.10',
                    'username': 'admin',
                    'password': 'admin123',
                    'port': 554,
                    'url': 'rtsp://192.168.0.10/stream',
                    'desc': 'Front Door',
                    'resolution': [1920, 1080],
                    'fps': 30,
                    'timeout': 2,
                    'streams_limit': 2,
                    'status': 'ONLINE',
                },
                {
                    'camera_id': 'cam02',
                    'ip': '192.168.0.11',
                    'username': 'admin',
                    'password': 'admin123',
                    'port': 554,
                    'url': 'rtsp://192.168.0.11/stream',
                    'desc': 'Back Door',
                    'resolution': [1280, 720],
                    'fps': 25,
                    'timeout': 2,
                    'streams_limit': 1,
                    'status': 'OFFLINE',
                },
            ]
        }
        if os.path.exists(f"{filename}.yaml"):
            raise FileExistsError(f"{filename}.yaml already exists!")
        with open(f"{filename}.yaml", "x") as f:
            yaml.dump(args, f)
        return args
