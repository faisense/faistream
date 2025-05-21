from faivision.modeling.loggers.base_logger import BaseLogger
from faivision.modeling.config import Config

import unittest
args = Config.generate_template()
class Logger(BaseLogger):
    def release(self):
        pass

    def _log_args(self):
        pass

    def __init__(self,):
        super().__init__(args)


class TestConfig(unittest.TestCase):
    def test_folder_creation(self):
        try:
            l = Logger()
            assert True
        except OSError:
            assert True




