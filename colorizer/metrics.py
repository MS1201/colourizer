
import torch
import torch.nn as nn
import numpy as np
from skimage.metrics import structural_similarity as ssim
from loss_functions import PerceptualLoss

def calculate_psnr(img1, img2):
    """
    Calculate Peak Signal-to-Noise Ratio (PSNR) between two images.
    img1, img2: torch tensors in range [0, 1] or [0, 255]
    """
    mse = torch.mean((img1 - img2) ** 2)
    if mse == 0:
        return float('inf')
    max_pixel = 1.0 # Assuming normalized [0, 1]
    psnr = 20 * torch.log10(max_pixel / torch.sqrt(mse))
    return psnr.item()

def calculate_ssim(img1, img2):
    """
    Calculate Structural Similarity Index (SSIM) between two images.
    img1, img2: torch tensors (C, H, W)
    """
    # Convert to numpy and transpose to (H, W, C)
    img1_np = img1.detach().cpu().numpy().transpose(1, 2, 0)
    img2_np = img2.detach().cpu().numpy().transpose(1, 2, 0)
    
    # Use multichannel if images have channels
    multichannel = img1_np.shape[-1] > 1
    
    # Range should be based on images (usually 1.0 for normalized)
    score, _ = ssim(img1_np, img2_np, full=True, channel_axis=2 if multichannel else None, data_range=1.0)
    return score

class EvaluationMetrics:
    def __init__(self, device):
        self.device = device
        self.perceptual_loss = PerceptualLoss().to(device)
        self.perceptual_loss.eval()

    def calculate_perceptual_realism(self, fake_rgb, real_rgb):
        """
        Calculate Perceptual Realism using VGG distance.
        Note: Lower is better (it's a distance).
        """
        with torch.no_grad():
            # Ensure images are in [0, 1] for VGG
            loss = self.perceptual_loss(fake_rgb, real_rgb)
        return loss.item()

    def calculate_distribution_similarity(self, fake_ab, real_ab):
        """
        Calculate Distribution Similarity using Histogram Correlation on ab channels.
        Higher is better (correlation).
        """
        fake_ab_np = fake_ab.detach().cpu().numpy()
        real_ab_np = real_ab.detach().cpu().numpy()
        
        # Flatten and calculate histograms for a and b channels
        corrs = []
        for i in range(2): # a and b channels
            h1, _ = np.histogram(fake_ab_np[:, i, :, :], bins=100, range=(-1, 1), density=True)
            h2, _ = np.histogram(real_ab_np[:, i, :, :], bins=100, range=(-1, 1), density=True)
            
            # Correlation coefficient
            if np.std(h1) == 0 or np.std(h2) == 0:
                corr = 0
            else:
                corr = np.corrcoef(h1, h2)[0, 1]
            corrs.append(corr)
            
        return np.mean(corrs)

    def evaluate_batch(self, fake_rgb, real_rgb, fake_ab, real_ab):
        """
        Evaluation for a batch of images.
        """
        results = {
            'psnr': [],
            'ssim': [],
            'perceptual_dist': self.calculate_perceptual_realism(fake_rgb, real_rgb),
            'dist_corr': self.calculate_distribution_similarity(fake_ab, real_ab)
        }
        
        batch_size = fake_rgb.size(0)
        for i in range(batch_size):
            results['psnr'].append(calculate_psnr(fake_rgb[i], real_rgb[i]))
            results['ssim'].append(calculate_ssim(fake_rgb[i], real_rgb[i]))
            
        return {
            'psnr': np.mean(results['psnr']),
            'ssim': np.mean(results['ssim']),
            'perceptual_dist': results['perceptual_dist'],
            'dist_corr': results['dist_corr']
        }
