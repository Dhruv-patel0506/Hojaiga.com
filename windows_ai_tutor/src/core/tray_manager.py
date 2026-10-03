"""
Tray Manager - System Tray Integration

This manages the Windows system tray icon and context menu.
Equivalent to MenuBarPanelManager.swift in Clicky.
"""

from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QCursor

from ..ui.control_panel import ControlPanel
from ..utils.logger import setup_logger


class TrayManager(QObject):
    """
    Manages the system tray icon and context menu for Windows AI Tutor.
    """

    # Signals
    quit_requested = pyqtSignal()
    show_panel_requested = pyqtSignal()
    hide_panel_requested = pyqtSignal()

    def __init__(self, state_manager):
        """
        Initialize the tray manager.

        Args:
            state_manager: State manager instance
        """
        super().__init__()

        self.logger = setup_logger("TrayManager")
        self.state_manager = state_manager

        # Create system tray icon
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(self._create_tray_icon())

        # Create control panel
        self.control_panel = ControlPanel(state_manager)

        # Create context menu
        self._create_context_menu()

        # Connect signals
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.state_manager.state_changed.connect(self._on_state_changed)

        self.logger.info("Tray manager initialized")

    def _create_tray_icon(self) -> QIcon:
        """
        Create the tray icon.

        Returns:
            QIcon: The tray icon
        """
        # For now, use a simple colored square
        # In production, this would be a proper icon file
        from PyQt5.QtGui import QPixmap, QPainter, QColor
        from PyQt5.QtCore import QSize

        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw a blue triangle (similar to Clicky's cursor)
        painter.setBrush(QColor("#3380FF"))
        painter.setPen(Qt.NoPen)

        # Triangle coordinates
        import math
        size = 20
        cx, cy = 16, 16
        height = size * math.sqrt(3) / 2

        # Rotate triangle by 35 degrees
        angle = 35 * math.pi / 180

        def rotate_point(x, y):
            dx = x - cx
            dy = y - cy
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            return (cx + cos_a * dx - sin_a * dy,
                    cy + sin_a * dx + cos_a * dy)

        # Triangle vertices
        top = rotate_point(cx, cy - height / 1.5)
        bottom_left = rotate_point(cx - size / 2, cy + height / 3)
        bottom_right = rotate_point(cx + size / 2, cy + height / 3)

        from PyQt5.QtGui import QPolygon
        triangle = QPolygon([
            int(top[0]), int(top[1]),
            int(bottom_left[0]), int(bottom_left[1]),
            int(bottom_right[0]), int(bottom_right[1])
        ])

        painter.drawPolygon(triangle)
        painter.end()

        return QIcon(pixmap)

    def _create_context_menu(self):
        """Create the context menu for the tray icon."""
        context_menu = QMenu()

        # Show/Hide Control Panel
        show_panel_action = QAction("Show Control Panel", self)
        show_panel_action.triggered.connect(self.show_control_panel)
        context_menu.addAction(show_panel_action)

        context_menu.addSeparator()

        # Status indicator
        status_action = QAction(f"Status: {self.state_manager.voice_state.value}", self)
        status_action.setEnabled(False)
        context_menu.addAction(status_action)

        context_menu.addSeparator()

        # Quit action
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_requested.emit)
        context_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(context_menu)

    def _on_tray_activated(self, reason):
        """
        Handle tray icon activation.

        Args:
            reason: Activation reason (click, double click, etc.)
        """
        if reason == QSystemTrayIcon.Trigger:
            # Single click - always show panel (don't hide)
            self.show_control_panel()
        elif reason == QSystemTrayIcon.DoubleClick:
            # Double click - always show panel
            self.show_control_panel()

    def _on_state_changed(self, state: str):
        """
        Handle state changes from state manager.

        Args:
            state: New voice state
        """
        # Update tray icon tooltip
        self.tray_icon.setToolTip(f"Windows AI Tutor - {state.title()}")

        # Update context menu status
        context_menu = self.tray_icon.contextMenu()
        for action in context_menu.actions():
            if action.text().startswith("Status:"):
                action.setText(f"Status: {state.title()}")
                break

    def show(self):
        """Show the tray icon."""
        self.tray_icon.show()
        self.logger.info("Tray icon shown")

    def hide(self):
        """Hide the tray icon."""
        self.tray_icon.hide()
        self.logger.info("Tray icon hidden")

    def show_control_panel(self):
        """Show the control panel."""
        self.control_panel.show()
        self.control_panel.raise_()
        self.control_panel.activateWindow()
        self.show_panel_requested.emit()
        self.logger.info("Control panel shown")

    def hide_control_panel(self):
        """Hide the control panel."""
        self.control_panel.hide()
        self.hide_panel_requested.emit()
        self.logger.info("Control panel hidden")

    def on_state_changed(self, state: str):
        """
        Handle state changes (called by state manager).

        Args:
            state: New state
        """
        self._on_state_changed(state)