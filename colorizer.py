"""
Image Colorization Module – Memory-Optimized for Render Free Tier (512 MB RAM)
===============================================================================
Memory budget (approximate):
  OS + Python runtime :  ~80 MB
  Flask + libraries   :  ~70 MB
  Caffe model loaded  : ~125 MB
  ─────────────────────────────
  Available for images:  ~237 MB   ← we must stay well under this

With MAX_DIM = 400 peak image memory is ~6 MB, well within budget.
The network processes at 224×224 internally, so limiting input to 400 px
does NOT reduce output quality.
"""

import cv2
import numpy as np
import os
import gc

# ── Model directory ──────────────────────────────────────────────────────────
# Override via env-var on Render so the path is always explicit.
MODEL_DIR = os.environ.get(
    'COLORIZER_MODEL_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
)

PROTOTXT_PATH   = os.path.join(MODEL_DIR, 'colorization_deploy_v2.prototxt')
CAFFEMODEL_PATH = os.path.join(MODEL_DIR, 'colorization_release_v2.caffemodel')
POINTS_PATH     = os.path.join(MODEL_DIR, 'pts_in_hull.npy')

# ── Tuning knobs ─────────────────────────────────────────────────────────────
# Keep this at/below 256 on Render free tier to minimize internal DNN buffers.
# The network is 224×224 so 256 gives a good balance of quality and RAM safety.
MAX_DIM = 256


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check_model_files():
    """Return list of (label, path) for every missing / corrupt model file."""
    problems = []
    checks = [
        ('prototxt',          PROTOTXT_PATH,   5_000),
        ('pts_in_hull',       POINTS_PATH,     1_000),
        ('caffemodel',        CAFFEMODEL_PATH, 100_000_000),  # must be ≥100 MB
    ]
    for label, path, min_bytes in checks:
        if not os.path.exists(path):
            problems.append((label + ' (missing)', path))
        elif os.path.getsize(path) < min_bytes:
            problems.append((label + f' (only {os.path.getsize(path)//1024} KB – corrupt?)', path))
    return problems


def _available_ram_mb():
    """Return approximate free RAM in MB (best-effort; returns None if psutil not installed)."""
    try:
        import psutil
        return psutil.virtual_memory().available // (1024 * 1024)
    except ImportError:
        return None


# ── Colorizer class ──────────────────────────────────────────────────────────

