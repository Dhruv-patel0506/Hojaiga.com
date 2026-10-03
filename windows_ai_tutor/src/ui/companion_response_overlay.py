"""
Companion Response Overlay - Cursor-Following Text Display (Clicky-style)

Cursor-following overlay that displays streaming AI response text.
Converted from CompanionResponseOverlay.swift to Windows Python.
"""

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import QObject, pyqtSignal, pyqtProperty, QTimer, Qt, QPoint, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QFont
from typing import Optional

from ..ui.design_system import DesignSystem
from ..utils.logger import setup_logger


class CompanionResponseOverlayViewModel(QObject):
    """View model for the response overlay."""

    # Signals
    streaming_response_textChanged = pyqtSignal(str)
    is_showing_responseChanged = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._streaming_response_text = ""
        self._is_showing_response = False

    @pyqtProperty(str)
    def streaming_response_text(self) -> str:
        """Current streaming response text."""
        return self._streaming_response_text

    @streaming_response_text.setter
    def streaming_response_text(self, value: str):
        self._streaming_response_text = value
        # Emit signal when text changes
        if hasattr(self, 'streaming_response_textChanged'):
            self.streaming_response_textChanged.emit(value)

    @pyqtProperty(bool)
    def is_showing_response(self) -> bool:
        """Whether response is currently being shown."""
        return self._is_showing_response

    @is_showing_response.setter
    def is_showing_response(self, value: bool):
        self._is_showing_response = value
        # Emit signal when state changes
        if hasattr(self, 'is_showing_responseChanged'):
            self.is_showing_responseChanged.emit(value)

    @is_showing_response.setter
    def is_showing_response(self, value: bool):
        self._is_showing_response = value


