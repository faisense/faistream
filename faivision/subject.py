from abc import ABC,abstractmethod

from faivision.observer import Observer


class Subject(ABC):


    @abstractmethod
    def attach(self,observer:Observer):
        pass

    @abstractmethod
    def deattach(self,observer:Observer):
        pass

    @abstractmethod
    def notify(self):
        pass