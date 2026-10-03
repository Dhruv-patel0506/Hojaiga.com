"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 30 Enhancement
Name: Predictive UWP App Pre-launcher

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e;stroke:#333;stroke-width:2px;color:#d4d4d4;
    classDef component fill:#2d2d2d;stroke:#569cd6;stroke-width:2px;color:#d4d4d4;
    
    PRELAUNCH[Predictive Pre-launcher]
    
    PRELAUNCH --> PATTERN[Pattern Analyzer]
    
    PRELAUNCH --> CACHE[App Cache]
    
    PRELAUNCH --> READY[Readiness Poller]
    
    PRELAUNCH --> LAUNCHER[Smart Launcher]
    
    class PRELAUNCH component
    class PATTERN component
    class CACHE component
    class READY component
    class LAUNCHER component
```

Inputs: Task commands, app requests
Outputs: Pre-launched apps, reduced launch latency
Dependencies: typing, logging, subprocess, ctypes...
"""

from __future__ import annotations

import logging
import time
import subprocess
import threading
import ctypes
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger("hojaiga.organ30.predictive_prelaunch")


class AppState(str, Enum):
    """State of an application in the pre-launch system."""
    NOT_LAUNCHED = "not_launched"
    PRE_LAUNCHING = "pre_launching"
    PRE_LAUNCHED = "pre_launched"
    LAUNCHING = "launching"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class AppMetadata:
    """Metadata for an application."""
    name: str
    executable_path: str
    app_user_model_id: Optional[str] = None  # For UWP apps
    is_uwp: bool = False
    typical_launch_time_sec: float = 3.0
    window_class: Optional[str] = None
    process_name: Optional[str] = None
    state: AppState = AppState.NOT_LAUNCHED
    hwnd: Optional[int] = None
    pre_launched_at: float = 0.0
    last_used: float = 0.0
    usage_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "executable_path": self.executable_path,
            "app_user_model_id": self.app_user_model_id,
            "is_uwp": self.is_uwp,
            "typical_launch_time_sec": self.typical_launch_time_sec,
            "window_class": self.window_class,
            "process_name": self.process_name,
            "state": self.state.value,
            "hwnd": self.hwnd,
            "pre_launched_at": self.pre_launched_at,
            "last_used": self.last_used,
            "usage_count": self.usage_count
        }


@dataclass
class LaunchPattern:
    """Pattern for predicting when to pre-launch an app."""
    app_name: str
    trigger_keywords: List[str]
    confidence: float
    min_pre_launch_delay: float = 1.0


class PredictivePreLauncher:
    """
    Predictive pre-launcher that reduces UWP app launch latency by:
    - Analyzing command patterns to predict app usage
    - Pre-launching apps in background
    - Polling for window readiness
    - Maintaining app metadata cache
    """
    
    def __init__(self):
        self._apps: Dict[str, AppMetadata] = {}
        self._patterns: List[LaunchPattern] = []
        self._pre_launch_queue: List[str] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cache_file = "D:\\new_automation\\app_prelaunch_cache.json"
        
        # Initialize common UWP apps
        self._initialize_uwp_apps()
        
        # Initialize launch patterns
        self._initialize_patterns()
        
        # Load cache
        self._load_cache()
    
    def _initialize_uwp_apps(self) -> None:
        """Initialize common UWP applications."""
        # Windows Calculator
        self._apps["calculator"] = AppMetadata(
            name="calculator",
            executable_path="calc.exe",
            app_user_model_id="Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
            is_uwp=True,
            typical_launch_time_sec=3.5,
            window_class="Windows.UI.Core.CoreWindow",
            process_name="CalculatorApp.exe"
        )
        
        # Windows Notepad
        self._apps["notepad"] = AppMetadata(
            name="notepad",
            executable_path="notepad.exe",
            app_user_model_id="Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
            is_uwp=True,
            typical_launch_time_sec=2.5,
            window_class="Windows.UI.Core.CoreWindow",
            process_name="Notepad.exe"
        )
        
        # Windows Settings
        self._apps["settings"] = AppMetadata(
            name="settings",
            executable_path="ms-settings:",
            app_user_model_id="windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows.immersivecontrolpanel",
            is_uwp=True,
            typical_launch_time_sec=4.0,
            window_class="Windows.UI.Core.CoreWindow",
            process_name="SystemSettings.exe"
        )
        
        # Other common apps
        self._apps["excel"] = AppMetadata(
            name="excel",
            executable_path="excel.exe",
            is_uwp=False,
            typical_launch_time_sec=2.0,
            process_name="EXCEL.EXE"
        )
        
        self._apps["word"] = AppMetadata(
            name="word",
            executable_path="winword.exe",
            is_uwp=False,
            typical_launch_time_sec=2.0,
            process_name="WINWORD.EXE"
        )
        
        logger.info(f"[Pre-launch] Initialized {len(self._apps)} apps")
    
    def _initialize_patterns(self) -> None:
        """Initialize launch patterns for prediction."""
        self._patterns = [
            LaunchPattern(
                app_name="calculator",
                trigger_keywords=["calculate", "math", "compute", "add", "subtract", "multiply", "divide", "formula"],
                confidence=0.9
            ),
            LaunchPattern(
                app_name="notepad",
                trigger_keywords=["note", "text", "write", "document", "type", "editor"],
                confidence=0.85
            ),
            LaunchPattern(
                app_name="settings",
                trigger_keywords=["setting", "configure", "option", "preference", "system"],
                confidence=0.8
            ),
            LaunchPattern(
                app_name="excel",
                trigger_keywords=["spreadsheet", "excel", "data", "table", "chart"],
                confidence=0.85
            ),
            LaunchPattern(
                app_name="word",
                trigger_keywords=["document", "word", "report", "letter", "text"],
                confidence=0.85
            )
        ]
        
        logger.info(f"[Pre-launch] Initialized {len(self._patterns)} launch patterns")
    
    def start(self) -> None:
        """Start the predictive pre-launcher daemon."""
        if self._running:
            logger.info("[Pre-launch] Already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="prelaunch-daemon")
        self._thread.start()
        logger.info("[Pre-launch] Daemon started")
    
    def stop(self) -> None:
        """Stop the predictive pre-launcher daemon."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("[Pre-launch] Daemon stopped")
    
    def analyze_command(self, command: str) -> Optional[str]:
        """
        Analyze a command to predict which app will be needed.
        
        Args:
            command: Natural language command
        
        Returns:
            App name if prediction found, None otherwise
        """
        command_lower = command.lower()
        
        for pattern in self._patterns:
            for keyword in pattern.trigger_keywords:
                if keyword in command_lower:
                    logger.info(f"[Pre-launch] Predicted app '{pattern.app_name}' from keyword '{keyword}' (confidence: {pattern.confidence})")
                    return pattern.app_name
        
        return None
    
    def pre_launch_app(self, app_name: str, force: bool = False) -> bool:
        """
        Pre-launch an application in the background.
        
        Args:
            app_name: Name of the app to pre-launch
            force: Force pre-launch even if already running
        
        Returns:
            True if pre-launch successful, False otherwise
        """
        if app_name not in self._apps:
            logger.warning(f"[Pre-launch] Unknown app: {app_name}")
            return False
        
        app = self._apps[app_name]
        
        # Check if already running
        if not force and app.state == AppState.RUNNING:
            logger.info(f"[Pre-launch] App {app_name} already running")
            return True
        
        # Check if already pre-launched
        if not force and app.state == AppState.PRE_LAUNCHED:
            age = time.time() - app.pre_launched_at
            if age < 300:  # 5 minutes
                logger.info(f"[Pre-launch] App {app_name} already pre-launched ({age:.0f}s ago)")
                return True
        
        # Perform pre-launch
        app.state = AppState.PRE_LAUNCHING
        
        try:
            if app.is_uwp:
                success = self._pre_launch_uwp(app)
            else:
                success = self._pre_launch_win32(app)
            
            if success:
                app.state = AppState.PRE_LAUNCHED
                app.pre_launched_at = time.time()
                logger.info(f"[Pre-launch] Successfully pre-launched: {app_name}")
                
                # Save cache
                self._save_cache()
                
                return True
            else:
                app.state = AppState.ERROR
                logger.error(f"[Pre-launch] Failed to pre-launch: {app_name}")
                return False
                
        except Exception as e:
            app.state = AppState.ERROR
            logger.error(f"[Pre-launch] Pre-launch error for {app_name}: {e}")
            return False
    
    def _pre_launch_uwp(self, app: AppMetadata) -> bool:
        """Pre-launch a UWP application."""
        try:
            if app.app_user_model_id:
                # Use Windows.ApplicationModel APIs via PowerShell
                ps_cmd = f'Start-Process "shell:AppsFolder\\{app.app_user_model_id}" -WindowStyle Hidden'
                subprocess.run(["powershell", "-Command", ps_cmd], 
                             capture_output=True, timeout=10, check=True)
                return True
            elif app.executable_path.startswith("ms-settings:"):
                # For settings, we can't truly pre-launch, but we can reduce delay
                # by spawning a hidden shell
                subprocess.run(["start", "ms-settings:"], shell=True, 
                             capture_output=True, timeout=5)
                return True
            else:
                logger.warning(f"[Pre-launch] No AUMID for UWP app: {app.name}")
                return False
                
        except Exception as e:
            logger.error(f"[Pre-launch] UWP pre-launch failed: {e}")
            return False
    
    def _pre_launch_win32(self, app: AppMetadata) -> bool:
        """Pre-launch a Win32 application."""
        try:
            # Launch with minimized window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 2  # SW_MINIMIZE
            
            subprocess.Popen([app.executable_path], 
                           startupinfo=startupinfo,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            
            return True
            
        except Exception as e:
            logger.error(f"[Pre-launch] Win32 pre-launch failed: {e}")
            return False
    
    def wait_for_readiness(self, app_name: str, timeout_sec: float = 10.0) -> bool:
        """
        Wait for an app to become ready (window created and responsive).
        
        Args:
            app_name: Name of the app
            timeout_sec: Maximum time to wait
        
        Returns:
            True if app is ready, False if timeout
        """
        if app_name not in self._apps:
            return False
        
        app = self._apps[app_name]
        start_time = time.time()
        
        logger.info(f"[Pre-launch] Waiting for {app_name} readiness (timeout: {timeout_sec}s)")
        
        while time.time() - start_time < timeout_sec:
            # Check if window exists
            hwnd = self._find_app_window(app)
            if hwnd:
                app.hwnd = hwnd
                app.state = AppState.RUNNING
                app.last_used = time.time()
                app.usage_count += 1
                logger.info(f"[Pre-launch] {app_name} is ready (found hwnd: {hwnd})")
                return True
            
            time.sleep(0.1)
        
        logger.warning(f"[Pre-launch] {app_name} readiness timeout after {timeout_sec}s")
        return False
    
    def _find_app_window(self, app: AppMetadata) -> Optional[int]:
        """Find the window for an application."""
        try:
            # Use Win32 to find window by class name or process name
            if app.window_class:
                hwnd = ctypes.windll.user32.FindWindowW(app.window_class, None)
                if hwnd:
                    return hwnd
            
            if app.process_name:
                # Enumerate windows to find matching process
                def enum_callback(hwnd, lParam):
                    _, pid = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
                    try:
                        handle = ctypes.windll.kernel32.OpenProcess(0x0410, False, pid)
                        if handle:
                            name_buf = ctypes.create_unicode_buffer(260)
                            ctypes.windll.psapi.GetModuleBaseNameW(handle, 0, name_buf, 260)
                            ctypes.windll.kernel32.CloseHandle(handle)
                            if app.process_name.lower() in name_buf.value.lower():
                                return hwnd
                    except Exception:
                        pass
                    return 0
                
                # Would need proper callback setup, simplified here
                pass
            
            return None
            
        except Exception as e:
            logger.error(f"[Pre-launch] Window finding failed: {e}")
            return None
    
    def mark_app_used(self, app_name: str) -> None:
        """Mark an app as used, updating statistics."""
        if app_name in self._apps:
            app = self._apps[app_name]
            app.last_used = time.time()
            app.usage_count += 1
            logger.debug(f"[Pre-launch] Marked {app_name} as used (count: {app.usage_count})")
    
    def _loop(self) -> None:
        """Background daemon loop."""
        logger.info("[Pre-launch] Background loop started")
        
        while self._running:
            try:
                time.sleep(1.0)
                
                # Process pre-launch queue
                if self._pre_launch_queue:
                    app_name = self._pre_launch_queue.pop(0)
                    self.pre_launch_app(app_name)
                
                # Clean up old pre-launched apps
                self._cleanup_old_prelaunches()
                
            except Exception as e:
                logger.error(f"[Pre-launch] Loop error: {e}")
        
        logger.info("[Pre-launch] Background loop stopped")
    
    def _cleanup_old_prelaunches(self) -> None:
        """Clean up pre-launched apps that haven't been used."""
        current_time = time.time()
        max_age = 600  # 10 minutes
        
        for app_name, app in self._apps.items():
            if app.state == AppState.PRE_LAUNCHED:
                age = current_time - app.pre_launched_at
                if age > max_age:
                    logger.info(f"[Pre-launch] Cleaning up old pre-launch: {app_name} (age: {age:.0f}s)")
                    # Mark as not launched (we don't actually close it to avoid disturbing user)
                    app.state = AppState.NOT_LAUNCHED
    
    def _load_cache(self) -> None:
        """Load app metadata from cache file."""
        try:
            if not self._cache_file:
                return
            
            with open(self._cache_file, 'r') as f:
                data = json.load(f)
                
            for app_name, app_data in data.items():
                if app_name in self._apps:
                    app = self._apps[app_name]
                    app.state = AppState(app_data.get("state", AppState.NOT_LAUNCHED.value))
                    app.last_used = app_data.get("last_used", 0.0)
                    app.usage_count = app_data.get("usage_count", 0)
            
            logger.info(f"[Pre-launch] Loaded cache from {self._cache_file}")
            
        except Exception as e:
            logger.warning(f"[Pre-launch] Failed to load cache: {e}")
    
    def _save_cache(self) -> None:
        """Save app metadata to cache file."""
        try:
            if not self._cache_file:
                return
            
            data = {
                name: app.to_dict()
                for name, app in self._apps.items()
            }
            
            with open(self._cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"[Pre-launch] Saved cache to {self._cache_file}")
            
        except Exception as e:
            logger.warning(f"[Pre-launch] Failed to save cache: {e}")
    
    def get_app_status(self, app_name: str) -> Optional[AppMetadata]:
        """Get the current status of an app."""
        return self._apps.get(app_name)
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all apps."""
        return {
            name: app.to_dict()
            for name, app in self._apps.items()
        }


# Singleton instance
_prelauncher_instance: Optional[PredictivePreLauncher] = None

def get_prelauncher() -> PredictivePreLauncher:
    """Get the singleton pre-launcher instance."""
    global _prelauncher_instance
    if _prelauncher_instance is None:
        _prelauncher_instance = PredictivePreLauncher()
    return _prelauncher_instance


def predict_and_prelaunch(command: str) -> Optional[str]:
    """
    Convenience function to predict and pre-launch an app from a command.
    
    Args:
        command: Natural language command
    
    Returns:
        App name if prediction found and pre-launched, None otherwise
    """
    prelauncher = get_prelauncher()
    app_name = prelauncher.analyze_command(command)
    
    if app_name:
        prelauncher.pre_launch_app(app_name)
        return app_name
    
    return None
