import json
from multiprocessing import Process

from shared_memory_dict import SharedMemoryDict
from faivision.camio.camera_state import CameraState
from faivision.camio.zmqcamera import ZMQCamera
from faivision.camio.managers.cameras_managers import CamerasManager
from faivision.strutures.messaging_system import Publisher


class OpencvCameraManager(CamerasManager):
    def __init__(self, cameras_dict: dict[str, ZMQCamera]):
        super().__init__(cameras_dict.get('cameras',{}))
        manager_configs = cameras_dict['manager']
        self.backup_mapping = manager_configs['backup_mapping']
        self.cameras_states = SharedMemoryDict(name='cameras_state', size=1024)
        self.backup_allowed_state = SharedMemoryDict(name='backup_state', size=1024)

        self._status_thread = Process(target=self.publish_cameras_status, kwargs=manager_configs['cameras_state_publisher_info'])

        self._backup_handler_thread = Process(target=self._backup_handler)


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
        self.backup_allowed_state.clear()
        for camera in self.cameras.values():
            camera.process.start()

            if camera.is_backup:
                self.backup_allowed_state[camera.camera_id] = False


        self._status_thread.start()
        self._backup_handler_thread.start()


    def stop_all(self):
        for camera in self.cameras.values():
            camera.stop_capture()

    def publish_cameras_status(self, interface, port, n_threads, protocol):
        publisher = Publisher(interface, port, n_threads, protocol)
        while True:
            data_str = {key: str(value) for key, value in self.cameras_states.items()}
            data_bytes = json.dumps(data_str).encode('utf-8')
            publisher.send(data_bytes)


    def _backup_handler(self):
        if self.backup_mapping is {}:
            return
        primary_cameras = [camera for camera in self.cameras.values() if not camera.is_backup]
        while True:

            for camera in primary_cameras:
                try:
                    if self.cameras_states.get(camera.camera_id,CameraState.ONLINE) == CameraState.ONLINE:

                        self.backup_allowed_state[self.backup_mapping[camera.camera_id]] = False
                    else:
                        self.backup_allowed_state[self.backup_mapping[camera.camera_id]] = True
                except KeyError:
                    pass





    
    def __repr__(self):
        return "\n".join([str(cam) for cam in self.cameras.values()])

