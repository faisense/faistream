import os
from abc import ABC, abstractmethod
import yaml

class Config(ABC):
    @staticmethod
    @abstractmethod
    def _compile(args):
        pass

    @staticmethod
    @abstractmethod
    def _decompile(args):
        pass

    @staticmethod
    @abstractmethod
    def generate_template(filename):
        pass

    @classmethod
    def from_yaml(cls, yaml_path):
        if os.path.exists(yaml_path):
            with open(yaml_path, mode='r') as f:
                args = yaml.full_load(f)
                cls._compile(args)
                return args
        raise FileNotFoundError

    @classmethod
    @abstractmethod
    def to_yaml(cls, filename, args):

            with open(f'{filename}.yaml', mode='x') as f:
                cls._decompile(args)
                f.writelines([f"{key}: {value}\n" for key, value in args.items()])
