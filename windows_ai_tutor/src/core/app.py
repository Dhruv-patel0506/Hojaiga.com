"""
Windows AI Tutor - Main Application Entry Point

This is the main entry point for the Windows AI Tutor application.
It initializes all core components and starts the system tray application.
"""

import sys
import asyncio
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from .state_manager import StateManager
from .tray_manager import TrayManager
from .hotkey_manager import HotkeyManager
from .permission_manager import PermissionManager
from ..utils.logger import setup_logger
from ..utils.config import ConfigManager


class WindowsAITutor:
    """
    Main application class that coordinates all components.
    Equivalent to leanring_buddyApp.swift in Clicky.
    """

    def __init__(self):
        """Initialize the Windows AI Tutor application."""
        # Set up logging
        self.logger = setup_logger("WindowsAITutor")
        self.logger.info("Starting Windows AI Tutor...")

        # Initialize Qt application
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)  # Don't quit when tray closes

        # Initialize configuration
        self.config_manager = ConfigManager()
        self.logger.info("Configuration loaded")

        # Initialize core components
        self.state_manager = StateManager(self.config_manager)
        self.permission_manager = PermissionManager()
        self.hotkey_manager = HotkeyManager()
        self.tray_manager = TrayManager(self.state_manager)

        # Connect components
        self._connect_components()

        self.logger.info("All components initialized")

    def _connect_components(self):
        """Connect signals and slots between components."""
        # Connect hotkey events to state manager
        self.hotkey_manager.hotkey_pressed.connect(
            self.state_manager.on_hotkey_pressed
        )
        self.hotkey_manager.hotkey_released.connect(
            self.state_manager.on_hotkey_released
        )

        # Connect state changes to tray manager
        self.state_manager.state_changed.connect(
            self.tray_manager.on_state_changed
        )

        self.logger.info("Component signals connected")

    def start(self):
        """Start the application."""
        self.logger.info("Starting application...")

        # Check permissions
        self.permission_manager.check_all_permissions()

        # Start hotkey monitoring
        if self.permission_manager.has_accessibility_permission:
            self.hotkey_manager.start()
            self.logger.info("Hotkey monitoring started")
        else:
            self.logger.warning("Accessibility permission not granted, hotkeys disabled")

        # Show tray icon
        self.tray_manager.show()

        # Show control panel immediately (so you can see the app)
        self.tray_manager.show_control_panel()

        self.logger.info("Application started successfully")

    def run(self):
        """Run the Qt event loop."""
        self.logger.info("Entering main event loop")
        return self.qt_app.exec_()

    def shutdown(self):
        """Clean shutdown of all components."""
        self.logger.info("Shutting down application...")

        # Stop hotkey monitoring
        self.hotkey_manager.stop()

        # Cleanup state manager
        self.state_manager.shutdown()

        # Hide tray
        self.tray_manager.hide()

        self.logger.info("Application shutdown complete")


def main():
    """Main entry point."""
    try:
        app = WindowsAITutor()
        app.start()
        exit_code = app.run()
        app.shutdown()
        sys.exit(exit_code)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()