"""
Image Colorization Module


import cv2
import numpy as np
import os

# Path to model files
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
PROTOTXT_PATH = os.path.join(MODEL_DIR, 'colorization_deploy_v2.prototxt')
CAFFEMODEL_PATH = os.path.join(MODEL_DIR, 'colorization_release_v2.caffemodel')
POINTS_PATH = os.path.join(MODEL_DIR, 'pts_in_hull.npy')


class ImageColorizer:
    """Class to handle image colorization using pre-trained Caffe model"""
    
    def __init__(self):
        self.net = None
        self.pts_in_hull = None
        self._load_model()
    
    def _load_model(self):
        if not os.path.exists(PROTOTXT_PATH):
            raise FileNotFoundError(f"Prototxt file not found: {PROTOTXT_PATH}")
        if not os.path.exists(CAFFEMODEL_PATH):
            raise FileNotFoundError(f"Caffemodel file not found: {CAFFEMODEL_PATH}")
        if not os.path.exists(POINTS_PATH):
            raise FileNotFoundError(f"Points file not found: {POINTS_PATH}")
        
        # Load the model
        self.net = cv2.dnn.readNetFromCaffe(PROTOTXT_PATH, CAFFEMODEL_PATH)
        
        # Load cluster centers
        self.pts_in_hull = np.load(POINTS_PATH)
        
        # Add cluster centers as 1x1 convolution to the model
        self.pts_in_hull = self.pts_in_hull.transpose().reshape(2, 313, 1, 1)
        self.net.getLayer(self.net.getLayerId('class8_ab')).blobs = [self.pts_in_hull.astype(np.float32)]
        self.net.getLayer(self.net.getLayerId('conv8_313_rh')).blobs = [np.full([1, 313], 2.606, dtype=np.float32)]
    
    def colorize(self, image_path):
        """
        Colorize a grayscale image

        Args:
            image_path: Path to the input image

        Returns:
            tuple: (colorized_image, quality_score)
        """
        # Read image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not read image: {image_path}")
            
        # 1. IMMEDIATE DOWNSCALE (Prevent OOM on large files)
        # AI works on 224x224 anyway; keeping >1000px wastes RAM on Free Tier.
        max_dim = 1000
        h, w = image.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        
        # 2. CONVERT TO FLOAT
        import gc
        image_float = image.astype(np.float32) / 255.0
        del image # Free original uint8 image
        gc.collect()

        # 3. CONVERT TO LAB color space
        lab = cv2.cvtColor(image_float, cv2.COLOR_BGR2LAB)
        del image_float # Free float BGR
        gc.collect()
        
        # Extract L channel and resize for network input
        L = lab[:, :, 0]
        L_resized = cv2.resize(L, (224, 224))
        L_resized -= 50  # Mean subtraction
        
        # Pass through network
        self.net.setInput(cv2.dnn.blobFromImage(L_resized))
        ab = self.net.forward()[0, :, :, :].transpose((1, 2, 0))
        ab = cv2.resize(ab, (L.shape[1], L.shape[0]))
        
        # Combine L and predicted ab channels
        L_exp = L[:, :, np.newaxis]
        colorized_lab = np.concatenate([L_exp, ab], axis=2)
        
        # Free memory-intensive arrays before finishing
        del ab
        del lab
        gc.collect()
        
        # Convert back to BGR
        colorized = cv2.cvtColor(colorized_lab, cv2.COLOR_LAB2BGR)
        del colorized_lab
        gc.collect()
        
        colorized = np.clip(colorized, 0, 1)
        colorized = (colorized * 255).astype(np.uint8)
        
        # Calculate quality score
        quality_score = self._calculate_quality_score(colorized)
        
        return colorized, quality_score
    
    def _calculate_quality_score(self, image):
        """
        Calculate a quality score based on color vibrancy

        Args:
            image: BGR image

        Returns:
            float: Quality score between 0 and 100
        """
        # Fast quality calculation on a downscaled version
        small_image = cv2.resize(image, (150, int(150 * image.shape[0] / image.shape[1])))
        
        # Convert to HSV
        hsv = cv2.cvtColor(small_image, cv2.COLOR_BGR2HSV)
        
        # Calculate saturation metrics
        saturation = hsv[:, :, 1]
        mean_saturation = np.mean(saturation)
        
        # Calculate value (brightness) metrics
        value = hsv[:, :, 2]
        mean_value = np.mean(value)
        
        # Color variety (hue standard deviation)
        hue = hsv[:, :, 0]
        hue_std = np.std(hue)
        
        # Combine metrics into quality score
        saturation_score = min(mean_saturation / 128 * 50, 50)   # Max 50 points
        brightness_score = min(mean_value / 255 * 25, 25)         # Max 25 points
        variety_score = min(hue_std / 50 * 25, 25)                # Max 25 points
        
        quality_score = saturation_score + brightness_score + variety_score
        
        return round(quality_score, 1)


# Global colorizer instance (lazy loaded)
_colorizer = None


def get_colorizer():
    """Get or create the global colorizer instance"""
    global _colorizer
    if _colorizer is None:
        _colorizer = ImageColorizer()
    return _colorizer


def colorize_image(input_path, output_path):
    """
    Convenience function to colorize an image and save it

    Args:
        input_path: Path to input grayscale image
        output_path: Path to save colorized image

    Returns:
        tuple: (success, quality_score or error_message)
    """
    try:
        colorizer = get_colorizer()
        colorized, quality_score = colorizer.colorize(input_path)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Write image and check success
        success = cv2.imwrite(output_path, colorized)
        if not success:
            return False, f"Could not write output image to {output_path}"
            
        return True, quality_score
    except Exception as e:
        return False, str(e)
