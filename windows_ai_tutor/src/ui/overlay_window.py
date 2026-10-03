"""
Overlay Window - Transparent Screen Overlay (Clicky-style)

System-wide transparent overlay window for the coral-red cursor.
One overlay per screen for multi-monitor support. Converted from OverlayWindow.swift.
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPolygonF, QPainterPath
from PyQt5.QtCore import QPointF
import math
from enum import Enum

from ..utils.logger import setup_logger


class BuddyNavigationMode(Enum):
    """The buddy's behavioral mode."""
    FOLLOWING_CURSOR = "following_cursor"
    NAVIGATING_TO_TARGET = "navigating_to_target"
    POINTING_AT_TARGET = "pointing_at_target"


class OverlayWindow(QWidget):
    """
    Full-screen transparent overlay window for the coral-red cursor.
    Clicky-style with vector drawing and bezier animations.
    """

    def __init__(self, screen_geometry):
        """
        Initialize the overlay window.

        Args:
            screen_geometry: QRect of the screen this overlay covers
        """
        super().__init__()

        self.logger = setup_logger("OverlayWindow")
        self.screen_geometry = screen_geometry

        # Window configuration - transparent and non-interactive
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_NoSystemBackground)

        # Cover the entire screen
        self.setGeometry(screen_geometry)

        # Cursor state
        self.cursor_position = QPoint(100, 100)
        self.is_cursor_on_screen = True
        self.cursor_opacity = 0.0
        self.target_position = None
        self.navigation_mode = BuddyNavigationMode.FOLLOWING_CURSOR
        self.navigation_bubble_text = ""
        self.navigation_bubble_opacity = 0.0

        # Animation state
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animation)
        self.animation_progress = 0.0
        self.animation_duration = 60  # frames
        self.start_position = None

        # Triangle rotation (default -35 degrees like cursor)
        self.triangle_rotation = -35.0

        # Speech bubble state
        self.bubble_text = ""
        self.bubble_opacity = 0.0

        # Mouse tracking timer
        self.mouse_tracker = QTimer()
        self.mouse_tracker.timeout.connect(self._track_mouse)
        self.mouse_tracker.start(16)  # ~60 FPS

        # Start animation timer
        self.animation_timer.start(16)

        self.logger.info(f"Overlay window created for screen: {screen_geometry}")

    def _track_mouse(self):
        """Track mouse position and update cursor."""
        from PyQt5.QtGui import QCursor
        global_pos = QCursor.pos()

        # Convert to local coordinates
        local_x = global_pos.x() - self.screen_geometry.x()
        local_y = global_pos.y() - self.screen_geometry.y()

        # Check if cursor is on this screen
        self.is_cursor_on_screen = self.screen_geometry.contains(global_pos)

        if self.is_cursor_on_screen and self.navigation_mode == BuddyNavigationMode.FOLLOWING_CURSOR:
            # Smooth follow with offset
            offset_x = 35
            offset_y = 25
            target_x = local_x + offset_x
            target_y = local_y + offset_y

            # Smooth interpolation
            self.cursor_position.setX(int(self.cursor_position.x() * 0.8 + target_x * 0.2))
            self.cursor_position.setY(int(self.cursor_position.y() * 0.8 + target_y * 0.2))

            self.cursor_opacity = 1.0

        self.update()

    def animate_to_position(self, x, y, label):
        """
        Animate cursor to a target position with bezier curve.

        Args:
            x: Target X coordinate
            y: Target Y coordinate
            label: Label to show in speech bubble
        """
        self.logger.info(f"Animating to position: {x}, {y} with label: {label}")

        self.start_position = QPoint(self.cursor_position)
        self.target_position = QPoint(x, y)
        self.navigation_bubble_text = label
        self.navigation_mode = BuddyNavigationMode.NAVIGATING_TO_TARGET
        self.animation_progress = 0.0

        # Reset animation timer
        self.animation_timer.start(16)

    def _update_animation(self):
        """Update animation frame."""
        if self.navigation_mode == BuddyNavigationMode.NAVIGATING_TO_TARGET and self.target_position:
            self.animation_progress += 1.0 / self.animation_duration

            if self.animation_progress >= 1.0:
                # Animation complete
                self.cursor_position = QPoint(self.target_position)
                self.navigation_mode = BuddyNavigationMode.POINTING_AT_TARGET
                self.navigation_bubble_opacity = 1.0
                self.logger.info("Animation complete, now pointing")
            else:
                # Bezier curve interpolation
                t = self.animation_progress
                # Ease in-out
                t = t * t * (3 - 2 * t)

                # Calculate control point for bezier curve (creates arc)
                start = self.start_position
                end = self.target_position
                mid_x = (start.x() + end.x()) / 2
                mid_y = (start.y() + end.y()) / 2 - 100  # Arc upward

                # Quadratic bezier
                x = (1 - t) * (1 - t) * start.x() + 2 * (1 - t) * t * mid_x + t * t * end.x()
                y = (1 - t) * (1 - t) * start.y() + 2 * (1 - t) * t * mid_y + t * t * end.y()

                self.cursor_position = QPoint(int(x), int(y))

                # Scale effect during flight
                scale = 1.0 + 0.3 * math.sin(t * math.pi)
                self.bubble_opacity = 0.0

        elif self.navigation_mode == BuddyNavigationMode.POINTING_AT_TARGET:
            # Fade out after pointing
            self.navigation_bubble_opacity -= 0.02
            if self.navigation_bubble_opacity <= 0:
                self.navigation_bubble_opacity = 0.0
                self.navigation_mode = BuddyNavigationMode.FOLLOWING_CURSOR
                self.navigation_bubble_text = ""

        self.update()

    def paintEvent(self, event):
        """Paint the overlay content."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw coral-red cursor triangle
        if self.is_cursor_on_screen and self.cursor_opacity > 0:
            self._draw_cursor_triangle(painter)

        # Draw navigation bubble if pointing
        if self.navigation_mode == BuddyNavigationMode.POINTING_AT_TARGET and self.navigation_bubble_opacity > 0:
            self._draw_navigation_bubble(painter)

        painter.end()

    def _draw_cursor_triangle(self, painter):
        """Draw the coral-red cursor triangle."""
        # Save painter state
        painter.save()

        # Move to cursor position
        painter.translate(self.cursor_position)

        # Rotate triangle
        painter.rotate(self.triangle_rotation)

        # Triangle parameters
        size = 24
        height = size * math.sqrt(3.0) / 2.0

        # Triangle vertices (equilateral)
        from PyQt5.QtCore import QPointF
        top = QPointF(0, -height / 1.5)
        bottom_left = QPointF(-size / 2, height / 3)
        bottom_right = QPointF(size / 2, height / 3)

        # Draw triangle
        path = QPainterPath()
        path.moveTo(top)
        path.lineTo(bottom_left)
        path.lineTo(bottom_right)
        path.closeSubpath()

        # Coral-red fill (#FF3B30)
        painter.setBrush(QBrush(QColor("#FF3B30")))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

        # Restore painter state
        painter.restore()

    def _draw_navigation_bubble(self, painter):
        """Draw the speech bubble when pointing at target."""
        if not self.navigation_bubble_text:
            return

        painter.save()

        # Position bubble above cursor
        bubble_x = self.cursor_position.x() + 10
        bubble_y = self.cursor_position.y() - 20

        # Calculate bubble size
        from PyQt5.QtGui import QFontMetrics, QFont
        font = QFont("Arial", 11, QFont.Medium)
        fm = QFontMetrics(font)
        text_width = fm.width(self.navigation_bubble_text)
        padding = 8
        bubble_width = text_width + padding * 2
        bubble_height = fm.height() + padding * 2

        # Draw rounded rectangle background
        from PyQt5.QtGui import QPainterPath
        bubble_path = QPainterPath()
        bubble_path.addRoundedRect(
            bubble_x, bubble_y,
            bubble_width, bubble_height,
            6, 6
        )

        # Coral-red background with shadow
        painter.setBrush(QBrush(QColor("#FF3B30")))
        painter.setPen(Qt.NoPen)
        painter.drawPath(bubble_path)

        # Draw text
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(font)
        painter.drawText(
            bubble_x + padding, bubble_y + padding + fm.ascent(),
            self.navigation_bubble_text
        )

        painter.restore()

    def show_overlay(self):
        """Show the overlay."""
        self.show()
        self.cursor_opacity = 1.0

    def hide_overlay(self):
        """Hide the overlay."""
        self.hide()
        self.cursor_opacity = 0.0
