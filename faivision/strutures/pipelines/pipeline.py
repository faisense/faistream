from blocks.pipeline_block import PipelineBlock
from multiprocessing import Process

class Pipeline:
    def __init__(self,blocks:list[PipelineBlock]):
        self.blocks = blocks
        self.process = Process(target=self.run())

    def add_block(self,block:PipelineBlock,index=-1):
        self.blocks.insert(index,block)

    def run(self,inputs):
        result = self.blocks[0].execute(inputs)
        for block in self.blocks[1:]:
            result = block.execute(result)


