import os
from abc import ABC, abstractmethod
class BaseLogger(ABC):
    def __init__(self, args:dict):
        self._args = args
        self._log_path = args.get('log_path', '.')
        self._log_dir = args.get('log_dir', '')
        self._exp_name = args.get('exp_name', 'experiment')
        self._path = os.path.join(self._log_path, self._log_dir, self._exp_name)
        self._make_exp_folder()
        self._logger = None # you must define the logger object

    def _make_exp_folder(self):
        try:
           os.makedirs(self._path)
        except OSError:
            raise OSError("log dir is already exist")

    @abstractmethod
    def release(self):
        pass

    @abstractmethod
    def _log_args(self):
        pass

    def _args_string(self):
        return "\n".join([f"{key} = {value}" for key,value in self._args.items()])
