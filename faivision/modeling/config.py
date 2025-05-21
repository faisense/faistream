import yaml
import os
from enum import Enum
from torch.optim import Adam,SGD,AdamW
from torch.nn import CrossEntropyLoss
class OptimizerType(Enum):
    ADAM=Adam
    SGD=SGD
    ADAMW=AdamW
class LossType(Enum):
    CROSS_ENTROPY = CrossEntropyLoss

class Config:
    @staticmethod
    def __compile(args):
        try:
            args['optimizer'] = OptimizerType[args['optimizer'].upper()].value
            args['loss_fun'] = LossType[args['loss_fun'].upper()].value

        except KeyError:
            raise KeyError("The Optimizer or loss_fun type is not exist. please check the available ones on: X")



        """

        :param args: the parameters from yaml file
        :return: update the args so user have actual optimizer and loss function.
        """


    @staticmethod
    def generate_template():
        """
        :return: created yaml file with default values and return default configuration values to train model.
        """
        args = dict(optimizer='ADAM',
                    loss_fun="CROSS_ENTROPY",
                    epochs=10,
                    lr=0.0001,
                    pretrained=True,
                    task='detect',
                    batch_size=4,
                    imgsz=[224, 224, 3],
                    workers=4,
                    seed=0,
                    exp_name="exp1",
                    log_dir="exps",
                    log_path="./"
                    )
        with open('configuration.yaml',mode='w') as f:

            f.write("# change parameters' name if your model needs that\n#to see possible optimizers and loss_fun: \n")
            f.writelines([f"{key}: {value}\n" for key,value in args.items()])

        Config.__compile(args)
        return args

    @staticmethod
    def from_yaml(yaml_path):
        if os.path.exists(yaml_path):
            with open(yaml_path,mode='r') as f:
                args = yaml.full_load(f)
                Config.__compile(args)
                return args
        raise FileNotFoundError

    @staticmethod
    def to_yaml(filename,args):
        """

        :param filename: the name of saved file with extension e.g. config.yaml
        :param args: the hyperparams you want to save e.g. {'epochs':10}
        :return: True if file created successfully, FileExistsError otherwise
        """
        if os.path.exists(filename):
            raise FileExistsError("The file with same name is occurred!")
        else:
            with open('configuration.yaml', mode='w') as f:


                f.writelines([f"{key}: {value}\n" for key, value in args.items()])






