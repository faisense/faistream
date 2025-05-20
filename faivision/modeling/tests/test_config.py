import os.path
import unittest
from faivision.modeling.test_config import Config

class TestConfig(unittest.TestCase):
    def test_generate_template(self):
        Config.generate_template()
        self.assertTrue(os.path.isfile("configuration.yaml"),"file not exist")

    def test_from_yaml(self):
        with self.assertRaises(FileNotFoundError):
            Config.from_yaml("NOT_EXIST_FILE.yaml")

    def test_to_yaml(self):
        with self.assertRaises(FileExistsError):
            Config.to_yaml("configuration.yaml",{"epochs":10})

        self.assertEqual(Config.generate_template(),Config.from_yaml("configuration.yaml"))






