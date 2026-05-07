
import os
import numpy as np
from PIL import Image
from torch.utils.data import Dataset
from skimage.color import rgb2lab, lab2rgb
import torch
from torchvision import transforms

class ColorizationDataset(Dataset):
    def __init__(self, root_dir, transform=None, mode='train'):
        self.root_dir = root_dir
        self.transform = transform
        self.mode = mode
        
        self.image_dir = os.path.join(root_dir, mode)
        if not os.path.exists(self.image_dir):
            self.image_dir = root_dir
            
        self.image_paths = [os.path.join(self.image_dir, f) for f in os.listdir(self.image_dir) 
                            if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        if len(self.image_paths) == 0:
            print(f"Warning: No images found in {self.image_dir}")

        self.size_transform = transforms.Compose([
            transforms.Resize((256, 256)),
            transforms.ToTensor(), 
        ])

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        img_path = self.image_paths[idx]
        img = Image.open(img_path).convert("RGB")
        
        img = transforms.Resize((256, 256))(img)
        
        img_np = np.array(img)
        img_lab = rgb2lab(img_np).astype("float32") 
        
        img_lab = transforms.ToTensor()(img_lab)
        
        L = img_lab[[0], ...] / 50.0 - 1.0 
        ab = img_lab[[1, 2], ...] / 110.0 
        
        return {'L': L, 'ab': ab}

def lab_to_rgb(L, ab):
    """
    Takes a batch of images
    L: [B, 1, H, W]
    ab: [B, 2, H, W]
    """
    L = (L + 1.0) * 50.0
    ab = ab * 110.0
    Lab = torch.cat([L, ab], dim=1).permute(0, 2, 3, 1).cpu().numpy()
    rgb_imgs = []
    for img in Lab:
        img_rgb = lab2rgb(img)
        rgb_imgs.append(img_rgb)
    return np.stack(rgb_imgs, axis=0)
