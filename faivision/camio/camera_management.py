from faivision.camio.camera import Camera
from faivision.configs.camera_config import CamerasConfig
class CamerasManagement:
    def __init__(self,cameras_dict:dict[str,Camera]):
        self.cameras = cameras_dict


    def camera_counts(self):
        return len(self.cameras.keys())
    def add_camera(self,camera:Camera):
        if camera.get_ip() in self.cameras.keys():
            return False
        else:
            self.cameras[camera.get_ip()] = camera
            return True

    def delete_camera(self,ip):
        try:
            del self.cameras[ip]
            return True
        except NameError:
            return False

    def modify_camera(self,camera,new_camera):
        if camera.get_ip() in self.cameras.keys():
            self.cameras[camera.get_ip()] = new_camera

            return True
        else:
            return False

    def start_all(self):
        for camera in self.cameras.values():
            camera.start_capture()


    def get_cameras_status(self):
        return [camera.test_connection() for camera in self.cameras.values()]



