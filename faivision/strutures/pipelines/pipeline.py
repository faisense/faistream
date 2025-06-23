from typing import Self
from abc import ABC,abstractmethod
class PipelineBlock(ABC):
    @abstractmethod
    def execute(self,block:Self):
        pass


class Pipeline:
    def __init__(self,blocks:list[PipelineBlock]):
        self.blocks = blocks

    def add_block(self,block:PipelineBlock,index=-1):
        self.blocks.insert(index,block)


