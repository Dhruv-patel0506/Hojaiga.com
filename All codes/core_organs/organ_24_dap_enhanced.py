"""
Organ 24 Enhanced — Desktop Automation Protocol (DAP) with Multi-Session Support

This is an enhanced version of DAP that adds:
- Session multiplexing (multiple apps simultaneously)
- Session routing (switch between apps)
- Parallel execution (work in multiple apps at once)
- Copy-paste-free (direct data transfer between sessions)
- State synchronization (unified state across apps)

This brings DAP to parity with CDP's multi-tab capabilities.
"""

import asyncio
import ctypes
import dataclasses
import enum
import json
import logging
import platform
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

logger = logging.getLogger("hojaiga.organ24_enhanced")

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import ctypes.wintypes as wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)


@dataclass
class DAPSession:
    """Represents a single app session (like CDP session)."""
    session_id: str
    hwnd: int
    process_id: int
    app_name: str
    window_title: str
    tree_state: Dict[str, Any] = field(default_factory=dict)
    input_state: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    is_focused: bool = False
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "hwnd": self.hwnd,
            "process_id": self.process_id,
            "app_name": self.app_name,
            "window_title": self.window_title,
            "is_active": self.is_active,
            "is_focused": self.is_focused,
            "created_at": self.created_at,
            "last_active": self.last_active,
        }


