import numpy as np

from faivision.modeling.detectors.bbox_conversions.bbox import BBox

class XYWHNormalized(BBox):
    @staticmethod
    def convert_to_xyxy(bbox, **kwargs):
        try:
            image_height = kwargs['image_height']
            image_width = kwargs['image_width']
        except KeyError:
            raise KeyError("please make sure you provide image_width & image_height")

        bbox = BBox._ensure_batch_dim(bbox)

        w = bbox[:, 2] * image_width
        h = bbox[:, 3] * image_height

        x1 = ((2 * bbox[:, 0] * bbox[:, 2]) - w) / 2
        y1 = ((2 * bbox[:, 1] * bbox[:, 3]) - h) / 2
        x2 = x1 + w
        y2 = y1 + h

        return np.stack([x1, y1, x2, y2], axis=1)

    @staticmethod
    def convert_from_xyxy(xyxy, **kwargs):
        try:
            image_height = kwargs['image_height']
            image_width = kwargs['image_width']
        except KeyError:
            raise KeyError("please make sure you provide image_width & image_height")

        xyxy = BBox._ensure_batch_dim(xyxy)

        x_center = (xyxy[:, 2] + xyxy[:, 0]) / (2 * image_width)
        y_center = (xyxy[:, 3] + xyxy[:, 1]) / (2 * image_height)
        w = (xyxy[:, 2] - xyxy[:, 0]) / image_width
        h = (xyxy[:, 3] - xyxy[:, 1]) / image_height

        return np.stack([x_center, y_center, w, h], axis=1)
