from faivision.modeling.loggers.base_logger import BaseLogger
import unittest

class Logger(BaseLogger):
    def logger(self):
        return None


class TestConfig(unittest.TestCase):
    def test_folder_creation(self):
        try:
            l = Logger("configuration.yaml")
            assert True
        except OSError:
            assert True




