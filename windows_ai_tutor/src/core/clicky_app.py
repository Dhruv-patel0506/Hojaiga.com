"""
Clicky App - Main Entry Point (Clicky-style)

Windows AI Tutor main application entry point.
Converted from leanring_buddyApp.swift to Windows Python.
Zero-window HUD with top status pill.
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from typing import Optional

from .companion_manager import CompanionManager
from .menu_bar_panel_manager import MenuBarPanelManager
from ..utils.config import ConfigManager
from ..utils.logger import setup_logger


class ClickyApp:
    """
    Main Windows AI Tutor application (Clicky-style).
    Zero-window HUD with system tray integration.
    """

    def __init__(self):
        """Initialize the Clicky application."""
        self.logger = setup_logger("ClickyApp")

        # Create Qt application
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)  # Don't quit when tray closes

        # Initialize configuration
        self.config_manager = ConfigManager()
        self.logger.info("Configuration loaded")

        # Initialize core components
        self.companion_manager = CompanionManager(self.config_manager)
        self.menu_bar_manager = MenuBarPanelManager(self.companion_manager)

        # Connect signals
        self._connect_signals()

        self.logger.info("Clicky app initialized")

    def _connect_signals(self):
        """Connect signals between components."""
        # Hotkey events
        from .hotkey_manager import HotkeyManager
        self.hotkey_manager = HotkeyManager()
        self.hotkey_manager.hotkey_pressed.connect(self.companion_manager.on_hotkey_pressed)
        self.hotkey_manager.hotkey_released.connect(self.companion_manager.on_hotkey_released)

        # Panel dismissal
        self.menu_bar_manager.panel_dismissed.connect(self._on_panel_dismissed)

    def _on_panel_dismissed(self):
        """Handle panel dismissal."""
        self.logger.info("Panel dismissed")

    def start(self):
        """Start the Clicky application."""
        self.logger.info("Starting Clicky application...")

        # Start companion manager
        self.companion_manager.start()

        # Start hotkey monitoring
        self.hotkey_manager.start()

        # Show tray icon
        self.menu_bar_manager.show_tray_icon()

        # Show panel on launch
        self.menu_bar_manager.show_panel_on_launch()

        self.logger.info("Clicky application started")

    def run(self):
        """Run the Qt event loop."""
        self.logger.info("Entering main event loop")
        return self.qt_app.exec_()

    def shutdown(self):
        """Clean shutdown of all components."""
        self.logger.info("Shutting down Clicky application...")

        # Stop components
        self.companion_manager.stop()
        self.hotkey_manager.stop()
        self.menu_bar_manager.hide_tray_icon()

        self.logger.info("Clicky application shut down")


def main():
    """Main entry point."""
    app = ClickyApp()
    app.start()
    exit_code = app.run()
    app.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
