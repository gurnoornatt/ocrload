"""
Image Preprocessing Service

Comprehensive image enhancement for better OCR results:
- Deskewing (rotation correction)
- Color correction and contrast enhancement
- Noise reduction and sharpening
- Resolution enhancement
- Binarization and thresholding
- Shadow removal and lighting correction

This preprocessing step dramatically improves OCR accuracy by cleaning up
document images before they're sent to the Marker API.
"""

import cv2
import numpy as np
import logging
from io import BytesIO
from PIL import Image, ImageEnhance, ImageFilter
from typing import Optional, Tuple, Dict, Any
import math

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Advanced image preprocessing for document OCR enhancement.
    
    Applies a pipeline of image improvements:
    1. Format standardization
    2. Deskewing (auto-rotation)
    3. Color/contrast enhancement
    4. Noise reduction
    5. Sharpening
    6. Resolution optimization
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize preprocessor with configuration."""
        # Default configuration
        self.config = {
            'enabled': True,
            'deskew': True,
            'color_correction': True,
            'noise_reduction': True,
            'sharpening': True,
            'contrast_enhancement': True,
            'resolution_enhancement': True,
            'binarization': False,  # Only for very poor quality docs
            'shadow_removal': True,
            'target_dpi': 300,      # Optimal DPI for OCR
            'max_dimension': 3000,   # Prevent memory issues with huge images
            'quality': 95           # JPEG quality for output
        }
        
        if config:
            self.config.update(config)
        
        logger.info(f"Image Preprocessor initialized - Enhanced processing: {'✓' if self.config['enabled'] else '✗'}")
    
    def preprocess_image(
        self, 
        image_bytes: bytes, 
        filename: str = "document",
        mime_type: str = "image/jpeg"
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Main preprocessing pipeline for document images.
        
        Args:
            image_bytes: Original image as bytes
            filename: Image filename for logging
            mime_type: Original MIME type
            
        Returns:
            Tuple of (processed_image_bytes, processing_metadata)
        """
        if not self.config['enabled']:
            logger.info("Image preprocessing disabled - returning original image")
            return image_bytes, {'preprocessing': 'disabled'}
        
        logger.info(f"Starting image preprocessing for {filename}")
        processing_log = []
        
        try:
            # Step 1: Load and standardize image
            image = self._load_image(image_bytes)
            original_size = image.size
            processing_log.append(f"Loaded image: {original_size[0]}x{original_size[1]}")
            
            # Step 2: Convert to OpenCV format for advanced processing
            cv_image = self._pil_to_cv2(image)
            
            # Step 3: Deskewing (rotation correction)
            if self.config['deskew']:
                cv_image, skew_angle = self._deskew_image(cv_image)
                processing_log.append(f"Deskewed by {skew_angle:.2f}°")
            
            # Step 4: Shadow removal and lighting correction
            if self.config['shadow_removal']:
                cv_image = self._remove_shadows(cv_image)
                processing_log.append("Shadow removal applied")
            
            # Step 5: Color correction and contrast enhancement
            if self.config['color_correction']:
                cv_image = self._enhance_contrast(cv_image)
                processing_log.append("Color/contrast enhanced")
            
            # Step 6: Noise reduction
            if self.config['noise_reduction']:
                cv_image = self._reduce_noise(cv_image)
                processing_log.append("Noise reduction applied")
            
            # Step 7: Convert back to PIL for final enhancements
            image = self._cv2_to_pil(cv_image)
            
            # Step 8: Sharpening
            if self.config['sharpening']:
                image = self._sharpen_image(image)
                processing_log.append("Image sharpened")
            
            # Step 9: Resolution enhancement
            if self.config['resolution_enhancement']:
                image = self._enhance_resolution(image)
                processing_log.append(f"Resolution enhanced to {image.size[0]}x{image.size[1]}")
            
            # Step 10: Optional binarization for very poor quality docs
            if self.config['binarization']:
                image = self._binarize_image(image)
                processing_log.append("Binarization applied")
            
            # Step 11: Size optimization
            image = self._optimize_size(image)
            final_size = image.size
            processing_log.append(f"Final size: {final_size[0]}x{final_size[1]}")
            
            # Step 12: Convert to optimized bytes
            processed_bytes = self._image_to_bytes(image)
            
            # Metadata
            metadata = {
                'preprocessing': 'enabled',
                'original_size': original_size,
                'final_size': final_size,
                'size_reduction': len(image_bytes) / len(processed_bytes),
                'processing_steps': processing_log,
                'config_used': self.config.copy()
            }
            
            logger.info(f"Image preprocessing complete for {filename}: {len(processing_log)} steps applied")
            logger.debug(f"Size change: {len(image_bytes):,} → {len(processed_bytes):,} bytes")
            
            return processed_bytes, metadata
            
        except Exception as e:
            logger.error(f"Image preprocessing failed for {filename}: {e}")
            # Return original image if preprocessing fails
            return image_bytes, {
                'preprocessing': 'failed',
                'error': str(e),
                'fallback': 'original_image'
            }
    
    def _load_image(self, image_bytes: bytes) -> Image.Image:
        """Load image from bytes with format detection."""
        try:
            image = Image.open(BytesIO(image_bytes))
            
            # Convert to RGB if needed (handles RGBA, CMYK, etc.)
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            
            return image
        except Exception as e:
            raise ValueError(f"Failed to load image: {e}")
    
    def _pil_to_cv2(self, pil_image: Image.Image) -> np.ndarray:
        """Convert PIL image to OpenCV format."""
        if pil_image.mode == 'L':  # Grayscale
            return np.array(pil_image)
        else:  # RGB
            return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    
    def _cv2_to_pil(self, cv_image: np.ndarray) -> Image.Image:
        """Convert OpenCV image back to PIL format."""
        if len(cv_image.shape) == 2:  # Grayscale
            return Image.fromarray(cv_image, 'L')
        else:  # Color
            return Image.fromarray(cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB))
    
    def _deskew_image(self, image: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Automatically detect and correct document skew/rotation.
        
        Uses Hough line detection to find dominant text lines and calculate skew angle.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Edge detection
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # Hough line detection
        lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
        
        if lines is not None:
            # Calculate angles of detected lines
            angles = []
            for line in lines[:20]:  # Use first 20 lines
                rho, theta = line[0]  # Extract rho, theta from nested array
                angle = theta * 180 / np.pi - 90
                # Filter angles to reasonable range
                if -30 < angle < 30:
                    angles.append(angle)
            
            if angles:
                # Use median angle to avoid outliers
                skew_angle = np.median(angles)
                
                # Only correct if skew is significant (> 0.5 degrees)
                if abs(skew_angle) > 0.5:
                    # Get rotation matrix
                    height, width = image.shape[:2]
                    center = (width // 2, height // 2)
                    rotation_matrix = cv2.getRotationMatrix2D(center, skew_angle, 1.0)
                    
                    # Apply rotation
                    corrected = cv2.warpAffine(
                        image, rotation_matrix, (width, height),
                        flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_REPLICATE
                    )
                    
                    return corrected, skew_angle
        
        return image, 0.0
    
    def _remove_shadows(self, image: np.ndarray) -> np.ndarray:
        """
        Remove shadows and uneven lighting from document images.
        
        Uses morphological operations to create a background model and subtract it.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Create background model using morphological opening with large kernel
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (20, 20))
        background = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
        
        # Subtract background to remove shadows
        normalized = cv2.subtract(gray, background)
        
        # Enhance contrast
        normalized = cv2.normalize(normalized, None, 0, 255, cv2.NORM_MINMAX)
        
        # Convert back to color if original was color
        if len(image.shape) == 3:
            return cv2.cvtColor(normalized, cv2.COLOR_GRAY2BGR)
        else:
            return normalized
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """
        Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization).
        """
        if len(image.shape) == 3:
            # Convert to LAB color space for better contrast enhancement
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            
            # Apply CLAHE to luminance channel
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l_channel = clahe.apply(l_channel)
            
            # Merge channels and convert back
            enhanced_lab = cv2.merge([l_channel, a_channel, b_channel])
            enhanced = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        else:
            # Grayscale
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(image)
        
        return enhanced
    
    def _reduce_noise(self, image: np.ndarray) -> np.ndarray:
        """
        Reduce noise while preserving text edges.
        
        Uses Non-local Means Denoising which is effective for document images.
        """
        if len(image.shape) == 3:
            # Color image
            denoised = cv2.fastNlMeansDenoisingColored(image, None, 6, 6, 7, 21)
        else:
            # Grayscale image
            denoised = cv2.fastNlMeansDenoising(image, None, 6, 7, 21)
        
        return denoised
    
    def _sharpen_image(self, image: Image.Image) -> Image.Image:
        """
        Apply unsharp masking for text sharpening.
        """
        # Use PIL's built-in unsharp mask filter
        enhanced = image.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
        return enhanced
    
    def _enhance_resolution(self, image: Image.Image) -> Image.Image:
        """
        Enhance resolution to optimal DPI for OCR.
        """
        current_width, current_height = image.size
        
        # Calculate current DPI (assume 72 DPI if unknown)
        target_dpi = self.config['target_dpi']
        current_dpi = getattr(image, 'info', {}).get('dpi', (72, 72))[0]
        
        if current_dpi < target_dpi:
            # Scale up to target DPI
            scale_factor = target_dpi / current_dpi
            new_width = int(current_width * scale_factor)
            new_height = int(current_height * scale_factor)
            
            # Use LANCZOS for high-quality upscaling
            enhanced = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return enhanced
        
        return image
    
    def _binarize_image(self, image: Image.Image) -> Image.Image:
        """
        Convert to black and white for very poor quality documents.
        """
        # Convert to grayscale first
        gray = image.convert('L')
        
        # Apply adaptive thresholding
        cv_gray = np.array(gray)
        binary = cv2.adaptiveThreshold(
            cv_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        return Image.fromarray(binary, 'L')
    
    def _optimize_size(self, image: Image.Image) -> Image.Image:
        """
        Optimize image size to prevent memory issues while maintaining quality.
        """
        width, height = image.size
        max_dim = self.config['max_dimension']
        
        if max(width, height) > max_dim:
            # Calculate scale factor
            scale = max_dim / max(width, height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            
            # Resize with high quality
            optimized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return optimized
        
        return image
    
    def _image_to_bytes(self, image: Image.Image) -> bytes:
        """
        Convert PIL image to optimized bytes.
        """
        output = BytesIO()
        
        # Save as JPEG with high quality for OCR
        if image.mode == 'L':
            # Grayscale
            image.save(output, format='JPEG', quality=self.config['quality'], optimize=True)
        else:
            # Color
            image.save(output, format='JPEG', quality=self.config['quality'], optimize=True)
        
        return output.getvalue()
    
    def get_preprocessing_config(self) -> Dict[str, Any]:
        """Get current preprocessing configuration."""
        return self.config.copy()
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update preprocessing configuration."""
        self.config.update(new_config)
        logger.info(f"Image preprocessing config updated: {new_config}")


# Convenience function for quick preprocessing
async def preprocess_document_image(
    image_bytes: bytes,
    filename: str = "document",
    mime_type: str = "image/jpeg",
    config: Optional[Dict[str, Any]] = None
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Quick preprocessing function for document images.
    
    Args:
        image_bytes: Original image bytes
        filename: Filename for logging
        mime_type: Image MIME type
        config: Optional preprocessing configuration
        
    Returns:
        Tuple of (processed_bytes, metadata)
    """
    preprocessor = ImagePreprocessor(config)
    return preprocessor.preprocess_image(image_bytes, filename, mime_type) 