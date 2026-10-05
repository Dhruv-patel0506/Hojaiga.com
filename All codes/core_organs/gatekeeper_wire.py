"""
gatekeeper_wire.py — Hojaiga Common Wire Box
Wires pyautogui + BeautifulSoup + Selenium into a single intelligence bus
that attaches to Brain_Gatekeeper (11435) for small-brain + eye.

All three tools live in one box with one common wire to the Gatekeeper.
Master helper (small brain = llama3, eye = qwen2.5vl:3b) uses this wire
to understand screen and remove popups.

Vision model hierarchy: qwen2.5vl:3b (fast, OCR) → minicpm-v (OCR) → moondream (fallback).
Window activation: Eye always activates target window before screenshots.

Usage:
    from core_organs.gatekeeper_wire import WireBox
    box = WireBox()
    box.attach()  # wire ready
    shot = box.screenshot_b64(max_size=512)  # pyautogui
    dom = box.parse_html(html)               # bs4
    el = box.selenium_find(driver, "button") # selenium
    answer = box.ask_gatekeeper("what popup is this?", image_b64=shot)
    box.screenshot_b64(activate="Chrome")    # activates Chrome first
"""

from __future__ import annotations
import base64
import io
import json
import time
import logging
import urllib.request
from typing import Optional, Dict, Any

logger = logging.getLogger("hojaiga.wire_box")

# soft imports - box works even if one tool missing
try:
    import pyautogui  # type: ignore
    _HAS_PYAUTOGUI = True
except Exception:
    pyautogui = None  # type: ignore
    _HAS_PYAUTOGUI = False

try:
    from bs4 import BeautifulSoup  # type: ignore
    _HAS_BS4 = True
except Exception:
    BeautifulSoup = None  # type: ignore
    _HAS_BS4 = False

try:
    from selenium.webdriver.common.by import By  # type: ignore
    from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
    from selenium.webdriver.support import expected_conditions as EC  # type: ignore
    _HAS_SELENIUM = True
except Exception:
    By = None  # type: ignore
    _HAS_SELENIUM = False

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    from mss import mss  # type: ignore
    _HAS_CV2 = True
except Exception:
    cv2 = np = mss = None  # type: ignore
    _HAS_CV2 = False

try:
    from PIL import Image  # type: ignore
    from io import BytesIO  # type: ignore
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

GATEKEEPER_URL = "http://127.0.0.1:11435"
GATEKEEPER_SECRET = "339680"

# --- Window activation: bring target app to foreground before Eye sees ---
try:
    import ctypes
    user32 = ctypes.windll.user32
    _HAS_CTYPES = True
except Exception:
    _HAS_CTYPES = False

def activate_window(title_contains: str = "Chrome") -> bool:
    """Bring a window whose title contains `title_contains` to foreground.
    Returns True if a matching window was found and activated.
    Used by Eye before screenshots so it always sees the right app.
    """
    if not _HAS_CTYPES:
        return False
    found = [None]
    def _enum(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if title_contains.lower() in buf.value.lower():
                found[0] = hwnd
                return False
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(_enum), 0)
    if found[0]:
        user32.SetForegroundWindow(found[0])
        time.sleep(0.3)
        logger.info("[WireBox] activated window containing '%s'", title_contains)
        return True
    logger.debug("[WireBox] no window containing '%s' found", title_contains)
    return False

# Model hierarchy — vision: qwen2.5vl (fast, OCR) → minicpm-v (precision OCR) → moondream (fallback)
# Text reasoning: llama3. Heavy vision: minicpm-v (5.5GB, fits in 6GB VRAM).
VISION_MODELS = ["qwen2.5vl:3b", "minicpm-v", "moondream"]
VISION_MODEL = VISION_MODELS[0]  # primary for backward compat
BRAIN_MODEL = "llama3"
HEAVY_VISION_MODEL = "minicpm-v"  # 5.5GB, fits in 6GB VRAM, excellent OCR

