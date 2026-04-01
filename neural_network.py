
import torch
import torch.nn as nn
from torchvision import models

class ResNetBlock(nn.Module):
    def __init__(self, in_channels, out_channels, stride=1, upsample=False):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_channels)
        
        self.shortcut = nn.Sequential()
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels)
            )

    def forward(self, x):
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += self.shortcut(x)
        out = self.relu(out)
        return out

class UNetResNet(nn.Module):
    def __init__(self, input_c=1, output_c=2):
        super().__init__()
        resnet = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
        
        self.initial = nn.Sequential(
            nn.Conv2d(input_c, 64, kernel_size=7, stride=2, padding=3, bias=False),
            resnet.bn1,
            resnet.relu,
            resnet.maxpool
        )
        
        self.layer1 = resnet.layer1 
        self.layer2 = resnet.layer2 
        self.layer3 = resnet.layer3
        self.layer4 = resnet.layer4 
        
        self.up1 = nn.Sequential(nn.ConvTranspose2d(512, 256, 4, 2, 1), nn.BatchNorm2d(256), nn.ReLU())
        self.up2 = nn.Sequential(nn.ConvTranspose2d(512, 128, 4, 2, 1), nn.BatchNorm2d(128), nn.ReLU()) # 256+256 skip
        self.up3 = nn.Sequential(nn.ConvTranspose2d(256, 64, 4, 2, 1), nn.BatchNorm2d(64), nn.ReLU()) # 128+128 skip
        self.up4 = nn.Sequential(nn.ConvTranspose2d(128, 64, 4, 2, 1), nn.BatchNorm2d(64), nn.ReLU()) # 64+64 skip
        
        self.final = nn.Sequential(
            nn.ConvTranspose2d(64, 32, 4, 2, 1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.Conv2d(32, output_c, kernel_size=3, padding=1),
            nn.Tanh()
        )

    def forward(self, x):
        x0 = x
        x1 = self.initial(x0) 
        x2 = self.layer1(x1)   
        x3 = self.layer2(x2)  
        x4 = self.layer3(x3) 
        x5 = self.layer4(x4)  
        
        u1 = self.up1(x5) 
        u1 = torch.cat([u1, x4], dim=1) 
        
        u2 = self.up2(u1) 
        u2 = torch.cat([u2, x3], dim=1) 
        
        u3 = self.up3(u2) 
        u3 = torch.cat([u3, x2], dim=1) 
        
        u4 = self.up4(u3)
        
        return self.final(u4) 

class PatchDiscriminator(nn.Module):
    def __init__(self, input_c=3, n_filters=64):
        super(PatchDiscriminator, self).__init__()
        
        self.model = nn.Sequential(
            nn.Conv2d(input_c, n_filters, 4, 2, 1),
            nn.LeakyReLU(0.2, inplace=True),
            
            nn.Conv2d(n_filters, n_filters*2, 4, 2, 1),
            nn.InstanceNorm2d(n_filters*2),
            nn.LeakyReLU(0.2, inplace=True),
            
            nn.Conv2d(n_filters*2, n_filters*4, 4, 2, 1),
            nn.InstanceNorm2d(n_filters*4),
            nn.LeakyReLU(0.2, inplace=True),
            
            nn.Conv2d(n_filters*4, n_filters*8, 4, 1, 1),
            nn.InstanceNorm2d(n_filters*8),
            nn.LeakyReLU(0.2, inplace=True),
            
            nn.Conv2d(n_filters*8, 1, 4, 1, 1)
        )
        
    def forward(self, x):
        return self.model(x)

def weights_init_normal(m):
    classname = m.__class__.__name__
    if classname.find('Conv') != -1:
        if not hasattr(m, 'weight') or m.weight is None: return
        torch.nn.init.normal_(m.weight.data, 0.0, 0.02)
    elif classname.find('BatchNorm2d') != -1:
        torch.nn.init.normal_(m.weight.data, 1.0, 0.02)
        torch.nn.init.constant_(m.bias.data, 0.0)
