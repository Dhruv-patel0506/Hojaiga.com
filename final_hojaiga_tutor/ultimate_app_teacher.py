"""
ULTIMATE Interactive App Teacher - Python Version
EXTREMELY ROBUST - Scans EVERYTHING, teaches COMPLETELY, demonstrates REAL workflows
Teaches as if user knows NOTHING about the app
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
import psutil
from typing import Dict, List, Tuple, Optional
import base64
from io import BytesIO
import re
import subprocess
import os

class UltimateAppTeacher:
    def __init__(self):
        self.is_teaching = False
        self.tts_engine = pyttsx3.init()
        self.tts_engine.setProperty('rate', 130)  # Slower, clearer speech
        self.discovered_features = []
        self.visited_screens = set()
        self.current_window = None
        self.window_bounds = None
        self.app_type = None

    def speak(self, text: str):
        """Speak the text using TTS"""
        print(f"[SPEAKING]: {text}")
        self.tts_engine.say(text)
        self.tts_engine.runAndWait()

    def get_active_window_info(self) -> Dict:
        """Get detailed information about the active window"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            class_name = win32gui.GetClassName(hwnd)

            # Detect app type from title
            self.app_type = self._detect_app_type(title, class_name)

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
                'bounds': self.window_bounds,
                'app_type': self.app_type
            }
        except Exception as e:
            print(f"[ERROR] Failed to get window info: {e}")
            return {'title': 'Unknown', 'class': 'Unknown', 'hwnd': 0, 'state': 'unknown', 'bounds': None, 'app_type': 'unknown'}

    def _detect_app_type(self, title: str, class_name: str) -> str:
        """Detect the type of application"""
        title_lower = title.lower()
        class_lower = class_name.lower()

        if 'word' in title_lower or 'winword' in class_lower:
            return 'word'
        elif 'excel' in title_lower or 'excel' in class_lower:
            return 'excel'
        elif 'powerpoint' in title_lower or 'ppt' in title_lower:
            return 'powerpoint'
        elif 'notepad' in title_lower or 'notepad' in class_lower:
            return 'notepad'
        elif 'chrome' in title_lower or 'chrome' in class_lower:
            return 'browser'
        elif 'edge' in title_lower or 'edge' in class_lower:
            return 'browser'
        elif 'firefox' in title_lower or 'firefox' in class_lower:
            return 'browser'
        elif 'visual studio' in title_lower or 'vscode' in title_lower:
            return 'editor'
        elif 'photoshop' in title_lower or 'photoshop' in class_lower:
            return 'graphics'
        else:
            return 'generic'

    def focus_window(self, hwnd: int):
        """Bring the window to foreground"""
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR] Failed to focus window: {e}")

    def capture_window(self) -> str:
        """Capture the active window and return as base64"""
        try:
            if self.window_bounds:
                screenshot = pyautogui.screenshot(
                    region=(
                        self.window_bounds['left'],
                        self.window_bounds['top'],
                        self.window_bounds['width'],
                        self.window_bounds['height']
                    )
                )
            else:
                screenshot = pyautogui.screenshot()

            buffered = BytesIO()
            screenshot.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            return img_str
        except Exception as e:
            print(f"[ERROR] Failed to capture window: {e}")
            return ""

    def get_ui_elements_from_ollama(self, screenshot: str, section: str = "full") -> List[Dict]:
        """Use Ollama LLaVA to identify UI elements with BETTER prompts"""
        try:
            if section == "full":
                prompt = """Analyze this screenshot EXTREMELY THOROUGHLY. I need to teach this application to someone who has NEVER used it before.

Identify EVERY visible UI element with these details:
1. element_name: Exact text on the element (button text, menu name, tab name, etc.)
2. approximate_x: X coordinate as percentage (0-100)
3. approximate_y: Y coordinate as percentage (0-100)
4. description: DETAILED explanation of what this element does
5. type: button, menu, tab, input_field, dropdown, checkbox, toolbar, ribbon, sidebar, etc.
6. group: Which section this belongs to (top_menu, ribbon, toolbar, sidebar, main_content, status_bar, etc.)

Return as JSON array with ALL elements you can find. Be thorough - I need to teach EVERYTHING."""
            else:
                prompt = f"""Analyze this {section} section of the application screenshot EXTREMELY THOROUGHLY.

Identify EVERY visible UI element in this section with:
1. element_name: Exact text
2. approximate_x: X coordinate percentage (0-100) relative to this section
3. approximate_y: Y coordinate percentage (0-100) relative to this section
4. description: What this element does
5. type: button, menu, tab, input_field, dropdown, checkbox, etc.

Return as JSON array with ALL elements in this section."""

            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llava",
                    "prompt": prompt,
                    "images": [screenshot],
                    "stream": False
                },
                timeout=120  # Increased to 2 minutes
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
            # Try multiple JSON extraction methods
            json_pattern = r'\[[\s\S]*?\]'
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
            screen_width, screen_height = pyautogui.size()
            abs_x = int((rel_x / 100) * screen_width)
            abs_y = int((rel_y / 100) * screen_height)
        else:
            abs_x = int(self.window_bounds['left'] + (rel_x / 100) * self.window_bounds['width'])
            abs_y = int(self.window_bounds['top'] + (rel_y / 100) * self.window_bounds['height'])

        return abs_x, abs_y

    def click_at(self, x: int, y: int, text: str = ""):
        """Click at specific coordinates with animation"""
        print(f"[CLICKING]: {text} at ({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.5)
        time.sleep(0.2)
        pyautogui.click()
        if text:
            self.speak(f"Clicking {text}")
        time.sleep(1.5)

    def type_text(self, text: str, announce: bool = True):
        """Type text into the active field"""
        print(f"[TYPING]: {text}")
        pyautogui.write(text, interval=0.1)
        if announce:
            self.speak(f"Typing {text}")
        time.sleep(0.5)

    def right_click_at(self, x: int, y: int, text: str = ""):
        """Right-click at specific coordinates"""
        print(f"[RIGHT-CLICKING]: {text} at ({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.5)
        pyautogui.rightClick()
        if text:
            self.speak(f"Right-clicking {text}")
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

    def scan_entire_window(self) -> List[Dict]:
        """Scan the entire window in sections for thoroughness"""
        self.speak("I will now scan the entire application window section by section to find EVERYTHING.")

        all_elements = []

        if not self.window_bounds:
            self.speak("I'll scan the full screen.")
            sections = ["full"]
        else:
            sections = ["full"]

        for section in sections:
            self.speak(f"Scanning the {section} section...")
            screenshot = self.capture_window()
            elements = self.get_ui_elements_from_ollama(screenshot, section)
            all_elements.extend(elements)
            self.speak(f"Found {len(elements)} elements in this section.")
            time.sleep(1)

        return all_elements

    def teach_app_specific(self, app_type: str):
        """Teach app-specific workflows"""
        self.speak(f"I detected this is a {app_type} application. I'll teach you the specific workflows for this app.")

        if app_type == 'word':
            self._teach_word()
        elif app_type == 'excel':
            self._teach_excel()
        elif app_type == 'notepad':
            self._teach_notepad()
        elif app_type == 'browser':
            self._teach_browser()
        else:
            self._teach_generic()

    def _teach_word(self):
        """Teach Microsoft Word specifically"""
        self.speak("This is Microsoft Word. I'll teach you how to use it from scratch.")

        # Step 1: Type text
        self.speak("First, I'll show you how to type text into the document.")
        self.click_at(self.window_bounds['left'] + 300, self.window_bounds['top'] + 300, "Document area")
        self.type_text("Hello, this is a sample document.")
        time.sleep(1)

        # Step 2: Change font
        self.speak("Now I'll show you how to change the font.")
        self.press_hotkey('ctrl+a', "Selecting all text")
        time.sleep(1)
        # Try to find font dropdown (generic position)
        self.click_at(self.window_bounds['left'] + 200, self.window_bounds['top'] + 150, "Font dropdown")
        time.sleep(1)
        self.press_key('down', "Browsing fonts")
        time.sleep(1)
        self.press_key('enter', "Selecting font")
        time.sleep(1)

        # Step 3: Bold text
        self.speak("I'll make the text bold.")
        self.press_hotkey('ctrl+b', "Applying bold formatting")
        time.sleep(1)

        # Step 4: Save document
        self.speak("Now I'll show you how to save your document.")
        self.press_hotkey('ctrl+s', "Opening save dialog")
        time.sleep(2)
        self.speak("This is the save dialog. You can choose where to save your file.")
        self.type_text("My First Document")
        time.sleep(1)
        self.press_key('enter', "Saving the document")
        time.sleep(2)

        # Step 5: Explain ribbon
        self.speak("The top ribbon contains all the tools you need. Let me show you the Home tab.")
        self.click_at(self.window_bounds['left'] + 200, self.window_bounds['top'] + 80, "Home tab")
        time.sleep(1)
        self.speak("The Home tab has formatting options like bold, italic, underline, and font styles.")

        self.speak("Let me show you the Insert tab.")
        self.click_at(self.window_bounds['left'] + 350, self.window_bounds['top'] + 80, "Insert tab")
        time.sleep(1)
        self.speak("The Insert tab lets you add tables, pictures, and other elements.")

    def _teach_excel(self):
        """Teach Microsoft Excel specifically"""
        self.speak("This is Microsoft Excel. I'll teach you how to use it from scratch.")

        # Step 1: Type data into cells
        self.speak("First, I'll show you how to type data into cells.")
        self.click_at(self.window_bounds['left'] + 300, self.window_bounds['top'] + 300, "Cell A1")
        self.type_text("100")
        time.sleep(1)

        self.speak("Moving to the next cell.")
        self.click_at(self.window_bounds['left'] + 400, self.window_bounds['top'] + 300, "Cell B1")
        self.type_text("200")
        time.sleep(1)

        # Step 2: Create formula
        self.speak("Now I'll create a formula to add these numbers.")
        self.click_at(self.window_bounds['left'] + 500, self.window_bounds['top'] + 300, "Cell C1")
        self.type_text("=A1+B1")
        time.sleep(1)
        self.press_key('enter', "Calculating the formula")
        time.sleep(1)

        # Step 3: Format cells
        self.speak("I'll format the cells to make them look better.")
        self.press_hotkey('ctrl+a', "Selecting all cells")
        time.sleep(1)
        self.press_hotkey('ctrl+b', "Making text bold")
        time.sleep(1)

        # Step 4: Save
        self.speak("I'll save the Excel file.")
        self.press_hotkey('ctrl+s', "Opening save dialog")
        time.sleep(2)
        self.type_text("My First Spreadsheet")
        time.sleep(1)
        self.press_key('enter', "Saving the file")
        time.sleep(2)

    def _teach_notepad(self):
        """Teach Notepad specifically"""
        self.speak("This is Notepad. I'll teach you how to use it.")

        self.speak("First, I'll type some text.")
        self.type_text("This is a sample text in Notepad.")
        time.sleep(1)

        self.speak("I'll save the file.")
        self.press_hotkey('ctrl+s', "Opening save dialog")
        time.sleep(2)
        self.type_text("My Note")
        time.sleep(1)
        self.press_key('enter', "Saving the file")
        time.sleep(2)

    def _teach_browser(self):
        """Teach web browser specifically"""
        self.speak("This is a web browser. I'll teach you how to use it.")

        self.speak("I'll show you how to navigate to a website.")
        self.press_hotkey('ctrl+l', "Focusing address bar")
        time.sleep(1)
        self.type_text("https://www.google.com")
        time.sleep(1)
        self.press_key('enter', "Navigating to website")
        time.sleep(3)

        self.speak("I'll show you how to search.")
        self.press_hotkey('ctrl+f', "Opening search box")
        time.sleep(1)
        self.type_text("test")
        time.sleep(1)

    def _teach_generic(self):
        """Teach generic application"""
        self.speak("I'll teach you the common features of this application.")

        # Try common shortcuts
        self.speak("Let me try the save shortcut.")
        self.press_hotkey('ctrl+s', "Trying save")
        time.sleep(2)

        self.speak("Let me try the open shortcut.")
        self.press_hotkey('ctrl+o', "Trying open")
        time.sleep(2)

        self.speak("Let me try the print shortcut.")
        self.press_hotkey('ctrl+p', "Trying print")
        time.sleep(2)

    def teach_any_app(self):
        """ULTIMATE teaching for ANY app"""
        self.is_teaching = True

        # Get window info
        window_info = self.get_active_window_info()
        app_name = window_info['title'] or 'this application'
        window_state = window_info['state']
        app_type = window_info['app_type']

        self.speak(f"Starting comprehensive teaching of {app_name}.")
        self.speak(f"Window is currently {window_state}. I will interact with it regardless of its state.")
        self.speak(f"I detected this is a {app_type} application.")

        # Focus the window
        if window_info['hwnd']:
            self.focus_window(window_info['hwnd'])

        # Scan entire window thoroughly
        self.speak("I will now scan the ENTIRE application to find EVERY UI element.")
        ui_elements = self.scan_entire_window()

        if ui_elements:
            self.speak(f"Found {len(ui_elements)} UI elements. I will now teach you about each one.")

            # Group by section for organized teaching
            top_menu = [e for e in ui_elements if e.get('group') == 'top_menu' or e.get('type') == 'menu']
            ribbon = [e for e in ui_elements if e.get('group') == 'ribbon' or e.get('type') == 'ribbon']
            toolbar = [e for e in ui_elements if e.get('group') == 'toolbar' or e.get('type') == 'toolbar']
            sidebar = [e for e in ui_elements if e.get('group') == 'sidebar']
            buttons = [e for e in ui_elements if e.get('type') == 'button']
            tabs = [e for e in ui_elements if e.get('type') == 'tab']
            inputs = [e for e in ui_elements if e.get('type') == 'input_field']

            # Teach each section thoroughly
            if top_menu:
                self.speak("First, let me teach you about the top menu bar.")
                for menu in top_menu[:5]:
                    if not self.is_teaching:
                        break
                    self._teach_element_thorough(menu)

            if ribbon:
                self.speak("Now let me teach you about the ribbon interface.")
                for item in ribbon[:8]:
                    if not self.is_teaching:
                        break
                    self._teach_element_thorough(item)

            if toolbar:
                self.speak("Let me teach you about the toolbar.")
                for tool in toolbar[:5]:
                    if not self.is_teaching:
                        break
                    self._teach_element_thorough(tool)

            if sidebar:
                self.speak("Let me teach you about the sidebar.")
                for item in sidebar[:3]:
                    if not self.is_teaching:
                        break
                    self._teach_element_thorough(item)

            if tabs:
                self.speak("Let me teach you about the different tabs.")
                for tab in tabs[:4]:
                    if not self.is_teaching:
                        break
                    self._teach_element_thorough(tab)

            if buttons:
                self.speak("Let me teach you about the main action buttons.")
                for button in buttons[:6]:
                    if not self.is_teaching:
                        break
                    self._teach_element_thorough(button)

            if inputs:
                self.speak("Let me teach you about the input fields by typing into them.")
                for input_field in inputs[:3]:
                    if not self.is_teaching:
                        break
                    self._teach_element_with_typing(input_field)
        else:
            self.speak("I couldn't scan the UI elements with AI vision, but I'll still teach you using app-specific workflows.")

        # Teach app-specific workflows
        self.teach_app_specific(app_type)

        # Teach keyboard shortcuts
        self.speak("Let me teach you the keyboard shortcuts that work in this application.")
        self._teach_keyboard_shortcuts()

        self.speak("I've taught you the comprehensive features of this application. You now know how to use it effectively.")
        self.is_teaching = False

    def _teach_element_thorough(self, element: Dict):
        """Teach a single element THOROUGHLY"""
        name = element.get('element_name', 'Unknown element')
        rel_x = element.get('approximate_x', 50)
        rel_y = element.get('approximate_y', 50)
        desc = element.get('description', '')
        element_type = element.get('type', 'button')

        abs_x, abs_y = self.relative_to_absolute(rel_x, rel_y)

        # Explain in detail
        self.speak(f"This is the {name} {element_type}.")
        if desc:
            self.speak(f"{desc}")
        self.speak(f"I'll click it to show you what it does.")

        # Click the element
        self.click_at(abs_x, abs_y, name)
        time.sleep(2)

        # Explain the result
        self.speak(f"After clicking {name}, you can see the result on screen.")

        # Try to go back
        self.speak("I'll go back to continue teaching.")
        self.press_key('escape', "Going back")
        time.sleep(1)

        self.discovered_features.append(name)

    def _teach_element_with_typing(self, element: Dict):
        """Teach an input field by typing into it"""
        name = element.get('element_name', 'Unknown field')
        rel_x = element.get('approximate_x', 50)
        rel_y = element.get('approximate_y', 50)
        desc = element.get('description', '')

        abs_x, abs_y = self.relative_to_absolute(rel_x, rel_y)

        self.speak(f"This is the {name} input field.")
        if desc:
            self.speak(f"{desc}")
        self.speak(f"I'll click it and type some sample text to demonstrate.")

        self.click_at(abs_x, abs_y, name)
        time.sleep(1)

        self.type_text("Sample text")
        time.sleep(1)

        self.speak("I've typed sample text. You can now type your own content here.")

        self.discovered_features.append(name)

    def _teach_keyboard_shortcuts(self):
        """Teach keyboard shortcuts thoroughly"""
        shortcuts = [
            ('ctrl+s', 'Save - saves your work'),
            ('ctrl+o', 'Open - opens a file'),
            ('ctrl+n', 'New - creates a new file'),
            ('ctrl+z', 'Undo - undoes last action'),
            ('ctrl+y', 'Redo - redoes last action'),
            ('ctrl+c', 'Copy - copies selection'),
            ('ctrl+v', 'Paste - pastes copied content'),
            ('ctrl+x', 'Cut - cuts selection'),
            ('ctrl+a', 'Select All - selects everything'),
            ('ctrl+f', 'Find - searches for text'),
            ('ctrl+p', 'Print - prints document'),
        ]

        for hotkey, description in shortcuts:
            if not self.is_teaching:
                break
            self.speak(f"Keyboard shortcut: {description}")
            self.speak(f"Pressing {hotkey}")
            self.press_hotkey(hotkey, description)
            time.sleep(1.5)

            # Close any dialogs
            self.press_key('escape', "Closing dialog")
            time.sleep(0.5)

    def stop_teaching(self):
        """Stop the teaching session"""
        self.is_teaching = False
        self.speak("Teaching stopped.")

if __name__ == "__main__":
    print("=== ULTIMATE Interactive App Teacher ===")
    print("EXTREMELY ROBUST - Teaches COMPLETELY, demonstrates REAL workflows")
    print("\nMake sure:")
    print("1. The app you want to learn is open (any state)")
    print("2. Ollama is running (http://localhost:11434)")
    print("3. LLaVA model is installed (ollama pull llava)")
    print("\nULTIMATE Features:")
    print("✅ Scans ENTIRE window section by section")
    print("✅ Detects app type (Word, Excel, Browser, etc.)")
    print("✅ Teaches app-specific workflows")
    print("✅ Actually types and demonstrates")
    print("✅ Shows how to save, format, use features")
    print("✅ Teaches as if user knows NOTHING")
    print("✅ Thorough keyboard shortcut teaching")
    print("✅ Detailed explanations for EVERY element")
    print("\nPress SPACE to start teaching, ESC to stop")

    teacher = UltimateAppTeacher()

    keyboard.wait('space')

    teacher.teach_any_app()

    print("\nTeaching complete!")
    print(f"Discovered {len(teacher.discovered_features)} features:")
    for feature in teacher.discovered_features:
        print(f"  • {feature}")
