/**
 * Virtual Cursor Controller - Clicky-style overlay approach
 * Shows a virtual cursor on an overlay instead of moving physical mouse
 * Parses [POINT:x,y:label] tags from LLM response like original Clicky
 * User's physical mouse remains independent
 */

import { execSync } from 'child_process';

interface PointTag {
  x: number;
  y: number;
  label: string;
  screenIndex?: number;
}

export class VirtualCursorController {
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
from PIL import ImageGrab, Image
import tkinter as tk

class VirtualCursor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', 'black')
        self.root.configure(bg='black')
        
        self.canvas = tk.Canvas(self.root, width=1920, height=1080, bg='black', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        
        # Virtual cursor image (blue circle - Clicky style)
        self.cursor_size = 20
        self.cursor_id = self.canvas.create_oval(0, 0, self.cursor_size, self.cursor_size, fill='#0066ff', outline='#00aaff', width=2)
        self.canvas.itemconfig(self.cursor_id, state='hidden')
        
        # Tooltip bubble for labels
        self.tooltip_id = self.canvas.create_text(0, 0, text='', fill='white', font=('Arial', 12), state='hidden')
        
        self.current_x = 0
        self.current_y = 0
        self.root.overrideredirect(True)
        self.root.update()

    def show_cursor(self):
        self.canvas.itemconfig(self.cursor_id, state='normal')

    def hide_cursor(self):
        self.canvas.itemconfig(self.cursor_id, state='hidden')
        self.canvas.itemconfig(self.tooltip_id, state='hidden')

    def move_cursor_to(self, x, y, label='', duration=0.5, click=False):
        # Bezier curve for natural movement (Clicky-style)
        start_x, start_y = self.current_x, self.current_y
        steps = 30

        for i in range(steps + 1):
            t = i / steps
            # Bezier curve calculation
            control_x = (start_x + x) / 2
            control_y = min(start_y, y) - 100  # Curve upward

            # Quadratic bezier: (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
            curr_x = (1-t)**2 * start_x + 2*(1-t)*t * control_x + t**2 * x
            curr_y = (1-t)**2 * start_y + 2*(1-t)*t * control_y + t**2 * y

            self.canvas.coords(self.cursor_id,
                             curr_x - self.cursor_size//2,
                             curr_y - self.cursor_size//2,
                             curr_x + self.cursor_size//2,
                             curr_y + self.cursor_size//2)

            self.root.update()
            time.sleep(duration / steps)

        self.current_x = x
        self.current_y = y

        # Show tooltip with label
        if label:
            self.canvas.coords(self.tooltip_id, x + 25, y - 10)
            self.canvas.itemconfig(self.tooltip_id, text=label, state='normal')
        else:
            self.canvas.itemconfig(self.tooltip_id, state='hidden')

        # Actually click if requested
        if click:
            time.sleep(0.2)  # Brief pause before click
            pyautogui.click(x, y)
            time.sleep(0.2)  # Brief pause after click

    def hide_tooltip(self):
        self.canvas.itemconfig(self.tooltip_id, state='hidden')

    def click_at(self, x, y, button='left'):
        """Actually click at coordinates (real OS interaction)"""
        pyautogui.click(x, y, button=button)
        time.sleep(0.3)

    def right_click_at(self, x, y):
        """Right-click at coordinates"""
        pyautogui.rightClick(x, y)
        time.sleep(0.3)

    def double_click_at(self, x, y):
        """Double-click at coordinates"""
        pyautogui.doubleClick(x, y)
        time.sleep(0.3)

    def type_text(self, text, speed=0.05):
        """Type text (real keyboard input)"""
        pyautogui.write(text, interval=speed)
        time.sleep(0.3)

    def press_key(self, key):
        """Press a key"""
        pyautogui.press(key)
        time.sleep(0.2)

    def hotkey(self, keys):
        """Press hotkey combination"""
        pyautogui.hotkey(*keys.split('+'))
        time.sleep(0.3)

    def capture_screen(self):
        screenshot = ImageGrab.grab()
        buffered = BytesIO()
        screenshot.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return json.dumps({"screenshot": img_str})

    def close(self):
        self.root.destroy()

if __name__ == "__main__":
    import sys
    cursor = VirtualCursor()
    command = sys.argv[1] if len(sys.argv) > 1 else ""

    if command == "capture":
        print(cursor.capture_screen())
    elif command == "move":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        label = sys.argv[4] if len(sys.argv) > 4 else ""
        click = sys.argv[5] == "true" if len(sys.argv) > 5 else False
        cursor.show_cursor()
        cursor.move_cursor_to(x, y, label, click=click)
        print(json.dumps({"success": True}))
    elif command == "click":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        cursor.click_at(x, y)
        print(json.dumps({"success": True}))
    elif command == "right_click":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        cursor.right_click_at(x, y)
        print(json.dumps({"success": True}))
    elif command == "double_click":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        cursor.double_click_at(x, y)
        print(json.dumps({"success": True}))
    elif command == "type":
        text = sys.argv[2]
        cursor.type_text(text)
        print(json.dumps({"success": True}))
    elif command == "press":
        key = sys.argv[2]
        cursor.press_key(key)
        print(json.dumps({"success": True}))
    elif command == "hotkey":
        keys = sys.argv[2]
        cursor.hotkey(keys)
        print(json.dumps({"success": True}))
    elif command == "show":
        cursor.show_cursor()
        print(json.dumps({"success": True}))
    elif command == "hide":
        cursor.hide_cursor()
        print(json.dumps({"success": True}))
    elif command == "close":
        cursor.close()
        print(json.dumps({"success": True}))
`;
  }

  /**
   * Initialize virtual cursor overlay
   */
  initializeOverlay(): void {
    try {
      console.log('[VirtualCursor] Overlay initialized (Clicky-style virtual cursor)');
      console.log('[VirtualCursor] Physical mouse remains independent');
    } catch (error) {
      console.error('[VirtualCursor] Failed to initialize overlay:', error);
    }
  }

  /**
   * Capture screen as base64
   */
  captureScreen(): string {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" capture`, {
        encoding: 'utf-8',
        maxBuffer: 10 * 1024 * 1024
      });
      const data = JSON.parse(result);
      return data.screenshot;
    } catch (error) {
      console.error('[VirtualCursor] Failed to capture screen:', error);
      return '';
    }
  }

  /**
   * Move virtual cursor to coordinates with label (Clicky-style)
   * Can optionally actually click the position
   */
  moveVirtualCursor(x: number, y: number, label: string, options: { duration?: number; click?: boolean } = {}): void {
    try {
      const duration = options.duration || 500;
      const click = options.click || false;
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" move ${x} ${y} "${label}" ${click}`, {
        encoding: 'utf-8'
      });
      console.log(`[VirtualCursor] Virtual cursor moved to (${x}, ${y}): ${label}${click ? ' (clicked)' : ''}`, JSON.parse(result));
    } catch (error) {
      console.error('[VirtualCursor] Failed to move virtual cursor:', error);
    }
  }

  /**
   * Actually click at coordinates (real OS interaction)
   */
  clickAt(x: number, y: number, button: 'left' | 'right' = 'left'): void {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" ${button === 'right' ? 'right_click' : 'click'} ${x} ${y}`, {
        encoding: 'utf-8'
      });
      console.log(`[VirtualCursor] Clicked at (${x}, ${y}):`, JSON.parse(result));
    } catch (error) {
      console.error('[VirtualCursor] Failed to click:', error);
    }
  }

  /**
   * Right-click at coordinates
   */
  rightClickAt(x: number, y: number): void {
    this.clickAt(x, y, 'right');
  }

  /**
   * Double-click at coordinates
   */
  doubleClickAt(x: number, y: number): void {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" double_click ${x} ${y}`, {
        encoding: 'utf-8'
      });
      console.log(`[VirtualCursor] Double-clicked at (${x}, ${y}):`, JSON.parse(result));
    } catch (error) {
      console.error('[VirtualCursor] Failed to double-click:', error);
    }
  }

  /**
   * Type text (real keyboard input)
   */
  typeText(text: string, options: { speed?: number } = {}): void {
    try {
      const speed = options.speed || 0.05;
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" type "${text}"`, {
        encoding: 'utf-8'
      });
      console.log(`[VirtualCursor] Typed "${text}":`, JSON.parse(result));
    } catch (error) {
      console.error('[VirtualCursor] Failed to type:', error);
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
      console.log(`[VirtualCursor] Pressed key "${key}":`, JSON.parse(result));
    } catch (error) {
      console.error('[VirtualCursor] Failed to press key:', error);
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
      console.log(`[VirtualCursor] Pressed hotkey "${keys}":`, JSON.parse(result));
    } catch (error) {
      console.error('[VirtualCursor] Failed to press hotkey:', error);
    }
  }

  /**
   * Show virtual cursor
   */
  showVirtualCursor(): void {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" show`, {
        encoding: 'utf-8'
      });
      console.log('[VirtualCursor] Virtual cursor shown:', JSON.parse(result));
    } catch (error) {
      console.error('[VirtualCursor] Failed to show virtual cursor:', error);
    }
  }

  /**
   * Hide virtual cursor
   */
  hideVirtualCursor(): void {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" hide`, {
        encoding: 'utf-8'
      });
      console.log('[VirtualCursor] Virtual cursor hidden:', JSON.parse(result));
    } catch (error) {
      console.error('[VirtualCursor] Failed to hide virtual cursor:', error);
    }
  }

  /**
   * Parse POINT tags from LLM response (Clicky-style)
   * Format: [POINT:x,y:label:screenN]
   */
  parsePointTags(text: string): PointTag[] {
    const pointRegex = /\[POINT:(\d+),(\d+):([^\]]+)\]/g;
    const points: PointTag[] = [];
    let match;

    while ((match = pointRegex.exec(text)) !== null) {
      points.push({
        x: parseInt(match[1]),
        y: parseInt(match[2]),
        label: match[3]
      });
    }

    return points;
  }

  /**
   * Remove POINT tags from text before sending to TTS
   * So TTS doesn't read coordinates
   */
  removePointTags(text: string): string {
    return text.replace(/\[POINT:[^\]]+\]/g, '');
  }

  /**
   * Get UI tree (simplified version)
   */
  getUITree(): any {
    try {
      const result = execSync(`python -c "${this.pythonScript.replace(/\n/g, ';')}" ui_tree`, {
        encoding: 'utf-8',
        maxBuffer: 10 * 1024 * 1024
      });
      return JSON.parse(result);
    } catch (error) {
      console.error('[VirtualCursor] Failed to get UI tree:', error);
      return { uiTree: [], activeWindow: { title: 'Unknown' } };
    }
  }
}
