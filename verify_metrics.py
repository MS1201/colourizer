
import torch
import numpy as np
from metrics import EvaluationMetrics, calculate_psnr, calculate_ssim

def test_metrics():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Testing metrics on {device}...")
    
    evaluator = EvaluationMetrics(device)
    
    # Create dummy images (Batch, Channels, H, W)
    # real_rgb and fake_rgb are in [0, 1]
    real_rgb = torch.rand(1, 3, 256, 256).to(device)
    fake_rgb = real_rgb.clone() # Identical
    
    # ab channels are typically in [-1, 1] for our model
    real_ab = torch.rand(1, 2, 256, 256).to(device) * 2 - 1
    fake_ab = real_ab.clone()
    
    # Test identical images
    print("\n--- Testing Identical Images ---")
    metrics = evaluator.evaluate_batch(fake_rgb, real_rgb, fake_ab, real_ab)
    print(f"PSNR (should be inf): {metrics['psnr']}")
    print(f"SSIM (should be 1.0): {metrics['ssim']}")
    print(f"Perceptual Dist (should be 0.0): {metrics['perceptual_dist']}")
    print(f"Dist Correlation (should be 1.0): {metrics['dist_corr']}")
    
    # Test slightly different images
    print("\n--- Testing Slightly Different Images ---")
    fake_rgb_noise = (real_rgb + torch.randn_like(real_rgb) * 0.05).clamp(0, 1)
    fake_ab_noise = (real_ab + torch.randn_like(real_ab) * 0.05).clamp(-1, 1)
    
    metrics_noise = evaluator.evaluate_batch(fake_rgb_noise, real_rgb, fake_ab_noise, real_ab)
    print(f"PSNR: {metrics_noise['psnr']:.2f}")
    print(f"SSIM: {metrics_noise['ssim']:.4f}")
    print(f"Perceptual Dist: {metrics_noise['perceptual_dist']:.4f}")
    print(f"Dist Correlation: {metrics_noise['dist_corr']:.4f}")
    
    # Test completely different images
    print("\n--- Testing Completely Different Images ---")
    fake_rgb_diff = torch.rand(1, 3, 256, 256).to(device)
    fake_ab_diff = torch.rand(1, 2, 256, 256).to(device) * 2 - 1
    
    metrics_diff = evaluator.evaluate_batch(fake_rgb_diff, real_rgb, fake_ab_diff, real_ab)
    print(f"PSNR: {metrics_diff['psnr']:.2f}")
    print(f"SSIM: {metrics_diff['ssim']:.4f}")
    print(f"Perceptual Dist: {metrics_diff['perceptual_dist']:.4f}")
    print(f"Dist Correlation: {metrics_diff['dist_corr']:.4f}")

if __name__ == "__main__":
    test_metrics()