class DAPSessionManager:
    """Manages multiple app sessions (CDP-style)."""

    def __init__(self):
        self._sessions: Dict[str, DAPSession] = {}
        self._active_session_id: Optional[str] = None
        self._session_counter = 0
        self._lock = threading.Lock()

    def create_session(self, hwnd: int, app_name: str) -> str:
        """Create a new session for an app."""
        with self._lock:
            session_id = f"dap_session_{self._session_counter}"
            self._session_counter += 1

            pid = self._get_process_id(hwnd)
            window_title = self._get_window_title(hwnd)

            session = DAPSession(
                session_id=session_id,
                hwnd=hwnd,
                process_id=pid,
                app_name=app_name,
                window_title=window_title,
                tree_state={},
                input_state={}
            )

            self._sessions[session_id] = session
            logger.info(f"[DAPSessionManager] Created session {session_id} for {app_name}")
            return session_id

    def get_session(self, session_id: str) -> Optional[DAPSession]:
        """Get a session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def get_active_session(self) -> Optional[DAPSession]:
        """Get the currently active session."""
        with self._lock:
            if self._active_session_id:
                return self._sessions.get(self._active_session_id)
            return None

    def switch_session(self, session_id: str) -> bool:
        """Switch active session (focus app)."""
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                logger.warning(f"[DAPSessionManager] Session {session_id} not found")
                return False

            # Focus the window
            success = self._focus_window(session.hwnd)
            if not success:
                logger.warning(f"[DAPSessionManager] Failed to focus window for session {session_id}")
                return False

            # Update active session
            self._active_session_id = session_id
            session.last_active = time.time()

            # Update focus states
            for sid, s in self._sessions.items():
                s.is_focused = (sid == session_id)

            logger.info(f"[DAPSessionManager] Switched to session {session_id} ({session.app_name})")
            return True

    def close_session(self, session_id: str) -> bool:
        """Close a session."""
        with self._lock:
            if session_id not in self._sessions:
                return False

            session = self._sessions[session_id]
            logger.info(f"[DAPSessionManager] Closing session {session_id} ({session.app_name})")

            del self._sessions[session_id]

            if self._active_session_id == session_id:
                self._active_session_id = None

            return True

    def list_sessions(self) -> List[DAPSession]:
        """List all active sessions."""
        with self._lock:
            return list(self._sessions.values())

    def get_session_by_app(self, app_name: str) -> Optional[DAPSession]:
        """Get session by app name."""
        with self._lock:
            for session in self._sessions.values():
                if session.app_name.lower() == app_name.lower():
                    return session
            return None

    def _get_process_id(self, hwnd: int) -> int:
        """Get process ID from window handle."""
        if not IS_WINDOWS:
            return 0
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        return int(pid.value)

    def _get_window_title(self, hwnd: int) -> str:
        """Get window title."""
        if not IS_WINDOWS:
            return ""
        length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
        return buf.value

    def _focus_window(self, hwnd: int) -> bool:
        """Focus a window."""
        if not IS_WINDOWS:
            return False
        return bool(user32.SetForegroundWindow(ctypes.c_void_p(hwnd)))


class DirectDataTransfer:
    """Copy-paste-free data transfer between sessions."""

    def __init__(self, session_manager: DAPSessionManager):
        self.session_manager = session_manager
        self._transfer_buffer: Dict[str, Any] = {}

    async def transfer_text(self, from_session: str, to_session: str,
                          source_selector: str, target_selector: str) -> bool:
        """
        Transfer text directly between apps without clipboard.

        Args:
            from_session: Source session ID
            to_session: Target session ID
            source_selector: Source element selector
            target_selector: Target element selector
        """
        source_session = self.session_manager.get_session(from_session)
        if not source_session:
            logger.error(f"[DirectDataTransfer] Source session {from_session} not found")
            return False

        # Get text from source (simulated - would use UIA/Win32)
        text = await self._get_element_text(source_session, source_selector)
        if not text:
            logger.error(f"[DirectDataTransfer] Failed to get text from source")
            return False

        # Switch to target
        self.session_manager.switch_session(to_session)

        # Type text directly (no clipboard)
        target_session = self.session_manager.get_session(to_session)
        if not target_session:
            logger.error(f"[DirectDataTransfer] Target session {to_session} not found")
            return False

        success = await self._type_into_element(target_session, target_selector, text)
        if success:
            logger.info(f"[DirectDataTransfer] Transferred text from {from_session} to {to_session}")

        return success

    async def transfer_data(self, from_session: str, to_session: str,
                          data: Any) -> bool:
        """Transfer structured data between sessions."""
        self._transfer_buffer[to_session] = {
            "from_session": from_session,
            "data": data,
            "timestamp": time.time()
        }
        logger.info(f"[DirectDataTransfer] Buffered data from {from_session} to {to_session}")
        return True

    async def retrieve_data(self, session_id: str) -> Optional[Any]:
        """Retrieve buffered data for a session."""
        if session_id in self._transfer_buffer:
            return self._transfer_buffer[session_id]["data"]
        return None

    async def _get_element_text(self, session: DAPSession, selector: str) -> Optional[str]:
        """Get text from element in session (placeholder implementation)."""
        # TODO: Implement using UIA/Win32
        logger.debug(f"[DirectDataTransfer] Getting text from {selector} in session {session.session_id}")
        return "Sample text"  # Placeholder

    async def _type_into_element(self, session: DAPSession, selector: str, text: str) -> bool:
        """Type text into element without clipboard (placeholder implementation)."""
        # TODO: Implement using SendInput
        logger.debug(f"[DirectDataTransfer] Typing into {selector} in session {session.session_id}")
        return True  # Placeholder


class ParallelExecutionEngine:
    """Execute tasks in parallel across multiple sessions."""

    def __init__(self, session_manager: DAPSessionManager):
        self.session_manager = session_manager
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def execute_parallel(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute tasks in parallel across multiple sessions.

        Args:
            tasks: List of task dicts with session_id and action
        """
        results = []

        async def execute_single_task(task):
            session_id = task["session_id"]
            action = task["action"]
            params = task.get("params", {})

            # Switch to session
            self.session_manager.switch_session(session_id)

            # Execute action
            try:
                result = await self._execute_action(session_id, action, params)
                return {"session_id": session_id, "result": result, "success": True}
            except Exception as e:
                logger.error(f"[ParallelExecutionEngine] Task failed for {session_id}: {e}")
                return {"session_id": session_id, "error": str(e), "success": False}

        # Run in parallel
        coroutines = [execute_single_task(task) for task in tasks]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        logger.info(f"[ParallelExecutionEngine] Executed {len(results)} parallel tasks")
        return results

    async def _execute_action(self, session_id: str, action: str, params: Dict[str, Any]) -> Any:
        """Execute a single action in a session (placeholder implementation)."""
        # TODO: Implement based on action type
        logger.debug(f"[ParallelExecutionEngine] Executing {action} on {session_id} with params {params}")
        return {"status": "completed"}  # Placeholder


