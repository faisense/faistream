import zmq

import cv2
from faivision.camio.managers.opencv_camera_manager import OpencvCameraManager
from faivision.configs.camera_config import CamerasConfig
class Publisher:
    def __init__(self,interface,port,n_threads=1,protocol="tcp"):
        self._context = zmq.Context(io_threads=n_threads)

        self._socket = self._context.socket(zmq.SocketType.PUB)
        self._socket.setsockopt(zmq.CONFLATE,1)
        self._socket.bind(f"{protocol}://{interface}:{port}")

    def send(self,inputs:bytes):
        self._socket.send(inputs)

    def get_socket(self):
        return self._socket


    

if __name__ == '__main__':
# Load cameras from YAML
    cameras_dict = CamerasConfig.from_yaml("cameras.yaml")


    camerasManager = OpencvCameraManager(cameras_dict)
    camerasManager.start_all()