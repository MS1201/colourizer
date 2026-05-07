
import torch
import torch.nn as nn
from torchvision import models

class PerceptualLoss(nn.Module):
    def __init__(self):
        super().__init__()
        vgg = models.vgg16(weights=models.VGG16_Weights.DEFAULT).features
        self.slice1 = nn.Sequential()
        self.slice2 = nn.Sequential()
        self.slice3 = nn.Sequential()
        self.slice4 = nn.Sequential()
        
        for x in range(4):
            self.slice1.add_module(str(x), vgg[x])
        for x in range(4, 9):
            self.slice2.add_module(str(x), vgg[x])
        for x in range(9, 16):
            self.slice3.add_module(str(x), vgg[x])
        for x in range(16, 23):
            self.slice4.add_module(str(x), vgg[x])
            
        for param in self.parameters():
            param.requires_grad = False
            
    def forward(self, x, y):

        h1_x = self.slice1(x)
        h2_x = self.slice2(h1_x)
        h3_x = self.slice3(h2_x)
        h4_x = self.slice4(h3_x)
        
        h1_y = self.slice1(y)
        h2_y = self.slice2(h1_y)
        h3_y = self.slice3(h2_y)
        h4_y = self.slice4(h3_y)
        
        loss = torch.nn.functional.l1_loss(h1_x, h1_y) + \
               torch.nn.functional.l1_loss(h2_x, h2_y) + \
               torch.nn.functional.l1_loss(h3_x, h3_y) + \
               torch.nn.functional.l1_loss(h4_x, h4_y)
        return loss
