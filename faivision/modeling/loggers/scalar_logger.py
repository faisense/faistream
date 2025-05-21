from abc import ABC,abstractmethod
class ScalarLogger(ABC):
    @abstractmethod
    def log_scalar(self, tag: str, value: float, step: int):
        pass
    @abstractmethod
    def log_scalars(self, main_tag: str, tag_values: dict[str,float], step: int):
        pass