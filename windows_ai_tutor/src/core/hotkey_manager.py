"""
Hotkey Manager - Global Hotkey Detection

This manages global keyboard shortcuts for push-to-talk functionality.
Equivalent to GlobalPushToTalkShortcutMonitor.swift in Clicky.
"""

from typing import Optional
from PyQt5.QtCore import QObject, pyqtSignal
import keyboard
import threading

from ..utils.logger import setup_logger


class HotkeyManager(QObject):
    """
    Manages global hotkey detection for push-to-talk functionality.
    Uses the keyboard library for cross-platform hotkey detection.
    """

    # Signals
    hotkey_pressed = pyqtSignal()
    hotkey_released = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self):
        """Initialize the hotkey manager."""
        super().__init__()

        self.logger = setup_logger("HotkeyManager")

        # Hotkey configuration (Ctrl+Alt by default)
        self.hotkey = 'ctrl+alt'

        # Hotkey state
        self._is_hotkey_pressed = False
        self._is_monitoring = False

        # Keyboard hook
        self._keyboard_hook = None

        self.logger.info(f"Hotkey manager initialized with hotkey: {self.hotkey}")

    def set_hotkey(self, hotkey: str):
        """
        Set the hotkey combination.

        Args:
            hotkey: Hotkey combination (e.g., 'ctrl+alt', 'ctrl+shift')
        """
        self.hotkey = hotkey
        self.logger.info(f"Hotkey changed to: {hotkey}")

    def start(self):
        """Start monitoring for hotkey presses."""
        if self._is_monitoring:
            self.logger.warning("Hotkey monitoring already active")
            return

        try:
            # Add hotkey listener
            keyboard.add_hotkey(
                self.hotkey,
                self._on_hotkey_press,
                args=('press',)
            )

            # Add hotkey release listener
            keyboard.hook(self._on_keyboard_event)

            self._is_monitoring = True
            self.logger.info(f"Hotkey monitoring started for: {self.hotkey}")

        except Exception as e:
            self.logger.error(f"Failed to start hotkey monitoring: {e}")
            self.error_occurred.emit(f"Failed to start hotkey monitoring: {str(e)}")

    def stop(self):
        """Stop monitoring for hotkey presses."""
        if not self._is_monitoring:
            return

        try:
            # Remove hotkey listener
            keyboard.remove_hotkey(self.hotkey)

            # Remove keyboard hook
            keyboard.unhook_all()

            self._is_monitoring = False
            self._is_hotkey_pressed = False
            self.logger.info("Hotkey monitoring stopped")

        except Exception as e:
            self.logger.error(f"Failed to stop hotkey monitoring: {e}")
            self.error_occurred.emit(f"Failed to stop hotkey monitoring: {str(e)}")

    def _on_hotkey_press(self, event_type: str):
        """
        Handle hotkey press event.

        Args:
            event_type: Type of event ('press' or 'release')
        """
        if event_type == 'press' and not self._is_hotkey_pressed:
            self._is_hotkey_pressed = True
            self.logger.debug("Hotkey pressed")
            self.hotkey_pressed.emit()

    def _on_keyboard_event(self, event):
        """
        Handle keyboard events for hotkey release detection.

        Args:
            event: Keyboard event
        """
        # Check if the hotkey keys are released
        if self._is_hotkey_pressed:
            # Check if all hotkey keys are released
            if not keyboard.is_pressed(self.hotkey):
                self._is_hotkey_pressed = False
                self.logger.debug("Hotkey released")
                self.hotkey_released.emit()

    @property
    def is_monitoring(self) -> bool:
        """Check if hotkey monitoring is active."""
        return self._is_monitoring

    @property
    def is_hotkey_pressed(self) -> bool:
        """Check if hotkey is currently pressed."""
        return self._is_hotkey_pressed