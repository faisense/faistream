import unittest
import filecmp

from faivision.configs.camera_config import CamerasConfig
class TestCamIO(unittest.TestCase):
    def test_template_config_file(self):
        try:
            CamerasConfig.generate_template("cameras")
            assert True
        except FileExistsError:
            assert True

    def test_cameras_list(self):
        cameras = CamerasConfig.from_yaml("../../../cameras.yaml")
        try:
            CamerasConfig.to_yaml("cameras_to_yaml", cameras)
            assert True
        except FileExistsError:
            assert True

        assert filecmp.cmp("../../../cameras.yaml", "cameras_to_yaml.yaml", shallow=False)






