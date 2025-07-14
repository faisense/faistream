from abc import ABC,abstractmethod

from faivision.camio.zmqcamera import ZMQCamera


class CamerasManager(ABC):
    def __init__(self, cameras_dict:dict[str,ZMQCamera]):
        self.cameras = cameras_dict


    def camera_counts(self):
        return len(self.cameras.values())


    @abstractmethod
    def add_camera(self, cam:ZMQCamera):
        pass

    @abstractmethod
    def delete_camera(self,cam_id):
        pass
    @abstractmethod
    def modify_camera(self, cam_id:str, camera:ZMQCamera):
        pass

    @abstractmethod

    def start_all(self):
        pass

    @abstractmethod
    def stop_all(self):
        pass

    @abstractmethod
    def __repr__(self):
        pass
