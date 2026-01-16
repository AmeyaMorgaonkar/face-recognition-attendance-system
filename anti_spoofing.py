import cv2
import numpy as np


class AntiSpoofingDetector:
    """
    Lightweight anti-spoofing detector using OpenCV.
    Designed for real-time performance with minimal false positives.
    """
    
    def __init__(self, config=None):
        self.config = {
            'specular_threshold': 0.005,      # % of very bright pixels (Stricter: was 0.008)
            'specular_intensity': 215,        # Brightness threshold (Stricter: was 230)
            'edge_sharpness_max': 45,         # Max edge density (Stricter: was 50)
            'color_blue_shift_max': 1.05,     # Blue channel ratio (Stricter: was 1.08)
            'reflection_variance_min': 50,    # Min brightness variance (Stricter: was 25)
            'min_checks_to_fail': 2,          # Only need 1 failed check to mark spoof (was 2)
            'enabled': True
        }
        
        if config:
            self.config.update(config)
    
    def detect_specular_highlights(self, face_bgr):
        """
        Detect specular highlights from screen backlight or flash reflection.
        
        Screens produce concentrated bright spots from backlight.
        Real faces have more diffuse, natural lighting.
        
        Returns:
            (is_spoof, score, details)
        """
        # Convert to grayscale for brightness analysis
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        
        # Also check V channel in HSV for saturation-independent brightness
        hsv = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]
        
        # Count very bright pixels (likely screen glare)
        threshold = self.config['specular_intensity']
        bright_pixels = np.sum(v_channel > threshold)
        total_pixels = v_channel.size
        bright_ratio = bright_pixels / total_pixels
        
        # Check for concentrated bright regions (not just overall brightness)
        # Apply threshold to find hot spots
        _, bright_mask = cv2.threshold(v_channel, threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(bright_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Count significant bright regions
        significant_regions = sum(1 for c in contours if cv2.contourArea(c) > 20)
        
        is_spoof = bright_ratio > self.config['specular_threshold'] or significant_regions >= 3
        
        return is_spoof, bright_ratio, {
            'bright_ratio': bright_ratio,
            'bright_regions': significant_regions
        }
    
    def detect_edge_sharpness(self, face_gray):
        """
        Analyze edge sharpness to detect screen pixel artifacts.
        
        Screens and high-res photos have unnaturally sharp, uniform edges.
        Real faces captured by webcam have natural blur from depth-of-field.
        
        Returns:
            (is_spoof, score, details)
        """
        # Apply Laplacian for edge detection
        laplacian = cv2.Laplacian(face_gray, cv2.CV_64F)
        
        # Calculate edge statistics
        edge_variance = laplacian.var()
        edge_mean = np.abs(laplacian).mean()
        
        # High variance with high mean indicates sharp pixel edges (screen)
        # Real faces have moderate variance
        sharpness_score = edge_mean
        
        is_spoof = sharpness_score > self.config['edge_sharpness_max']
        
        return is_spoof, sharpness_score, {
            'edge_mean': edge_mean,
            'edge_variance': edge_variance
        }
    
    def detect_color_anomaly(self, face_bgr):
        """
        Detect unnatural color distribution from screens.
        
        LCD/OLED screens often produce blue-shifted colors.
        They also have different color temperature than natural skin.
        
        Returns:
            (is_spoof, score, details)
        """
        # Split into channels
        b, g, r = cv2.split(face_bgr)
        
        b_mean = np.mean(b)
        g_mean = np.mean(g)
        r_mean = np.mean(r)
        
        # Calculate blue shift ratio (screens tend to be bluer)
        avg_rg = (r_mean + g_mean) / 2
        blue_ratio = b_mean / (avg_rg + 1e-6)
        
        # Also check for color clipping (common in screens)
        # Screens often have values clustered at extremes
        total_pixels = b.size
        clipped_low = (np.sum(b < 10) + np.sum(g < 10) + np.sum(r < 10)) / (3 * total_pixels)
        clipped_high = (np.sum(b > 250) + np.sum(g > 250) + np.sum(r > 250)) / (3 * total_pixels)
        clipping_ratio = clipped_low + clipped_high
        
        is_spoof = blue_ratio > self.config['color_blue_shift_max'] or clipping_ratio > 0.08
        
        return is_spoof, blue_ratio, {
            'blue_ratio': blue_ratio,
            'clipping_ratio': clipping_ratio,
            'rgb_means': (r_mean, g_mean, b_mean)
        }
    
    def detect_reflection_pattern(self, face_gray):
        """
        Detect unnatural reflection patterns from flat surfaces.
        
        Real 3D faces have varied brightness due to facial structure.
        Flat photos/screens have more uniform brightness gradients.
        
        Returns:
            (is_spoof, score, details)
        """
        # Divide face into regions and check variance
        h, w = face_gray.shape
        
        # Split into 3x3 grid
        regions = []
        for i in range(3):
            for j in range(3):
                y1, y2 = i * h // 3, (i + 1) * h // 3
                x1, x2 = j * w // 3, (j + 1) * w // 3
                region = face_gray[y1:y2, x1:x2]
                regions.append(np.mean(region))
        
        # Calculate variance between regions
        # Real faces have more variation (nose brighter than sides, etc.)
        region_variance = np.var(regions)
        
        # Also check gradient consistency
        sobelx = cv2.Sobel(face_gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(face_gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)
        gradient_std = np.std(gradient_magnitude)
        
        # Low variance = flat surface = likely spoof
        is_spoof = region_variance < self.config['reflection_variance_min']
        
        return is_spoof, region_variance, {
            'region_variance': region_variance,
            'gradient_std': gradient_std
        }

    def detect_texture_analysis(self, face_gray):
        """
        Detect liveness using texture analysis (LBP-style simple check).
        Real faces have micro-texture (pores). Photos often blur this.
        Returns: (is_spoof, score, details)
        """
        # Simple Laplacian of Gaussian to detect "High Frequency" content
        # Resize to fixed small size to ignore noise but keep face structure
        resized = cv2.resize(face_gray, (100, 100))
        laplacian_var = cv2.Laplacian(resized, cv2.CV_64F).var()
        
        # Real faces usually have variance > 100-150.
        # Smart phones/Photos often look "smooth" (< 100) or heavily denoised.
        # We increase threshold to 80.0 to catch "good" quality photos/screens too.
        threshold = 80.0 
        is_spoof = laplacian_var < threshold
        
        return is_spoof, laplacian_var, {'texture_val': laplacian_var}

    def check_liveness(self, face_bgr):
        """
        Main anti-spoofing check combining all detection methods.
        """
        if not self.config['enabled']:
            return {
                'is_live': True,
                'confidence': 1.0,
                'spoof_type': 'none',
                'checks': {},
                'scores': {}
            }
        
        # Ensure minimum size for analysis
        if face_bgr.shape[0] < 50 or face_bgr.shape[1] < 50:
            return {
                'is_live': True,  # Can't analyze small faces reliably
                'confidence': 0.5,
                'spoof_type': 'unknown',
                'checks': {},
                'scores': {}
            }
        
        # Convert to grayscale once
        face_gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        
        # Run all checks
        checks = {}
        scores = {}
        failed_checks = []
        
        # 1. Specular highlights (screen glare)
        spoof1, score1, details1 = self.detect_specular_highlights(face_bgr)
        checks['specular'] = not spoof1
        scores['specular'] = score1
        if spoof1:
            failed_checks.append('specular')
        
        # 2. Edge sharpness (pixel artifacts)
        spoof2, score2, details2 = self.detect_edge_sharpness(face_gray)
        checks['sharpness'] = not spoof2
        scores['sharpness'] = score2
        if spoof2:
            failed_checks.append('sharpness')
        
        # 3. Color anomaly (blue shift)
        spoof3, score3, details3 = self.detect_color_anomaly(face_bgr)
        checks['color'] = not spoof3
        scores['color'] = score3
        if spoof3:
            failed_checks.append('color')
        
        # 4. Reflection pattern (flat surface)
        spoof4, score4, details4 = self.detect_reflection_pattern(face_gray)
        checks['reflection'] = not spoof4
        scores['reflection'] = score4
        if spoof4:
            failed_checks.append('reflection')

        # 5. Texture Check (Laplacian Variance) - THE FIX FOR PHOTOS
        spoof5, score5, details5 = self.detect_texture_analysis(face_gray)
        checks['texture'] = not spoof5
        scores['texture'] = score5
        if spoof5:
            failed_checks.append('texture')
        
        # Voting: require multiple checks to fail before marking as spoof
        # Config says 1 check is enough (strict).
        num_failed = len(failed_checks)
        is_live = num_failed < self.config['min_checks_to_fail']
        
        # Calculate confidence
        total_checks = 5
        confidence = (total_checks - num_failed) / total_checks
        
        # Determine spoof type based on failed checks
        spoof_type = 'none'
        if not is_live:
            if 'specular' in failed_checks or 'color' in failed_checks:
                spoof_type = 'screen'
            elif 'reflection' in failed_checks or 'texture' in failed_checks:
                spoof_type = 'print'
            else:
                spoof_type = 'unknown'
        
        return {
            'is_live': is_live,
            'confidence': confidence,
            'spoof_type': spoof_type,
            'checks': checks,
            'scores': scores,
            'failed': failed_checks
        }


# Convenience function for quick checks
def check_liveness(face_bgr, config=None):
    """
    Quick liveness check for a face region.
    
    Args:
        face_bgr: Face region in BGR format
        config: Optional configuration overrides
    
    Returns:
        dict with 'is_live', 'confidence', and details
    """
    detector = AntiSpoofingDetector(config)
    return detector.check_liveness(face_bgr)
