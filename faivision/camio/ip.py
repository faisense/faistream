import ipaddress
import cv2
class IP:
    def __init__(self,ip:str):
        self._ip = None
        self.set_ip(ip)

    @staticmethod
    def validate(ip):
        try:
            ipaddress.IPv4Address(ip)
            return True
        except ipaddress.AddressValueError:
            return False

    def test_connection(self,username,password, port=554, timeout=2):
        url = f"rtsp://{username}:{self.password}@{self._ip}:{port}/"

        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)

        if not cap.isOpened():
            return False

        ret, _ = cap.read()
        cap.release()

        return ret

    def set_ip(self,ip:str):
        if self.validate(ip):
            self._ip = ip
        else:
            raise ValueError(f"Invalid IP address: {ip}")

    def get_ip(self):
        return self._ip

