from faivision.messaging_system import Subscriber
import numpy as np
import cv2

class FrameGrabber:
    def __init__(self,cam_resolution:tuple[int,int],interface,port,n_threads=1,protocol="tcp"):
        self.subscriber = Subscriber(interface,port,n_threads,protocol)
        self.cam_resolution = cam_resolution
        
        
    def execute(self, *args):
        bytes = self.subscriber.get_socket().recv(0,copy=True)
        frame = np.frombuffer(bytes,dtype=np.uint8).reshape((*self.cam_resolution,3))

        return cv2.resize(frame,(640,640))




