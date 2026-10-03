"""
Image Processor - Image Processing Utilities

This provides image processing utilities for the application.
"""

from typing import Optional, Tuple
from PIL import Image
import numpy as np


class ImageProcessor:
    """
    Provides image processing utilities for screen captures.
    """

    @staticmethod
    def resize_image(image: Image.Image, max_dimension: int = 1280) -> Image.Image:
        """
        Resize image to fit within max dimension while maintaining aspect ratio.

        Args:
            image: PIL Image to resize
            max_dimension: Maximum dimension (width or height)

        Returns:
            Resized PIL Image
        """
        width, height = image.size

        if max(width, height) <= max_dimension:
            return image

        # Calculate new dimensions
        if width > height:
            new_width = max_dimension
            new_height = int(height * (max_dimension / width))
        else:
            new_height = max_dimension
            new_width = int(width * (max_dimension / height))

        return image.resize((new_width, new_height), Image.LANCZOS)

    @staticmethod
    def convert_to_jpeg(image: Image.Image, quality: int = 85) -> bytes:
        """
        Convert PIL Image to JPEG bytes.

        Args:
            image: PIL Image to convert
            quality: JPEG quality (0-100)

        Returns:
            JPEG encoded bytes
        """
        import io
        jpeg_bytes = io.BytesIO()
        image.save(jpeg_bytes, format='JPEG', quality=quality)
        return jpeg_bytes.getvalue()

    @staticmethod
    def crop_to_coordinates(
        image: Image.Image,
        x: int,
        y: int,
        width: int,
        height: int
    ) -> Image.Image:
        """
        Crop image to specific coordinates.

        Args:
            image: PIL Image to crop
            x: X coordinate
            y: Y coordinate
            width: Width of crop area
            height: Height of crop area

        Returns:
            Cropped PIL Image
        """
        return image.crop((x, y, x + width, y + height))

    @staticmethod
    def get_image_dimensions(image: Image.Image) -> Tuple[int, int]:
        """
        Get image dimensions.

        Args:
            image: PIL Image

        Returns:
            Tuple of (width, height)
        """
        return image.size

    @staticmethod
    def optimize_for_ai(image: Image.Image) -> Image.Image:
        """
        Optimize image for AI processing.

        Args:
            image: PIL Image to optimize

        Returns:
            Optimized PIL Image
        """
        # Resize to reasonable size for AI processing
        max_size = 1280
        if max(image.size) > max_size:
            image = ImageProcessor.resize_image(image, max_size)

        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')

        return image