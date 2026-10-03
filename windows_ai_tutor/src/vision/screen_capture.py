"""
Screen Capture Utility - Multi-Monitor Screen Capture

This manages screen capture for multiple monitors.
Equivalent to CompanionScreenCaptureUtility in Clicky.
"""

import asyncio
from typing import List, Optional, Tuple
from dataclasses import dataclass
from PyQt5.QtCore import QObject, pyqtSignal
import mss
import numpy as np
from PIL import Image
import io

from ..utils.logger import setup_logger


@dataclass
class ScreenCapture:
    """Data class for screen capture information."""
    image_data: bytes  # JPEG encoded image data
    label: str  # Screen label
    is_cursor_screen: bool  # Whether cursor is on this screen
    width: int  # Width in pixels
    height: int  # Height in pixels
    display_frame: Tuple[float, float, float, float]  # (x, y, width, height)
    screenshot_width: int  # Screenshot width
    screenshot_height: int  # Screenshot height


class ScreenCaptureUtility(QObject):
    """
    Manages screen capture for multiple monitors.
    Uses mss for high-performance screen capture.
    """

    # Signals
    capture_completed = pyqtSignal(object)  # ScreenCapture object
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self):
        """Initialize the screen capture utility."""
        super().__init__()

        self.logger = setup_logger("ScreenCaptureUtility")

        # Capture configuration
        self.quality = 85  # JPEG quality (0-100)

        self.logger.info("Screen capture utility initialized")

    def start(self):
        """Start the screen capture utility."""
        self.logger.info("Starting screen capture utility...")
        # Nothing to start for mss, just ready state

    def stop(self):
        """Stop the screen capture utility."""
        self.logger.info("Stopping screen capture utility...")
        # Nothing to stop for mss
        self.max_dimension = 1280  # Maximum dimension for screenshots

        # mss instance
        self.sct: Optional[mss.mss] = None

        self.logger.info("Screen capture utility initialized")

    async def capture_all_screens(self) -> List[ScreenCapture]:
        """
        Capture all connected screens.

        Returns:
            List of ScreenCapture objects
        """
        try:
            # Initialize mss
            with mss.mss() as sct:
                monitors = sct.monitors

                # Get cursor position to determine which screen has the cursor
                cursor_pos = self._get_cursor_position()

                captures = []

                # Capture each monitor
                for i, monitor in enumerate(monitors):
                    if i == 0:  # Skip the "all monitors" entry
                        continue

                    # Capture this monitor
                    screenshot = sct.grab(monitor)

                    # Convert to PIL Image
                    img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

                    # Resize if needed
                    img = self._resize_image(img)

                    # Convert to JPEG
                    jpeg_bytes = io.BytesIO()
                    img.save(jpeg_bytes, format='JPEG', quality=self.quality)
                    image_data = jpeg_bytes.getvalue()

                    # Determine if cursor is on this screen
                    is_cursor_screen = self._is_cursor_on_screen(
                        cursor_pos, monitor
                    )

                    # Create label
                    label = self._create_screen_label(i, len(monitors) - 1, is_cursor_screen)

                    # Create ScreenCapture object
                    capture = ScreenCapture(
                        image_data=image_data,
                        label=label,
                        is_cursor_screen=is_cursor_screen,
                        width=monitor["width"],
                        height=monitor["height"],
                        display_frame=(
                            monitor["left"],
                            monitor["top"],
                            monitor["width"],
                            monitor["height"]
                        ),
                        screenshot_width=img.width,
                        screenshot_height=img.height
                    )

                    captures.append(capture)

                # Sort so cursor screen is first
                captures.sort(key=lambda x: not x.is_cursor_screen)

                self.logger.info(f"Captured {len(captures)} screens")
                return captures

        except Exception as e:
            self.logger.error(f"Error capturing screens: {e}")
            self.error_occurred.emit(f"Screen capture error: {str(e)}")
            return []

    def _get_cursor_position(self) -> Tuple[int, int]:
        """
        Get current cursor position.

        Returns:
            Tuple of (x, y) coordinates
        """
        try:
            import pyautogui
            return pyautogui.position()
        except ImportError:
            # Fallback if pyautogui not available
            import win32api
            return win32api.GetCursorPos()

    def _is_cursor_on_screen(
        self,
        cursor_pos: Tuple[int, int],
        monitor: dict
    ) -> bool:
        """
        Check if cursor is on a specific screen.

        Args:
            cursor_pos: Cursor (x, y) position
            monitor: Monitor information

        Returns:
            True if cursor is on this screen
        """
        x, y = cursor_pos
        monitor_left = monitor["left"]
        monitor_top = monitor["top"]
        monitor_right = monitor["left"] + monitor["width"]
        monitor_bottom = monitor["top"] + monitor["height"]

        return (monitor_left <= x < monitor_right and
                monitor_top <= y < monitor_bottom)

    def _resize_image(self, img: Image.Image) -> Image.Image:
        """
        Resize image to fit within max dimension.

        Args:
            img: PIL Image to resize

        Returns:
            Resized PIL Image
        """
        width, height = img.size

        if max(width, height) <= self.max_dimension:
            return img

        # Calculate new dimensions
        if width > height:
            new_width = self.max_dimension
            new_height = int(height * (self.max_dimension / width))
        else:
            new_height = self.max_dimension
            new_width = int(width * (self.max_dimension / height))

        return img.resize((new_width, new_height), Image.LANCZOS)

    def _create_screen_label(
        self,
        screen_index: int,
        total_screens: int,
        is_cursor_screen: bool
    ) -> str:
        """
        Create a label for the screen.

        Args:
            screen_index: Screen index (1-based)
            total_screens: Total number of screens
            is_cursor_screen: Whether cursor is on this screen

        Returns:
            Screen label string
        """
        if total_screens == 1:
            return "user's screen (cursor is here)"
        elif is_cursor_screen:
            return f"screen {screen_index} of {total_screens} — cursor is on this screen (primary focus)"
        else:
            return f"screen {screen_index} of {total_screens} — secondary screen"

    async def capture_primary_screen(self) -> Optional[ScreenCapture]:
        """
        Capture only the primary screen (where cursor is).

        Returns:
            ScreenCapture object or None
        """
        try:
            all_captures = await self.capture_all_screens()
            for capture in all_captures:
                if capture.is_cursor_screen:
                    return capture
            return all_captures[0] if all_captures else None

        except Exception as e:
            self.logger.error(f"Error capturing primary screen: {e}")
            self.error_occurred.emit(f"Primary screen capture error: {str(e)}")
            return None