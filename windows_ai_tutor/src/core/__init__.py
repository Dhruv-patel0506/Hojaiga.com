"""
Core components for Windows AI Tutor
"""

from .app import WindowsAITutor
from .state_manager import StateManager
from .tray_manager import TrayManager
from .hotkey_manager import HotkeyManager
from .permission_manager import PermissionManager

__all__ = [
    'WindowsAITutor',
    'StateManager',
    'TrayManager',
    'HotkeyManager',
    'PermissionManager'
]