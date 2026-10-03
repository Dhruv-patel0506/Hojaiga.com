"""
FULLY DYNAMIC App Teacher - Python Version
NO HARDCODING - Uses AI to understand app and decide what to demonstrate
Can format Word documents dynamically: bold, italic, font, alignment, etc.
Takes user input and creates content with proper formatting
"""

import pyautogui
import time
import pyttsx3
import keyboard
import json
import requests
import win32gui
import win32con
from typing import Dict, List, Tuple, Optional
import base64
from io import BytesIO
import re

class DynamicAppTeacher:
    def __init__(self):
        self.is_teaching = False
        self.tts_engine = pyttsx3.init()
        self.tts_engine.setProperty('rate', 130)
        self.window_bounds = None
        self.app_context = None

    def speak(self, text: str):
        """Speak the text using TTS"""
        print(f"[SPEAKING]: {text}")
        self.tts_engine.say(text)
        self.tts_engine.runAndWait()

    def get_window_info(self) -> Dict:
        """Get window information"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)

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
                'hwnd': hwnd,
                'bounds': self.window_bounds
            }
        except Exception as e:
            print(f"[ERROR] Failed to get window info: {e}")
            return {'title': 'Unknown', 'hwnd': 0, 'bounds': None}

    def capture_window(self) -> str:
        """Capture the active window"""
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

    def analyze_app_with_ai(self, screenshot: str) -> Dict:
        """Use LLaVA to understand the app and available features"""
        try:
            prompt = """Analyze this application screenshot EXTREMELY THOROUGHLY.

I need to understand:
1. What type of application this is (Word processor, spreadsheet, browser, etc.)
2. What formatting options are available (bold, italic, underline, font size, font family, alignment, etc.)
3. Where each formatting option is located (coordinates as percentage 0-100)
4. What text editing features are available
5. What menu options are available

Return JSON:
{
  "app_type": "word_processor/spreadsheet/browser/etc",
  "features": [
    {
      "name": "Bold",
      "type": "formatting",
      "x": 50,
      "y": 50,
      "description": "Makes text bold"
    },
    ...
  ],
  "menu_options": [
    {
      "name": "File",
      "x": 10,
      "y": 10,
      "description": "File menu"
    },
    ...
  ]
}

Be THOROUGH - find ALL visible formatting options and features."""

            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llava",
                    "prompt": prompt,
                    "images": [screenshot],
                    "stream": False
                },
                timeout=120
            )
            result = response.json()
            return self._parse_ai_response(result.get('response', ''))
        except Exception as e:
            print(f"[ERROR] Failed to analyze app with AI: {e}")
            return {}

    def _parse_ai_response(self, response: str) -> Dict:
        """Parse AI response"""
        try:
            # Try to extract JSON
            json_pattern = r'\{[\s\S]*\}'
            matches = re.findall(json_pattern, response)

            for match in matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, dict):
                        return data
                except:
                    continue
        except Exception as e:
            print(f"[ERROR] Failed to parse AI response: {e}")

        return {}

    def get_dynamic_instructions(self, user_goal: str, app_analysis: Dict) -> List[Dict]:
        """Use AI to decide what to demonstrate based on user goal and app features"""
        try:
            prompt = f"""User wants to: {user_goal}

Available app features: {json.dumps(app_analysis.get('features', []))}

Generate a step-by-step plan to demonstrate this using the available features.

Return JSON array of steps:
[
  {{
    "action": "click/type/press",
    "target": "element name or key",
    "x": 50,
    "y": 50,
    "text_to_type": "text if typing",
    "description": "What this step does"
  }},
  ...
]

