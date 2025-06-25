from faivision.messaging_system import Subscriber
from faivision.strutures.pipelines.blocks.pipeline_block import PipelineBlock
import numpy as np


class FrameGrabber(PipelineBlock):
    def __init__(self,cam_resolution:tuple[int,int],interface,port,n_threads=1,protocol="tcp"):
        self.subscriber = Subscriber(interface,port,n_threads,protocol)
        self.cam_resolution = cam_resolution
        
    def execute(self, *args):
        bytes = self.subscriber.get_socket().recv(0)
        print("recived")

        return np.frombuffer(bytes,dtype=np.uint8).reshape((*self.cam_resolution,3))




