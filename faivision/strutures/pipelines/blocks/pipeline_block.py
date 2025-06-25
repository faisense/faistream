from abc import ABC,abstractmethod


class PipelineBlock(ABC):
    @abstractmethod
    def execute(self,*args):
        pass
