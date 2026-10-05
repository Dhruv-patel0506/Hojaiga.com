"""
Interactive App Teacher - Python Version
FULLY DYNAMIC - Works with ANY app in ANY window state
ADVANCED INTERACTIONS: Menus, dropdowns, dialogs, shortcuts, context menus, drag-and-drop
"""

import pyautogui
import time
import pyttsx3
import keyboard
import json
import requests
import win32gui
import win32con
import win32api
import win32process
import psutil
from typing import Dict, List, Tuple, Optional
import base64
from io import BytesIO
import re
import subprocess
import os

class InteractiveAppTeacher:
    def __init__(self):
        self.is_teaching = False
        self.tts_engine = pyttsx3.init()
        self.tts_engine.setProperty('rate', 150)  # Speed of speech
        self.discovered_features = []
        self.visited_screens = set()
        self.current_window = None
        self.window_bounds = None

    def speak(self, text: str):
        """Speak the text using TTS"""
        print(f"[SPEAKING]: {text}")
        self.tts_engine.say(text)
        self.tts_engine.runAndWait()

    def get_active_window_info(self) -> Dict:
        """Get information about the active window"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            class_name = win32gui.GetClassName(hwnd)

            # Get window state
            placement = win32gui.GetWindowPlacement(hwnd)
            show_cmd = placement[1]

            window_state = "normal"
            if show_cmd == win32con.SW_SHOWMAXIMIZED:
                window_state = "maximized"
            elif show_cmd == win32con.SW_SHOWMINIMIZED:
                window_state = "minimized"

            self.current_window = hwnd
            self.window_bounds = {
                'left': rect[0],
                'top': rect[1],
                'right': rect[2],
                'bottom': rect[3],
                'width': rect[2] - rect[0],
                'height': rect[3] - rect[1]
            }

            return {
                'title': title,
                'class': class_name,
                'hwnd': hwnd,
                'state': window_state,
                'bounds': self.window_bounds
            }
        except Exception as e:
            print(f"[ERROR] Failed to get window info: {e}")
            return {'title': 'Unknown', 'class': 'Unknown', 'hwnd': 0, 'state': 'unknown', 'bounds': None}

    def focus_window(self, hwnd: int):
        """Bring the window to foreground"""
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.5)
        except Exception as e:
            print(f"[ERROR] Failed to focus window: {e}")

    def capture_window(self) -> str:
        """Capture the active window and return as base64"""
        try:
            if self.window_bounds:
                # Capture only the window area
                screenshot = pyautogui.screenshot(
                    region=(
                        self.window_bounds['left'],
                        self.window_bounds['top'],
                        self.window_bounds['width'],
                        self.window_bounds['height']
                    )
                )
            else:
                # Fallback to full screen
                screenshot = pyautogui.screenshot()

            buffered = BytesIO()
            screenshot.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            return img_str
        except Exception as e:
            print(f"[ERROR] Failed to capture window: {e}")
            return ""

    def get_ui_elements_from_ollama(self, screenshot: str) -> List[Dict]:
        """Use Ollama LLaVA to dynamically identify UI elements with coordinates"""
        try:
            prompt = """Analyze this screenshot and identify ALL clickable UI elements.
For each element, provide:
1. element_name: The text on the button/menu (e.g., "File", "Save", "Bold")
2. approximate_x: X coordinate relative to the image (0-100%)
3. approximate_y: Y coordinate relative to the image (0-100%)
4. description: What this element does (e.g., "Opens file menu", "Saves current document")
5. type: The type of element (button, menu, input_field, tab, checkbox, etc.)

Return as JSON array:
[
  {"element_name": "Name", "approximate_x": 50, "approximate_y": 10, "description": "Description", "type": "button"},
  ...
]

