import multiprocessing

from faivision.camio.camera import Camera
from faivision.camio.managers.cameras_managers import CamerasManager
from concurrent.futures import ThreadPoolExecutor

class OpencvCameraManager(CamerasManager):
    def __init__(self, cameras_dict: dict[str, Camera]):
        super().__init__(cameras_dict)

    def camera_counts(self):
        return len(self.cameras.keys())

    def add_camera(self, camera: Camera):
        if camera.camera_id in self.cameras.keys():
            return False
        else:
            self.cameras[camera.camera_id] = camera
            return True

    def delete_camera(self, cam_id):
        try:
            del self.cameras[cam_id]
            return True
        except NameError:
            return False

    def modify_camera(self, cam_id: str, new_camera):
        if cam_id in self.cameras.keys():
            self.cameras[cam_id] = new_camera
            return True
        else:
            return False

    def start_all(self):
        for camera in self.cameras.values():
            camera.process.start()

    def stop_all(self):
        for camera in self.cameras.values():
            camera.stop_capture()

    def get_cameras_status(self):
        return [camera.test_connection() for camera in self.cameras.values()]

    
    def __repr__(self):
        return "\n".join([str(cam) for cam in self.cameras.values()])

