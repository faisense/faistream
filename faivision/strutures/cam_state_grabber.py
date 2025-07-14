import json
from faivision.strutures.messaging_system import Subscriber
class CamStateGrabber:
    def __init__(self,interface, port, n_threads=1, protocol="tcp"):
        self.subscriber = Subscriber(interface, port, n_threads, protocol)

    def execute(self):
        return json.loads(self.subscriber.get_socket().recv(0,copy=True))