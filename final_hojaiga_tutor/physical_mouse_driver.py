"""
Physical Mouse Driver - Glides the OS cursor like a human
Uses PyAutoGUI for smooth, human-like mouse movement
Can be called from TypeScript via command line
"""

import sys
import json
import pyautogui
import time

# Safety feature: moving mouse to corner aborts the script
pyautogui.FAILSAFE = True

def move_and_click(x: int, y: int, duration: float = 0.8, click_delay: float = 0.2) -> dict:
    """
    Smoothly glides the physical OS cursor to target and clicks
    
    Args:
        x: Target X coordinate
        y: Target Y coordinate
        duration: Movement duration in seconds
        click_delay: Human-like pause before clicking
    
    Returns:
        Dict with success status and action performed
    """
    try:
        print(f"Gliding physical mouse to ({x}, {y}) over {duration}s...")
        
        # Smooth glide with easeInOutQuad tweening
        pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)
        
        # Human-like pause before clicking
        time.sleep(click_delay)
        pyautogui.click()
        
        print(f"Physical mouse click executed at ({x}, {y})")
        
        return {
            "success": True,
            "action": "physical_click",
            "x": x,
            "y": y
        }
    except Exception as e:
        print(f"Physical mouse movement failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def move_only(x: int, y: int, duration: float = 0.8) -> dict:
    """
    Smoothly glides the physical OS cursor without clicking
    
    Args:
        x: Target X coordinate
        y: Target Y coordinate
        duration: Movement duration in seconds
    
    Returns:
        Dict with success status
    """
    try:
        print(f"Gliding physical mouse to ({x}, {y}) over {duration}s...")
        pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)
        print(f"Physical mouse movement complete at ({x}, {y})")
        
        return {
            "success": True,
            "action": "physical_move",
            "x": x,
            "y": y
        }
    except Exception as e:
        print(f"Physical mouse movement failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def main():
    """Command line interface"""
    if len(sys.argv) < 3:
        print("Usage: python physical_mouse_driver.py <action> <x> <y> [duration]")
        print("Actions: click, move")
        sys.exit(1)
    
    action = sys.argv[1]
    x = int(sys.argv[2])
    y = int(sys.argv[3])
    duration = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8
    
    if action == "click":
        result = move_and_click(x, y, duration)
    elif action == "move":
        result = move_only(x, y, duration)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
    
    # Output JSON result for TypeScript to parse
    print(json.dumps(result))
    sys.exit(0 if result["success"] else 1)

if __name__ == "__main__":
    main()