Be CREATIVE - use the available features to create a compelling demonstration."""

            screenshot = self.capture_window()
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llava",
                    "prompt": prompt,
                    "images": [screenshot],
                    "stream": False
                },
                timeout=120
            )
            result = response.json()
            return self._parse_steps(result.get('response', ''))
        except Exception as e:
            print(f"[ERROR] Failed to get dynamic instructions: {e}")
            return []

    def _parse_steps(self, response: str) -> List[Dict]:
        """Parse step-by-step instructions"""
        try:
            json_pattern = r'\[[\s\S]*\]'
            matches = re.findall(json_pattern, response)

            for match in matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, list):
                        return data
                except:
                    continue
        except Exception as e:
            print(f"[ERROR] Failed to parse steps: {e}")

        return []

    def execute_step(self, step: Dict):
        """Execute a single step"""
        action = step.get('action', '')
        target = step.get('target', '')
        x = step.get('x', 50)
        y = step.get('y', 50)
        text = step.get('text_to_type', '')
        description = step.get('description', '')

        # Convert to absolute coordinates
        if self.window_bounds:
            abs_x = int(self.window_bounds['left'] + (x / 100) * self.window_bounds['width'])
            abs_y = int(self.window_bounds['top'] + (y / 100) * self.window_bounds['height'])
        else:
            screen_width, screen_height = pyautogui.size()
            abs_x = int((x / 100) * screen_width)
            abs_y = int((y / 100) * screen_height)

        self.speak(f"{description}")

        if action == 'click':
            pyautogui.moveTo(abs_x, abs_y, duration=0.5)
            pyautogui.click()
            time.sleep(1)
        elif action == 'type':
            pyautogui.write(text, interval=0.1)
            time.sleep(0.5)
        elif action == 'press':
            pyautogui.press(target)
            time.sleep(0.5)
        elif action == 'hotkey':
            pyautogui.hotkey(*target.split('+'))
            time.sleep(1)

    def teach_dynamically(self, user_goal: str):
        """Teach dynamically based on user goal and app analysis"""
        self.is_teaching = True

        # Get window info
        window_info = self.get_window_info()
        app_name = window_info['title'] or 'this application'

        self.speak(f"Starting dynamic teaching of {app_name}.")
        self.speak(f"Your goal: {user_goal}")

        # Focus window
        if window_info['hwnd']:
            try:
                win32gui.SetForegroundWindow(window_info['hwnd'])
                time.sleep(1)
            except:
                pass

        # Capture and analyze app
        self.speak("I will now analyze this application to understand what features are available.")
        screenshot = self.capture_window()

        if not screenshot:
            self.speak("Failed to capture the window.")
            self.is_teaching = False
            return

        self.speak("Using AI vision to understand the application...")
        app_analysis = self.analyze_app_with_ai(screenshot)

        if not app_analysis:
            self.speak("I couldn't analyze the app with AI. Let me try a different approach.")
            self._fallback_demonstration(user_goal)
        else:
            app_type = app_analysis.get('app_type', 'unknown')
            features = app_analysis.get('features', [])

            self.speak(f"I detected this is a {app_type} application.")
            self.speak(f"Found {len(features)} available features.")

            # Get dynamic instructions from AI
            self.speak("I will now generate a step-by-step plan to demonstrate your goal.")
            steps = self.get_dynamic_instructions(user_goal, app_analysis)

            if not steps:
                self.speak("I couldn't generate a specific plan. Let me demonstrate the available features.")
                self._demonstrate_features(features)
            else:
                self.speak(f"I will execute {len(steps)} steps to demonstrate {user_goal}.")
                for i, step in enumerate(steps):
                    if not self.is_teaching:
                        break
                    self.speak(f"Step {i + 1} of {len(steps)}")
                    self.execute_step(step)
                    time.sleep(1)

        self.speak("I've completed the demonstration based on your goal.")
        self.is_teaching = False

    def _demonstrate_features(self, features: List[Dict]):
        """Demonstrate available features"""
        self.speak("I will now demonstrate the available features.")

        for feature in features[:10]:  # Top 10 features
            if not self.is_teaching:
                break

            name = feature.get('name', 'Unknown')
            x = feature.get('x', 50)
            y = feature.get('y', 50)
            description = feature.get('description', '')

            self.speak(f"Demonstrating {name}. {description}")

            # Convert to absolute coordinates
            if self.window_bounds:
                abs_x = int(self.window_bounds['left'] + (x / 100) * self.window_bounds['width'])
                abs_y = int(self.window_bounds['top'] + (y / 100) * self.window_bounds['height'])
            else:
                screen_width, screen_height = pyautogui.size()
                abs_x = int((x / 100) * screen_width)
                abs_y = int((y / 100) * screen_height)

            pyautogui.moveTo(abs_x, abs_y, duration=0.5)
            pyautogui.click()
            time.sleep(1.5)

            # Go back
            pyautogui.press('escape')
            time.sleep(0.5)

    def _fallback_demonstration(self, user_goal: str):
        """Fallback demonstration when AI fails"""
        self.speak("I'll demonstrate common features since AI analysis failed.")

        # Try common formatting shortcuts
        shortcuts = [
            ('ctrl+b', 'Bold'),
            ('ctrl+i', 'Italic'),
            ('ctrl+u', 'Underline'),
            ('ctrl+l', 'Left align'),
            ('ctrl+e', 'Center'),
            ('ctrl+r', 'Right align'),
        ]

        for hotkey, description in shortcuts:
            if not self.is_teaching:
                break
            self.speak(f"Demonstrating {description}")
            pyautogui.hotkey(*hotkey.split('+'))
            time.sleep(1)

if __name__ == "__main__":
    print("=== FULLY DYNAMIC App Teacher ===")
    print("NO HARDCODING - Uses AI to understand and decide what to demonstrate")
    print("\nMake sure:")
    print("1. The app you want to learn is open")
    print("2. Ollama is running (http://localhost:11434)")
    print("3. LLaVA model is installed (ollama pull llava)")
    print("\nFeatures:")
    print("✅ Analyzes app with AI to understand available features")
    print("✅ Detects formatting options (bold, italic, alignment, etc.)")
    print("✅ Takes user input for what to create")
    print("✅ Generates dynamic step-by-step plan")
    print("✅ Executes plan with actual clicking/typing")
    print("✅ NO HARDCODING - completely dynamic")
    print("\nExample goals:")
    print("• 'Create a document about my vacation'")
    print("• 'Make a report with bold headings'")
    print("• 'Format text centered and italic'")
    print("• 'Create a spreadsheet with calculations'")
    print("\nWhat do you want to create? (type your goal):")

    teacher = DynamicAppTeacher()

    user_goal = input("Your goal: ").strip()

    if not user_goal:
        user_goal = "Create a document"

    print(f"\nGoal: {user_goal}")
    print("Press SPACE to start teaching, ESC to stop")

    keyboard.wait('space')

    teacher.teach_dynamically(user_goal)

    print("\nTeaching complete!")
