import os
from abc import ABC, abstractmethod
from faivision.modeling.config import Config

class BaseLogger(ABC):
    def __init__(self, config_file: str = None):
        self._config_file = config_file
        self.args = self._load_args()
        self.log_path = self.args.get('log_path', '.')
        self.log_dir = self.args.get('log_dir', '')
        self.exp_name = self.args.get('exp_name', 'experiment')
        self._make_exp_folder()

    def _make_exp_folder(self):
        try:
           os.makedirs(os.path.join(self.log_path,self.log_dir,self.exp_name))
        except OSError:
            raise OSError("log dir is already exist")

    def _load_args(self) -> dict:
        if self._config_file:
            return Config.from_yaml(self._config_file)
        else:
            return Config.generate_template()

    @abstractmethod
    def logger(self):
        """Return the underlying logger object."""
        pass
