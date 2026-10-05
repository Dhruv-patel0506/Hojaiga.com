"""
Vision-Based UI State Detection - "Sensory Next" Mechanism
Captures screenshots and uses vision models to evaluate current UI state
Implements adaptive branching for manual user intervention handling
"""

import mss
import mss.tools
from PIL import Image
import io
import time
from typing import Optional, Literal
import httpx
import json

class VisionStateDetector:
    """Vision-based UI state detection with adaptive behavior"""
    
    def __init__(self, ollama_host: str = "http://127.0.0.1:11434"):
        """
        Initialize vision state detector
        
        Args:
            ollama_host: Ollama API endpoint for vision model
        """
        self.ollama_host = ollama_host
        self.sct = mss.mss()
        self.last_screenshot: Optional[bytes] = None
        self.last_capture_time: float = 0
    
    def capture_screen(self, monitor: Optional[dict] = None) -> bytes:
        """
        Capture the current screen state
        
        Args:
            monitor: Monitor to capture (None for primary monitor)
            
        Returns:
            Screenshot as PNG bytes
        """
        if monitor is None:
            monitor = self.sct.monitors[1]  # Primary monitor
        
        # Capture screenshot
        screenshot = self.sct.grab(monitor)
        
        # Convert to PNG bytes
        img_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
        
        self.last_screenshot = img_bytes
        self.last_capture_time = time.time()
        
        print(f"[VisionState] Screen captured: {len(img_bytes)} bytes")
        return img_bytes
    
    def capture_screen_as_pil(self, monitor: Optional[dict] = None) -> Image.Image:
        """
        Capture screen and return as PIL Image
        
        Args:
            monitor: Monitor to capture (None for primary monitor)
            
        Returns:
            PIL Image object
        """
        if monitor is None:
            monitor = self.sct.monitors[1]
        
        screenshot = self.sct.grab(monitor)
        img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
        
        print(f"[VisionState] Screen captured as PIL: {img.size}")
        return img
    
    def evaluate_state_with_vision(
        self,
        goal: str,
        expected_state: str,
        screenshot: Optional[bytes] = None,
        model: str = "llava:latest"
    ) -> dict:
        """
        Use vision model to evaluate if expected state is achieved
        
        Args:
            goal: Current goal (e.g., "open the new document")
            expected_state: Expected state description
            screenshot: Screenshot bytes (captures new if None)
            model: Vision model to use
            
        Returns:
            Dict with 'achieved' (bool) and 'explanation' (str)
        """
        if screenshot is None:
            screenshot = self.capture_screen()
        
        # Encode screenshot as base64
        import base64
        img_base64 = base64.b64encode(screenshot).decode('utf-8')
        
        # Construct prompt for vision model
        prompt = f"""
You are a UI state detector. Analyze this screenshot and answer:

GOAL: {goal}
EXPECTED STATE: {expected_state}

QUESTION: Based on this screenshot, is the expected state already achieved?

Reply with ONLY valid JSON in this format:
{{
  "achieved": true/false,
  "explanation": "Brief explanation of what you see"
}}
"""
        
        try:
            # Call Ollama vision API
            response = httpx.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "images": [img_base64],
                    "stream": False,
                    "format": "json"
                },
                timeout=30
            )
            
            result = response.json()
            vision_response = json.loads(result.get("response", "{}"))
            
            achieved = vision_response.get("achieved", False)
            explanation = vision_response.get("explanation", "No explanation provided")
            
            print(f"[VisionState] Vision evaluation: achieved={achieved}, explanation={explanation}")
            
            return {
                "achieved": achieved,
                "explanation": explanation
            }
            
        except Exception as e:
            print(f"[VisionState] Vision evaluation failed: {e}")
            # Fallback: assume not achieved
            return {
                "achieved": False,
                "explanation": f"Vision check failed: {str(e)}"
            }
    
    def detect_ui_change(
        self,
        previous_screenshot: Optional[bytes] = None,
        threshold: float = 0.1
    ) -> bool:
        """
        Detect if UI has changed significantly since last capture
        
        Args:
            previous_screenshot: Previous screenshot (uses last capture if None)
            threshold: Change threshold (0.0 to 1.0)
            
        Returns:
            True if UI changed significantly
        """
        if previous_screenshot is None:
            if self.last_screenshot is None:
                previous_screenshot = self.capture_screen()
            else:
                previous_screenshot = self.last_screenshot
        
        current_screenshot = self.capture_screen()
        
        # Simple comparison: check if sizes differ
        if len(previous_screenshot) != len(current_screenshot):
            print("[VisionState] UI changed: screenshot size differs")
            return True
        
        # More sophisticated comparison could use image diff
        # For now, assume no change if same size
        print("[VisionState] UI appears unchanged")
        return False
    
    def adaptive_action_decision(
        self,
        goal: str,
        current_action: str,
        screenshot: Optional[bytes] = None,
        model: str = "llava:latest"
    ) -> Literal["proceed", "skip", "reassess"]:
        """
        Adaptive decision: should we proceed with action or skip it?
        
        Args:
            goal: Current goal
            current_action: Action we're about to perform
            screenshot: Current screenshot
            model: Vision model to use
            
        Returns:
            "proceed" - execute the action
            "skip" - goal already achieved, skip this action
            "reassess" - state unclear, reassess from scratch
        """
        if screenshot is None:
            screenshot = self.capture_screen()
        
        # Check if goal is already achieved
        evaluation = self.evaluate_state_with_vision(
            goal=goal,
            expected_state=f"After: {current_action}",
            screenshot=screenshot,
            model=model
        )
        
        if evaluation["achieved"]:
            print(f"[VisionState] Goal already achieved, skipping action: {current_action}")
            return "skip"
        
        # Check if we're in an unexpected state
        unexpected_evaluation = self.evaluate_state_with_vision(
            goal=goal,
            expected_state="User manually intervened or state changed unexpectedly",
            screenshot=screenshot,
            model=model
        )
        
        if unexpected_evaluation["achieved"]:
            print("[VisionState] Unexpected state detected, need to reassess")
            return "reassess"
        
        # Proceed with action
        print(f"[VisionState] Proceeding with action: {current_action}")
        return "proceed"


# Example usage
if __name__ == "__main__":
    detector = VisionStateDetector()
    
    # Capture screen
    screenshot = detector.capture_screen()
    
    # Evaluate if a document is open
    result = detector.evaluate_state_with_vision(
        goal="open a new document",
        expected_state="A blank document is visible in the editor",
        screenshot=screenshot
    )
    
    print(f"Result: {result}")
    
    # Adaptive decision
    decision = detector.adaptive_action_decision(
        goal="open a new document",
        current_action="Click File menu",
        screenshot=screenshot
    )
    
    print(f"Decision: {decision}")
