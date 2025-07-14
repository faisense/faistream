from faivision.strutures.messaging_system import Subscriber
import zstandard as zstd
import numpy as np


class FrameGrabber:
    def __init__(self,cam_resolution:tuple[int,int],interface,port,n_threads=1,protocol="tcp"):
        self.subscriber = Subscriber(interface,port,n_threads,protocol)
        self.cam_resolution = cam_resolution
        self.dctx = zstd.ZstdDecompressor()

        
    def execute(self, *args):
        bytes_frame = self.dctx.decompress(self.subscriber.get_socket().recv(0,copy=True))
        frame = np.frombuffer(bytes_frame,dtype=np.uint8).reshape((*self.cam_resolution,3))

        return frame




