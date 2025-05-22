from urllib.parse import urlparse, urlunparse

import cv2

from faivision.camio.ip import IP


class Camera:
    def __init__(self, id:str,ip:str,username:str,password:str,port,url:str,desc:str,resolution:tuple[int,int],fps:int,timeout):
        self.id = id
        self.url = url
        self.username = username
        self.password = password
        self.ip = IP(ip)
        self.port = port
        self.desc = desc
        self.resolution = resolution
        self.fps = fps
        self.timeout = timeout*1000


    def test_connection(self):
        cap = cv2.VideoCapture(self.url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.timeout)

        if not cap.isOpened():
            return False

        ret, _ = cap.read()
        cap.release()

        return ret