class WireBox:
    """One box, three tools, one common wire to Gatekeeper. Hybrid: cv2 15ms fast path → moondream 0.8s fallback."""

    def __init__(self, gatekeeper_url: str = GATEKEEPER_URL, secret: str = GATEKEEPER_SECRET):
        self.gatekeeper_url = gatekeeper_url
        self.secret = secret
        self._attached = False
        self.templates: Dict[str, Any] = {}  # ui_name -> gray template np array

    def register_known_ui(self, ui_name: str, template_path: str) -> bool:
        """Pre-loads known icons (e.g., Chrome menu, Blender tool) for 15ms hit."""
        if not _HAS_CV2:
            logger.warning("cv2 not available for %s", template_path)
            return False
        try:
            img = cv2.imread(template_path, 0)  # type: ignore
            if img is not None:
                self.templates[ui_name] = img
                logger.info("[WireBox] registered template %s %s", ui_name, template_path)
                return True
        except Exception as e:
            logger.debug("register fail %s", e)
        return False

    def _fast_path_opencv(self, template_img, threshold: float = 0.8):
        """15ms spatial pixel match — mss + cv2.matchTemplate."""
        if not _HAS_CV2:
            return None
        try:
            with mss() as sct:  # type: ignore
                monitor = sct.monitors[1]
                screenshot = np.array(sct.grab(monitor))  # type: ignore
                gray = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)  # type: ignore
                result = cv2.matchTemplate(gray, template_img, cv2.TM_CCOEFF_NORMED)  # type: ignore
                loc = np.where(result >= threshold)  # type: ignore
                for pt in zip(*loc[::-1]):
                    h, w = template_img.shape
                    return (pt[0] + w // 2, pt[1] + h // 2)
        except Exception as e:
            logger.debug("fast path fail %s", e)
        return None

    def _slow_path_vision(self, semantic_prompt: str, activate: str = None) -> Optional[str]:
        """Semantic fallback via Gatekeeper vision models (mss screenshot → gatekeeper).
        If `activate` is given, brings that window to foreground first.
        """
        try:
            b64 = self.screenshot_b64(max_size=768, activate=activate)
            if not b64:
                return None
            logger.info("[WireBox] slow path vision for '%s'", semantic_prompt)
            return self.eye_describe_raw(b64, semantic_prompt)
        except Exception as e:
            logger.debug("slow path fail %s", e)
            return None

    def eye_describe_raw(self, image_b64: str, question: str) -> str:
        """Direct eye call — tries qwen2.5vl (fast) → minicpm-v (precision) → moondream (fallback)."""
        return self.ask_gatekeeper(question, image_b64=image_b64)

    def attach(self) -> bool:
        """Wire ready — verify Gatekeeper reachable. Auto-starts if offline."""
        try:
            req = urllib.request.Request(
                f"{self.gatekeeper_url}/api/tags",
                headers={"X-Hojaiga-Validation": self.secret},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=2) as r:
                self._attached = r.status == 200
        except Exception:
            # Gatekeeper not running — auto-launch it
            logger.info("[WireBox] Gatekeeper offline, auto-launching...")
            self._launch_gatekeeper()
            time.sleep(4)
            try:
                req = urllib.request.Request(
                    f"{self.gatekeeper_url}/api/tags",
                    headers={"X-Hojaiga-Validation": self.secret},
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=3) as r:
                    self._attached = r.status == 200
            except Exception:
                self._attached = True  # proceed anyway — may still be starting
        # Ensure virtual mouse is online
        if virtual_mouse is not None and not virtual_mouse.is_online():
            virtual_mouse.start()
            logger.info("[WireBox] virtual mouse daemon started")
        logger.info("[WireBox] attached=%s pyautogui=%s bs4=%s selenium=%s virtual_mouse=%s",
                     self._attached, _HAS_PYAUTOGUI, _HAS_BS4, _HAS_SELENIUM,
                     virtual_mouse.is_online() if virtual_mouse else False)
        return self._attached

    def _launch_gatekeeper(self):
        """Launch Brain_Gatekeeper.py in background if not already running."""
        import subprocess, os
        gatekeeper_script = os.path.join(os.path.dirname(__file__), "..", "..", "Brain_Gatekeeper.py")
        gatekeeper_script = os.path.normpath(gatekeeper_script)
        if not os.path.exists(gatekeeper_script):
            # fallback: try from All codes directory
            gatekeeper_script = r"D:\new_automation\Brain_Gatekeeper.py"
        try:
            subprocess.Popen(
                ["python", gatekeeper_script],
                cwd=os.path.dirname(gatekeeper_script),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            logger.info("[WireBox] launched Gatekeeper from %s", gatekeeper_script)
        except Exception as e:
            logger.warning("[WireBox] failed to launch Gatekeeper: %s", e)

    # --- Tool 1: pyautogui ---
    def screenshot_b64(self, max_size: int = 512, activate: str = None) -> str:
        """pyautogui screenshot → base64 PNG thumbnail for eye.
        If `activate` is given (e.g. "Chrome"), brings that window to foreground first.
        """
        if activate:
            activate_window(activate)
        if not _HAS_PYAUTOGUI:
            return ""
        try:
            from PIL import ImageGrab  # pyautogui uses pillow
            shot = ImageGrab.grab()
            shot.thumbnail((max_size, max_size))
            buf = io.BytesIO()
            shot.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            logger.debug("screenshot fail %s", e)
            return ""

    def pyautogui_click(self, x: int, y: int):
        """Removed (backlog 1.1): a pyautogui click moves the user's real pointer. Click through headless_input.post_click
        (a posted message to a target window) or a UIA pattern. Kept so an old caller gets an honest False, not a crash."""
        return False

    # --- Tool 2: BeautifulSoup ---
    def parse_html(self, html: str, selector: str = "") -> Any:
        """bs4 parse → soup or selected nodes."""
        if not _HAS_BS4 or not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        if selector:
            return soup.select(selector)
        return soup

    def extract_text(self, html: str) -> str:
        soup = self.parse_html(html)
        return soup.get_text(" ", strip=True)[:4000] if soup else ""

    # --- Tool 3: Selenium ---
    def selenium_find(self, driver, css: str, timeout: int = 3):
        if not _HAS_SELENIUM or driver is None:
            return None
        try:
            return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
        except Exception:
            return None

    def selenium_click(self, driver, css: str) -> bool:
        el = self.selenium_find(driver, css)
        if el:
            try:
                el.click()
                return True
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", el)
                    return True
                except Exception:
                    return False
        return False

    # --- Common wire to Gatekeeper (small brain + eye) ---
    def ask_gatekeeper(self, prompt: str, image_b64: str = "", model: str = "", fallback: bool = True) -> str:
        """Small brain (llama3) or eye (vision models) via Gatekeeper.
        When image_b64 is provided and no explicit model, tries vision models in order:
        qwen2.5vl:3b → minicpm-v → moondream.
        Set fallback=False to use only the specified/primary model.
        """
        if model:
            models_to_try = [model]
        elif image_b64 and fallback:
            models_to_try = VISION_MODELS
        elif image_b64:
            models_to_try = [VISION_MODEL]
        else:
            models_to_try = [BRAIN_MODEL]

        for use_model in models_to_try:
            payload = json.dumps({
                "model": use_model,
                "messages": [{"role": "user", "content": prompt, **({"images": [image_b64]} if image_b64 else {})}],
                "stream": False,
            }).encode()
            req = urllib.request.Request(
                f"{self.gatekeeper_url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json", "X-Hojaiga-Validation": self.secret},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read())
                    result = data.get("message", {}).get("content", "")
                    if result:
                        logger.info("[WireBox] model %s responded OK", use_model)
                        return result
                    logger.debug("[WireBox] model %s returned empty, trying next", use_model)
            except Exception as e:
                logger.debug("[WireBox] model %s failed: %s", use_model, e)
        return ""

    def eye_describe(self, image_b64: str = "", question: str = "what popup is this and which button dismisses it?", known_ui_name: str = None, semantic_prompt: str = None, activate: str = None) -> Any:
        """Hybrid routing: cv2 fast path (15ms) → vision models slow fallback.
        Vision model hierarchy: qwen2.5vl:3b (fast, OCR) → minicpm-v (precision OCR) → moondream (fallback).
        If `activate` is given (e.g. "Chrome"), brings that window to foreground before Eye sees.
        """
        # 1. FAST PATH: known template
        if known_ui_name and known_ui_name in self.templates:
            import time as _t
            start = _t.time()
            coords = self._fast_path_opencv(self.templates[known_ui_name])
            if coords:
                logger.info("[WireBox] fast hit %s in %.1fms -> %s", known_ui_name, (_t.time()-start)*1000, coords)
                return {"source": "cv2", "coords": coords, "status": "found"}
            else:
                logger.info("[WireBox] template %s not found (UI drift)", known_ui_name)
        # 2. SLOW PATH: semantic via vision models
        if image_b64 or semantic_prompt:
            if image_b64:
                return self.ask_gatekeeper(question, image_b64=image_b64)
            if semantic_prompt:
                b64 = self.screenshot_b64(max_size=768, activate=activate)
                return self.ask_gatekeeper(semantic_prompt, image_b64=b64)
        # legacy: image_b64 + question
        if image_b64:
            return self.ask_gatekeeper(question, image_b64=image_b64)
        return {"status": "failed", "reason": "No target provided"}

    def eye_describe_compat(self, image_b64: str, question: str = "what popup is this and which button dismisses it?") -> str:
        """Back-compat string return."""
        res = self.eye_describe(image_b64=image_b64, question=question)
        if isinstance(res, dict):
            return res.get("data", "") or res.get("coords", "") or ""
        return res or ""

    def brain_decide(self, eye_text: str, prompt: str = "") -> str:
        q = prompt or f"Popup text: {eye_text}. Which button closes it safely (OK, Cancel, Close, No)? Reply ONLY button text."
        return self.ask_gatekeeper(q, model=BRAIN_MODEL).strip()

    # --- Master helper: eye + brain popup removal (hybrid) ---
    def handle_popup(self, image_b64: str = "", fallback_text: str = "", known_ui_name: str = None, activate: str = None) -> str:
        """Hybrid: try cv2 coords for known UI, else eye+brain. Returns coords or button name.
        If `activate` is given (e.g. "Chrome"), brings that window to foreground before Eye sees.
        """
        # fast path for known UI
        if known_ui_name:
            res = self.eye_describe(known_ui_name=known_ui_name)
            if isinstance(res, dict) and res.get("status") == "found":
                return res  # caller can funnel coords to CDP/UIA
        if not image_b64:
            image_b64 = self.screenshot_b64(activate=activate)
        eye_text = self.eye_describe(image_b64, activate=activate) if image_b64 else fallback_text
        # eye_describe may return dict for hybrid, unwrap
        if isinstance(eye_text, dict):
            eye_text = eye_text.get("data", "") or str(eye_text)
        if not eye_text:
            eye_text = fallback_text or "unknown popup"
        decision = self.brain_decide(str(eye_text))
        for cand in ["cancel", "close", "no", "ok", "dismiss"]:
            if cand in decision.lower():
                return cand.capitalize()
        return "Cancel"

# persistent virtual mouse — always online, any surface
try:
    from core_organs.virtual_mouse_service import virtual_mouse
except Exception:
    virtual_mouse = None  # type: ignore

# cookie vault re-export for agents — from core_organs.cookie_vault import vault_path, save_cookies_selenium
try:
    from core_organs.cookie_vault import vault_path, save_cookies_selenium, load_cookies_selenium
except Exception:
    vault_path = save_cookies_selenium = load_cookies_selenium = None  # type: ignore

# singleton for orchestrator/cdp/dap to import
wire_box = WireBox()

def attach_cdp_invoker(invoker):
    """Wire CDP invoker to virtual mouse — called by organ_19 after CDP connection.
    The invoker is an async function(session_id, method, params) that sends CDP commands.
    """
    if virtual_mouse is not None:
        virtual_mouse.attach_cdp(invoker)
        logger.info("[WireBox] CDP invoker attached to virtual mouse")

# backward compat alias
_attach_virtual_mouse_cdp = attach_cdp_invoker
