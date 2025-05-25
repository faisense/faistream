import numpy as np

from faivision.modeling.detectors.bboxes.bbox import BBox
class XYWH(BBox):
    @staticmethod
    def convert_to_xyxy(bbox:tuple[float,float,float,float],**kwargs):
        bbox = XYWH._ensure_batch_dim(bbox)
        x1 = bbox[:, 0] - bbox[:, 2] / 2
        y1 = bbox[:, 1] - bbox[:, 3] / 2
        x2 = bbox[:, 0] + bbox[:, 2] / 2
        y2 = bbox[:, 1] + bbox[:, 3] / 2
        return np.stack([x1, y1, x2, y2], axis=1)

    @staticmethod
    def convert_from_xyxy(xyxy:tuple[float,float,float,float],**kwargs):
        xyxy = BBox._ensure_batch_dim(xyxy)
        x_center = (xyxy[:, 0] + xyxy[:, 2]) / 2
        y_center = (xyxy[:, 1] + xyxy[:, 3]) / 2
        w = np.abs(xyxy[:, 2] - xyxy[:, 0])
        h = np.abs(xyxy[:, 3] - xyxy[:, 1])
        return np.stack([x_center, y_center, w, h], axis=1)
