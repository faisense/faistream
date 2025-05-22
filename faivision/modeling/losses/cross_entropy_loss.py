import torch.nn as nn

from faivision.modeling.losses.base_loss import BaseLoss

class CrossEntropyLoss(BaseLoss):
    def __init__(self, task='classification'):
        self.loss_fn = nn.CrossEntropyLoss(reduction='sum')
        self.task = task
    def __call__(self, outputs,targets):
        loss_sum = self.loss_fn(outputs, targets)

        if self.task == 'segmentation':
            n_samples = targets.numel()

        else:
            n_samples = targets.size(0)  # fallback

        return loss_sum, n_samples


