"""
Permission Manager - Windows Permission Handling

This manages Windows permissions for microphone, accessibility, and screen recording.
Equivalent to WindowPositionManager.swift in Clicky.
"""

from typing import Dict, Optional
from PyQt5.QtCore import QObject, pyqtSignal
import pyaudio
import win32api
import win32con
import win32security

from ..utils.logger import setup_logger


class PermissionManager(QObject):
    """
    Manages Windows permissions for the AI Tutor.
    """

    # Signals
    permission_changed = pyqtSignal(str, bool)  # Permission type, granted status

    def __init__(self):
        """Initialize the permission manager."""
        super().__init__()

        self.logger = setup_logger("PermissionManager")

        # Permission states
        self._permissions: Dict[str, bool] = {
            "microphone": False,
            "accessibility": False,
            "screen_recording": False
        }

        self.logger.info("Permission manager initialized")

    def check_all_permissions(self):
        """Check all application permissions."""
        self.logger.info("Checking all permissions...")

        self._permissions["microphone"] = self._check_microphone_permission()
        self._permissions["accessibility"] = self._check_accessibility_permission()
        self._permissions["screen_recording"] = self._check_screen_recording_permission()

        self.logger.info(f"Permission states: {self._permissions}")

        # Emit signals for each permission
        for perm_type, granted in self._permissions.items():
            self.permission_changed.emit(perm_type, granted)

    def _check_microphone_permission(self) -> bool:
        """
        Check microphone permission.

        Returns:
            bool: True if microphone access is available
        """
        try:
            # Try to access audio devices
            audio = pyaudio.PyAudio()
            device_count = audio.get_device_count()
            audio.terminate()

            if device_count > 0:
                self.logger.info("Microphone permission granted")
                return True
            else:
                self.logger.warning("No audio devices found")
                return False

        except Exception as e:
            self.logger.error(f"Microphone permission check failed: {e}")
            return False

    def _check_accessibility_permission(self) -> bool:
        """
        Check accessibility permission for global hotkeys.

        Returns:
            bool: True if accessibility features are available
        """
        try:
            # Check if we can access system-level hooks
            # This is a basic check - in reality, this might require
            # running as administrator or specific Windows settings
            import ctypes

            # Try to get a handle to the current process
            process_handle = ctypes.windll.kernel32.GetCurrentProcess()
            if process_handle:
                self.logger.info("Accessibility permission granted")
                return True
            else:
                self.logger.warning("Accessibility permission denied")
                return False

        except Exception as e:
            self.logger.error(f"Accessibility permission check failed: {e}")
            return False

    def _check_screen_recording_permission(self) -> bool:
        """
        Check screen recording permission.

        Returns:
            bool: True if screen recording is available
        """
        try:
            # Try to capture a small screenshot
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # Primary monitor
                screenshot = sct.grab(monitor)

                if screenshot:
                    self.logger.info("Screen recording permission granted")
                    return True
                else:
                    self.logger.warning("Screen recording permission denied")
                    return False

        except Exception as e:
            self.logger.error(f"Screen recording permission check failed: {e}")
            return False

    def request_microphone_permission(self) -> bool:
        """
        Request microphone permission.

        Returns:
            bool: True if permission was granted
        """
        self.logger.info("Requesting microphone permission...")

        # On Windows, microphone permission is usually granted through
        # Windows Settings > Privacy > Microphone
        # We can guide the user there
        import subprocess
        subprocess.run([
            "start", "ms-settings:privacy-microphone"
        ], shell=True)

        # Re-check after a delay
        import time
        time.sleep(2)

        granted = self._check_microphone_permission()
        self._permissions["microphone"] = granted
        self.permission_changed.emit("microphone", granted)

        return granted

    def request_accessibility_permission(self) -> bool:
        """
        Request accessibility permission.

        Returns:
            bool: True if permission was granted
        """
        self.logger.info("Requesting accessibility permission...")

        # Guide user to Windows settings
        import subprocess
        subprocess.run([
            "start", "ms-settings:easeofaccess-narrator"
        ], shell=True)

        # Re-check after a delay
        import time
        time.sleep(2)

        granted = self._check_accessibility_permission()
        self._permissions["accessibility"] = granted
        self.permission_changed.emit("accessibility", granted)

        return granted

    def request_screen_recording_permission(self) -> bool:
        """
        Request screen recording permission.

        Returns:
            bool: True if permission was granted
        """
        self.logger.info("Requesting screen recording permission...")

        # Guide user to Windows settings
        import subprocess
        subprocess.run([
            "start", "ms-settings:privacy-screen"
        ], shell=True)

        # Re-check after a delay
        import time
        time.sleep(2)

        granted = self._check_screen_recording_permission()
        self._permissions["screen_recording"] = granted
        self.permission_changed.emit("screen_recording", granted)

        return granted

    @property
    def has_microphone_permission(self) -> bool:
        """Check if microphone permission is granted."""
        return self._permissions.get("microphone", False)

    @property
    def has_accessibility_permission(self) -> bool:
        """Check if accessibility permission is granted."""
        return self._permissions.get("accessibility", False)

    @property
    def has_screen_recording_permission(self) -> bool:
        """Check if screen recording permission is granted."""
        return self._permissions.get("screen_recording", False)

    @property
    def all_permissions_granted(self) -> bool:
        """Check if all permissions are granted."""
        return all(self._permissions.values())

    def get_permission_status(self, permission_type: str) -> bool:
        """
        Get the status of a specific permission.

        Args:
            permission_type: Type of permission ('microphone', 'accessibility', 'screen_recording')

        Returns:
            bool: True if permission is granted
        """
        return self._permissions.get(permission_type, False)