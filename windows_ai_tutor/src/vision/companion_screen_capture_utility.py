"""
Companion Screen Capture Utility - Clicky-style Multi-Monitor Capture

Standalone screenshot capture for companion voice flow.
Converted from CompanionScreenCaptureUtility.swift to Windows Python.
"""

from dataclasses import dataclass
from typing import List, Optional
from PyQt5.QtCore import QRect, QPoint
from PyQt5.QtWidgets import QApplication
import mss
from PIL import Image
import io

from ..utils.logger import setup_logger


@dataclass
class CompanionScreenCapture:
    """Data class for screen capture information."""
    image_data: bytes  # JPEG encoded image data
    label: str  # Screen label
    is_cursor_screen: bool  # Whether cursor is on this screen
    display_width_in_points: int  # Width in points
    display_height_in_points: int  # Height in points
    display_frame: QRect  # Display frame
    screenshot_width_in_pixels: int  # Screenshot width
    screenshot_height_in_pixels: int  # Screenshot height


class CompanionScreenCaptureUtility:
    """
    Companion screen capture utility.
    Captures all connected displays as JPEG data with cursor detection.
    """

    @staticmethod
    def capture_all_screens_as_jpeg() -> List[CompanionScreenCapture]:
        """
        Capture all connected displays as JPEG data.

        Returns:
            List of CompanionScreenCapture objects
        """
        logger = setup_logger("CompanionScreenCaptureUtility")
        logger.info("Capturing all screens...")

        captured_screens = []

        try:
            # Get all screens
            screens = QApplication.screens()
            if not screens:
                logger.error("No displays available for capture")
                return []

            # Get current mouse position
            from PyQt5.QtGui import QCursor
            mouse_location = QCursor.pos()

            # Sort displays so cursor screen is first
            screens_with_cursor = []
            screens_without_cursor = []

            for screen in screens:
                screen_geometry = screen.geometry()
                if screen_geometry.contains(mouse_location):
                    screens_with_cursor.append((screen, True))
                else:
                    screens_without_cursor.append((screen, False))

            sorted_screens = screens_with_cursor + screens_without_cursor

            # Capture each screen
            for screen_index, (screen, is_cursor_screen) in enumerate(sorted_screens):
                screen_geometry = screen.geometry()

                # Capture screen using mss
                with mss.mss() as sct:
                    monitor = {
                        "left": screen_geometry.x(),
                        "top": screen_geometry.y(),
                        "width": screen_geometry.width(),
                        "height": screen_geometry.height()
                    }

                    # Capture with max dimension of 1280
                    max_dimension = 1280
                    width = screen_geometry.width()
                    height = screen_geometry.height()

                    if width >= height:
                        if width > max_dimension:
                            scale = max_dimension / width
                            monitor["width"] = max_dimension
                            monitor["height"] = int(height * scale)
                    else:
                        if height > max_dimension:
                            scale = max_dimension / height
                            monitor["height"] = max_dimension
                            monitor["width"] = int(width * scale)

                    # Capture screenshot
                    screenshot = sct.grab(monitor)

                    # Convert to PIL Image
                    img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

                    # Convert to JPEG
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='JPEG', quality=80)
                    image_data = img_byte_arr.getvalue()

                    # Create label
                    if len(sorted_screens) == 1:
                        screen_label = "user's screen (cursor is here)"
                    elif is_cursor_screen:
                        screen_label = f"screen {screen_index + 1} of {len(sorted_screens)} — cursor is on this screen (primary focus)"
                    else:
                        screen_label = f"screen {screen_index + 1} of {len(sorted_screens)} — secondary screen"

                    captured_screens.append(CompanionScreenCapture(
                        image_data=image_data,
                        label=screen_label,
                        is_cursor_screen=is_cursor_screen,
                        display_width_in_points=screen_geometry.width(),
                        display_height_in_points=screen_geometry.height(),
                        display_frame=screen_geometry,
                        screenshot_width_in_pixels=monitor["width"],
                        screenshot_height_in_pixels=monitor["height"]
                    ))

                    logger.info(f"Captured screen {screen_index + 1}: {screen_label}")

            logger.info(f"Successfully captured {len(captured_screens)} screen(s)")
            return captured_screens

        except Exception as e:
            logger.error(f"Failed to capture screens: {e}")
            return []
