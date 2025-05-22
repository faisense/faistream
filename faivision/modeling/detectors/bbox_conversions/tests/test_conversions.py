import unittest

import numpy as np

from faivision.modeling.detectors.bbox_conversions.xywh import XYWH

xyxy = [10, 20, 30, 40]  # example bbox in xyxy
expected_xywh = [20, 30, 20, 20]  # example expected xywh

class TestConfig(unittest.TestCase):
    def test_xyxy_to_xywh(self):
        result = XYWH.convert_from_xyxy(xyxy)

        # Use np.testing.assert_allclose for float comparison with tolerance
        np.testing.assert_allclose(result.squeeze(), expected_xywh, rtol=1e-5, atol=1e-8)


    def test_xywh_to_xyxy(self):
        result = XYWH.convert_to_xyxy(expected_xywh)

        np.testing.assert_allclose(result.squeeze(), xyxy, rtol=1e-5, atol=1e-8)

