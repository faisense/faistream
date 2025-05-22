import unittest

import numpy as np

from faivision.modeling.detectors.bbox_conversions.xywh import XYWH
from faivision.modeling.detectors.bbox_conversions.xywh_normalized import XYWHNormalized

xyxy = [10, 20, 30, 40]  # example bbox in xyxy
expected_xywh = [20, 30, 20, 20]  # example expected xywh

image_w, image_h = 640, 480
yolo = [0.5, 0.5, 0.2, 0.3]  # normalized
expected_voc = [256, 168, 384, 312]


class TestConfig(unittest.TestCase):
    def test_xyxy_to_xywh(self):
        result = XYWH.convert_from_xyxy(xyxy)

        # Use np.testing.assert_allclose for float comparison with tolerance
        np.testing.assert_allclose(result.squeeze(), expected_xywh, rtol=1e-5, atol=1e-8)


    def test_xywh_to_xyxy(self):
        result = XYWH.convert_to_xyxy(expected_xywh)

        np.testing.assert_allclose(result.squeeze(), xyxy, rtol=1e-5, atol=1e-8)


    def test_xyxy_to_xywh_normalized(self):
        result = XYWHNormalized.convert_from_xyxy(expected_voc,image_width=image_w,image_height=image_h)
        np.testing.assert_allclose(result.squeeze(), yolo, rtol=1e-5, atol=1e-8)

    def test_xywh_normalized_to_xyxy(self):
        result = XYWHNormalized.convert_to_xyxy(yolo,image_width=image_w,image_height=image_h)
        np.testing.assert_allclose(result.squeeze(), expected_voc, rtol=1e-5, atol=1e-8)
