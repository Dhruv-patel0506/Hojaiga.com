"""
Smooth Cursor Automation - Human-like mouse movement with PyAutoGUI
Provides smooth, physical cursor movement with tweening animations
"""

import pyautogui
import time
from typing import Optional

# Safety feature: moving mouse to corner aborts the script
pyautogui.FAILSAFE = True

class SmoothCursorAutomation:
    """Handles smooth, human-like cursor movement and clicking"""
    
    def __init__(self, duration: float = 1.2):
        """
        Initialize smooth cursor automation
        
        Args:
            duration: Default duration for mouse movement in seconds
        """
        self.duration = duration
        self.moveTween = pyautogui.easeInOutQuad
    
    def smooth_move_and_click(
        self, 
        target_x: int, 
        target_y: int, 
        duration: Optional[float] = None,
        click_delay: float = 0.2
    ) -> None:
        """
        Moves the physical OS cursor smoothly to the target and clicks
        
        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            duration: Movement duration (uses default if not specified)
            click_delay: Human-like pause before clicking
        """
        move_duration = duration if duration is not None else self.duration
        
        print(f"[SmoothCursor] Gliding cursor to ({target_x}, {target_y}) over {move_duration}s...")
        
        # easeInOutQuad makes it start slow, speed up, and slow down before stopping
        pyautogui.moveTo(target_x, target_y, duration=move_duration, tween=self.moveTween)
        
        # Tiny human-like pause before the click
        time.sleep(click_delay)
        pyautogui.click()
        print("[SmoothCursor] Click executed")
    
    def smooth_move_only(
        self, 
        target_x: int, 
        target_y: int, 
        duration: Optional[float] = None
    ) -> None:
        """
        Moves the physical OS cursor smoothly without clicking
        
        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            duration: Movement duration (uses default if not specified)
        """
        move_duration = duration if duration is not None else self.duration
        
        print(f"[SmoothCursor] Gliding cursor to ({target_x}, {target_y}) over {move_duration}s...")
        pyautogui.moveTo(target_x, target_y, duration=move_duration, tween=self.moveTween)
        print("[SmoothCursor] Movement complete")
    
    def right_click_smooth(
        self, 
        target_x: int, 
        target_y: int, 
        duration: Optional[float] = None,
        click_delay: float = 0.2
    ) -> None:
        """
        Moves the physical OS cursor smoothly and right-clicks
        
        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            duration: Movement duration (uses default if not specified)
            click_delay: Human-like pause before clicking
        """
        move_duration = duration if duration is not None else self.duration
        
        print(f"[SmoothCursor] Gliding cursor to ({target_x}, {target_y}) over {move_duration}s...")
        pyautogui.moveTo(target_x, target_y, duration=move_duration, tween=self.moveTween)
        
        time.sleep(click_delay)
        pyautogui.rightClick()
        print("[SmoothCursor] Right-click executed")
    
    def double_click_smooth(
        self, 
        target_x: int, 
        target_y: int, 
        duration: Optional[float] = None,
        click_delay: float = 0.2
    ) -> None:
        """
        Moves the physical OS cursor smoothly and double-clicks
        
        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            duration: Movement duration (uses default if not specified)
            click_delay: Human-like pause before clicking
        """
        move_duration = duration if duration is not None else self.duration
        
        print(f"[SmoothCursor] Gliding cursor to ({target_x}, {target_y}) over {move_duration}s...")
        pyautogui.moveTo(target_x, target_y, duration=move_duration, tween=self.moveTween)
        
        time.sleep(click_delay)
        pyautogui.doubleClick()
        print("[SmoothCursor] Double-click executed")
    
    def type_text(self, text: str, interval: float = 0.05) -> None:
        """
        Types text with human-like typing speed
        
        Args:
            text: Text to type
            interval: Delay between keystrokes
        """
        print(f"[SmoothCursor] Typing: {text[:50]}...")
        pyautogui.typewrite(text, interval=interval)
        print("[SmoothCursor] Typing complete")
    
    def get_current_position(self) -> tuple[int, int]:
        """Returns current mouse position"""
        return pyautogui.position()


# Example usage
if __name__ == "__main__":
    automation = SmoothCursorAutomation(duration=1.2)
    
    # Example: Move to center of screen and click
    screen_width, screen_height = pyautogui.size()
    center_x, center_y = screen_width // 2, screen_height // 2
    
    automation.smooth_move_and_click(center_x, center_y)
