from enum import Enum
from torch.optim import Adam, SGD, AdamW
import yaml
from faivision.modeling.losses.cross_entropy_loss import CrossEntropyLoss
from faivision.configs.config import Config

class OptimizerType(Enum):
    ADAM = Adam
    SGD = SGD
    ADAMW = AdamW

class LossType(Enum):
    CROSS_ENTROPY = CrossEntropyLoss


class TrainConfig(Config):
    @staticmethod
    def _compile(args):
        # Compile optimizer
        opt_name = args["training"]["optimizer"]
        args["training"]["optimizer"] = OptimizerType[opt_name.upper()].value

        # Compile loss
        loss_name = args["training"]["loss_fun"]
        args["training"]["loss_fun"] = LossType[loss_name.upper()].value

    @staticmethod
    def _decompile(args):
        # Decompile optimizer
        opt_class = args["training"]["optimizer"]
        for name, enum_val in OptimizerType.__members__.items():
            if enum_val.value == opt_class:
                args["training"]["optimizer"] = name
                break

        # Decompile loss
        loss_class = args["training"]["loss_fun"]
        for name, enum_val in LossType.__members__.items():
            if enum_val.value == loss_class:
                args["training"]["loss_fun"] = name
                break

    @staticmethod
    def generate_template(filename="configuration"):
        args = {
            "model": {
                "arch": "resnet50",
                "pretrained": True,
                "input_shape": [3, 224, 224]
            },
            "training": {
                "optimizer": "ADAM",
                "loss_fun": "CROSS_ENTROPY",
                "epochs": 20,
                "lr": 0.001,
                "weight_decay": 0.0001,
                "batch_size": 32
            },
            "data": {
                "train_path": "data/train",
                "val_path": "data/val",
                "num_workers": 4
            },
            "logging": {
                "exp_name": "exp1",
                "log_dir": "logs"
            },
            "seed": 42
        }

        with open(f"{filename}.yaml", "w") as f:
            yaml.dump(args, f)
        TrainConfig._compile(args)
        return args
