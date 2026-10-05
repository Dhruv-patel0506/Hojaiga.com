"""
Enhanced Visual Cursor with Magnetic Attachment and Multi-Cursor Spawning

Features:
- Magnetic attachment to physical mouse when idle
- Detaches and works independently during automation
- Multiple independent cursor spawns for each tab/window/app
- Each cursor operates independently
- Physical mouse tracking via Windows API
"""

import threading
import time
import ctypes
import ctypes.wintypes as win32con
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

if True:
    try:
        _HAS_CTYPES = True
        _user32 = ctypes.windll.user32
        _kernel32 = ctypes.windll.kernel32
    except Exception:
        _HAS_CTYPES = False
        _user32 = None
        _kernel32 = None

logger = logging.getLogger("hojaiga.visual_cursor_enhanced")


class CursorState(Enum):
    """Cursor states."""
    IDLE = "idle"  # Attached to physical mouse
    ACTIVE = "active"  # Detached, working independently
    MOVING = "moving"  # Moving to target
    CLICKING = "clicking"  # Performing click
    BUFFERING = "buffering"  # Processing/rotating


@dataclass
class CursorInstance:
    """Independent cursor instance for a specific window/app."""
    cursor_id: str
    window_handle: int = 0
    window_title: str = ""
    x: float = 0.0
    y: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    state: CursorState = CursorState.IDLE
    rotation_angle: float = 0.0
    is_visible: bool = True
    color: int = 0x00FF00FF  # Bright green (BGR)
    is_attached_to_physical: bool = True  # Starts attached to physical mouse
    
    # Animation state
    click_animations: List[Dict] = field(default_factory=list)
    trail_points: List[Tuple[float, float, float]] = field(default_factory=list)
    
    # Movement
    move_speed: float = 22.0
    is_moving: bool = False


