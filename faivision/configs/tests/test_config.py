import os.path
import unittest
from faivision.configs.train_config import TrainConfig

class TestConfig(unittest.TestCase):
    def test_generate_template(self):
        TrainConfig.generate_template()
        self.assertTrue(os.path.isfile("configuration.yaml"),"file not exist")

    def test_from_yaml(self):
        with self.assertRaises(FileNotFoundError):
            TrainConfig.from_yaml("NOT_EXIST_FILE.yaml")


        try:
            args = TrainConfig.from_yaml("configuration.yaml")
            assert True
        except KeyError:
            assert True

    def test_to_yaml(self):
        with self.assertRaises(FileExistsError):
            TrainConfig.to_yaml("configuration.yaml", {"epochs":10})







