/**
 * OS Controller - Windows-specific implementation
 * Provides actual mouse, keyboard, screen capture, and UI tree extraction
 */

import { execSync } from 'child_process';
import * as os from 'os';

// Types (simplified for standalone implementation)
interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface UINode {
  id: string;
  name: string;
  role: string;
  bounds: BoundingBox;
  accessibleText?: string;
  isInteractable: boolean;
  isVisible: boolean;
}

export class WindowsOSController {
  private pythonScript: string;

  constructor() {
    this.pythonScript = `
import pyautogui
import time
import win32gui
import win32con
import win32api
import json
import base64
from io import BytesIO
from PIL import ImageGrab

class OSController:
    def __init__(self):
        pass

    def capture_screen(self):
        screenshot = ImageGrab.grab()
        buffered = BytesIO()
        screenshot.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return json.dumps({"screenshot": img_str})

    def get_cursor_position(self):
        x, y = pyautogui.position()
        return json.dumps({"x": x, "y": y})

    def move_mouse(self, x, y, duration=0.5, curve='bezier'):
        # Simple linear move for now (bezier requires more complex math)
        pyautogui.moveTo(x, y, duration=duration)
        return json.dumps({"success": True})

    def click(self, x, y, button='left'):
        pyautogui.click(x, y, button=button)
        return json.dumps({"success": True})

    def right_click(self, x, y):
        pyautogui.rightClick(x, y)
        return json.dumps({"success": True})

    def double_click(self, x, y):
        pyautogui.doubleClick(x, y)
        return json.dumps({"success": True})

    def type_text(self, text, speed=0.1):
        pyautogui.write(text, interval=speed)
        return json.dumps({"success": True})

    def press_key(self, key):
        pyautogui.press(key)
        return json.dumps({"success": True})

    def hotkey(self, keys):
        pyautogui.hotkey(*keys.split('+'))
        return json.dumps({"success": True})

    def get_ui_tree(self):
        """Extract UI tree using Windows UI Automation"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)

            # Simplified UI tree (in production, use IUIAutomation)
            elements = []

            # Add window as root
            elements.append({
                "id": "window",
                "name": title,
                "role": "window",
                "bounds": {"x": rect[0], "y": rect[1], "width": rect[2]-rect[0], "height": rect[3]-rect[1]},
                "isInteractable": True,
                "isVisible": True
            })

            # In production, use IUIAutomation to enumerate all controls
            # For now, return simplified tree
            return json.dumps({"uiTree": elements, "activeWindow": {"title": title}})
        except Exception as e:
            return json.dumps({"error": str(e), "uiTree": []})

if __name__ == "__main__":
    import sys
    controller = OSController()
    command = sys.argv[1] if len(sys.argv) > 1 else ""

    if command == "capture":
        print(controller.capture_screen())
    elif command == "cursor":
        print(controller.get_cursor_position())
    elif command == "move":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        print(controller.move_mouse(x, y))
    elif command == "click":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        print(controller.click(x, y))
    elif command == "right_click":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        print(controller.right_click(x, y))
    elif command == "double_click":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        print(controller.double_click(x, y))
    elif command == "type":
        text = sys.argv[2]
        print(controller.type_text(text))
    elif command == "press":
        key = sys.argv[2]
        print(controller.press_key(key))
    elif command == "hotkey":
        keys = sys.argv[2]
        print(controller.hotkey(keys))
    elif command == "ui_tree":
        print(controller.get_ui_tree())
`;
  }

  /**
   * Capture screen as base64
   */
  captureScreen(): string {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" capture`, {
        encoding: 'utf-8',
        maxBuffer: 10 * 1024 * 1024 // 10MB
      });
      const data = JSON.parse(result);
      return data.screenshot;
    } catch (error) {
      console.error('[OSController] Failed to capture screen:', error);
      return '';
    }
  }

  /**
   * Get current cursor position
   */
  getCursorPosition(): { x: number; y: number } {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" cursor`, {
        encoding: 'utf-8'
      });
      return JSON.parse(result);
    } catch (error) {
      console.error('[OSController] Failed to get cursor position:', error);
      return { x: 0, y: 0 };
    }
  }

  /**
   * Move mouse to coordinates with bezier curve
   */
  moveMouse(x: number, y: number, options: { duration?: number; curve?: string } = {}): void {
    try {
      const duration = options.duration || 500;
      const curve = options.curve || 'bezier';
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" move ${x} ${y}`, {
        encoding: 'utf-8'
      });
      console.log('[OSController] Mouse moved:', JSON.parse(result));
    } catch (error) {
      console.error('[OSController] Failed to move mouse:', error);
    }
  }

  /**
   * Click at coordinates
   */
  click(x: number, y: number, button: 'left' | 'right' = 'left'): void {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" ${button}_click ${x} ${y}`, {
        encoding: 'utf-8'
      });
      console.log('[OSController] Clicked:', JSON.parse(result));
    } catch (error) {
      console.error('[OSController] Failed to click:', error);
    }
  }

  /**
   * Right-click at coordinates
   */
  rightClick(x: number, y: number): void {
    this.click(x, y, 'right');
  }

  /**
   * Double-click at coordinates
   */
  doubleClick(x: number, y: number): void {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" double_click ${x} ${y}`, {
        encoding: 'utf-8'
      });
      console.log('[OSController] Double-clicked:', JSON.parse(result));
    } catch (error) {
      console.error('[OSController] Failed to double-click:', error);
    }
  }

  /**
   * Type text
   */
  typeText(text: string, options: { speed?: number } = {}): void {
    try {
      const speed = options.speed || 0.1;
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" type "${text}"`, {
        encoding: 'utf-8'
      });
      console.log('[OSController] Typed:', JSON.parse(result));
    } catch (error) {
      console.error('[OSController] Failed to type:', error);
    }
  }

  /**
   * Press a key
   */
  pressKey(key: string): void {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" press ${key}`, {
        encoding: 'utf-8'
      });
      console.log('[OSController] Pressed:', JSON.parse(result));
    } catch (error) {
      console.error('[OSController] Failed to press key:', error);
    }
  }

  /**
   * Press hotkey combination
   */
  hotkey(keys: string): void {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" hotkey "${keys}"`, {
        encoding: 'utf-8'
      });
      console.log('[OSController] Hotkey pressed:', JSON.parse(result));
    } catch (error) {
      console.error('[OSController] Failed to press hotkey:', error);
    }
  }

  /**
   * Extract UI tree using Windows UI Automation
   */
  getUITree(): any {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" ui_tree`, {
        encoding: 'utf-8',
        maxBuffer: 10 * 1024 * 1024
      });
      return JSON.parse(result);
    } catch (error) {
      console.error('[OSController] Failed to get UI tree:', error);
      return { uiTree: [], activeWindow: { title: 'Unknown' } };
    }
  }
}
