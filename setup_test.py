
import os
from PIL import Image
import numpy as np

def create_dummy_data(root_dir='data'):
    train_dir = os.path.join(root_dir, 'train')
    os.makedirs(train_dir, exist_ok=True)
    
    print(f"Creating dummy images in {train_dir}...")
    for i in range(5):
        img = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        img = Image.fromarray(img)
        img.save(os.path.join(train_dir, f"dummy_{i}.jpg"))
    print("Done.")

if __name__ == "__main__":
    create_dummy_data()
    print("Now run: python train.py --epochs 1 --batch_size 2")
