from faivision.modeling.loggers.base_logger import BaseLogger
from faivision.modeling.model import Model
from torch.utils.data.dataloader import DataLoader

class Trainer:
    def __init__(self,args:dict[str,float],model:Model,dataloaders:dict[str,DataLoader],logger:BaseLogger):
        self.args = args
        self._model = model
        self.loaders = dataloaders
        self.logger = logger



