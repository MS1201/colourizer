
import argparse
import torch
from PIL import Image
from skimage.color import rgb2lab, lab2rgb
import numpy as np
from neural_network import UNetResNet
from metrics import EvaluationMetrics

def colorize_image(image_path, model_path, output_path, device='cuda'):
    device = torch.device(device if torch.cuda.is_available() else 'cpu')
    
    netG = UNetResNet(input_c=1, output_c=2).to(device)
    checkpoint = torch.load(model_path, map_location=device)
    if 'state_dict_G' in checkpoint:
        netG.load_state_dict(checkpoint['state_dict_G'])
    else:
        netG.load_state_dict(checkpoint)
    netG.eval()
    
    img = Image.open(image_path).convert("RGB")
    original_size = img.size
    
    input_size = (256, 256)
    img_resized = img.resize(input_size, Image.BICUBIC)
    
    img_np = np.array(img_resized)
    img_lab = rgb2lab(img_np).astype("float32")
    
    L = img_lab[:, :, 0]
    L_tensor = torch.from_numpy(L).unsqueeze(0).unsqueeze(0).to(device)
    L_tensor = L_tensor / 50.0 - 1.0
    
    with torch.no_grad():
        ab_tensor = netG(L_tensor)
        
    ab_numpy = ab_tensor.squeeze(0).cpu().numpy()
    ab_numpy = ab_numpy.transpose(1, 2, 0)
    ab_numpy = ab_numpy * 110.0
    
    L_numpy = (L_tensor.squeeze(0).squeeze(0).cpu().numpy() + 1.0) * 50.0
    Lab_final = np.zeros((input_size[1], input_size[0], 3))
    Lab_final[:, :, 0] = L_numpy
    Lab_final[:, :, 1:] = ab_numpy
    
    rgb_final = lab2rgb(Lab_final)
    
    rgb_img_pil = Image.fromarray((rgb_final * 255).astype(np.uint8))
    rgb_img_pil = rgb_img_pil.resize(original_size, Image.BICUBIC)
    
    rgb_img_pil.save(output_path)
    print(f"Saved colorized image to {output_path}")
    return output_path

def evaluate_colorization(fake_rgb_np, real_rgb_np, fake_ab_t, real_ab_t, device):
    """
    Helper to calculate metrics for a single image comparison.
    Expects numpy arrays (H, W, 3) in [0, 1] for RGB and tensors for ab.
    """
    evaluator = EvaluationMetrics(device)
    
    # Convert numpy to tensor (C, H, W)
    fake_rgb_t = torch.from_numpy(fake_rgb_np).permute(2, 0, 1).unsqueeze(0).to(device).float()
    real_rgb_t = torch.from_numpy(real_rgb_np).permute(2, 0, 1).unsqueeze(0).to(device).float()
    
    metrics = evaluator.evaluate_batch(fake_rgb_t, real_rgb_t, fake_ab_t, real_ab_t)
    return metrics

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=str, required=True, help="Path to input grayscale/bw image")
    parser.add_argument("--model", type=str, required=True, help="Path to model checkpoint")
    parser.add_argument("--output", type=str, default="output.jpg", help="Path to save result")
    args = parser.parse_args()
    
    colorize_image(args.image, args.model, args.output)
