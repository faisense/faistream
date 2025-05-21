
from faivision.modeling.config import Config

from faivision.modeling.loggers.tensorboard_logger import TensorboardLogger


args = Config.from_yaml("configuration.yaml")

tensorboard_logger = TensorboardLogger(args)

tensorboard_logger.log_text("test","hello world",1)
