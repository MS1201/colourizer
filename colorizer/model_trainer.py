
import os
import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from tqdm import tqdm
from data_loader import ColorizationDataset, lab_to_rgb
from neural_network import UNetResNet, PatchDiscriminator, weights_init_normal
from loss_functions import PerceptualLoss
from helper_utils import AverageMeter, save_checkpoint
from metrics import EvaluationMetrics
import matplotlib.pyplot as plt
import numpy as np

def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    os.makedirs(args.checkpoint_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    train_dataset = ColorizationDataset(args.data_dir, mode='train')
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, pin_memory=True)
    
    print(f"Found {len(train_dataset)} images for training.")

    netG = UNetResNet(input_c=1, output_c=2).to(device)
    netD = PatchDiscriminator(input_c=3).to(device)
    
    netD.apply(weights_init_normal)
    netG.up1.apply(weights_init_normal)
    netG.up2.apply(weights_init_normal)
    netG.up3.apply(weights_init_normal)
    netG.up4.apply(weights_init_normal)
    netG.final.apply(weights_init_normal)

    criterion_GAN = nn.BCEWithLogitsLoss().to(device)
    criterion_L1 = nn.L1Loss().to(device)
    criterion_Perceptual = PerceptualLoss().to(device)

    optimizer_G = optim.Adam(netG.parameters(), lr=args.lr, betas=(0.5, 0.999))
    optimizer_D = optim.Adam(netD.parameters(), lr=args.lr, betas=(0.5, 0.999))

    evaluator = EvaluationMetrics(device)

    for epoch in range(args.epochs):
        netG.train()
        netD.train()
        
        loss_G_meter = AverageMeter()
        loss_D_meter = AverageMeter()
        psnr_meter = AverageMeter()
        ssim_meter = AverageMeter()
        perc_dist_meter = AverageMeter()
        dist_corr_meter = AverageMeter()
        
        pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}/{args.epochs}")
        
        for i, data in enumerate(pbar):
            L = data['L'].to(device)
            ab = data['ab'].to(device)
            
           
            optimizer_D.zero_grad()
            
            real_image = torch.cat([L, ab], dim=1)
            pred_real = netD(real_image)
            label_real = torch.ones_like(pred_real).to(device)
            loss_D_real = criterion_GAN(pred_real, label_real)
            
            fake_ab = netG(L)
            fake_image = torch.cat([L, fake_ab.detach()], dim=1)
            pred_fake = netD(fake_image)
            label_fake = torch.zeros_like(pred_fake).to(device)
            loss_D_fake = criterion_GAN(pred_fake, label_fake)
            
            loss_D = (loss_D_real + loss_D_fake) * 0.5
            loss_D.backward()
            optimizer_D.step()
            
            
            optimizer_G.zero_grad()
            
            fake_image_G = torch.cat([L, fake_ab], dim=1)
            pred_fake_G = netD(fake_image_G)
            loss_G_GAN = criterion_GAN(pred_fake_G, label_real)
            
            loss_G_L1 = criterion_L1(fake_ab, ab) * args.lambda_L1
            
            real_image = torch.cat([L, ab], dim=1)
            loss_G_Perceptual = criterion_Perceptual(fake_image_G, real_image) * args.lambda_perc
            
            loss_G = loss_G_GAN + loss_G_L1 + loss_G_Perceptual
            loss_G.backward()
            optimizer_G.step()
            
            loss_D_meter.update(loss_D.item(), L.size(0))
            loss_G_meter.update(loss_G.item(), L.size(0))
            
            # Calculate metrics every N steps to avoid slow training
            if i % 10 == 0:
                fake_rgb = lab_to_rgb(L, fake_ab)
                real_rgb = lab_to_rgb(L, ab)
                
                # Convert list of numpy arrays back to batch tensor for evaluator
                fake_rgb_t = torch.from_numpy(np.stack(fake_rgb)).permute(0, 3, 1, 2).to(device).float() / 255.0
                real_rgb_t = torch.from_numpy(np.stack(real_rgb)).permute(0, 3, 1, 2).to(device).float() / 255.0
                
                metrics = evaluator.evaluate_batch(fake_rgb_t, real_rgb_t, fake_ab, ab)
                
                psnr_meter.update(metrics['psnr'], L.size(0))
                ssim_meter.update(metrics['ssim'], L.size(0))
                perc_dist_meter.update(metrics['perceptual_dist'], L.size(0))
                dist_corr_meter.update(metrics['dist_corr'], L.size(0))

            pbar.set_postfix({
                'Loss_D': f"{loss_D_meter.avg:.4f}", 
                'Loss_G': f"{loss_G_meter.avg:.4f}",
                'PSNR': f"{psnr_meter.avg:.2f}",
                'SSIM': f"{ssim_meter.avg:.4f}"
            })

        save_checkpoint({
            'epoch': epoch + 1,
            'state_dict_G': netG.state_dict(),
            'state_dict_D': netD.state_dict(),
        }, is_best=False, filename=os.path.join(args.checkpoint_dir, f"checkpoint_epoch_{epoch+1}.pth"))

        with torch.no_grad():
            netG.eval()
            sample_L = L[:1]
            sample_fake_ab = netG(sample_L)
            sample_real_ab = ab[:1]
            
            real_rgb = lab_to_rgb(sample_L, sample_real_ab)[0]
            fake_rgb = lab_to_rgb(sample_L, sample_fake_ab)[0]
            
            plt.figure(figsize=(10, 5))
            plt.subplot(1, 2, 1)
            plt.imshow(real_rgb)
            plt.axis('off')
            plt.subplot(1, 2, 2)
            plt.imshow(fake_rgb)
            plt.axis('off')
            plt.savefig(os.path.join(args.output_dir, f"sample_epoch_{epoch+1}.png"))
            plt.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default="data", help="Root data directory")
    parser.add_argument("--epochs", type=int, default=100, help="Number of epochs")
    parser.add_argument("--batch_size", type=int, default=16, help="Batch size")
    parser.add_argument("--lr", type=float, default=0.0002, help="Learning rate")
    parser.add_argument("--lambda_L1", type=float, default=100.0, help="Weight for L1 loss")
    parser.add_argument("--lambda_perc", type=float, default=10.0, help="Weight for Perceptual loss")
    parser.add_argument("--checkpoint_dir", type=str, default="checkpoints", help="Directory to save checkpoints")
    parser.add_argument("--output_dir", type=str, default="outputs", help="Directory to save sample outputs")
    
    args = parser.parse_args()
    train(args)
