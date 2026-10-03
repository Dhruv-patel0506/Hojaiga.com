"""
Global Push-to-Talk Shortcut Monitor - System-Wide Hotkey Detection (Clicky-style)

Captures push-to-talk keyboard shortcuts while app runs in background.
Uses keyboard library for Windows global hotkey detection.
Converted from GlobalPushToTalkShortcutMonitor.swift to Windows Python.
"""

from enum import Enum
from typing import Optional
from PyQt5.QtCore import QObject, pyqtSignal
import keyboard

from ..audio.buddy_dictation_manager import BuddyPushToTalkShortcut, ShortcutTransition
from ..utils.logger import setup_logger


class GlobalPushToTalkShortcutMonitor(QObject):
    """
    Global push-to-talk shortcut monitor.
    Detects Ctrl+Alt shortcuts system-wide using keyboard library.
    """

    # Signals
    shortcut_transition = pyqtSignal(ShortcutTransition)
    is_shortcut_currently_pressed = pyqtSignal(bool)

    def __init__(self):
        """Initialize the global shortcut monitor."""
        super().__init__()

        self.logger = setup_logger("GlobalPushToTalkShortcutMonitor")

        # Shortcut configuration
        self.current_shortcut = BuddyPushToTalkShortcut.CONTROL_OPTION
        self._is_shortcut_pressed = False
        self._last_trigger_time = 0
        self._debounce_ms = 500  # Debounce for 500ms to prevent spam

        # Hotkey state
        self._hotkey_active = False

        self.logger.info("Global push-to-talk shortcut monitor initialized")

    def start(self):
        """Start monitoring for the push-to-talk shortcut."""
        self.logger.info(f"Starting global shortcut monitor for: {self.current_shortcut.display_text()}")

        # Don't restart if already running
        if self._hotkey_active:
            return

        try:
            # Add hotkey listener for Ctrl+Alt
            keyboard.add_hotkey(
                "ctrl+alt",
                self._on_hotkey_press,
                args=('press',)
            )

            # Add hotkey release listener
            keyboard.hook(self._on_keyboard_event)

            self._hotkey_active = True
            self.logger.info("Global shortcut monitor started successfully")

        except Exception as e:
            self.logger.error(f"Failed to start global shortcut monitor: {e}")

    def stop(self):
        """Stop monitoring for the push-to-talk shortcut."""
        self.logger.info("Stopping global shortcut monitor...")

        self._is_shortcut_pressed = False
        self.is_shortcut_currently_pressed.emit(False)

        if self._hotkey_active:
            try:
                keyboard.remove_hotkey("ctrl+alt")
                keyboard.unhook_all()
                self._hotkey_active = False
                self.logger.info("Global shortcut monitor stopped")
            except Exception as e:
                self.logger.error(f"Failed to stop global shortcut monitor: {e}")

    def _on_hotkey_press(self, event_type: str):
        """Handle hotkey press event."""
        import time
        current_time = time.time() * 1000  # Convert to milliseconds

        # Debounce: ignore if triggered within 500ms of last trigger
        if current_time - self._last_trigger_time < self._debounce_ms:
            return

        self._last_trigger_time = current_time
        self.logger.info(f"Hotkey {event_type} (debounced)")

        if event_type == 'press':
            self._is_shortcut_pressed = True
            self.is_shortcut_currently_pressed.emit(True)
            self.shortcut_transition.emit(ShortcutTransition.PRESSED)
        elif event_type == 'release':
            self._is_shortcut_pressed = False
            self.is_shortcut_currently_pressed.emit(False)
            self.shortcut_transition.emit(ShortcutTransition.RELEASED)

    def _on_keyboard_event(self, event):
        """Handle keyboard events to detect hotkey release."""
        # Check if Ctrl+Alt keys are still pressed
        if keyboard.is_pressed('ctrl') and keyboard.is_pressed('alt'):
            # Still pressed
            if not self._is_shortcut_pressed:
                self._is_shortcut_pressed = True
                self.is_shortcut_currently_pressed.emit(True)
                self.shortcut_transition.emit(ShortcutTransition.PRESSED)
        else:
            # Released
            if self._is_shortcut_pressed:
                self._is_shortcut_pressed = False
                self.is_shortcut_currently_pressed.emit(False)
                self.shortcut_transition.emit(ShortcutTransition.RELEASED)

    def set_shortcut(self, shortcut: BuddyPushToTalkShortcut):
        """Set the push-to-talk shortcut."""
        self.logger.info(f"Setting shortcut to: {shortcut.value}")
        self.current_shortcut = shortcut
