from abc import ABC,abstractmethod
from torch.nn import Module 
class Model(ABC,Module):
    def __init__(self,name:str,arch:str,model_obj:Module,device="cuda"):
        super().__init__()
        self.name = name
        self.arch = arch
        self.model_obj:Module = model_obj
        self.model_obj.to(device)



    @abstractmethod
    def preprocess(self,inputs):
        pass
    @abstractmethod
    def postprocess(self,outputs):
        pass
    
    def forward(self,inputs):
        result = self.preprocess(inputs)
        result = self.model_obj.forward(result)
        result = self.postprocess(result)

        return result        
