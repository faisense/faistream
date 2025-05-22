from abc import ABC,abstractmethod
import torch.nn
class Model(ABC):
    def __init__(self,name:str,arch:str,task:str,n_params:int,input_shape:tuple,output_shape:tuple,model_obj:torch.nn):
        self.name = name
        self.arch = arch
        self.task = task
        self.n_params = n_params
        self.input_shape = input_shape
        self.output_shape = output_shape
        self.model_obj = model_obj

    @abstractmethod
    def preprocess(self,inputs):
        pass
    @abstractmethod
    def postprocess(self,outputs):
        pass
    @abstractmethod
    def load(self):
        pass
    @abstractmethod
    def save(self):
        pass
    @abstractmethod
    def forward(self,inputs):
        pass
    @abstractmethod
    def evaluate(self,dataloader):
        pass