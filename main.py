import cv2
from faivision.camio.managers.opencv_camera_manager import OpencvCameraManager
from faivision.configs.camera_config import CamerasConfig
from faivision.command_line_observer import CLIObserver

# Load cameras from YAML
cameras_dict = CamerasConfig.from_yaml("cameras.yaml")

# Initialize camera manager with 4 threads

camerasManager = OpencvCameraManager(cameras_dict)



camerasManager.start_all()

camerasManager.stop_all()