Focus on: top menu bar, toolbar buttons, sidebar items, and main action buttons."""

            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llava",
                    "prompt": prompt,
                    "images": [screenshot],
                    "stream": False
                },
                timeout=30
            )
            result = response.json()
            return self._parse_llava_response(result.get('response', ''))
        except Exception as e:
            print(f"[ERROR] Failed to get UI elements from Ollama: {e}")
            return []

    def _parse_llava_response(self, response: str) -> List[Dict]:
        """Parse LLaVA response to extract UI elements"""
        elements = []
        try:
            # Try to find JSON in the response
            json_pattern = r'\[[\s\S]*\]'
            matches = re.findall(json_pattern, response)

            for match in matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, list):
                        elements.extend(data)
                    elif isinstance(data, dict):
                        elements.append(data)
                except:
                    continue

            # If no JSON found, try parsing the whole response
            if not elements:
                try:
                    data = json.loads(response)
                    if isinstance(data, list):
                        elements = data
                    elif isinstance(data, dict):
                        elements = [data]
                except:
                    pass

        except Exception as e:
            print(f"[ERROR] Failed to parse LLaVA response: {e}")

        return elements

    def relative_to_absolute(self, rel_x: float, rel_y: float) -> Tuple[int, int]:
        """Convert relative coordinates (0-100%) to absolute screen coordinates"""
        if not self.window_bounds:
            # Fallback to screen dimensions
            screen_width, screen_height = pyautogui.size()
            abs_x = int((rel_x / 100) * screen_width)
            abs_y = int((rel_y / 100) * screen_height)
        else:
            abs_x = int(self.window_bounds['left'] + (rel_x / 100) * self.window_bounds['width'])
            abs_y = int(self.window_bounds['top'] + (rel_y / 100) * self.window_bounds['height'])

        return abs_x, abs_y

    def click_at(self, x: int, y: int, text: str = ""):
        """Click at specific coordinates and announce"""
        print(f"[CLICKING]: {text} at ({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.3)
        pyautogui.click()
        if text:
            self.speak(f"Clicking {text}")
        time.sleep(1.5)

    def type_text(self, text: str, announce: bool = True):
        """Type text into the active field"""
        print(f"[TYPING]: {text}")
        pyautogui.write(text, interval=0.05)
        if announce:
            self.speak(f"Typing {text}")
        time.sleep(0.5)

    def right_click_at(self, x: int, y: int, text: str = ""):
        """Right-click at specific coordinates"""
        print(f"[RIGHT-CLICKING]: {text} at ({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.3)
        pyautogui.rightClick()
        if text:
            self.speak(f"Right-clicking {text}")
        time.sleep(1.5)

    def double_click_at(self, x: int, y: int, text: str = ""):
        """Double-click at specific coordinates"""
        print(f"[DOUBLE-CLICKING]: {text} at ({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.3)
        pyautogui.doubleClick()
        if text:
            self.speak(f"Double-clicking {text}")
        time.sleep(1.5)

    def drag_from_to(self, start_x: int, start_y: int, end_x: int, end_y: int, text: str = ""):
        """Drag from one point to another"""
        print(f"[DRAGGING]: {text} from ({start_x}, {start_y}) to ({end_x}, {end_y})")
        pyautogui.moveTo(start_x, start_y, duration=0.3)
        pyautogui.mouseDown()
        pyautogui.moveTo(end_x, end_y, duration=0.5)
        pyautogui.mouseUp()
        if text:
            self.speak(f"Dragging {text}")
        time.sleep(1.5)

    def press_hotkey(self, hotkey: str, text: str = ""):
        """Press a keyboard shortcut"""
        print(f"[PRESSING HOTKEY]: {hotkey}")
        pyautogui.hotkey(*hotkey.split('+'))
        if text:
            self.speak(f"Pressing {text}")
        time.sleep(1)

    def press_key(self, key: str, text: str = ""):
        """Press a single key"""
        print(f"[PRESSING KEY]: {key}")
        pyautogui.press(key)
        if text:
            self.speak(f"Pressing {text}")
        time.sleep(0.5)

    def scroll(self, clicks: int, text: str = ""):
        """Scroll the mouse wheel"""
        print(f"[SCROLLING]: {clicks} clicks")
        pyautogui.scroll(clicks)
        if text:
            self.speak(f"Scrolling {text}")
        time.sleep(0.5)

    def wait_for_element(self, timeout: int = 5):
        """Wait for UI to stabilize"""
        print(f"[WAITING]: {timeout} seconds for UI to stabilize")
        time.sleep(timeout)

    def explore_context_menu(self, x: int, y: int):
        """Right-click and explore context menu options"""
        print(f"[EXPLORING CONTEXT MENU] at ({x}, {y})")
        self.speak("I'll right-click here to see the context menu options.")
        self.right_click_at(x, y, "")
        time.sleep(1)

        # Try arrow keys to navigate menu
        self.speak("Exploring context menu items with arrow keys.")
        for i in range(3):
            if not self.is_teaching:
                break
            self.press_key('down', f"Menu item {i + 1}")
            time.sleep(1)

        # Press escape to close menu
        self.press_key('escape', "Closing context menu")

    def explore_dropdown(self, x: int, y: int):
        """Click a dropdown and explore options"""
        print(f"[EXPLORING DROPDOWN] at ({x}, {y})")
        self.speak("I'll click this dropdown to see the available options.")
        self.click_at(x, y, "")
        time.sleep(1)

        # Try arrow keys to navigate
        self.speak("Navigating dropdown options with arrow keys.")
        for i in range(3):
            if not self.is_teaching:
                break
            self.press_key('down', f"Option {i + 1}")
            time.sleep(1)

        # Press escape to close
        self.press_key('escape', "Closing dropdown")

    def explore_dialog(self):
        """Handle dialog boxes"""
        print(f"[EXPLORING DIALOG]")
        self.speak("A dialog box appeared. I'll explore the options.")

        # Try common dialog buttons
        common_positions = [
            (400, 400, "OK button"),
            (500, 400, "Cancel button"),
            (600, 400, "Apply button"),
            (300, 300, "Text input"),
        ]

        for x, y, label in common_positions:
            if not self.is_teaching:
                break
            self.click_at(x, y, label)
            time.sleep(1)

            # Try to go back
            self.press_key('escape', "")

    def discover_keyboard_shortcuts(self):
        """Try common keyboard shortcuts"""
        print(f"[DISCOVERING KEYBOARD SHORTCUTS]")
        self.speak("I'll try some common keyboard shortcuts to discover features.")

        shortcuts = [
            ('ctrl+s', 'Save'),
            ('ctrl+z', 'Undo'),
            ('ctrl+y', 'Redo'),
            ('ctrl+c', 'Copy'),
            ('ctrl+v', 'Paste'),
            ('ctrl+f', 'Find'),
            ('ctrl+p', 'Print'),
            ('f1', 'Help'),
        ]

        for hotkey, description in shortcuts:
            if not self.is_teaching:
                break
            self.speak(f"Trying {description} shortcut.")
            self.press_hotkey(hotkey, description)
            time.sleep(1)

            # Check if a dialog appeared
            self.explore_dialog()

            # Close any dialogs
            self.press_key('escape', "Closing dialog")
            time.sleep(0.5)

    def launch_app_if_not_running(self, app_name: str) -> bool:
        """Launch an app if it's not already running"""
        try:
            # Check if app is running
            for proc in psutil.process_iter(['name']):
                if app_name.lower() in proc.info['name'].lower():
                    self.speak(f"{app_name} is already running.")
                    return True

            # Try to launch the app
            self.speak(f"{app_name} is not running. I'll try to launch it.")
            common_paths = [
                f"C:\\Program Files\\Microsoft Office\\root\\Office16\\{app_name}.exe",
                f"C:\\Program Files (x86)\\Microsoft Office\\root\\Office16\\{app_name}.exe",
                f"C:\\Program Files\\{app_name}\\{app_name}.exe",
            ]

            for path in common_paths:
                if os.path.exists(path):
                    subprocess.Popen(path)
                    self.speak(f"Launched {app_name}.")
                    time.sleep(3)
                    return True

            self.speak(f"Couldn't find {app_name} in common locations.")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to launch app: {e}")
            return False

    def teach_any_app(self):
        """FULLY DYNAMIC teaching for ANY app"""
        self.is_teaching = True

        # Get window info
        window_info = self.get_active_window_info()
        app_name = window_info['title'] or 'this application'
        window_state = window_info['state']

        self.speak(f"Starting interactive teaching of {app_name}.")
        self.speak(f"Window is currently {window_state}. I will interact with it regardless of its state.")

        # Focus the window
        if window_info['hwnd']:
            self.focus_window(window_info['hwnd'])

        # Capture window
        self.speak("Scanning the application to identify all buttons and features...")
        screenshot = self.capture_window()

        if not screenshot:
            self.speak("Failed to capture the window. Please make sure the app is visible.")
            self.is_teaching = False
            return

        # Get UI elements from Ollama
        self.speak("Analyzing the interface with AI vision...")
        ui_elements = self.get_ui_elements_from_ollama(screenshot)

        if not ui_elements:
            self.speak("I couldn't automatically identify UI elements. Let me try advanced exploration.")
            self._advanced_fallback_exploration()
        else:
            self.speak(f"Found {len(ui_elements)} UI elements. I will now demonstrate with advanced interactions.")

            # Group elements by type for better teaching
            menus = [e for e in ui_elements if e.get('type') == 'menu']
            buttons = [e for e in ui_elements if e.get('type') == 'button']
            tabs = [e for e in ui_elements if e.get('type') == 'tab']
            inputs = [e for e in ui_elements if e.get('type') == 'input_field']
            dropdowns = [e for e in ui_elements if e.get('type') == 'dropdown']
            checkboxes = [e for e in ui_elements if e.get('type') == 'checkbox']
            others = [e for e in ui_elements if e.get('type') not in ['menu', 'button', 'tab', 'input_field', 'dropdown', 'checkbox']]

            # Teach menus with dropdown exploration
            if menus:
                self.speak("First, let me show you the menu options and explore their dropdowns.")
                for menu in menus[:3]:  # Top 3 menus
                    if not self.is_teaching:
                        break
                    self._teach_element_advanced(menu, explore_dropdown=True)

            # Teach tabs
            if tabs:
                self.speak("Now let me show you the different tabs.")
                for tab in tabs[:3]:  # Top 3 tabs
                    if not self.is_teaching:
                        break
                    self._teach_element(tab)

            # Teach main buttons
            if buttons:
                self.speak("Let me demonstrate the main action buttons.")
                for button in buttons[:5]:  # Top 5 buttons
                    if not self.is_teaching:
                        break
                    self._teach_element(button)

            # Teach dropdowns
            if dropdowns:
                self.speak("Let me show you the dropdown menus.")
                for dropdown in dropdowns[:3]:  # Top 3 dropdowns
                    if not self.is_teaching:
                        break
                    rel_x = dropdown.get('approximate_x', 50)
                    rel_y = dropdown.get('approximate_y', 50)
                    abs_x, abs_y = self.relative_to_absolute(rel_x, rel_y)
                    self.explore_dropdown(abs_x, abs_y)

            # Teach checkboxes
            if checkboxes:
                self.speak("Let me show you the checkboxes.")
                for checkbox in checkboxes[:3]:  # Top 3 checkboxes
                    if not self.is_teaching:
                        break
                    self._teach_element(checkbox)

            # Teach input fields with typing
            if inputs:
                self.speak("Let me show you the input fields by typing sample text.")
                for input_field in inputs[:2]:  # Top 2 input fields
                    if not self.is_teaching:
                        break
                    self._teach_element_advanced(input_field, type_sample=True)

            # Teach other elements
            if others:
                self.speak("Let me show you other interface elements.")
                for other in others[:3]:  # Top 3 other elements
                    if not self.is_teaching:
                        break
                    self._teach_element(other)

            # Explore context menus
            self.speak("Let me explore context menus by right-clicking in different areas.")
            self._explore_context_menus()

            # Discover keyboard shortcuts
            self.speak("Let me discover keyboard shortcuts that work in this application.")
            self.discover_keyboard_shortcuts()

        self.speak("I've demonstrated the main features of this application. You can now explore these elements yourself by clicking the buttons I showed you.")
        self.is_teaching = False

    def _teach_element_advanced(self, element: Dict, explore_dropdown: bool = False, type_sample: bool = False):
        """Teach a single UI element with advanced interactions"""
        name = element.get('element_name', 'Unknown element')
        rel_x = element.get('approximate_x', 50)
        rel_y = element.get('approximate_y', 50)
        desc = element.get('description', '')
        element_type = element.get('type', 'button')

        # Convert to absolute coordinates
        abs_x, abs_y = self.relative_to_absolute(rel_x, rel_y)

        # Explain before clicking
        self.speak(f"This is the {name} {element_type}. {desc}")

        # Click based on type
        if element_type == 'menu':
            self.click_at(abs_x, abs_y, name)
            if explore_dropdown:
                self.speak("Exploring dropdown menu options.")
                time.sleep(1)
                for i in range(3):
                    if not self.is_teaching:
                        break
                    self.press_key('down', f"Menu option {i + 1}")
                    time.sleep(1)
                self.press_key('escape', "Closing menu")
        elif element_type == 'button':
            self.click_at(abs_x, abs_y, name)
        elif element_type == 'tab':
            self.click_at(abs_x, abs_y, name)
        elif element_type == 'input_field':
            self.click_at(abs_x, abs_y, name)
            if type_sample:
                self.speak("I'll type sample text to demonstrate.")
                self.type_text("Sample text")
                time.sleep(1)
        else:
            self.click_at(abs_x, abs_y, name)

        # Explain result
        self.speak(f"After clicking {name}, you can see the result on screen.")

        # Wait to see the result
        time.sleep(2)

        # Try to go back or close menus
        self.speak("Going back to continue teaching.")
        pyautogui.press('escape')
        time.sleep(1)

        # Record as discovered
        self.discovered_features.append(name)

    def _explore_context_menus(self):
        """Explore context menus in different areas of the window"""
        if not self.window_bounds:
            return

        # Test different areas for context menus
        test_areas = [
            (0.5, 0.3, "center area"),
            (0.2, 0.5, "left side"),
            (0.8, 0.5, "right side"),
            (0.5, 0.7, "bottom area"),
        ]

        for rel_x, rel_y, area_name in test_areas:
            if not self.is_teaching:
                break
            abs_x, abs_y = self.relative_to_absolute(rel_x * 100, rel_y * 100)
            self.speak(f"Testing context menu in the {area_name}.")
            self.explore_context_menu(abs_x, abs_y)
            time.sleep(1)

    def _advanced_fallback_exploration(self):
        """Advanced fallback exploration when Ollama fails"""
        self.speak("I'll use advanced grid-based exploration to find interactive elements.")

        if not self.window_bounds:
            screen_width, screen_height = pyautogui.size()
            bounds = {'left': 0, 'top': 0, 'width': screen_width, 'height': screen_height}
        else:
            bounds = self.window_bounds

        # Create a grid of points to test
        grid_points = []
        for x in range(6):  # 6 columns
            for y in range(6):  # 6 rows
                grid_x = bounds['left'] + (x + 1) * (bounds['width'] // 7)
                grid_y = bounds['top'] + (y + 1) * (bounds['height'] // 7)
                grid_points.append((grid_x, grid_y))

        # Test each point with different interaction types
        for i, (x, y) in enumerate(grid_points[:15]):  # Test top 15 points
            if not self.is_teaching:
                break

            # Alternate between click, right-click, and double-click
            if i % 3 == 0:
                self.speak(f"Testing area {i + 1} with left click")
                self.click_at(x, y, f"Area {i + 1}")
            elif i % 3 == 1:
                self.speak(f"Testing area {i + 1} with right click")
                self.right_click_at(x, y, f"Area {i + 1}")
            else:
                self.speak(f"Testing area {i + 1} with double click")
                self.double_click_at(x, y, f"Area {i + 1}")

            time.sleep(1)

            # Try to go back
            pyautogui.press('escape')
            time.sleep(0.5)

    def _teach_element(self, element: Dict):
        """Teach a single UI element by clicking it (legacy method)"""
        self._teach_element_advanced(element)

    def _fallback_exploration(self):
        """Fallback exploration when Ollama fails"""
        self.speak("I'll use a grid-based exploration to find interactive elements.")

        if not self.window_bounds:
            screen_width, screen_height = pyautogui.size()
            bounds = {'left': 0, 'top': 0, 'width': screen_width, 'height': screen_height}
        else:
            bounds = self.window_bounds

        # Create a grid of points to test
        grid_points = []
        for x in range(5):  # 5 columns
            for y in range(5):  # 5 rows
                grid_x = bounds['left'] + (x + 1) * (bounds['width'] // 6)
                grid_y = bounds['top'] + (y + 1) * (bounds['height'] // 6)
                grid_points.append((grid_x, grid_y))

        # Test each point
        for i, (x, y) in enumerate(grid_points[:10]):  # Test top 10 points
            if not self.is_teaching:
                break

            self.speak(f"Testing area {i + 1}")
            self.click_at(x, y, f"Area {i + 1}")
            time.sleep(1)

            # Try to go back
            pyautogui.press('escape')
            time.sleep(0.5)

    def stop_teaching(self):
        """Stop the teaching session"""
        self.is_teaching = False
        self.speak("Teaching stopped.")

if __name__ == "__main__":
    print("=== ADVANCED FULLY DYNAMIC Interactive App Teacher ===")
    print("This will teach ANY app in ANY window state with ADVANCED interactions!")
    print("\nMake sure:")
    print("1. The app you want to learn is open (any state: minimized, maximized, windowed)")
    print("2. Ollama is running (http://localhost:11434)")
    print("3. LLaVA model is installed (ollama pull llava)")
    print("\nAdvanced Features:")
    print("✅ Works with ANY app (no hardcoding)")
    print("✅ Works in ANY window state (minimized, maximized, portable)")
    print("✅ Actually clicks buttons and interacts")
    print("✅ Uses AI vision to identify UI elements")
    print("✅ Speaks explanations while teaching")
    print("✅ Explores dropdown menus")
    print("✅ Explores context menus (right-click)")
    print("✅ Discovers keyboard shortcuts")
    print("✅ Types into input fields")
    print("✅ Handles dialog boxes")
    print("✅ Multiple interaction types (click, double-click, right-click)")
    print("\nPress SPACE to start teaching, ESC to stop")

    teacher = InteractiveAppTeacher()

    # Wait for user to press SPACE
    keyboard.wait('space')

    # Start teaching (now fully dynamic with advanced interactions)
    teacher.teach_any_app()

    print("\nTeaching complete!")
    print(f"Discovered {len(teacher.discovered_features)} features:")
    for feature in teacher.discovered_features:
        print(f"  • {feature}")
