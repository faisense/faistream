from enum import Enum

class CameraState(Enum):
    OFFLINE = 0
    ONLINE = 1
    MAINTENANCE=2
    ERROR = 3