import os
from torch.utils.tensorboard import SummaryWriter
from base_logger import BaseLogger
from scalar_logger import ScalarLogger
from text_logger import TextLogger
from image_logger import ImageLogger

class TensorboardLogger(BaseLogger, ScalarLogger, TextLogger, ImageLogger):
    def __init__(self, config_file: str = None):
        super().__init__(config_file)
        base_path = os.path.join(self.log_path, self.log_dir, self.exp_name)
        exp_path = base_path
        exp_number = 1
        while os.path.exists(exp_path):
            exp_number += 1
            exp_path = f"{base_path}_{exp_number}"
        os.makedirs(exp_path, exist_ok=True)
        self.exp_path = exp_path
        self._writer = SummaryWriter(log_dir=self.exp_path)

    def _string_args(self) -> str:
        return "\n".join([f"{k} = {v}" for k, v in self.args.items()])

    def logger(self):
        """Return the underlying TensorBoard SummaryWriter."""
        return self._writer

    def log_scalar(self, tag: str, value: float, step: int):
        self._writer.add_scalar(tag, value, step)

    def log_scalars(self, main_tag: str, tag_values: dict, step: int):
        self._writer.add_scalars(main_tag, tag_values, step)

    def log_text(self, tag: str, text: str, step: int):
        self._writer.add_text(tag, text, step)

    def log_image(self, tag: str, image, step: int):
        self._writer.add_image(tag, image, step)
