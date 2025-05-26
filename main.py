import cv2
from faivision.camio.managers.opencv_camera_manager import OpencvCameraManager
from faivision.configs.camera_config import CamerasConfig
from faivision.command_line_observer import CLIObserver

# Load cameras from YAML
cameras_dict = CamerasConfig.from_yaml("cameras.yaml")

# Initialize camera manager with 4 threads
camerasManager = OpencvCameraManager(cameras_dict, 16)
camerasManager.start_all()
print(camerasManager)
try:
    while True:
        frames = camerasManager.read_all_frames()

        for id, frame in frames.items():
            if frame is not None:
                window_name = f"Camera {id}"

                cv2.imshow(window_name, cv2.resize(frame,(1280,720)))
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
finally:
    # Cleanup
    camerasManager.stop_all()
    cv2.destroyAllWindows()
