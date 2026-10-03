"""
Cursor Overlay Manager - Custom Cursor Overlay

This manages the transparent overlay window for the custom cursor.
Equivalent to OverlayWindow.swift in Clicky.
"""

from typing import Optional, Tuple
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath
import math

from ..utils.logger import setup_logger


class CursorOverlayWidget(QWidget):
    """
    Custom widget that renders the cursor overlay.
    """

    def __init__(self):
        """Initialize the cursor overlay widget."""
        super().__init__()

        self.logger = setup_logger("CursorOverlayWidget")

        # Window properties
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.WindowTransparentForInput |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Cursor position
        self.cursor_position = QPoint(100, 100)

        # Cursor appearance
        self.cursor_color = QColor("#3380FF")  # Blue cursor
        self.cursor_size = 20
        self.cursor_rotation = -35  # Degrees

        # Animation state
        self.target_position: Optional[QPoint] = None
        self.animation_progress = 0.0
        self.is_animating = False

        # Speech bubble
        self.bubble_text = ""
        self.show_bubble = False

        # Tracking timer
        self.tracking_timer = QTimer()
        self.tracking_timer.timeout.connect(self.update_cursor_position)
        self.tracking_timer.start(16)  # ~60 FPS

        self.logger.info("Cursor overlay widget initialized")

    def update_cursor_position(self):
        """Update cursor position to follow actual mouse cursor."""
        try:
            import pyautogui
            x, y = pyautogui.position()
            self.cursor_position = QPoint(x, y)
            self.update()
        except ImportError:
            import win32api
            x, y = win32api.GetCursorPos()
            self.cursor_position = QPoint(x, y)
            self.update()

    def set_target_position(self, x: int, y: int, label: str = ""):
        """
        Set target position for pointing animation.

        Args:
            x: Target X coordinate
            y: Target Y coordinate
            label: Label to show in speech bubble
        """
        self.target_position = QPoint(x, y)
        self.bubble_text = label
        self.show_bubble = True
        self.animation_progress = 0.0
        self.is_animating = True

        # Start animation timer
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._animate_to_target)
        self.animation_timer.start(16)  # ~60 FPS

    def _animate_to_target(self):
        """Animate cursor to target position using bezier curve."""
        if not self.is_animating or not self.target_position:
            return

        # Increment animation progress
        self.animation_progress += 0.02

        if self.animation_progress >= 1.0:
            # Animation complete
            self.cursor_position = self.target_position
            self.is_animating = False
            self.animation_timer.stop()

            # Show bubble briefly then hide
            QTimer.singleShot(2000, self._hide_bubble)
        else:
            # Calculate position along bezier curve
            start = self.cursor_position
            end = self.target_position

            # Control point for bezier curve (creates arc)
            control = QPoint(
                (start.x() + end.x()) // 2,
                min(start.y(), end.y()) - 100
            )

            # Quadratic bezier formula
            t = self.animation_progress
            x = (1 - t) ** 2 * start.x() + 2 * (1 - t) * t * control.x() + t ** 2 * end.x()
            y = (1 - t) ** 2 * start.y() + 2 * (1 - t) * t * control.y() + t ** 2 * end.y()

            self.cursor_position = QPoint(int(x), int(y))

        self.update()

    def _hide_bubble(self):
        """Hide the speech bubble."""
        self.show_bubble = False
        self.target_position = None
        self.update()

    def paintEvent(self, event):
        """Paint the cursor overlay."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw cursor triangle
        self._draw_cursor_triangle(painter)

        # Draw speech bubble if needed
        if self.show_bubble and self.bubble_text:
            self._draw_speech_bubble(painter)

        painter.end()

    def _draw_cursor_triangle(self, painter: QPainter):
        """Draw the cursor triangle."""
        painter.save()

        # Move to cursor position
        painter.translate(self.cursor_position)

        # Rotate
        painter.rotate(self.cursor_rotation)

        # Set up brush and pen
        painter.setBrush(QBrush(self.cursor_color))
        painter.setPen(Qt.NoPen)

        # Draw triangle
        size = self.cursor_size
        height = size * math.sqrt(3) / 2

        path = QPainterPath()
        path.moveTo(0, -height / 1.5)  # Top
        path.lineTo(-size / 2, height / 3)  # Bottom left
        path.lineTo(size / 2, height / 3)  # Bottom right
        path.closeSubpath()

        painter.drawPath(path)

        # Add glow effect
        painter.setBrush(Qt.NoBrush)
        pen = QPen(self.cursor_color)
        pen.setWidth(2)
        pen.setColor(QColor(self.cursor_color.red(), self.cursor_color.green(),
                          self.cursor_color.blue(), 100))
        painter.setPen(pen)
        painter.drawPath(path)

        painter.restore()

    def _draw_speech_bubble(self, painter: QPainter):
        """Draw speech bubble with text."""
        painter.save()

        # Bubble position (above cursor)
        bubble_x = self.cursor_position.x() + 10
        bubble_y = self.cursor_position.y() - 30

        # Calculate bubble size
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_width = metrics.width(self.bubble_text)
        text_height = metrics.height()

        bubble_width = text_width + 20
        bubble_height = text_height + 10

        # Draw bubble background
        bubble_rect = painter.drawRect(bubble_x, bubble_y - bubble_height,
                                       bubble_width, bubble_height)

        painter.setBrush(QBrush(self.cursor_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(bubble_x, bubble_y - bubble_height,
                                 bubble_width, bubble_height, 6, 6)

        # Draw text
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(bubble_x + 10, bubble_y - bubble_height / 2 + text_height / 2,
                        self.bubble_text)

        painter.restore()


class CursorOverlayManager(QObject):
    """
    Manages the cursor overlay window across multiple screens.
    """

    def __init__(self):
        """Initialize the cursor overlay manager."""
        super().__init__()

        self.logger = setup_logger("CursorOverlayManager")

        # Overlay widgets for each screen
        self.overlays: list = []

        # Visibility state
        self._is_visible = False

        self.logger.info("Cursor overlay manager initialized")

    def show_overlay(self):
        """Show the cursor overlay on all screens."""
        if self._is_visible:
            return

        try:
            # Get screen information
            import screeninfo
            screens = screeninfo.get_monitors()

            # Create overlay for each screen
            for screen in screens:
                overlay = CursorOverlayWidget()
                overlay.setGeometry(screen.x, screen.y, screen.width, screen.height)
                overlay.show()
                self.overlays.append(overlay)

            self._is_visible = True
            self.logger.info(f"Cursor overlay shown on {len(screens)} screens")

        except Exception as e:
            self.logger.error(f"Error showing cursor overlay: {e}")

    def hide_overlay(self):
        """Hide the cursor overlay."""
        if not self._is_visible:
            return

        try:
            for overlay in self.overlays:
                overlay.close()

            self.overlays.clear()
            self._is_visible = False
            self.logger.info("Cursor overlay hidden")

        except Exception as e:
            self.logger.error(f"Error hiding cursor overlay: {e}")

    def animate_to_position(self, x: int, y: int, label: str = ""):
        """
        Animate cursor to a specific position.

        Args:
            x: Target X coordinate
            y: Target Y coordinate
            label: Label to show in speech bubble
        """
        for overlay in self.overlays:
            overlay.set_target_position(x, y, label)

    @property
    def is_visible(self) -> bool:
        """Check if overlay is visible."""
        return self._is_visible