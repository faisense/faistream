import torch.nn as nn
from faivision.modeling.losses.base_loss import BaseLoss

class CrossEntropyLoss(BaseLoss):
    def __init__(self, task='classification'):
        super().__init__(task)
        self.loss_fn = nn.CrossEntropyLoss(reduction='sum')

    def forward(self, outputs, targets):
        loss_sum = self.loss_fn(outputs, targets)

        if self.task == 'segmentation':
            n_samples = targets.numel()
        else:
            n_samples = targets.size(0)

        return loss_sum, n_samples
