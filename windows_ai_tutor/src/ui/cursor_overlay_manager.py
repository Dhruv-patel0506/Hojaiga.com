"""
Cursor Overlay Manager - Multi-screen Overlay Management (Clicky-style)

Manages transparent overlay windows across all connected monitors.
Converted from OverlayWindow.swift overlay management.
"""

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QScreen
from typing import List

from .overlay_window import OverlayWindow
from ..utils.logger import setup_logger


class CursorOverlayManager(QObject):
    """
    Manages cursor overlay windows across all screens.
    Clicky-style multi-monitor support.
    """

    # Signals
    overlay_visibility_changed = pyqtSignal(bool)

    def __init__(self):
        """Initialize the cursor overlay manager."""
        super().__init__()

        self.logger = setup_logger("CursorOverlayManager")
        self.overlays: List[OverlayWindow] = []
        self.is_visible = False

        self.logger.info("Cursor overlay manager initialized")

    def start(self):
        """Start the overlay manager and create overlays for all screens."""
        self.logger.info("Starting cursor overlay manager...")

        # Create overlay for each screen
        screens = QApplication.screens()
        self.logger.info(f"Found {len(screens)} screen(s)")

        for screen in screens:
            overlay = OverlayWindow(screen.geometry())
            self.overlays.append(overlay)
            self.logger.info(f"Created overlay for screen: {screen.geometry()}")

        # Show overlays if enabled
        if self.is_visible:
            self.show()

    def stop(self):
        """Stop the overlay manager and destroy all overlays."""
        self.logger.info("Stopping cursor overlay manager...")

        for overlay in self.overlays:
            overlay.close()
        self.overlays.clear()

    def show(self):
        """Show all overlay windows."""
        self.logger.info("Showing cursor overlays")
        for overlay in self.overlays:
            overlay.show_overlay()
        self.is_visible = True
        self.overlay_visibility_changed.emit(True)

    def hide(self):
        """Hide all overlay windows."""
        self.logger.info("Hiding cursor overlays")
        for overlay in self.overlays:
            overlay.hide_overlay()
        self.is_visible = False
        self.overlay_visibility_changed.emit(False)

    def animate_to_position(self, x, y, label):
        """
        Animate cursor to a specific position on all overlays.

        Args:
            x: Target X coordinate (global)
            y: Target Y coordinate (global)
            label: Label to show in speech bubble
        """
        self.logger.info(f"Animating cursor to: {x}, {y} with label: {label}")

        # Find which screen contains the target position
        from PyQt5.QtCore import QPoint
        target_point = QPoint(x, y)

        for overlay in self.overlays:
            if overlay.screen_geometry.contains(target_point):
                # Convert to local coordinates
                local_x = x - overlay.screen_geometry.x()
                local_y = y - overlay.screen_geometry.y()
                overlay.animate_to_position(local_x, local_y, label)
                break
