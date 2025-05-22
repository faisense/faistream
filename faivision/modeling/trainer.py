from faivision.modeling.loggers.base_logger import BaseLogger
from faivision.modeling.model import Model
from torch.utils.data.dataloader import DataLoader
from tqdm import tqdm


class Trainer:
    def __init__(self, args: dict, model: Model, dataloaders: dict[str, DataLoader], logger: BaseLogger, device='cuda'):
        self.args = args
        self.optimizer = args['optimizer'](model.model_obj.parameters(), args['weight_decay'])
        self.loss_function = args['loss_fun'](args['task'])
        self._model = model
        self.loaders = dataloaders
        self.logger = logger
        self.device = device if device == 'cuda' else 'cpu'
        self.current_epoch = 0


    def _send_to_logger(self):
        pass


    def _train_one_epoch(self, at_epoch_end: callable = None):
        self._model.model_obj.train()
        total_loss = 0
        total_number_of_samples = 0
        for images, targets in tqdm(self.loaders['train'], desc=f"Epoch: {self.current_epoch}"):
            images, targets = images.to(self.device), targets.to(self.device)

            outputs = self._model.forward(images)
            # compute loss:
            batch_loss, number_of_samples = self.loss_function(outputs, targets)  #outputs, targets

            avg_loss = batch_loss / number_of_samples

            #backprop
            avg_loss.backward()
            self.optimizer.step()
            self.optimizer.zero_grad()

            total_loss += batch_loss.item()
            total_number_of_samples += number_of_samples

        self.at_epoch_end_event(at_epoch_end)
        return total_loss / total_number_of_samples

    def train(self, at_epoch_end: callable = None):
        self.current_epoch = 1
        for _ in range(self.args['epochs']):
            self._train_one_epoch()

    def at_epoch_end_event(self, callback_fun=None):
        if callback_fun:
            callback_fun()
