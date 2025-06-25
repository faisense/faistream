import cv2
from faivision.camio.managers.opencv_camera_manager import OpencvCameraManager
from faivision.configs.camera_config import CamerasConfig
from faivision.command_line_observer import CLIObserver
from faivision.strutures.pipelines.blocks.frame_grabber import FrameGrabber

# Load cameras from YAML
cameras_dict = CamerasConfig.from_yaml("cameras.yaml")


camerasManager = OpencvCameraManager(cameras_dict)


camerasManager.start_all()