class CompanionResponseOverlayManager(QObject):
    """
    Manages the cursor-following response overlay.
    Repositions itself near the mouse cursor each frame.
    """

    def __init__(self):
        super().__init__()

        self.logger = setup_logger("CompanionResponseOverlayManager")

        self.view_model = CompanionResponseOverlayViewModel()
        self.overlay_panel: Optional[QWidget] = None
        self.cursor_tracking_timer: Optional[QTimer] = None
        self.auto_hide_timer: Optional[QTimer] = None

        # Offset configuration
        self.cursor_offset_x = 22
        self.cursor_offset_y = 6
        self.overlay_max_width = 340

        self.logger.info("Companion response overlay manager initialized")

    def show_overlay_and_begin_streaming(self):
        """Show overlay and begin streaming response."""
        self.logger.info("Showing response overlay and beginning streaming")

        # Cancel any pending auto-hide
        if self.auto_hide_timer:
            self.auto_hide_timer.stop()
            self.auto_hide_timer = None

        self.view_model.streaming_response_text = ""
        self.view_model.is_showing_response = True

        self._create_overlay_panel_if_needed()
        self._start_cursor_tracking()

        if self.overlay_panel:
            self.overlay_panel.show()
            self.overlay_panel.raise_()
            self.overlay_panel.activateWindow()

    def update_streaming_text(self, accumulated_text: str):
        """Update the streaming text and resize panel."""
        self.view_model.streaming_response_text = accumulated_text
        self._resize_panel_to_fit_content()

    def finish_streaming(self):
        """Finish streaming and schedule auto-hide."""
        self.logger.info("Finishing streaming, scheduling auto-hide")

        # Keep response visible for 6 seconds, then fade out
        self.auto_hide_timer = QTimer()
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self._fade_out_and_hide)
        self.auto_hide_timer.start(6000)

    def hide_overlay(self):
        """Hide the overlay immediately."""
        self.logger.info("Hiding response overlay")

        if self.auto_hide_timer:
            self.auto_hide_timer.stop()
            self.auto_hide_timer = None

        self._stop_cursor_tracking()
        self.view_model.is_showing_response = False
        self.view_model.streaming_response_text = ""

        if self.overlay_panel:
            self.overlay_panel.hide()

    def _create_overlay_panel_if_needed(self):
        """Create the overlay panel if it doesn't exist."""
        if self.overlay_panel is not None:
            return

        self.overlay_panel = CompanionResponseOverlayView(self.view_model)
        self.overlay_panel.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowTransparentForInput
        )
        self.overlay_panel.setAttribute(Qt.WA_TranslucentBackground)
        self.overlay_panel.setAttribute(Qt.WA_ShowWithoutActivating)
        self.overlay_panel.setMaximumWidth(self.overlay_max_width)

        # Apply styling
        DesignSystem.apply_dark_theme(self.overlay_panel)

        self.logger.info("Created response overlay panel")

    def _start_cursor_tracking(self):
        """Start 60fps cursor tracking."""
        self.cursor_tracking_timer = QTimer()
        self.cursor_tracking_timer.timeout.connect(self._reposition_panel_near_cursor)
        self.cursor_tracking_timer.start(16)  # ~60 FPS

    def _stop_cursor_tracking(self):
        """Stop cursor tracking."""
        if self.cursor_tracking_timer:
            self.cursor_tracking_timer.stop()
            self.cursor_tracking_timer = None

    def _reposition_panel_near_cursor(self):
        """Reposition the panel near the mouse cursor."""
        if not self.overlay_panel:
            return

        from PyQt5.QtGui import QCursor
        mouse_location = QCursor.pos()
        panel_size = self.overlay_panel.size()

        # Position panel to the right and slightly below cursor
        panel_origin_x = mouse_location.x() + self.cursor_offset_x
        panel_origin_y = mouse_location.y() + self.cursor_offset_y - panel_size.height()

        # Clamp to visible frame of screen
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.screenAt(mouse_location)
        if screen:
            visible_frame = screen.availableGeometry()

            # If panel would go off right edge, flip to left of cursor
            if panel_origin_x + panel_size.width() > visible_frame.right():
                panel_origin_x = mouse_location.x() - self.cursor_offset_x - panel_size.width()

            # If panel would go below bottom edge, push above cursor
            if panel_origin_y + panel_size.height() > visible_frame.bottom():
                panel_origin_y = mouse_location.y() - self.cursor_offset_y - panel_size.height()

            # Final clamp
            panel_origin_x = max(visible_frame.left(), min(panel_origin_x, visible_frame.right() - panel_size.width()))
            panel_origin_y = max(visible_frame.top(), min(panel_origin_y, visible_frame.bottom() - panel_size.height()))

        self.overlay_panel.move(panel_origin_x, panel_origin_y)

    def _resize_panel_to_fit_content(self):
        """Resize panel to fit the current content."""
        if not self.overlay_panel:
            return

        # Get current text and calculate required size
        text = self.view_model.streaming_response_text
        if not text:
            text = "..."

        # Calculate required size
        font = QFont("Arial", 13)
        from PyQt5.QtGui import QFontMetrics
        fm = QFontMetrics(font)
        padding = 14
        max_width = 300

        # Word wrap and calculate height
        from PyQt5.QtGui import QTextOption
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WordWrap)

        # Simple height calculation
        lines = text.split('\n')
        max_line_width = max((fm.width(line) for line in lines), default=0)
        width = min(max_line_width + padding * 2, max_width)
        height = fm.height() * len(lines) + padding * 2

        # Clamp to max width
        width = min(width, self.overlay_max_width)

        # Update panel size
        self.overlay_panel.setFixedSize(width, height)

    def _fade_out_and_hide(self):
        """Fade out the overlay and hide it."""
        if not self.overlay_panel:
            return

        # Simple fade animation
        opacity_animation = QPropertyAnimation(self.overlay_panel, b"windowOpacity")
        opacity_animation.setDuration(400)
        opacity_animation.setStartValue(1.0)
        opacity_animation.setEndValue(0.0)
        opacity_animation.setEasingCurve(QEasingCurve.OutQuad)

        opacity_animation.finished.connect(self.hide_overlay)
        opacity_animation.start()


class CompanionResponseOverlayView(QWidget):
    """SwiftUI-style view for the response overlay."""

    def __init__(self, view_model: CompanionResponseOverlayViewModel):
        super().__init__()

        self.view_model = view_model

        # Build UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(0)

        # Text label
        self.text_label = QLabel()
        self.text_label.setFont(QFont("Arial", 13))
        self.text_label.setStyleSheet(f"color: {DesignSystem.Colors.TEXT_PRIMARY.name()};")
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

        # Update text when view model changes
        self.view_model.streaming_response_textChanged.connect(self._update_text)
        self.view_model.is_showing_responseChanged.connect(self._update_visibility)

        # Apply background styling
        self._apply_background_styling()

    def _update_text(self, text: str):
        """Update the displayed text."""
        self.text_label.setText(text if text else "...")

    def _update_visibility(self, visible: bool):
        """Update overlay visibility."""
        if visible:
            self.show()
        else:
            self.hide()

    def _apply_background_styling(self):
        """Apply the background styling (rounded rect with shadow)."""
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignSystem.Colors.SURFACE1.name()};
                border: 1px solid {DesignSystem.Colors.BORDER_SUBTLE.name()};
                border-radius: 10px;
            }}
        """)
