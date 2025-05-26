from abc import ABC,abstractmethod

from faivision.camio.camera import Camera
from faivision.subject import Subject


class CamerasManager(ABC):
    def __init__(self,cameras_dict:dict[str,Camera],n_workers=4):
        self.cameras = cameras_dict
        self.n_workers = n_workers


    def camera_counts(self):
        return len(self.cameras.values())


    @abstractmethod
    def add_camera(self,cam:Camera):
        pass

    @abstractmethod
    def delete_camera(self,cam_id):
        pass
    @abstractmethod
    def modify_camera(self,cam_id:str,camera:Camera):
        pass

    @abstractmethod

    def start_all(self):
        pass

    @abstractmethod
    def stop_all(self):
        pass
    @abstractmethod
    def get_cameras_status(self):
        pass

    @abstractmethod
    def read_all_frames(self):
        pass
    @abstractmethod
    def __repr__(self):
        pass
