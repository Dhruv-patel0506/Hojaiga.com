"""
Menu Bar Panel Manager - System Tray Integration (Clicky-style)

Manages the Windows system tray icon and a custom borderless panel
that drops down below it when clicked. Converted from MenuBarPanelManager.swift.
"""

from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QWidget
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QPoint, QTimer
from PyQt5.QtGui import QIcon, QCursor, QPixmap, QPainter, QColor, QBrush
from PyQt5.QtWidgets import QGraphicsOpacityEffect

from ..ui.companion_panel_view import CompanionPanelView
from ..utils.logger import setup_logger


class MenuBarPanelManager(QObject):
    """
    Manages the Windows system tray icon and custom floating panel.
    Clicky-style zero-window HUD with top status pill.
    """

    # Signals
    panel_dismissed = pyqtSignal()

    def __init__(self, companion_manager):
        """
        Initialize the menu bar panel manager.

        Args:
            companion_manager: Companion manager instance
        """
        super().__init__()

        self.logger = setup_logger("MenuBarPanelManager")
        self.companion_manager = companion_manager

        # Panel configuration
        self.panel_width = 320
        self.panel_height = 380

        # Components
        self.tray_icon = None
        self.panel = None
        self.panel_view = None
        self.click_outside_timer = None

        # Create tray icon
        self._create_tray_icon()

        self.logger.info("Menu bar panel manager initialized")

    def _create_tray_icon(self):
        """Create the system tray icon with Clicky triangle."""
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(self._make_clicky_tray_icon())
        self.tray_icon.activated.connect(self._on_tray_activated)

        # Create context menu
        self._create_context_menu()

    def _make_clicky_tray_icon(self) -> QIcon:
        """
        Draw the Clicky triangle as a tray icon.
        Same shape and rotation as the in-app cursor.
        """
        icon_size = 18
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Triangle parameters
        triangle_size = icon_size * 0.7
        cx = icon_size * 0.5
        cy = icon_size * 0.5
        height = triangle_size * (3 ** 0.5) / 2.0

        # Triangle vertices
        top = QPoint(int(cx), int(cy + height / 1.5))
        bottom_left = QPoint(int(cx - triangle_size / 2), int(cy - height / 3))
        bottom_right = QPoint(int(cx + triangle_size / 2), int(cy - height / 3))

        # Rotate by 35 degrees
        import math
        angle = 35.0 * math.pi / 180.0
        def rotate(point):
            dx = point.x() - cx
            dy = point.y() - cy
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            return QPoint(int(cx + cos_a * dx - sin_a * dy),
                        int(cy + sin_a * dx + cos_a * dy))

        # Draw triangle
        from PyQt5.QtGui import QPolygon
        polygon = QPolygon([rotate(top), rotate(bottom_left), rotate(bottom_right)])
        painter.setBrush(QBrush(QColor("#FF3B30")))  # Coral red
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(polygon)

        painter.end()
        return QIcon(pixmap)

    def _create_context_menu(self):
        """Create the tray icon context menu."""
        menu = QMenu()

        show_action = QAction("Show Panel", self)
        show_action.triggered.connect(self.show_panel)
        menu.addAction(show_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._on_quit)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)

    def _on_tray_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.Trigger:
            # Single click - toggle panel
            if self.panel and self.panel.isVisible():
                self.hide_panel()
            else:
                self.show_panel()

    def show_panel_on_launch(self):
        """Show panel automatically on app launch."""
        # Small delay so tray icon has time to appear
        QTimer.singleShot(300, self.show_panel)

    def show_panel(self):
        """Show the floating panel below the tray icon."""
        if self.panel is None:
            self._create_panel()

        self._position_panel_below_tray_icon()
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

        self._install_click_outside_monitor()

    def hide_panel(self):
        """Hide the floating panel."""
        if self.panel:
            self.panel.hide()
            self._remove_click_outside_monitor()

    def _create_panel(self):
        """Create the floating panel window."""
        self.panel_view = CompanionPanelView(self.companion_manager)
        self.panel_view.setFixedWidth(self.panel_width)

        self.panel = QWidget()
        self.panel.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.panel.setAttribute(Qt.WA_TranslucentBackground)
        self.panel.setAttribute(Qt.WA_ShowWithoutActivating)
        self.panel.setFixedSize(self.panel_width, self.panel_height)

        # Set the panel view as content
        layout = self.panel.layout()
        if layout is None:
            from PyQt5.QtWidgets import QVBoxLayout
            layout = QVBoxLayout(self.panel)
            layout.setContentsMargins(0, 0, 0, 0)
        else:
            layout.addWidget(self.panel_view)

        # Apply Clicky styling
        self._apply_clicky_styling()

    def _apply_clicky_styling(self):
        """Apply Clicky's dark theme styling to the panel."""
        from PyQt5.QtGui import QPalette, QColor
        palette = self.panel.palette()
        palette.setColor(QPalette.Window, QColor("#1e1e1e"))
        palette.setColor(QPalette.WindowText, QColor("#ffffff"))
        self.panel.setPalette(palette)

    def _position_panel_below_tray_icon(self):
        """Position the panel below the tray icon."""
        if not self.panel or not self.tray_icon:
            return

        # Get tray icon geometry
        tray_geometry = self.tray_icon.geometry()
        gap_below = 4

        # Calculate panel position
        panel_x = tray_geometry.center().x() - (self.panel_width // 2)
        panel_y = tray_geometry.bottom() + gap_below

        self.panel.move(panel_x, panel_y)

    def _install_click_outside_monitor(self):
        """Install click-outside monitor to dismiss panel."""
        self._remove_click_outside_monitor()

        self.click_outside_timer = QTimer()
        self.click_outside_timer.setSingleShot(True)
        self.click_outside_timer.timeout.connect(self._check_click_outside)

        # Start checking after a delay
        self.click_outside_timer.start(300)

    def _check_click_outside(self):
        """Check if user clicked outside the panel."""
        if not self.panel or not self.panel.isVisible():
            return

        # Get current mouse position
        mouse_pos = QCursor.pos()
        panel_rect = self.panel.geometry()

        # If click is outside panel, dismiss it
        if not panel_rect.contains(mouse_pos):
            # Don't dismiss if permissions not granted (onboarding)
            if not self.companion_manager.all_permissions_granted:
                return
            self.hide_panel()

    def _remove_click_outside_monitor(self):
        """Remove click-outside monitor."""
        if self.click_outside_timer:
            self.click_outside_timer.stop()
            self.click_outside_timer = None

    def show_tray_icon(self):
        """Show the system tray icon."""
        if self.tray_icon:
            self.tray_icon.show()

    def hide_tray_icon(self):
        """Hide the system tray icon."""
        if self.tray_icon:
            self.tray_icon.hide()

    def _on_quit(self):
        """Handle quit action."""
        self.panel_dismissed.emit()
