import yaml
import os
class Config:


    @staticmethod
    def generate_template():
        args = dict(optimizer='OPTIMIZER_TYPE_ADAM',
                    loss_fun="LOSS_TYPE_CROSS_ENTROPY",
                    epochs=10,
                    lr=0.0001,
                    pretrained=True,
                    task='detect',
                    batch_size=4,
                    imgsz=[224, 224, 3],
                    workers=4,
                    seed=0,
                    )
        with open('configuration.yaml',mode='w') as f:

            f.write("# change parameters' name if your model needs that\n#to see possible optimizers and loss_fun: \n")
            f.writelines([f"{key}: {value}\n" for key,value in args.items()])

        return args

    @staticmethod
    def from_yaml(yaml_path):
        if os.path.exists(yaml_path):
            with open(yaml_path,mode='r') as f:
                return yaml.full_load(f)
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






