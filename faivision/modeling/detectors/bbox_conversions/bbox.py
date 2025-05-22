from abc import ABC,abstractmethod

import numpy as np


class BBox(ABC):
    @staticmethod
    @abstractmethod
    def convert_to_xyxy(bbox:tuple[float,float,float,float],**kwargs) -> np.array:
        pass
    @staticmethod
    @abstractmethod
    def convert_from_xyxy(xyxy:tuple[float,float,float,float],**kwargs) -> np.array:
        pass

    @staticmethod
    def _ensure_batch_dim(arr):
        arr = np.asarray(arr, dtype=np.float32)
        if arr.ndim == 1:
            arr = np.expand_dims(arr, axis=0)
        return arr