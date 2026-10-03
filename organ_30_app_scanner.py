"""
organ_30_app_scanner.py
Hojaiga Automation OS — Universal Desktop UI & Webapp Crawler / Scanner Organ.

Universally handles:
- Native Win32 apps (C++, standard Win32 dialogs #32770, menus)
- Qt/Qt6 apps (OBS Studio benchmark, custom-drawn menus, multi-dock panels, child dialogs)
- WinUI 3 / XAML / UWP apps (Windows 11 Notepad, Calculator, Settings, ContentDialog, flyouts)
- WPF applications (Ribbon, floating toolbars, custom panels)
- Chromium, Electron, and Web applications (Chrome, Edge, VS Code, Teams, Slack, web DOMs in DocumentControl)

Dependencies: uiautomation, pywin32, pyautogui
    pip install uiautomation pywin32 pyautogui
"""

from __future__ import annotations

import concurrent.futures
import ctypes
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

_DESKTOP_ATTACHED = False

def ensure_interactive_desktop():
    """Ensures calling thread is attached to the active interactive input desktop."""
    global _DESKTOP_ATTACHED
    if _DESKTOP_ATTACHED:
        return
    try:
        user32 = ctypes.windll.user32
        hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if not hdesk:
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk:
            if user32.SetThreadDesktop(hdesk):
                _DESKTOP_ATTACHED = True
    except Exception:
        pass

# Attach to interactive desktop immediately before initializing COM/UIA
ensure_interactive_desktop()

try:
    import uiautomation as auto
    # Guard against COM query stalls on non-responsive controls
    auto.SetGlobalSearchTimeout(1.0)
    auto.TIME_OUT_SECOND = 1.0
except ImportError:
    auto = None

try:
    import win32api
    import win32con
    import win32gui
    import win32process
except ImportError:
    win32api = win32con = win32gui = win32process = None

# --------------------------------------------------------------------------- #
# Integration stubs (fallback mocks if real organs are absent)
# --------------------------------------------------------------------------- #
try:
    from core_organs.database_manager import DatabaseManager
except ImportError:
    class DatabaseManager:
        """Fallback mock. Real impl lazily opens self._conn on first use."""
        def __init__(self):
            self._conn = None
            self._cache: Dict[str, Any] = {}

        def _safe_call(self, func, *args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logging.getLogger("organ_30").warning("DB call failed: %s", e)
                return None

        def get_modal_resolution(self, key: str):
            return self._safe_call(lambda: self._cache.get(key))

        def store_modal_resolution(self, key: str, value: Any):
            self._safe_call(lambda: self._cache.__setitem__(key, value))

        def generate_layout_hash(self, name: str) -> str:
            return hashlib.md5((name or "layout").encode("utf-8")).hexdigest()[:16]

        def log_new_pathway(self, layout_hash: str, element_name: str, x: int, y: int, action_type: str, parent_path: str):
            pass

try:
    from core_organs.cns_bridge import CNSPopupInterceptor
except ImportError:
    class CNSPopupInterceptor:
        """Fallback mock CNS alert bridge."""
        def __init__(self, role: str = "AppAgent", port: int = 11436):
            self.role = role
            self.port = port
        def start(self, on_popup_detected=None): pass
        def alert_popup_detected(self, title: str, layout_hash: str, x: int, y: int) -> str:
            logging.getLogger("organ_30").info("[CNS-MOCK] Popup alert: %s at (%d, %d)", title, x, y)
            return f"mock_{int(time.time()*1000)}"
        def wait_for_resolution(self, popup_id: str, timeout: float = 10.0) -> Optional[Dict]:
            return {"type": "POPUP_RESOLUTION", "popup_id": popup_id, "action": "dismiss", "x": 0, "y": 0}
        def send_resolution(self, popup_id: str, action: str, x: int, y: int): pass
        def stop(self): pass

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logger = logging.getLogger("organ_30_app_scanner")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

# --------------------------------------------------------------------------- #
# Constants & Shields
# --------------------------------------------------------------------------- #
DANGEROUS_NAMES = {
    "exit", "quit", "close", "close tab", "close window", "minimize", "maximize", "restore", "system",
    "shut down", "shutdown", "uninstall", "format", "delete partition", "delete",
    "remove", "reset windows", "factory reset", "clear data", "delete account",
    "sign out", "log out", "disconnect", "wipe", "erase", "kill", "terminate",
    "power off", "restart", "reboot", "cancel subscription", "deactivate account",
}

# Live streaming/recording actions that should be cataloged but shielded from clicking
BROADCAST_SHIELD_NAMES = {
    "start streaming", "stop streaming", "start recording", "stop recording",
    "start virtual camera", "stop virtual camera", "start replay buffer",
    "stop replay buffer", "manage broadcast",
}

# Browser chrome navigation buttons that should not be clicked during crawling
BROWSER_NAV_SHIELD_NAMES = {
    "back", "click to go back", "forward", "click to go forward",
    "reload", "reload this page", "refresh", "close tab", "new tab",
    "close window", "reopen closed tab", "bookmark this tab",
    "extensions", "customize and control", "app menu",
    "minimize", "maximize", "restore", "close this view",
}

KNOWN_DOCKABLE_NAMES = {
    "scenes", "sources", "audio mixer", "scene transitions", "controls",
    "stats", "properties", "filters", "explorer", "solution explorer",
    "terminal", "output", "timeline", "inspector", "hierarchy", "console",
    "assets", "palette", "layers", "history", "navigator", "toolbox",
}

DIALOG_TRIGGER_NAMES = {
    "settings", "properties", "filters", "open scene filters",
    "transition properties", "advanced audio properties", "options",
    "configure", "preferences", "advanced", "parameters", "setup",
    "customize", "details", "about", "configuration",
}

ACTIONABLE_CONTROL_TYPES = {
    "ButtonControl", "CheckBoxControl", "ComboBoxControl", "EditControl",
    "ListItemControl", "RadioButtonControl", "TabItemControl", "HyperlinkControl",
    "MenuItemControl", "SliderControl",
}

CONTAINER_CONTROL_TYPES = {
    "PaneControl", "GroupControl", "CustomControl", "ToolBarControl",
    "ListControl", "TabControl", "TreeControl", "WindowControl", "MenuBarControl",
}

WEB_ACTIONABLE_ROLES = {
    "button", "link", "combobox", "checkbox", "radio", "tab", "menuitem", "textbox",
}

# Standard accelerators for common desktop top menu bars
DEFAULT_MENU_ACCELERATORS = {
    "file": "%f", "edit": "%e", "view": "%v", "insert": "%i", "format": "%o",
    "tools": "%t", "window": "%w", "help": "%h", "options": "%o", "settings": "%s",
    "project": "%p", "build": "%b", "debug": "%d", "run": "%r", "terminal": "%t",
    "navigate": "%n", "selection": "%s", "docks": "%d", "profile": "%p",
    "scene collection": "%sc", "scenes": "%s", "sources": "%s",
}
MENU_ACCELERATORS = DEFAULT_MENU_ACCELERATORS


def get_menu_accelerator(ctrl=None, header_name: str = "") -> Optional[str]:
    """Dynamically determines the Alt accelerator sequence for any menu header."""
    norm = (header_name or "").strip().lower()
    if norm in DEFAULT_MENU_ACCELERATORS:
        return DEFAULT_MENU_ACCELERATORS[norm]

    if ctrl is not None:
        try:
            acc_key = getattr(ctrl, "AccessKey", "")
            if acc_key:
                m = re.search(r"alt\+([a-z0-9])", acc_key, re.IGNORECASE)
                if m:
                    return f"%{m.group(1).lower()}"
        except Exception:
            pass

        try:
            name = getattr(ctrl, "Name", "") or ""
            if "&" in name:
                idx = name.find("&")
                if idx + 1 < len(name) and name[idx + 1].isalnum():
                    return f"%{name[idx + 1].lower()}"
        except Exception:
            pass

    for ch in header_name:
        if ch.isalnum():
            return f"%{ch.lower()}"

    return None


GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000

SCREEN_W = win32api.GetSystemMetrics(0) if win32api else 1920
SCREEN_H = win32api.GetSystemMetrics(1) if win32api else 1080


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #


def safe_bounding_rect(ctrl) -> Optional[Tuple[int, int, int, int]]:
    """Return (l, t, r, b) or None. Wraps COMError-prone BoundingRectangle."""
    if not ctrl:
        return None
    try:
        r = ctrl.BoundingRectangle
        if r is None:
            return None
        l, t, rr, b = int(r.left), int(r.top), int(r.right), int(r.bottom)
        if rr <= l or b <= t:
            return None
        if l < -500 or t < -500 or rr > SCREEN_W + 500 or b > SCREEN_H + 500:
            return None
        return (l, t, rr, b)
    except Exception:
        return None


def is_onscreen(box: Tuple[int, int, int, int]) -> bool:
    if not box:
        return False
    l, t, r, b = box
    cx, cy = (l + r) // 2, (t + b) // 2
    return 0 <= cx < SCREEN_W and 0 <= cy < SCREEN_H


def center_of(box: Tuple[int, int, int, int]) -> Tuple[int, int]:
    l, t, r, b = box
    return (l + r) // 2, (t + b) // 2


def is_dangerous(name: str) -> bool:
    n = (name or "").strip().lower()
    return any(bad in n for bad in DANGEROUS_NAMES)


def is_broadcast_action(name: str) -> bool:
    n = (name or "").strip().lower()
    return any(b == n or n.startswith(b) for b in BROADCAST_SHIELD_NAMES)


def is_browser_nav_action(name: str) -> bool:
    n = (name or "").strip().lower()
    return any(b in n for b in BROWSER_NAV_SHIELD_NAMES)


def is_dockable_hwnd(hwnd: int) -> bool:
    if not hwnd or not win32gui:
        return False
    try:
        style = win32gui.GetWindowLong(hwnd, GWL_STYLE)
        title = (win32gui.GetWindowText(hwnd) or "").strip().lower()
        if style & WS_CHILD:
            return True
        if title in KNOWN_DOCKABLE_NAMES:
            return True
    except Exception:
        pass
    return False


def is_viewport_canvas(ctrl, box: Tuple[int, int, int, int], win_box: Optional[Tuple[int, int, int, int]] = None) -> bool:
    """
    Identifies central preview viewport and custom audio canvas controls
    that lack standard click patterns and cause COM stalls (>30% window area).
    """
    if not box or not win_box:
        return False
    ctrl_w = box[2] - box[0]
    ctrl_h = box[3] - box[1]
    ctrl_area = ctrl_w * ctrl_h
    win_w = max(1, win_box[2] - win_box[0])
    win_h = max(1, win_box[3] - win_box[1])
    win_area = win_w * win_h

    ratio = ctrl_area / float(win_area)
    try:
        ctype = ctrl.ControlTypeName or ""
        name = (ctrl.Name or "").strip().lower()
    except Exception:
        return False

    if ratio > 0.30 and ctype in ("PaneControl", "CustomControl", "GroupControl", "ImageControl"):
        if not name or any(k in name for k in ("preview", "display", "canvas", "viewport", "central", "glwidget", "qt5qwindowicon")):
            return True

    return False


def get_pid_for_hwnd(hwnd: int) -> Optional[int]:
    if not hwnd or not win32process:
        return None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return pid
    except Exception:
        return None


def bring_to_foreground(hwnd: int, retries: int = 3) -> bool:
    """Brings window to foreground reliably via SwitchToThisWindow and Alt pulse."""
    if not hwnd or not win32gui:
        return False
    ensure_interactive_desktop()
    for attempt in range(retries):
        try:
            if hasattr(ctypes.windll.user32, "SwitchToThisWindow"):
                ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.05)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            logger.debug("SetForegroundWindow attempt %d failed: %s", attempt + 1, e)
            try:
                if win32api:
                    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.1)
                win32gui.SetForegroundWindow(hwnd)
                return True
            except Exception:
                time.sleep(0.15)
    return False