class ImageColorizer:
    """Colorize grayscale images using the Zhang et al. (2016) Caffe model."""

    def __init__(self):
        self.net = None
        self._load_model()

    # ── Model loading ────────────────────────────────────────────────────────

    def _load_model(self):
        problems = _check_model_files()
        if problems:
            detail = '\n  '.join(f'{lbl}: {p}' for lbl, p in problems)
            raise FileNotFoundError(
                'Model files missing or corrupt.  '
                'Run  python download_models.py  on the server.\n'
                f'Problems:\n  {detail}\n'
                f'Model directory: {MODEL_DIR}'
            )

        print(f'[Colorizer] Loading model from {MODEL_DIR} …')
        self.net = cv2.dnn.readNetFromCaffe(PROTOTXT_PATH, CAFFEMODEL_PATH)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

        # Attach cluster centres to the network
        pts = np.load(POINTS_PATH).transpose().reshape(2, 313, 1, 1).astype(np.float32)
        self.net.getLayer(self.net.getLayerId('class8_ab')).blobs = [pts]
        self.net.getLayer(self.net.getLayerId('conv8_313_rh')).blobs = [
            np.full([1, 313], 2.606, dtype=np.float32)
        ]
        del pts
        print('[Colorizer] Model ready.')

    # ── Colorization ─────────────────────────────────────────────────────────

    def colorize(self, image_path):
        """
        Colorize image at *image_path*.

        Returns:
            (colorized_bgr_uint8, quality_score_float)
        Raises:
            ValueError  – if the image cannot be read
            RuntimeError – if the model is not loaded
        """
        if self.net is None:
            raise RuntimeError('Model not loaded.')

        # ── 0. Pre-flight memory check ────────────────────────────────────
        free_mb = _available_ram_mb()
        if free_mb is not None and free_mb < 100:
            raise MemoryError(
                f'Cloud server is critically low on memory ({free_mb} MB available). '
                'Please try again in 1 minute. The system is auto-cleaning.'
            )

        # ── 1. Read image ────────────────────────────────────────────────
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(
                f'Cannot read image: {image_path}. '
                'Ensure the file is a valid PNG / JPG / JPEG / BMP / WEBP.'
            )

        # ── 2. Down-scale BEFORE float conversion (saves most memory) ────
        h, w = img.shape[:2]
        if max(h, w) > MAX_DIM:
            scale = MAX_DIM / max(h, w)
            img = cv2.resize(
                img,
                (max(1, int(w * scale)), max(1, int(h * scale))),
                interpolation=cv2.INTER_AREA
            )
        # img is uint8 BGR, small – keep it for a moment

        # ── 3. Convert to float32 LAB (in-place where possible) ─────────
        # We convert uint8 → float32 here; this is the peak of RAM usage.
        img_f = img.astype(np.float32) * (1.0 / 255.0)
        del img          # free uint8 copy immediately

        lab = cv2.cvtColor(img_f, cv2.COLOR_BGR2LAB)
        del img_f

        # ── 4. Prepare L channel for the 224×224 network ─────────────────
        L = lab[:, :, 0]                          # shape (H, W)
        L_net = cv2.resize(L, (224, 224)) - 50.0  # mean subtraction

        # ── 5. Forward pass ───────────────────────────────────────────────
        self.net.setInput(cv2.dnn.blobFromImage(L_net))
        ab = self.net.forward()[0].transpose(1, 2, 0)   # (224,224,2)
        del L_net

        # ── 6. Resize ab back to image dimensions ────────────────────────
        ab = cv2.resize(ab, (L.shape[1], L.shape[0]))   # (H, W, 2)

        # ── 7. Reconstruct colorised image ────────────────────────────────
        colorized_lab = np.concatenate([L[:, :, np.newaxis], ab], axis=2)
        del L, ab, lab

        colorized = cv2.cvtColor(colorized_lab, cv2.COLOR_LAB2BGR)
        del colorized_lab

        colorized = np.clip(colorized, 0.0, 1.0)
        colorized = (colorized * 255.0).astype(np.uint8)

        quality = self._quality_score(colorized)
        
        # Explicitly collect garbage to free up memory before returning
        gc.collect()
        return colorized, quality

    # ── Quality scoring ───────────────────────────────────────────────────

    def _quality_score(self, bgr):
        """Return a 0–100 quality score from HSV statistics (fast thumbnail approach)."""
        th = 120
        tw = max(1, int(120 * bgr.shape[1] / bgr.shape[0]))
        thumb = cv2.resize(bgr, (tw, th))
        hsv = cv2.cvtColor(thumb, cv2.COLOR_BGR2HSV)

        sat_score = min(float(np.mean(hsv[:, :, 1])) / 128.0 * 50.0, 50.0)
        val_score = min(float(np.mean(hsv[:, :, 2])) / 255.0 * 25.0, 25.0)
        var_score = min(float(np.std (hsv[:, :, 0])) /  50.0 * 25.0, 25.0)

        return round(sat_score + val_score + var_score, 1)


# ── On-Demand Model Lifecycle (RAM Safety for 512MB Tiers) ───────────────────

def get_colorizer():
    """Deprecated: No longer using a shared singleton to save RAM."""
    return True

def colorize_image(input_path, output_path):
    """
    On-Demand lifecycle: Loads model, processes, and PURGES model from RAM immediately.
    """
    colorizer = None
    try:
        # Load model ONLY when needed
        colorizer = ImageColorizer()
        colorized, quality_score = colorizer.colorize(input_path)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if not cv2.imwrite(output_path, colorized):
            return False, f'cv2.imwrite failed – cannot write to {output_path}'

        return True, quality_score

    except FileNotFoundError as e:
        return False, (
            'AI model files are not yet available on this server. '
            'Please contact the administrator. '
            f'Details: {e}'
        )
    except MemoryError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)
    finally:
        # ABSOLUTE PURGE: Free heavy model buffers from RAM
        if colorizer:
            if hasattr(colorizer, 'net'):
                del colorizer.net
            del colorizer
        gc.collect()
