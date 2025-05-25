from abc import ABC,abstractmethod
from torch.nn.modules import Module
class BaseLoss(ABC,Module):
    def __init__(self, task):
        super().__init__()
        self.task = task
    @abstractmethod
    def forward(self,outputs,targets):
        pass