def _probe_input_capability() -> bool:
    try:
        user32 = ctypes.windll.user32
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return False
        orig_x, orig_y = pt.x, pt.y
        target_x = max(10, min(SCREEN_W - 10, orig_x + (50 if orig_x < SCREEN_W // 2 else -50)))
        target_y = max(10, min(SCREEN_H - 10, orig_y + (50 if orig_y < SCREEN_H // 2 else -50)))
        res = user32.SetCursorPos(target_x, target_y)
        if not res:
            return False
        time.sleep(0.04)
        user32.GetCursorPos(ctypes.byref(pt))
        moved = (abs(pt.x - target_x) < 5 and abs(pt.y - target_y) < 5)
        user32.SetCursorPos(orig_x, orig_y)
        return moved
    except Exception:
        return False


CAN_INJECT_INPUT = _probe_input_capability()
logger.info("Physical input injection available: %s (Tier %s)",
            CAN_INJECT_INPUT, "2: Live Injection" if CAN_INJECT_INPUT else "1: UIA Native")


def uia_activate(ctrl, fallback_coords: Optional[Tuple[int, int]] = None) -> bool:
    """
    Activates an actionable control using UIA patterns first (Invoke, Expand, Select, Toggle),
    gracefully falling back to physical click if injection is available.
    Runs pat.Invoke in a daemon worker thread with 0.35s timeout to prevent COM
    synchronous lockups when a modal dialog enters a nested message loop.
    """
    if ctrl is None:
        if CAN_INJECT_INPUT and fallback_coords:
            return physical_click(fallback_coords[0], fallback_coords[1])
        return False

    # 1. InvokePattern (Button, MenuItem, Hyperlink, Web actions)
    try:
        if hasattr(ctrl, "GetInvokePattern"):
            pat = ctrl.GetInvokePattern()
            if pat:
                def _do_invoke():
                    try:
                        pat.Invoke()
                    except Exception:
                        pass

                t = threading.Thread(target=_do_invoke, daemon=True)
                t.start()
                t.join(timeout=0.35)
                time.sleep(0.15)
                return True
    except Exception:
        pass

    # 2. SelectionItemPattern (ListItem, TabItem, RadioButton, Web Tab)
    try:
        if hasattr(ctrl, "GetSelectionItemPattern"):
            pat = ctrl.GetSelectionItemPattern()
            if pat:
                pat.Select()
                time.sleep(0.2)
                return True
    except Exception:
        pass

    # 3. TogglePattern (CheckBox, Web Toggle)
    try:
        if hasattr(ctrl, "GetTogglePattern"):
            pat = ctrl.GetTogglePattern()
            if pat:
                pat.Toggle()
                time.sleep(0.2)
                return True
    except Exception:
        pass

    # 4. ExpandCollapsePattern (ComboBox, Dropdown)
    try:
        if hasattr(ctrl, "GetExpandCollapsePattern"):
            pat = ctrl.GetExpandCollapsePattern()
            if pat:
                pat.Expand()
                time.sleep(0.2)
                return True
    except Exception:
        pass

    # 5. UIA ctrl.Click(simulateMove=False)
    try:
        if hasattr(ctrl, "Click"):
            ctrl.Click(simulateMove=False)
            time.sleep(0.2)
            return True
    except Exception:
        pass

    # 6. Fallback to physical click
    if CAN_INJECT_INPUT:
        if fallback_coords:
            cx, cy = fallback_coords
        else:
            box = safe_bounding_rect(ctrl)
            if box:
                cx, cy = center_of(box)
            else:
                return False
        return physical_click(cx, cy, ctrl)

    return False


def physical_click(x: int, y: int, ctrl=None, settle: float = 0.15) -> bool:
    """
    Physical mouse click with settle delays. If input injection is blocked,
    delegates to uia_activate.
    """
    ensure_interactive_desktop()

    if not CAN_INJECT_INPUT:
        if ctrl is not None:
            return uia_activate(ctrl, fallback_coords=(x, y))
        return False

    user32 = ctypes.windll.user32
    if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
        try:
            user32.SetCursorPos(x, y)
            time.sleep(0.12)
            user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
            time.sleep(0.08)
            user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
            time.sleep(settle)
            return True
        except Exception as e:
            logger.debug("ctypes mouse_event click failed at (%d, %d): %s", x, y, e)

    if ctrl is not None:
        return uia_activate(ctrl, fallback_coords=(x, y))

    if auto is not None and 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
        try:
            auto.Click(x, y)
            time.sleep(settle)
            return True
        except Exception as e:
            logger.debug("auto.Click fallback failed at (%d, %d): %s", x, y, e)

    return False


def sort_controls_spatially(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda it: (it["coords"]["box"][1], it["coords"]["box"][0]))


def send_keys(*vks_and_pauses):
    user32 = ctypes.windll.user32
    for vk in vks_and_pauses:
        try:
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.04)
            user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
            time.sleep(0.06)
        except Exception:
            pass


def send_alt_sequence(accel: str):
    if not accel.startswith("%"):
        return
    user32 = ctypes.windll.user32
    keys = accel[1:]
    try:
        user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU
        time.sleep(0.06)
        for ch in keys:
            vk = ord(ch.upper())
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.04)
            user32.keybd_event(vk, 0, 2, 0)
            time.sleep(0.04)
        user32.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.18)
    except Exception as e:
        logger.debug("send_alt_sequence failed: %s", e)


# --------------------------------------------------------------------------- #
# Smart Control Label & Name Extractor (Web & Desktop)
# --------------------------------------------------------------------------- #
def resolve_control_name(ctrl, ctype: str) -> str:
    """
    Extracts a rich semantic label for any desktop or web control.
    If direct ctrl.Name is empty, inspects:
    1. Child TextControl elements (e.g. HTML button with inner text span)
    2. HelpText (tooltip/title)
    3. AutomationId (e.g. data-testid or DOM ID)
    4. ValuePattern.Value
    5. AriaRole / LocalizedControlType
    """
    try:
        name = (ctrl.Name or "").strip()
        if name:
            return name

        # 1. Child TextControl elements
        try:
            child_texts = []
            for ch in ctrl.GetChildren():
                if getattr(ch, "ControlTypeName", "") == "TextControl":
                    txt = (getattr(ch, "Name", "") or "").strip()
                    if txt:
                        child_texts.append(txt)
            if child_texts:
                return " ".join(child_texts)
        except Exception:
            pass

        # 2. HelpText
        try:
            ht = getattr(ctrl, "HelpText", "")
            if ht:
                return ht.strip()
        except Exception:
            pass

        # 3. AutomationId
        try:
            aid = getattr(ctrl, "AutomationId", "")
            if aid:
                return aid.strip()
        except Exception:
            pass

        # 4. ValuePattern
        try:
            val_pat = ctrl.GetValuePattern()
            if val_pat and hasattr(val_pat, "Value"):
                val = (val_pat.Value or "").strip()
                if val:
                    return val
        except Exception:
            pass

        # 5. LocalizedControlType
        try:
            lct = getattr(ctrl, "LocalizedControlType", "")
            if lct:
                return lct.strip()
        except Exception:
            pass

    except Exception:
        pass

    return ctype


# --------------------------------------------------------------------------- #
# Chromium & Webapp Wake-Up Engine
# --------------------------------------------------------------------------- #
def is_chromium_or_electron_window(hwnd: int, root_ctrl=None) -> bool:
    """Identifies Chromium browsers and Electron desktop applications."""
    if not hwnd or not win32gui:
        return False
    try:
        cls = win32gui.GetClassName(hwnd).strip()
        if cls in ("Chrome_WidgetWin_1", "MozillaWindowClass"):
            return True
        title = (win32gui.GetWindowText(hwnd) or "").lower()
        if any(k in title for k in ("chrome", "edge", "visual studio code", "slack", "teams", "discord")):
            return True
    except Exception:
        pass
    return False


def wake_chromium_accessibility(hwnd: int, root_ctrl=None) -> None:
    """
    Triggers Chromium's accessibility engine to populate the DocumentControl tree.
    In Chromium, accessibility can be dormant until focused or queried via WM_GETOBJECT.
    """
    if not hwnd:
        return
    ensure_interactive_desktop()
    bring_to_foreground(hwnd)
    time.sleep(0.2)

    if root_ctrl and auto:
        try:
            # Query DocumentControl to force tree population
            doc = root_ctrl.DocumentControl()
            if doc.Exists(0.5):
                logger.info("[CHROMIUM] Active DocumentControl DOM connected.")
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Modal / popup interceptor (Universal Native + In-Window Modals)
# --------------------------------------------------------------------------- #
class ModalPopupInterceptor:
    def __init__(self, db: DatabaseManager, cns: CNSPopupInterceptor):
        self.db = db
        self.cns = cns

    def detect_true_modal(self, main_hwnd: int, target_pid: Optional[int] = None) -> Optional[int]:
        """
        Returns hwnd of a genuine top-level modal blocking main_hwnd/target_pid.
        Filters dockable panes and tooltips.
        """
        if not win32gui:
            return None
        ensure_interactive_desktop()

        candidates: List[int] = []

        # 1. Standard Win32 enabled popup
        try:
            popup_hwnd = win32gui.GetWindow(main_hwnd, win32con.GW_ENABLEDPOPUP)
            if popup_hwnd and popup_hwnd != main_hwnd:
                candidates.append(popup_hwnd)
        except Exception:
            pass

        # 2. Foreground window check
        try:
            fg = win32gui.GetForegroundWindow()
            if fg and fg != main_hwnd:
                candidates.append(fg)
        except Exception:
            pass

        # 3. Desktop root search for top-level windows matching target PID
        if auto and target_pid:
            try:
                for win in auto.GetRootControl().GetChildren():
                    h = getattr(win, "NativeWindowHandle", 0)
                    if h and h != main_hwnd and win.ProcessId == target_pid:
                        candidates.append(h)
            except Exception:
                pass

        for h in candidates:
            if self._is_genuine_modal(h, main_hwnd, target_pid):
                return h

        return None

    def _is_genuine_modal(self, hwnd: int, main_hwnd: int, target_pid: Optional[int]) -> bool:
        if not hwnd or hwnd == main_hwnd or not win32gui.IsWindow(hwnd):
            return False
        if not win32gui.IsWindowVisible(hwnd):
            return False
        if is_dockable_hwnd(hwnd):
            return False

        if target_pid:
            pid = get_pid_for_hwnd(hwnd)
            if pid and pid != target_pid:
                return False

        try:
            style = win32gui.GetWindowLong(hwnd, GWL_STYLE)
            if style & WS_CHILD:
                return False
            title = (win32gui.GetWindowText(hwnd) or "").strip().lower()
            if not title and not (style & WS_POPUP):
                return False
            if title in KNOWN_DOCKABLE_NAMES:
                return False
        except Exception:
            return False

        return True

    def detect_in_window_modals(self, root_ctrl) -> List[Any]:
        """
        Discovers in-window modals, WinUI 3 ContentDialog, flyouts, and web <dialog> elements.
        """
        if not root_ctrl or not auto:
            return []

        modals = []
        try:
            for ctrl, depth in auto.WalkControl(root_ctrl, includeTop=False, maxDepth=14):
                try:
                    ccls = (ctrl.ClassName or "").strip()
                    cname = (ctrl.Name or "").strip().lower()
                    aid = (ctrl.AutomationId or "").strip().lower()
                    ctype = ctrl.ControlTypeName or ""

                    is_modal = False
                    try:
                        is_modal = getattr(ctrl, "IsModal", False) or getattr(ctrl, "AriaRole", "") in ("dialog", "alertdialog")
                    except Exception:
                        pass

                    if any(k in ccls for k in ("ContentDialog", "Flyout", "Popup", "ModalDialog", "Chrome_WidgetWin")):
                        is_modal = True

                    norm_text = f"{cname} {aid} {ccls}"
                    if any(k in norm_text for k in ("cookie", "consent", "gdpr", "notification", "permission", "warning")):
                        if ctype in ("PaneControl", "GroupControl", "CustomControl", "WindowControl"):
                            is_modal = True

                    if is_modal:
                        box = safe_bounding_rect(ctrl)
                        if box and is_onscreen(box):
                            modals.append(ctrl)
                except Exception:
                    continue
        except Exception as e:
            logger.debug("In-window modal scan notice: %s", e)

        return modals

    def handle(self, hwnd: int) -> str:
        """Consult DB cache first, else alert CNS bridge (Organ 29) and await resolution."""
        title = win32gui.GetWindowText(hwnd) if win32gui else "Modal"
        norm_title = title.strip().lower()
        key = f"modal:{norm_title}"
        cached = self.db.get_modal_resolution(key)
        if cached:
            logger.info("Modal '%s' resolved from cache: %s", title, cached)
            return cached

        cx, cy = 0, 0
        if win32gui and hwnd:
            try:
                rect = win32gui.GetWindowRect(hwnd)
                cx = (rect[0] + rect[2]) // 2
                cy = (rect[1] + rect[3]) // 2
            except Exception:
                pass
        layout_hash = hashlib.md5((title or "modal").encode("utf-8")).hexdigest()[:16]

        resolution = "dismiss"
        try:
            logger.info("[CNS BRIDGE] Forwarding popup '%s' to Organ 29 at (%d, %d)", title, cx, cy)
            popup_id = self.cns.alert_popup_detected(title=title, layout_hash=layout_hash, x=cx, y=cy)
            res_data = self.cns.wait_for_resolution(popup_id, timeout=12.0)
            if res_data:
                resolution = res_data.get("action", "dismiss")
                tx = int(res_data.get("x", cx))
                ty = int(res_data.get("y", cy))
                logger.info("[CNS BRIDGE] Organ 29 resolved popup '%s' -> action='%s' at (%d, %d)",
                            title, resolution, tx, ty)
            else:
                logger.warning("[CNS BRIDGE] Organ 29 resolution timed out. Defaulting to dismiss.")
        except Exception as e:
            logger.warning("[CNS BRIDGE] Popup alert across bridge failed: %s. Defaulting to dismiss.", e)

        self.db.store_modal_resolution(key, resolution)
        return resolution


# --------------------------------------------------------------------------- #
# Qt-aware keyboard menu scanner
# --------------------------------------------------------------------------- #
class MenuScanner:
    def __init__(self, main_hwnd: int, menu_header_names: Set[str], root_ctrl=None):
        self.main_hwnd = main_hwnd
        self.menu_header_names = {n.strip().lower() for n in menu_header_names}
        self.root_ctrl = root_ctrl

    def scan_menu(self, header_name: str, ctrl_obj=None, max_items: int = 40) -> List[Dict[str, Any]]:
        if not CAN_INJECT_INPUT:
            return self._scan_menu_via_uia(header_name, ctrl_obj=ctrl_obj)

        accel = get_menu_accelerator(ctrl=ctrl_obj, header_name=header_name)
        if not accel:
            return self._scan_menu_via_uia(header_name, ctrl_obj=ctrl_obj)

        results: List[Dict[str, Any]] = []
        bring_to_foreground(self.main_hwnd)
        time.sleep(0.15)
        send_alt_sequence(accel)
        time.sleep(0.25)

        seen_names: List[str] = []
        first_name: Optional[str] = None

        for _ in range(max_items):
            send_keys(0x28)  # VK_DOWN
            time.sleep(0.12)
            focused_name = self._read_focused_name()

            if not focused_name:
                continue
            norm = focused_name.strip().lower()

            if norm in self.menu_header_names:
                continue

            if re.match(r"^desktop \d+$", norm):
                continue

            if first_name is None:
                first_name = norm
            elif norm == first_name:
                break

            if norm in [s.lower() for s in seen_names]:
                break

            seen_names.append(focused_name)

            box = self._read_focused_box()
            entry = {
                "name": focused_name,
                "type": "MenuItem",
                "coords": {
                    "x": box[0] if box else -1,
                    "y": box[1] if box else -1,
                    "box": list(box[2]) if box else [-1, -1, -1, -1],
                },
                "parent_menu": header_name,
            }
            results.append(entry)

            if box and is_onscreen(box[2]):
                try:
                    ctypes.windll.user32.SetCursorPos(box[0], box[1])
                    time.sleep(0.08)
                except Exception:
                    pass

        send_keys(0x1B)  # VK_ESCAPE
        time.sleep(0.15)

        if not results:
            return self._scan_menu_via_uia(header_name, ctrl_obj=ctrl_obj)

        return results

    def _scan_menu_via_uia(self, header_name: str, ctrl_obj=None) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        if auto is None:
            return items

        if ctrl_obj is not None:
            try:
                pat = ctrl_obj.GetExpandCollapsePattern()
                if pat:
                    pat.Expand()
                    time.sleep(0.2)
            except Exception:
                pass

        search_roots = []
        if self.root_ctrl:
            search_roots.append(self.root_ctrl)
        try:
            search_roots.append(auto.GetRootControl())
        except Exception:
            pass

        seen_sigs = set()
        for sroot in search_roots:
            try:
                for ctrl, depth in auto.WalkControl(sroot, includeTop=False, maxDepth=6):
                    ctype = ctrl.ControlTypeName or ""
                    if ctype != "MenuItemControl":
                        continue
                    name = (ctrl.Name or "").strip()
                    if not name or name.lower() == header_name.lower() or name.lower() in self.menu_header_names:
                        continue
                    if re.match(r"^Desktop \d+$", name, re.IGNORECASE):
                        continue
                    box = safe_bounding_rect(ctrl)
                    if box and is_onscreen(box):
                        cx, cy = center_of(box)
                        sig = f"{name}:{box}"
                        if sig in seen_sigs:
                            continue
                        seen_sigs.add(sig)
                        items.append({
                            "name": name,
                            "type": "MenuItem",
                            "coords": {"x": cx, "y": cy, "box": list(box)},
                            "parent_menu": header_name,
                        })
            except Exception as e:
                logger.debug("UIA menu extraction error: %s", e)

        if ctrl_obj is not None:
            try:
                pat = ctrl_obj.GetExpandCollapsePattern()
                if pat:
                    pat.Collapse()
            except Exception:
                pass
        return items

    def _read_focused_name(self) -> Optional[str]:
        if auto is None:
            return None
        try:
            fc = auto.GetFocusedControl()
            if not fc:
                return None
            name = (fc.Name or "").strip()
            if not name or re.match(r"^Desktop \d+$", name, re.IGNORECASE):
                return None
            return name
        except Exception:
            return None

    def _read_focused_box(self):
        if auto is None:
            return None
        try:
            fc = auto.GetFocusedControl()
            if not fc:
                return None
            name = (fc.Name or "").strip()
            if not name or re.match(r"^Desktop \d+$", name, re.IGNORECASE):
                return None
            box = safe_bounding_rect(fc)
            if not box:
                return None
            cx, cy = center_of(box)
            return (cx, cy, box)
        except Exception:
            return None


# --------------------------------------------------------------------------- #
# Child dialog & In-Window Dialog Traversal
# --------------------------------------------------------------------------- #
class DialogTraversal:
    CLOSE_NAMES = {"cancel", "close", "dismiss", "don't save", "dont save", "no thanks"}
    FORBIDDEN_CLOSE = {"ok", "apply", "save"}

    def scan_dialog(self, dialog_hwnd: int, parent_button: str = "") -> List[Dict[str, Any]]:
        elements: List[Dict[str, Any]] = []
        if auto is None or not dialog_hwnd:
            return elements

        bring_to_foreground(dialog_hwnd)
        time.sleep(0.3)
        try:
            dlg_ctrl = auto.ControlFromHandle(dialog_hwnd)
        except Exception:
            dlg_ctrl = None
        if dlg_ctrl is None:
            return elements

        dlg_title = (dlg_ctrl.Name or (win32gui.GetWindowText(dialog_hwnd) if win32gui else "") or "Dialog").strip()
        logger.info("[DIALOG] Scanning dialog: '%s' (triggered by '%s')", dlg_title, parent_button)

        tabs = self._find_tabs(dlg_ctrl)
        if tabs:
            logger.info("[DIALOG] Multi-tab navigation found: %d tabs in '%s'", len(tabs), dlg_title)
            for tab in tabs:
                tab_name = tab.Name or "Tab"
                box = safe_bounding_rect(tab)
                if not box or not is_onscreen(box):
                    continue
                cx, cy = center_of(box)
                logger.info("[DIALOG TAB] Selecting tab: '%s'", tab_name)
                selected = False
                try:
                    pat = tab.GetSelectionItemPattern()
                    if pat:
                        pat.Select()
                        selected = True
                except Exception:
                    pass
                if not selected:
                    uia_activate(tab, fallback_coords=(cx, cy))

                time.sleep(0.3)
                page_items = self._collect_controls(dlg_ctrl, parent_tab=tab_name, parent_dialog=dlg_title)
                elements.extend(page_items)
        else:
            elements.extend(self._collect_controls(dlg_ctrl, parent_dialog=dlg_title))

        self._close_safely(dlg_ctrl, dialog_hwnd)
        return elements

    def _find_tabs(self, dlg_ctrl) -> List[Any]:
        tabs = []
        try:
            list_ctrl = dlg_ctrl.ListControl()
            if list_ctrl.Exists(0.5):
                for child in list_ctrl.GetChildren():
                    box = safe_bounding_rect(child)
                    if box and is_onscreen(box):
                        tabs.append(child)
        except Exception:
            pass

        if not tabs:
            try:
                for ctrl, depth in auto.WalkControl(dlg_ctrl, includeTop=False, maxDepth=6):
                    ctype = ctrl.ControlTypeName
                    name = ctrl.Name
                    if not name:
                        continue
                    if ctype in ("TabItemControl", "ListItemControl"):
                        box = safe_bounding_rect(ctrl)
                        if box and is_onscreen(box):
                            tabs.append(ctrl)
            except Exception as e:
                logger.debug("Tab enumeration failed: %s", e)

        tabs.sort(key=lambda t: (safe_bounding_rect(t)[1] if safe_bounding_rect(t) else 0))
        return tabs

    def _collect_controls(self, dlg_ctrl, parent_tab: Optional[str] = None,
                          parent_dialog: Optional[str] = None) -> List[Dict[str, Any]]:
        found = []
        seen_sigs = set()
        try:
            for ctrl, depth in auto.WalkControl(dlg_ctrl, includeTop=False, maxDepth=14):
                box = safe_bounding_rect(ctrl)
                if not box or not is_onscreen(box):
                    continue
                ctype = ctrl.ControlTypeName or ""
                name = resolve_control_name(ctrl, ctype)

                if ctype not in ACTIONABLE_CONTROL_TYPES:
                    continue

                if is_dangerous(name):
                    continue

                cx, cy = center_of(box)
                sig = f"{name}:{ctype}:{box}"
                if sig in seen_sigs:
                    continue
                seen_sigs.add(sig)

                found.append({
                    "name": name,
                    "type": ctype,
                    "coords": {"x": cx, "y": cy, "box": list(box)},
                    "parent_tab": parent_tab,
                    "parent_dialog": parent_dialog,
                })
        except Exception as e:
            logger.debug("Dialog control collection failed: %s", e)
        return found

    def _close_safely(self, dlg_ctrl, dialog_hwnd: int):
        """Always close via Cancel/Escape — never OK/Apply, per safety rules."""
        logger.info("[DIALOG EXIT] Safely dismissing dialog hwnd=%s", dialog_hwnd)
        closed = False
        try:
            cancel_btn = dlg_ctrl.ButtonControl(Name="Cancel")
            if cancel_btn.Exists(0.5):
                pat = cancel_btn.GetInvokePattern()
                if pat:
                    pat.Invoke()
                    closed = True
                    logger.info("Closed dialog via Cancel InvokePattern.")
                else:
                    box = safe_bounding_rect(cancel_btn)
                    if box:
                        cx, cy = center_of(box)
                        closed = uia_activate(cancel_btn, fallback_coords=(cx, cy))
        except Exception as e:
            logger.debug("Cancel button lookup failed: %s", e)

        if not closed:
            try:
                for ctrl, depth in auto.WalkControl(dlg_ctrl, includeTop=False, maxDepth=8):
                    name = (ctrl.Name or "").strip().lower()
                    ctype = ctrl.ControlTypeName
                    if ctype == "ButtonControl" and name in self.CLOSE_NAMES and name not in self.FORBIDDEN_CLOSE:
                        box = safe_bounding_rect(ctrl)
                        if box and is_onscreen(box):
                            cx, cy = center_of(box)
                            uia_activate(ctrl, fallback_coords=(cx, cy))
                            closed = True
                            break
            except Exception as e:
                logger.debug("Close-button search failed: %s", e)

        time.sleep(0.2)
        if win32gui and win32gui.IsWindow(dialog_hwnd) and win32gui.IsWindowVisible(dialog_hwnd):
            if CAN_INJECT_INPUT:
                send_keys(0x1B)  # VK_ESCAPE
                time.sleep(0.15)
            if win32gui.IsWindowVisible(dialog_hwnd):
                try:
                    win32gui.PostMessage(dialog_hwnd, win32con.WM_CLOSE, 0, 0)
                    time.sleep(0.2)
                except Exception:
                    pass


# --------------------------------------------------------------------------- #
# Main Universal App Scanner
# --------------------------------------------------------------------------- #
class AppScanner:
    def __init__(self, db: Optional[DatabaseManager] = None,
                 cns: Optional[CNSPopupInterceptor] = None):
        self.db = db or DatabaseManager()
        self.cns = cns or CNSPopupInterceptor(role="AppAgent", port=11436)
        try:
            if hasattr(self.cns, "start"):
                self.cns.start()
                logger.info("[SCANNER] AppAgent CNS socket bridge active on port %d", self.cns.port + 1)
        except Exception as cns_err:
            logger.warning("[SCANNER] AppAgent CNS bridge failed to bind: %s", cns_err)
        self.popup_interceptor = ModalPopupInterceptor(self.db, self.cns)
        self.dialog_traversal = DialogTraversal()
        self.controls_scanned = 0
        self.controls_failed = 0

    def stop(self):
        try:
            if hasattr(self.cns, "stop"):
                self.cns.stop()
                logger.info("[SCANNER] AppAgent CNS bridge terminated.")
        except Exception:
            pass

    # --- public entry point ------------------------------------------------
    def scan_app_active(self, app_name: str, target_hwnd: int) -> Dict[str, Any]:
        ensure_interactive_desktop()
        if auto is None or win32gui is None:
            return {"status": "error", "message": "uiautomation/pywin32 not available",
                    "tree_hash": "", "controls_scanned": 0, "controls_failed": 0, "elements": []}

        self.controls_scanned = 0
        self.controls_failed = 0
        elements: List[Dict[str, Any]] = []

        bring_to_foreground(target_hwnd)
        time.sleep(0.3)

        try:
            root_ctrl = auto.ControlFromHandle(target_hwnd)
        except Exception as e:
            logger.error("Could not attach to hwnd %s: %s", target_hwnd, e)
            return {"status": "error", "message": str(e),
                    "tree_hash": "", "controls_scanned": 0, "controls_failed": 0, "elements": []}

        # If Chromium/Electron or Web, wake up accessibility
        is_chromium = is_chromium_or_electron_window(target_hwnd, root_ctrl)
        if is_chromium:
            logger.info("[SCANNER] Detected Chromium/Electron environment. Activating web DOM accessibility.")
            wake_chromium_accessibility(target_hwnd, root_ctrl)

        win_box = safe_bounding_rect(root_ctrl)
        target_pid = get_pid_for_hwnd(target_hwnd)

        # 1. Collect actionable controls up to depth 25 (allowing deep web DOMs)
        raw_items = self._collect_actionable_controls(root_ctrl, win_box, is_web_app=is_chromium)
        raw_items = sort_controls_spatially(raw_items)
        seen_control_sigs = {f"{it['name']}:{it['type']}:{it['coords']['box']}" for it in raw_items}
        logger.info("[SCANNER] Discovered %d actionable surface controls (Web/DOM=%s)", len(raw_items), is_chromium)

        # 2. Identify desktop top menu headers
        def is_menu_header(it: Dict[str, Any]) -> bool:
            ctype = it.get("type", "")
            name = (it.get("name") or "").strip()
            norm = name.lower()
            box = it.get("coords", {}).get("box", [-1, -1, -1, -1])
            if ctype != "MenuItemControl":
                return False
            if norm == "system":
                return False
            if norm in DEFAULT_MENU_ACCELERATORS:
                return True
            if win_box and box[1] < win_box[1] + 120:
                return True
            return False

        menu_header_names = {it["name"] for it in raw_items if is_menu_header(it)}
        menu_scanner = MenuScanner(target_hwnd, menu_header_names, root_ctrl=root_ctrl)

        # 3. Walk items in visual order with deep active probing
        for item in raw_items:
            name = item["name"]
            norm_name = name.strip().lower()
            ctype = item["type"]
            box = tuple(item["coords"]["box"])
            cx, cy = item["coords"]["x"], item["coords"]["y"]
            ctrl_obj = item.get("ctrl_obj")

            # Title-bar "System" menu at (0,0) or Close button shield
            if norm_name == "system" and box[:2] == (0, 0):
                continue

            # Safety Shield: Never click Quit/Exit/Close buttons
            if is_dangerous(name):
                logger.info("Safety shield: cataloged dangerous control '%s' (skipping click)", name)
                elements.append(item)
                self.controls_scanned += 1
                continue

            # Safety Shield: Catalog broadcast actions (Start Streaming, etc.) but avoid live triggers
            if is_broadcast_action(name):
                logger.info("Safety shield: cataloged broadcast control '%s' (skipping click)", name)
                elements.append(item)
                self.controls_scanned += 1
                continue

            # Safety Shield: Protect browser navigation (Back, Reload, Close Tab) when in a browser
            if is_chromium and is_browser_nav_action(name):
                logger.info("Browser shield: cataloged browser chrome navigation '%s' (skipping click)", name)
                elements.append(item)
                self.controls_scanned += 1
                continue

            # Menu headers: Drive via keyboard accelerators or UIA tree
            if is_menu_header(item):
                try:
                    logger.info("[MENU SCAN] Traversing menu '%s'", name)
                    menu_items = menu_scanner.scan_menu(name, ctrl_obj=ctrl_obj)
                    elements.append(item)
                    elements.extend(menu_items)
                    self.controls_scanned += 1 + len(menu_items)
                except Exception as e:
                    logger.warning("Menu scan failed for '%s': %s", name, e)
                    self.controls_failed += 1
                continue

            # Child Dialog Triggers ("Settings", "Properties", "Filters", etc.)
            if norm_name in DIALOG_TRIGGER_NAMES:
                logger.info("[DIALOG TRIGGER] Activating '%s' to spawn child dialog", name)
                elements.append(item)
                self.controls_scanned += 1
                try:
                    activated = uia_activate(ctrl_obj, fallback_coords=(cx, cy))
                    time.sleep(0.6)
                    child_hwnd = self._find_spawned_dialog(target_hwnd, target_pid)
                    if child_hwnd:
                        dialog_elements = self.dialog_traversal.scan_dialog(child_hwnd, parent_button=name)
                        elements.extend(dialog_elements)
                        self.controls_scanned += len(dialog_elements)
                    else:
                        logger.debug("No child dialog detected after activating '%s'", name)
                except Exception as e:
                    logger.warning("Error interacting with dialog trigger '%s': %s", name, e)
                    self.controls_failed += 1
                bring_to_foreground(target_hwnd)
                continue

            # Generic Actionable Control: Deep Active Probing ("every button scanned should be clicked")
            elements.append(item)
            self.controls_scanned += 1

            # Proactively persist control event to SSMS DatabaseManager
            try:
                elem_hash = hashlib.md5(f"{name}_{ctype}_{cx}_{cy}".encode("utf-8")).hexdigest()[:16]
                self.db.log_new_pathway(
                    layout_hash=elem_hash,
                    element_name=name or ctype,
                    x=cx,
                    y=cy,
                    action_type=ctype,
                    parent_path=app_name,
                )
            except Exception:
                pass

            try:
                logger.info("[ACTIVE PROBE] Clicking / Activating %s: '%s' at (%d, %d)", ctype, name, cx, cy)
                activated = uia_activate(ctrl_obj, fallback_coords=(cx, cy))
                time.sleep(0.35)

                # 1. Did a child dialog spawn from this click?
                child_hwnd = self._find_spawned_dialog(target_hwnd, target_pid)
                if child_hwnd:
                    logger.info("[ACTIVE PROBE] Child dialog spawned by '%s' (hwnd=%s)", name, child_hwnd)
                    dialog_elements = self.dialog_traversal.scan_dialog(child_hwnd, parent_button=name)
                    elements.extend(dialog_elements)
                    self.controls_scanned += len(dialog_elements)
                    bring_to_foreground(target_hwnd)
                    continue

                # 2. Did a roadblock modal or in-window modal appear?
                modal_hwnd = self.popup_interceptor.detect_true_modal(target_hwnd, target_pid)
                if modal_hwnd:
                    logger.info("[ACTIVE PROBE] Top-level modal popup detected by '%s' (hwnd=%s)", name, modal_hwnd)
                    self._handle_possible_modal(target_hwnd, target_pid, elements)
                    bring_to_foreground(target_hwnd)
                    continue

                # Check for in-window modals (WinUI 3 ContentDialog, web cookies, etc.)
                in_win_modals = self.popup_interceptor.detect_in_window_modals(root_ctrl)
                if in_win_modals:
                    logger.info("[ACTIVE PROBE] In-window modal detected by '%s'", name)
                    self._handle_in_window_modal(root_ctrl, in_win_modals, elements)
                    bring_to_foreground(target_hwnd)
                    continue

                # 3. If ComboBox, inspect dropdown and collapse
                if ctype == "ComboBoxControl":
                    self._probe_combobox_items(ctrl_obj, name, elements)

                # 4. If TabItem, collect controls exposed by switching tab
                elif ctype == "TabItemControl":
                    new_tab_items = self._collect_actionable_controls(root_ctrl, win_box, is_web_app=is_chromium)
                    for t_item in new_tab_items:
                        sig = f"{t_item['name']}:{t_item['type']}:{t_item['coords']['box']}"
                        if sig not in seen_control_sigs:
                            seen_control_sigs.add(sig)
                            elements.append(t_item)
                            self.controls_scanned += 1

            except Exception as probe_err:
                logger.debug("Failed to actively probe '%s': %s", name, probe_err)
                self.controls_failed += 1

        bring_to_foreground(target_hwnd)
        tree_hash = self._hash_elements(elements)

        # Strip internal COM objects before JSON serialization
        cleaned_elements = []
        for e in elements:
            clean_e = {k: v for k, v in e.items() if k != "ctrl_obj"}
            cleaned_elements.append(clean_e)

        return {
            "status": "completed",
            "tree_hash": tree_hash,
            "controls_scanned": self.controls_scanned,
            "controls_failed": self.controls_failed,
            "elements": cleaned_elements,
        }

    # --- internals -----------------------------------------------------
    def _collect_actionable_controls(self, root_ctrl, win_box: Optional[Tuple[int, int, int, int]],
                                     is_web_app: bool = False) -> List[Dict[str, Any]]:
        """
        Deeply enumerates UI controls. Supports both desktop hierarchies and deep
        web application DOMs (up to depth 25 inside DocumentControl).
        """
        items: List[Dict[str, Any]] = []
        seen_sigs: Set[str] = set()

        max_search_depth = 25 if is_web_app else 14

        try:
            walker = auto.WalkControl(root_ctrl, includeTop=False, maxDepth=max_search_depth)
        except Exception as e:
            logger.error("WalkControl failed: %s", e)
            return items

        for ctrl, depth in walker:
            box = safe_bounding_rect(ctrl)
            if not box or not is_onscreen(box):
                continue

            try:
                ctype = ctrl.ControlTypeName or ""
            except Exception:
                continue

            # Central canvas / video preview filter
            if is_viewport_canvas(ctrl, box, win_box):
                continue

            # Determine if control is actionable
            is_actionable = ctype in ACTIONABLE_CONTROL_TYPES

            # In Web applications, also check CustomControl / GroupControl with actionable AriaRoles or patterns
            if not is_actionable and is_web_app and ctype in ("CustomControl", "GroupControl"):
                try:
                    aria_role = getattr(ctrl, "AriaRole", "")
                    if aria_role in WEB_ACTIONABLE_ROLES:
                        is_actionable = True
                    elif hasattr(ctrl, "GetInvokePattern") and ctrl.GetInvokePattern() is not None:
                        is_actionable = True
                    elif hasattr(ctrl, "GetTogglePattern") and ctrl.GetTogglePattern() is not None:
                        is_actionable = True
                except Exception:
                    pass

            # Layout filler filter: Skip unnamed container panes
            if not is_actionable:
                continue

            name = resolve_control_name(ctrl, ctype)
            if not name:
                name = ctype

            cx, cy = center_of(box)
            sig = f"{name}:{ctype}:{box}"
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)

            items.append({
                "name": name,
                "type": ctype,
                "coords": {"x": cx, "y": cy, "box": list(box)},
                "ctrl_obj": ctrl,
            })

        return items

    def _find_spawned_dialog(self, main_hwnd: int, target_pid: Optional[int]) -> Optional[int]:
        ensure_interactive_desktop()
        time.sleep(0.5)

        if auto:
            try:
                for win in auto.GetRootControl().GetChildren():
                    h = getattr(win, "NativeWindowHandle", 0)
                    if h and h != main_hwnd:
                        wname = (win.Name or "").strip().lower()
                        pid = getattr(win, "ProcessId", 0)
                        if (target_pid and pid == target_pid) or any(k in wname for k in ("settings", "properties", "filters", "preferences")):
                            is_vis = win32gui.IsWindowVisible(h) if win32gui else True
                            if is_vis and not is_dockable_hwnd(h):
                                return h
            except Exception:
                pass

        if win32gui:
            try:
                pop = win32gui.GetWindow(main_hwnd, win32con.GW_ENABLEDPOPUP)
                if pop and pop != main_hwnd and win32gui.IsWindowVisible(pop) and not is_dockable_hwnd(pop):
                    return pop
            except Exception:
                pass

            try:
                fg = win32gui.GetForegroundWindow()
                if fg and fg != main_hwnd and win32gui.IsWindowVisible(fg):
                    fg_pid = get_pid_for_hwnd(fg)
                    if (not target_pid or fg_pid == target_pid) and not is_dockable_hwnd(fg):
                        return fg
            except Exception:
                pass

        return None

    def _handle_possible_modal(self, main_hwnd: int, target_pid: Optional[int], elements: List[Dict[str, Any]]):
        modal_hwnd = self.popup_interceptor.detect_true_modal(main_hwnd, target_pid)
        if not modal_hwnd:
            return

        title = win32gui.GetWindowText(modal_hwnd) if win32gui else "Modal"
        logger.info("[ROADBLOCK] Genuine modal detected: hwnd=%s | title='%s'", modal_hwnd, title)
        resolution = self.popup_interceptor.handle(modal_hwnd)

        dialog_elements = self.dialog_traversal.scan_dialog(modal_hwnd, parent_button=title)
        elements.extend(dialog_elements)
        self.controls_scanned += len(dialog_elements)

        bring_to_foreground(main_hwnd)

    def _handle_in_window_modal(self, root_ctrl, in_win_modals: List[Any], elements: List[Dict[str, Any]]):
        for modal_ctrl in in_win_modals:
            mname = (modal_ctrl.Name or "").strip() or "In-Window Modal"
            box = safe_bounding_rect(modal_ctrl)
            cx, cy = center_of(box) if box else (0, 0)
            logger.info("[IN-WINDOW ROADBLOCK] Mitigating in-window modal '%s' at (%d, %d)", mname, cx, cy)

            # Alert CNS bridge
            layout_hash = hashlib.md5(mname.encode("utf-8")).hexdigest()[:16]
            cns_handled = False
            try:
                popup_id = self.cns.alert_popup_detected(title=mname, layout_hash=layout_hash, x=cx, y=cy)
                res = self.cns.wait_for_resolution(popup_id, timeout=8.0)
                if res and res.get("action") == "escape_fallback":
                    if CAN_INJECT_INPUT:
                        send_keys(0x1B)
                    cns_handled = True
            except Exception:
                pass

            # Safe dismissal attempt: recursively search for positive or safe buttons
            dismissed = False
            try:
                dismiss_targets = {
                    "accept", "accept all", "agree", "allow", "allow all", "ok", "yes",
                    "continue", "got it", "done", "cancel", "close", "dismiss",
                    "don't save", "dont save", "no thanks", "not now", "later", "x",
                }
                for ch, depth in auto.WalkControl(modal_ctrl, includeTop=False, maxDepth=6):
                    ctype = getattr(ch, "ControlTypeName", "")
                    if ctype not in ("ButtonControl", "HyperlinkControl", "CustomControl"):
                        continue
                    btext = resolve_control_name(ch).strip().lower()
                    aid = (getattr(ch, "AutomationId", "") or "").strip().lower()
                    cls_name = (getattr(ch, "ClassName", "") or "").strip().lower()

                    matched = False
                    if btext in dismiss_targets or any(k in btext for k in ("accept", "allow", "agree", "cancel", "close", "dismiss", "got it", "ok")):
                        matched = True
                    elif any(k in (aid + " " + cls_name) for k in ("closebutton", "dismissbutton", "part_closebutton", "btn-close", "modal-close")):
                        matched = True

                    if matched:
                        uia_activate(ch)
                        dismissed = True
                        break
            except Exception:
                pass

            # Fallback: send Escape if still present
            if not dismissed and not cns_handled and CAN_INJECT_INPUT:
                send_keys(0x1B)

    def _probe_combobox_items(self, ctrl_obj, name: str, elements: List[Dict[str, Any]]):
        try:
            if not ctrl_obj:
                return
            children = getattr(ctrl_obj, "GetChildren", lambda: [])()
            for ch in children:
                if getattr(ch, "ControlTypeName", "") == "ListItemControl":
                    cname = getattr(ch, "Name", "") or ""
                    box = safe_bounding_rect(ch)
                    if box and is_onscreen(box):
                        cx, cy = center_of(box)
                        elements.append({
                            "name": cname,
                            "type": "ListItemControl",
                            "coords": {"x": cx, "y": cy, "box": list(box)},
                            "parent_combobox": name,
                        })
                        self.controls_scanned += 1
            pat = getattr(ctrl_obj, "GetExpandCollapsePattern", lambda: None)()
            if pat and hasattr(pat, "Collapse"):
                pat.Collapse()
            elif CAN_INJECT_INPUT:
                send_keys(0x1B)
        except Exception as e:
            logger.debug("ComboBox item probing failed for '%s': %s", name, e)

    @staticmethod
    def _hash_elements(elements: List[Dict[str, Any]]) -> str:
        payload = json.dumps(
            [{"name": e.get("name"), "type": e.get("type"), "box": e.get("coords", {}).get("box")}
             for e in elements],
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- #
# Process / window discovery helpers (Universal: Win32, Qt, WinUI, Web, Browsers)
# --------------------------------------------------------------------------- #
def find_hwnd_by_process_name(process_name: str) -> Optional[int]:
    ensure_interactive_desktop()
    if not win32gui:
        return None

    target_pids = set()
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name"]):
            name = proc.info["name"] or ""
            if name.lower() == process_name.lower():
                target_pids.add(proc.info["pid"])
    except ImportError:
        pass

    found_hwnd = {"hwnd": None}

    def _enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True
        pid = get_pid_for_hwnd(hwnd)
        if pid in target_pids:
            found_hwnd["hwnd"] = hwnd
            return False
        return True

    try:
        win32gui.EnumWindows(_enum_handler, None)
    except Exception:
        pass
    return found_hwnd["hwnd"]


def find_hwnd_by_title_substring(substring: str, exclude_keywords=("crash", "qmessagebox", "safe mode", "error")) -> Optional[int]:
    ensure_interactive_desktop()
    if not win32gui:
        return None
    found_hwnd = {"hwnd": None}

    def _enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = (win32gui.GetWindowText(hwnd) or "").strip()
        cls = (win32gui.GetClassName(hwnd) or "").strip().lower()
        norm_title = title.lower()
        if any(bad in norm_title or bad in cls for bad in exclude_keywords):
            return True
        if substring.lower() in norm_title:
            found_hwnd["hwnd"] = hwnd
            return False
        return True

    try:
        win32gui.EnumWindows(_enum_handler, None)
    except Exception:
        pass
    return found_hwnd["hwnd"]


def find_app_hwnd(app_identifier: str) -> Optional[int]:
    """
    Universally locates the main visible window for an application by:
    1. Integer/Hex HWND if numeric
    2. Exact or substring match in active UIA root windows
    3. Window title substring via win32gui
    4. Process name (e.g. 'obs64.exe', 'notepad.exe', 'msedge.exe', 'chrome.exe')
    """
    ensure_interactive_desktop()

    roadblock_keywords = ("crash", "qmessagebox", "safe mode", "unclean shutdown", "error")

    # 1. Numeric HWND check
    if isinstance(app_identifier, int):
        if win32gui and win32gui.IsWindow(app_identifier):
            return app_identifier
    if isinstance(app_identifier, str):
        try:
            val = int(app_identifier, 0)
            if win32gui and win32gui.IsWindow(val):
                return val
        except ValueError:
            pass

    norm_id = app_identifier.strip().lower()

    # 2. UIA root window check
    if auto:
        try:
            for win in auto.GetRootControl().GetChildren():
                wname = (win.Name or "").strip()
                wcls = (win.ClassName or "").strip().lower()
                norm_wname = wname.lower()
                if any(bad in norm_wname or bad in wcls for bad in roadblock_keywords):
                    continue
                is_obs_target = "obs" in norm_id
                if (norm_id in norm_wname) or (norm_id in wcls) or (is_obs_target and ("profile:" in norm_wname or "obs " in norm_wname or norm_wname.startswith("obs"))):
                    h = getattr(win, "NativeWindowHandle", 0)
                    if h and (not win32gui or (win32gui.IsWindow(h) and win32gui.IsWindowVisible(h))):
                        return h
        except Exception:
            pass

    # 3. win32gui title substring search
    h = find_hwnd_by_title_substring(app_identifier)
    if h:
        return h
    if "obs" in norm_id:
        h = find_hwnd_by_title_substring("OBS")
        if h:
            return h

    # 4. Process name match
    proc_name = app_identifier if app_identifier.endswith(".exe") else f"{app_identifier}.exe"
    h = find_hwnd_by_process_name(proc_name)
    if h:
        return h

    return None


def ensure_app_running(app_identifier: str = "OBS Studio", exe_path: Optional[str] = None) -> Optional[int]:
    """
    Locates running window for the specified app or launches it.
    Auto-dismisses startup crash/dialog prompts and returns the main window HWND.
    Works universally across Win32, Qt, WPF, Electron, WinUI, and Web browsers.
    """
    ensure_interactive_desktop()

    hwnd = find_app_hwnd(app_identifier)
    if hwnd and win32gui and win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
        logger.info("Found active window for '%s' -> hwnd=%s (0x%x)", app_identifier, hwnd, hwnd)
        bring_to_foreground(hwnd)
        return hwnd

    # Resolve executable path
    target_exe = None
    target_args = []
    if exe_path and os.path.isfile(exe_path):
        target_exe = os.path.abspath(exe_path)
        if "obs" in app_identifier.lower():
            target_args = ["--disable-shutdown-check", "--multi"]
    else:
        norm_id = app_identifier.strip().lower()
        if "obs" in norm_id:
            known = [
                r"D:\obs-studio\bin\64bit\obs64.exe",
                r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
                r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe",
            ]
            target_exe = next((p for p in known if os.path.isfile(p)), None)
            target_args = ["--disable-shutdown-check", "--multi"]
        elif norm_id in ("notepad", "notepad.exe"):
            target_exe = r"C:\Windows\System32\notepad.exe"
        elif norm_id in ("calc", "calculator"):
            target_exe = r"C:\Windows\System32\calc.exe"
        elif norm_id in ("edge", "msedge"):
            known_edge = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]
            target_exe = next((p for p in known_edge if os.path.isfile(p)), None)
        elif norm_id in ("chrome", "google chrome"):
            known_chrome = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]
            target_exe = next((p for p in known_chrome if os.path.isfile(p)), None)
        elif norm_id.startswith("http://") or norm_id.startswith("https://"):
            subprocess.Popen(['cmd.exe', '/c', 'start', '', app_identifier])
            time.sleep(3.0)
            return find_app_hwnd("Edge") or find_app_hwnd("Chrome")
        else:
            import shutil
            found_which = shutil.which(app_identifier) or shutil.which(f"{app_identifier}.exe")
            if found_which and os.path.isfile(found_which):
                target_exe = os.path.abspath(found_which)

    if not target_exe:
        logger.error("Could not locate executable for app '%s'. Provide --exe <path>.", app_identifier)
        return None

    logger.info("Launching '%s' from: %s %s", app_identifier, target_exe, " ".join(target_args))
    working_dir = os.path.dirname(target_exe)

    try:
        if norm_id in ("notepad", "notepad.exe"):
            subprocess.Popen(["powershell.exe", "-Command", "Start-Process 'shell:AppsFolder\\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App'"])
        else:
            subprocess.Popen(['cmd.exe', '/c', 'start', '', target_exe] + target_args, cwd=working_dir)
    except Exception as launch_err:
        logger.warning("Shell start error: %s, falling back to direct Popen", launch_err)
        subprocess.Popen([target_exe] + target_args, cwd=working_dir)

    roadblock_keywords = ("crash", "qmessagebox", "safe mode", "unclean shutdown",
                          "restore previous session", "welcome", "tip of the day", "update available")
    safe_dismiss_buttons = ("Run in Normal Mode", "Run in Safe Mode", "Restore", "Continue",
                            "OK", "Close", "Cancel", "Later", "Don't Send", "No")

    norm_id = app_identifier.strip().lower()
    is_obs = "obs" in norm_id

    for second in range(25):
        time.sleep(1.0)
        if auto:
            try:
                root_children = auto.GetRootControl().GetChildren()
            except Exception:
                root_children = []

            for win in root_children:
                try:
                    wname = (win.Name or "").strip().lower()
                    wcls = (win.ClassName or "").strip().lower()
                    if any(k in wname or k in wcls for k in roadblock_keywords):
                        logger.info("Detected startup roadblock: '%s' (class: %s)", win.Name, win.ClassName)
                        for bname in safe_dismiss_buttons:
                            btn = win.ButtonControl(Name=bname)
                            if btn.Exists(0.2):
                                logger.info("Auto-dismissing startup roadblock via '%s'", bname)
                                pat = btn.GetInvokePattern()
                                if pat:
                                    pat.Invoke()
                                else:
                                    btn.Click()
                                time.sleep(1.0)
                                break
                    elif (norm_id in wname) or (is_obs and ("profile:" in wname or "obs " in wname or wname.startswith("obs"))):
                        h = win.NativeWindowHandle
                        if h and (not win32gui or (win32gui.IsWindow(h) and win32gui.IsWindowVisible(h))):
                            logger.info("Discovered main window for '%s' -> hwnd=%s (0x%x) in %d iteration(s)",
                                        app_identifier, h, h, second + 1)
                            bring_to_foreground(h)
                            return h
                except Exception:
                    continue

        hwnd = find_app_hwnd(app_identifier)
        if hwnd and win32gui and win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
            logger.info("Discovered main window for '%s' -> hwnd=%s (0x%x) in %d iteration(s)",
                        app_identifier, hwnd, hwnd, second + 1)
            bring_to_foreground(hwnd)
            return hwnd

    return find_app_hwnd(app_identifier)


# --------------------------------------------------------------------------- #
# CLI test harness
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Hojaiga Automation OS — Universal Desktop & Webapp UI Crawler / Scanner Organ"
    )
    parser.add_argument(
        "--app",
        default="OBS Studio",
        help="Target app name or window title substring (default: 'OBS Studio')",
    )
    parser.add_argument(
        "--hwnd",
        type=lambda x: int(x, 0),
        default=None,
        help="Target window HWND in decimal or hex (e.g. 0x1234)",
    )
    parser.add_argument(
        "--exe",
        default=None,
        help="Path to application executable if launch is required",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="URL of web application to launch in browser and scan",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output JSON filepath (default: <app_name>_scan_result.json)",
    )
    args = parser.parse_args()

    logger.info("Hojaiga Automation OS — organ_30_app_scanner starting for target: '%s'", args.app)
    ensure_interactive_desktop()

    if args.url:
        import subprocess
        edge_exe = None
        for p in [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]:
            if os.path.isfile(p):
                edge_exe = p
                break
        url_formatted = args.url if args.url.startswith("http") else f"file:///{os.path.abspath(args.url).replace(os.sep, '/')}"
        if edge_exe:
            subprocess.Popen([edge_exe, "--new-window", url_formatted])
        else:
            subprocess.Popen(["cmd.exe", "/c", "start", "", url_formatted])
        time.sleep(3.5)
        hwnd = find_app_hwnd("Edge") or find_app_hwnd("Chrome") or find_app_hwnd(args.app)
    elif args.hwnd:
        hwnd = args.hwnd
        logger.info("Using user-specified target hwnd: %s (0x%x)", hwnd, hwnd)
    else:
        hwnd = ensure_app_running(args.app, exe_path=args.exe)

    if not hwnd:
        logger.error("Target window for '%s' not found. Launch the app and retry.", args.app)
        raise SystemExit(1)

    logger.info("Scanning target window -> hwnd=%s (0x%x)", hwnd, hwnd)

    scanner = AppScanner()
    start = time.time()
    try:
        result = scanner.scan_app_active(args.app, hwnd)
    finally:
        scanner.stop()
    elapsed = time.time() - start

    logger.info("Scan status: %s", result["status"])
    logger.info("Controls scanned: %d | failed: %d | elements: %d",
                result["controls_scanned"], result["controls_failed"], len(result["elements"]))
    logger.info("Tree hash: %s", result["tree_hash"])
    logger.info("Elapsed: %.2fs", elapsed)

    if args.out:
        out_path = args.out
    else:
        safe_name = re.sub(r"[^\w\-]", "_", args.app.lower()).strip("_")
        out_path = f"{safe_name}_scan_result.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    logger.info("Exported results to %s", out_path)
