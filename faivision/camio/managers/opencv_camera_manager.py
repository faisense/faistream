import multiprocessing
from threading import Thread
from time import sleep

from shared_memory_dict import SharedMemoryDict
from faivision.camio.zmqcamera import ZMQCamera
from faivision.camio.managers.cameras_managers import CamerasManager

class OpencvCameraManager(CamerasManager):
    def __init__(self, cameras_dict: dict[str, ZMQCamera]):
        super().__init__(cameras_dict)
        self.cameras_states = SharedMemoryDict(name='cameras_state', size=1024)
        self._status_thread = Thread(target=self.get_cameras_status)


    def camera_counts(self):
        return len(self.cameras.keys())

    def add_camera(self, camera: ZMQCamera):
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
        self.cameras_states.clear()
        for camera in self.cameras.values():
            camera.process.start()

        self._status_thread.start()


    def stop_all(self):
        for camera in self.cameras.values():
            camera.stop_capture()

    def get_cameras_status(self):
        while True:
            print(self.cameras_states)


    
    def __repr__(self):
        return "\n".join([str(cam) for cam in self.cameras.values()])

