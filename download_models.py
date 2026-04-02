"""
Download script for colorization model files
Downloads required files from OpenCV's GitHub repository
"""

import os
import urllib.request
import sys

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')

# URLs for model files
FILES = {
    'colorization_deploy_v2.prototxt': 
        'https://raw.githubusercontent.com/richzhang/colorization/caffe/colorization/models/colorization_deploy_v2.prototxt',
    'pts_in_hull.npy':
        'https://raw.githubusercontent.com/richzhang/colorization/caffe/colorization/resources/pts_in_hull.npy',
    'colorization_release_v2.caffemodel':
        'https://www.dropbox.com/s/dx0qvhhp5hbcx7z/colorization_release_v2.caffemodel?dl=1'
}


def download_file(url, filepath):
    """Download a file with progress indicator"""
    print(f"Downloading: {os.path.basename(filepath)}")
    
    def progress_hook(count, block_size, total_size):
        if total_size > 0:
            percent = min(100, count * block_size * 100 // total_size)
            bar = '█' * (percent // 2) + '░' * (50 - percent // 2)
            sys.stdout.write(f'\r  [{bar}] {percent}%')
            sys.stdout.flush()
    
    try:
        urllib.request.urlretrieve(url, filepath, progress_hook)
        print(f'\n  ✓ Downloaded successfully')
        return True
    except Exception as e:
        print(f'\n  ✗ Failed: {e}')
        return False


def main():
    print("\n" + "="*60)
    print("Colorization Model Downloader")
    print("="*60 + "\n")
    
    # Create models directory if it doesn't exist
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    success_count = 0
    
    for filename, url in FILES.items():
        filepath = os.path.join(MODEL_DIR, filename)
        
        if os.path.exists(filepath):
            print(f"✓ {filename} already exists, skipping...")
            success_count += 1
            continue
        
        if download_file(url, filepath):
            success_count += 1
        print()
    
    print("="*60)
    if success_count == len(FILES):
        print("All model files are ready!")
        sys.exit(0)
    else:
        print(f"{len(FILES) - success_count} file(s) failed to download")
        sys.exit(1)
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