class SmoothSwitchingOrchestrator:
    """Orchestrate smooth switching between apps."""

    def __init__(self, session_manager: DAPSessionManager):
        self.session_manager = session_manager
        self._switch_history: List[str] = []
        self._switch_cache: Dict[str, Any] = {}
        self._max_history = 10

    async def switch_with_state(self, from_session: str, to_session: str) -> bool:
        """
        Switch between apps while preserving state.

        Args:
            from_session: Current session
            to_session: Target session
        """
        # Save current state
        current_session = self.session_manager.get_session(from_session)
        if current_session:
            self._switch_cache[from_session] = {
                "hwnd": current_session.hwnd,
                "tree_state": current_session.tree_state.copy(),
                "input_state": current_session.input_state.copy(),
                "timestamp": time.time()
            }

        # Switch to target
        success = self.session_manager.switch_session(to_session)

        if success:
            # Restore target state
            target_session = self.session_manager.get_session(to_session)
            if to_session in self._switch_cache:
                cached = self._switch_cache[to_session]
                target_session.tree_state = cached["tree_state"]
                target_session.input_state = cached["input_state"]

            # Record switch
            self._switch_history.append(to_session)
            if len(self._switch_history) > self._max_history:
                self._switch_history.pop(0)

            logger.info(f"[SmoothSwitchingOrchestrator] Switched from {from_session} to {to_session}")

        return success

    async def quick_switch(self, session_id: str) -> bool:
        """Quick switch without full state restoration."""
        return self.session_manager.switch_session(session_id)

    async def switch_back(self) -> bool:
        """Switch back to previous session."""
        if len(self._switch_history) < 2:
            return False

        # Get previous session
        prev_session = self._switch_history[-2]
        current_session = self._switch_history[-1]

        return await self.switch_with_state(current_session, prev_session)

    def get_switch_history(self) -> List[str]:
        """Get switch history."""
        return self._switch_history.copy()


class DAPEnhancedRuntime:
    """Enhanced DAP runtime with multi-session support."""

    def __init__(self):
        self.session_manager = DAPSessionManager()
        self.data_transfer = DirectDataTransfer(self.session_manager)
        self.parallel_engine = ParallelExecutionEngine(self.session_manager)
        self.switch_orchestrator = SmoothSwitchingOrchestrator(self.session_manager)
        self._running = False

    async def start(self):
        """Start the enhanced DAP runtime."""
        self._running = True
        logger.info("[DAPEnhancedRuntime] Started")

    async def stop(self):
        """Stop the enhanced DAP runtime."""
        self._running = False
        # Close all sessions
        sessions = self.session_manager.list_sessions()
        for session in sessions:
            self.session_manager.close_session(session.session_id)
        logger.info("[DAPEnhancedRuntime] Stopped")

    async def create_app_session(self, app_name: str) -> str:
        """Create a new session for an app."""
        # Find window for app (placeholder - would use window enumeration)
        hwnd = self._find_app_window(app_name)
        if not hwnd:
            raise ValueError(f"App not found: {app_name}")

        # Create session
        session_id = self.session_manager.create_session(hwnd, app_name)
        return session_id

    async def switch_to_app(self, session_id: str) -> bool:
        """Switch to an app session."""
        current = self.session_manager.get_active_session()
        from_session = current.session_id if current else None

        if from_session == session_id:
            return True  # Already there

        return await self.switch_orchestrator.switch_with_state(from_session, session_id)

    async def transfer_between_apps(self, from_session: str, to_session: str,
                                   source: str, target: str) -> bool:
        """Transfer data between apps without clipboard."""
        return await self.data_transfer.transfer_text(from_session, to_session, source, target)

    async def execute_parallel_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute tasks in parallel across multiple apps."""
        return await self.parallel_engine.execute_parallel(tasks)

    def _find_app_window(self, app_name: str) -> Optional[int]:
        """Find window for app (placeholder implementation)."""
        # TODO: Implement using window enumeration
        logger.debug(f"[DAPEnhancedRuntime] Finding window for {app_name}")
        return 0  # Placeholder

    def get_status(self) -> Dict[str, Any]:
        """Get runtime status."""
        sessions = self.session_manager.list_sessions()
        return {
            "running": self._running,
            "session_count": len(sessions),
            "active_session": self.session_manager._active_session_id,
            "sessions": [s.to_dict() for s in sessions],
            "switch_history": self.switch_orchestrator.get_switch_history(),
        }