class EnhancedVisualCursor:
    """
    Enhanced visual cursor with magnetic attachment and multi-cursor spawning.
    
    Features:
    - Magnetic attachment to physical mouse when idle
    - Detaches and works independently during automation
    - Multiple independent cursor spawns for each tab/window/app
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *a, **kw):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance
    
    def _init(self):
        """Initialize enhanced cursor system."""
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Physical mouse tracking
        self._physical_mouse_x: float = 0.0
        self._physical_mouse_y: float = 0.0
        self._physical_mouse_tracking: bool = True
        self._last_physical_update: float = 0.0
        
        # Main cursor (attached to physical mouse when idle)
        self._main_cursor = CursorInstance(
            cursor_id="main",
            x=960.0,
            y=540.0,
            is_attached_to_physical=True
        )
        
        # Spawned cursors (independent)
        self._spawned_cursors: Dict[str, CursorInstance] = {}
        self._next_cursor_id: int = 1
        
        # Configuration
        self._magnetic_strength: float = 0.8  # How quickly it follows physical mouse
        self._detach_threshold: float = 0.1  # Distance threshold for detachment
        self._idle_timeout: float = 2.0  # Seconds before considered idle
        
        # Screen dimensions
        if _HAS_CTYPES:
            self._screen_w = _user32.GetSystemMetrics(0)
            self._screen_h = _user32.GetSystemMetrics(1)
        else:
            self._screen_w = 1920
            self._screen_h = 1080
        
        logger.info("[EnhancedCursor] Initialized with magnetic attachment and multi-cursor support")
    
    def start(self):
        """Start the enhanced cursor system."""
        if self._running:
            logger.warning("[EnhancedCursor] Already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._main_loop, daemon=True)
        self._thread.start()
        logger.info("[EnhancedCursor] Started enhanced cursor system")
    
    def stop(self):
        """Stop the enhanced cursor system."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("[EnhancedCursor] Stopped enhanced cursor system")
    
    def _main_loop(self):
        """Main loop for cursor management."""
        while self._running:
            loop_start = time.time()
            
            try:
                # Track physical mouse position
                self._track_physical_mouse()
                
                # Update main cursor (magnetic attachment when idle)
                self._update_main_cursor()
                
                # Update all spawned cursors (independent operation)
                self._update_spawned_cursors()
                
                # Render all cursors
                self._render_cursors()
                
            except Exception as e:
                logger.error(f"[EnhancedCursor] Main loop error: {e}")
            
            # Maintain ~60 FPS
            elapsed = time.time() - loop_start
            sleep_time = max(0, 1.0/60.0 - elapsed)
            time.sleep(sleep_time)
    
    def _track_physical_mouse(self):
        """Track physical mouse position using Windows API."""
        if not _HAS_CTYPES:
            return
        
        try:
            # Get physical mouse position
            point = win32con.POINT()
            _user32.GetCursorPos(ctypes.byref(point))
            
            self._physical_mouse_x = float(point.x)
            self._physical_mouse_y = float(point.y)
            self._last_physical_update = time.time()
            
        except Exception as e:
            logger.debug(f"[EnhancedCursor] Physical mouse tracking error: {e}")
    
    def _update_main_cursor(self):
        """Update main cursor with magnetic attachment logic."""
        cursor = self._main_cursor
        
        if cursor.is_attached_to_physical:
            # Magnetic attachment: follow physical mouse smoothly
            if time.time() - self._last_physical_update < 1.0:
                # Smooth magnetic follow
                dx = self._physical_mouse_x - cursor.x
                dy = self._physical_mouse_y - cursor.y
                
                cursor.x += dx * self._magnetic_strength * 0.1
                cursor.y += dy * self._magnetic_strength * 0.1
                
                cursor.state = CursorState.IDLE
                cursor.rotation_angle = 0.0  # No rotation when attached
            else:
                # Physical mouse tracking lost, stay in place
                cursor.state = CursorState.IDLE
        else:
            # Detached: move independently
            if cursor.is_moving:
                self._move_cursor_towards_target(cursor)
            
            # Rotation when buffering
            if cursor.state == CursorState.BUFFERING:
                cursor.rotation_angle = (cursor.rotation_angle + 180.0 * 0.016) % 360.0
            else:
                # Smoothly return to upright
                if abs(cursor.rotation_angle) > 1.0:
                    cursor.rotation_angle *= 0.9
                else:
                    cursor.rotation_angle = 0.0
    
    def _update_spawned_cursors(self):
        """Update all spawned cursors independently."""
        for cursor_id, cursor in self._spawned_cursors.items():
            # Spawned cursors are always independent
            if cursor.is_moving:
                self._move_cursor_towards_target(cursor)
            
            # Rotation when buffering
            if cursor.state == CursorState.BUFFERING:
                cursor.rotation_angle = (cursor.rotation_angle + 180.0 * 0.016) % 360.0
            else:
                # Smoothly return to upright
                if abs(cursor.rotation_angle) > 1.0:
                    cursor.rotation_angle *= 0.9
                else:
                    cursor.rotation_angle = 0.0
    
    def _move_cursor_towards_target(self, cursor: CursorInstance):
        """Move cursor towards its target position."""
        dx = cursor.target_x - cursor.x
        dy = cursor.target_y - cursor.y
        distance = (dx**2 + dy**2)**0.5
        
        if distance < 1.0:
            cursor.x = cursor.target_x
            cursor.y = cursor.target_y
            cursor.is_moving = False
            cursor.state = CursorState.ACTIVE
        else:
            # Move at constant speed
            cursor.x += (dx / distance) * cursor.move_speed * 0.016
            cursor.y += (dy / distance) * cursor.move_speed * 0.016
            cursor.state = CursorState.MOVING
    
    def _render_cursors(self):
        """Render all cursors (placeholder for actual rendering)."""
        # In a real implementation, this would use the overlay window
        # to draw all cursors at their respective positions
        pass
    
    # Public API
    
    def spawn_cursor(self, window_handle: int = 0, window_title: str = "", 
                    x: float = None, y: float = None, 
                    color: int = 0x00FF00FF) -> str:
        """
        Spawn a new independent cursor for a specific window/app.
        
        Args:
            window_handle: Handle of the window this cursor is for
            window_title: Title of the window
            x: Initial X position (defaults to center of screen)
            y: Initial Y position (defaults to center of screen)
            color: Cursor color (BGR format)
        
        Returns:
            ID of the spawned cursor
        """
        cursor_id = f"cursor_{self._next_cursor_id}"
        self._next_cursor_id += 1
        
        if x is None:
            x = self._screen_w / 2
        if y is None:
            y = self._screen_h / 2
        
        cursor = CursorInstance(
            cursor_id=cursor_id,
            window_handle=window_handle,
            window_title=window_title,
            x=x,
            y=y,
            target_x=x,
            target_y=y,
            state=CursorState.ACTIVE,
            is_attached_to_physical=False,  # Spawned cursors are always independent
            color=color
        )
        
        self._spawned_cursors[cursor_id] = cursor
        
        logger.info(f"[EnhancedCursor] Spawned cursor {cursor_id} for window '{window_title}' at ({x}, {y})")
        
        return cursor_id
    
    def despawn_cursor(self, cursor_id: str):
        """Remove a spawned cursor."""
        if cursor_id in self._spawned_cursors:
            del self._spawned_cursors[cursor_id]
            logger.info(f"[EnhancedCursor] Despawned cursor {cursor_id}")
    
    def despawn_all_cursors(self):
        """Remove all spawned cursors."""
        count = len(self._spawned_cursors)
        self._spawned_cursors.clear()
        logger.info(f"[EnhancedCursor] Despawned all {count} cursors")
    
    def move_cursor(self, cursor_id: str = "main", x: float = None, y: float = None):
        """
        Move a cursor to a specific position.
        
        Args:
            cursor_id: ID of the cursor ("main" for main cursor, or spawned cursor ID)
            x: Target X position
            y: Target Y position
        """
        if cursor_id == "main":
            cursor = self._main_cursor
        elif cursor_id in self._spawned_cursors:
            cursor = self._spawned_cursors[cursor_id]
        else:
            logger.warning(f"[EnhancedCursor] Unknown cursor ID: {cursor_id}")
            return
        
        if x is not None:
            cursor.target_x = x
        if y is not None:
            cursor.target_y = y
        
        cursor.is_moving = True
        cursor.is_attached_to_physical = False  # Detach from physical mouse
        
        logger.debug(f"[EnhancedCursor] Moving cursor {cursor_id} to ({x}, {y})")
    
    def click_cursor(self, cursor_id: str = "main"):
        """
        Perform a click action with a cursor.
        
        Args:
            cursor_id: ID of the cursor
        """
        if cursor_id == "main":
            cursor = self._main_cursor
        elif cursor_id in self._spawned_cursors:
            cursor = self._spawned_cursors[cursor_id]
        else:
            logger.warning(f"[EnhancedCursor] Unknown cursor ID: {cursor_id}")
            return
        
        cursor.state = CursorState.CLICKING
        cursor.click_animations.append({
            "start_time": time.time(),
            "duration": 0.2,
            "radius": 0.0
        })
        
        logger.debug(f"[EnhancedCursor] Click performed by cursor {cursor_id}")
    
    def set_cursor_state(self, cursor_id: str = "main", state: CursorState = CursorState.ACTIVE):
        """
        Set the state of a cursor.
        
        Args:
            cursor_id: ID of the cursor
            state: New cursor state
        """
        if cursor_id == "main":
            cursor = self._main_cursor
        elif cursor_id in self._spawned_cursors:
            cursor = self._spawned_cursors[cursor_id]
        else:
            logger.warning(f"[EnhancedCursor] Unknown cursor ID: {cursor_id}")
            return
        
        cursor.state = state
        
        # If going to ACTIVE, reattach main cursor to physical mouse
        if cursor_id == "main" and state == CursorState.IDLE:
            cursor.is_attached_to_physical = True
        elif cursor_id == "main" and state in [CursorState.ACTIVE, CursorState.MOVING, CursorState.CLICKING, CursorState.BUFFERING]:
            cursor.is_attached_to_physical = False
        
        logger.debug(f"[EnhancedCursor] Cursor {cursor_id} state set to {state.value}")
    
    def attach_to_physical_mouse(self, cursor_id: str = "main"):
        """
        Attach a cursor to the physical mouse (magnetic mode).
        
        Args:
            cursor_id: ID of the cursor (only main cursor can be attached)
        """
        if cursor_id != "main":
            logger.warning("[EnhancedCursor] Only main cursor can be attached to physical mouse")
            return
        
        self._main_cursor.is_attached_to_physical = True
        self._main_cursor.state = CursorState.IDLE
        logger.info("[EnhancedCursor] Main cursor attached to physical mouse")
    
    def detach_from_physical_mouse(self, cursor_id: str = "main"):
        """
        Detach a cursor from the physical mouse.
        
        Args:
            cursor_id: ID of the cursor
        """
        if cursor_id == "main":
            self._main_cursor.is_attached_to_physical = False
            self._main_cursor.state = CursorState.ACTIVE
            logger.info("[EnhancedCursor] Main cursor detached from physical mouse")
        elif cursor_id in self._spawned_cursors:
            # Spawned cursors are always detached
            logger.debug(f"[EnhancedCursor] Cursor {cursor_id} is already detached")
    
    def get_cursor_position(self, cursor_id: str = "main") -> Tuple[float, float]:
        """
        Get current position of a cursor.
        
        Args:
            cursor_id: ID of the cursor
        
        Returns:
            Tuple of (x, y) position
        """
        if cursor_id == "main":
            cursor = self._main_cursor
        elif cursor_id in self._spawned_cursors:
            cursor = self._spawned_cursors[cursor_id]
        else:
            logger.warning(f"[EnhancedCursor] Unknown cursor ID: {cursor_id}")
            return (0.0, 0.0)
        
        return (cursor.x, cursor.y)
    
    def get_all_cursors(self) -> Dict[str, CursorInstance]:
        """Get all cursor instances."""
        cursors = {"main": self._main_cursor}
        cursors.update(self._spawned_cursors)
        return cursors
    
    def set_physical_mouse_tracking(self, enabled: bool):
        """
        Enable or disable physical mouse tracking.
        
        Args:
            enabled: Whether to track physical mouse
        """
        self._physical_mouse_tracking = enabled
        logger.info(f"[EnhancedCursor] Physical mouse tracking {'enabled' if enabled else 'disabled'}")


# Singleton instance
enhanced_cursor = EnhancedVisualCursor()


def get_enhanced_cursor() -> EnhancedVisualCursor:
    """Get the singleton enhanced cursor instance."""
    return enhanced_cursor
