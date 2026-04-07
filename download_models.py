"""
Download script for colorization model files.
Uses requests for proper redirect handling (critical for Dropbox/cloud URLs on Render).
Includes multiple fallback mirrors for the large caffemodel file.
"""

import os
import sys
import hashlib

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')

# ---------------------------------------------------------------------------
# File definitions – list multiple mirrors per file (tried in order)
# ---------------------------------------------------------------------------
FILES = {
    'colorization_deploy_v2.prototxt': [
        'https://raw.githubusercontent.com/richzhang/colorization/caffe/colorization/models/colorization_deploy_v2.prototxt',
    ],
    'pts_in_hull.npy': [
        'https://raw.githubusercontent.com/richzhang/colorization/caffe/colorization/resources/pts_in_hull.npy',
    ],
    # The caffemodel is ~125 MB – Dropbox often blocks Render's IPs.
    # We list several mirrors; the first one that succeeds wins.
    'colorization_release_v2.caffemodel': [
        # Mirror 1: Berkeley official server
        'http://eecs.berkeley.edu/~rich.zhang/projects/2016_colorization/files/demo_v2/colorization_release_v2.caffemodel',
        # Mirror 2: Dropbox direct-download (dl=1 forces binary download)
        'https://www.dropbox.com/s/dx0qvhhp5hbcx7z/colorization_release_v2.caffemodel?dl=1',
        # Mirror 3: Dropbox alternative param
        'https://dl.dropboxusercontent.com/s/dx0qvhhp5hbcx7z/colorization_release_v2.caffemodel',
    ],
}

# Minimum acceptable sizes (bytes) – used for sanity-checking downloads
MIN_SIZES = {
    'colorization_deploy_v2.prototxt': 5_000,
    'pts_in_hull.npy': 1_000,
    'colorization_release_v2.caffemodel': 100_000_000,   # ~125 MB
}

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    )
}


def download_file(urls, filepath):
    """
    Try each URL in turn.  Uses requests so Dropbox / HTTP redirects are
    followed automatically.  Streams the response to avoid loading the entire
    model into RAM.
    Returns True on success, False if every mirror failed.
    """
    filename = os.path.basename(filepath)
    min_size = MIN_SIZES.get(filename, 0)

    for idx, url in enumerate(urls, 1):
        print(f"  [{idx}/{len(urls)}] Trying: {url[:80]}{'…' if len(url) > 80 else ''}")
        try:
            with requests.get(url, headers=HEADERS, stream=True,
                              timeout=300, allow_redirects=True) as r:
                r.raise_for_status()

                content_length = int(r.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 1024 * 1024  # 1 MB chunks

                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if content_length:
                                pct = min(100, downloaded * 100 // content_length)
                                bar = '█' * (pct // 2) + '░' * (50 - pct // 2)
                                sys.stdout.write(f'\r    [{bar}] {pct}%  ({downloaded // (1024*1024)} MB)')
                                sys.stdout.flush()

                print()  # newline after progress bar

                # Sanity-check file size
                actual_size = os.path.getsize(filepath)
                if actual_size < min_size:
                    print(f"    ✗ File too small ({actual_size} bytes) – may be an error page. Trying next mirror…")
                    os.remove(filepath)
                    continue

                print(f"    ✓ Downloaded ({actual_size // (1024*1024) if actual_size > 1024*1024 else actual_size} {'MB' if actual_size > 1024*1024 else 'bytes'})")
                return True

        except requests.exceptions.RequestException as e:
            print(f"    ✗ Failed: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            continue

    return False


def main():
    print("\n" + "=" * 64)
    print("  Colorization Model Downloader")
    print("=" * 64 + "\n")

    os.makedirs(MODEL_DIR, exist_ok=True)
    print(f"Model directory: {MODEL_DIR}\n")

    success_count = 0

    for filename, urls in FILES.items():
        filepath = os.path.join(MODEL_DIR, filename)

        # Skip if file already exists and is large enough
        if os.path.exists(filepath):
            actual = os.path.getsize(filepath)
            needed = MIN_SIZES.get(filename, 0)
            if actual >= needed:
                print(f"✓ {filename} already present ({actual // 1024} KB) – skipping.")
                success_count += 1
                continue
            else:
                print(f"⚠ {filename} exists but looks corrupt ({actual} bytes). Re-downloading…")
                os.remove(filepath)

        print(f"⬇  Downloading: {filename}")
        if download_file(urls, filepath):
            success_count += 1
        else:
            print(f"✗ All mirrors failed for {filename}!")
        print()

    print("=" * 64)
    if success_count == len(FILES):
        print("✅ All model files are ready.")
        sys.exit(0)
    else:
        failed = len(FILES) - success_count
        print(f"❌ {failed} file(s) failed to download. Colorization will not work.")
        sys.exit(1)


if __name__ == '__main__':
    main()
