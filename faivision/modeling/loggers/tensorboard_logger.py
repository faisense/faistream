import os
import subprocess
from torch.utils.tensorboard import SummaryWriter
from faivision.modeling.loggers.base_logger import BaseLogger
from faivision.modeling.loggers.image_logger import ImageLogger
from faivision.modeling.loggers.scalar_logger import ScalarLogger
from faivision.modeling.loggers.text_logger import TextLogger


class TensorboardLogger(BaseLogger, ScalarLogger, TextLogger, ImageLogger):

    def __init__(self, args: dict[str, float]):
        super().__init__(args)

        self._logger = SummaryWriter(log_dir=self._path)
        self._log_args()

    def _string_args(self) -> str:
        return "\n".join([f"{k} = {v}" for k, v in self._args.items()])

    def log_scalar(self, tag: str, value: float, step: int):
        self._logger.add_scalar(tag, value, step)

    def log_scalars(self, main_tag: str, tag_values: dict, step: int):
        self._logger.add_scalars(main_tag, tag_values, step)

    def log_text(self, tag: str, text: str, step: int):
        self._logger.add_text(tag, text, step)

    def log_image(self, tag: str, image, step: int):
        self._logger.add_image(tag, image, step)

    def release(self):
        self._logger.close()

    def _log_args(self):
        self._logger.add_text("Args params",self._string_args(),0)

