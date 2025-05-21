from faivision.modeling.model import Model
from torch.utils.data.dataloader import DataLoader

class Train:
    def __init__(self,model:Model,dataloaders:dict[str,DataLoader],configfile=None):
        self._model = model
        self.dataloaders = dataloaders
        self.configfile = configfile


