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
    try:
        from core_organs import headless_input as _hin
        if _hin.on_input_desktop():
            return  # already on the interactive desktop: do not touch window station/desktop
        user32 = ctypes.windll.user32
        hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x0002 | 0x0100 | 0x0200)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if not hdesk:
            hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass

# Attach to interactive desktop immediately before initializing COM/UIA
ensure_interactive_desktop()

try:
    import uiautomation as auto
    # Guard against COM query stalls on non-responsive controls
    auto.SetGlobalSearchTimeout(1.0)
    auto.TIME_OUT_SECOND = 1.0  # type: ignore[assignment]
except ImportError:
    auto = None

try:
    import win32api
    import win32con
    import win32gui
    import win32process
except ImportError:
    win32api = win32con = win32gui = win32process = None

VK_MENU = getattr(win32con, "VK_MENU", 0x12) if win32con else 0x12
KEYEVENTF_KEYUP = getattr(win32con, "KEYEVENTF_KEYUP", 0x0002) if win32con else 0x0002
SW_RESTORE = getattr(win32con, "SW_RESTORE", 9) if win32con else 9
GW_ENABLEDPOPUP = getattr(win32con, "GW_ENABLEDPOPUP", 6) if win32con else 6
WM_CLOSE = getattr(win32con, "WM_CLOSE", 0x0010) if win32con else 0x0010

# --------------------------------------------------------------------------- #
# Unicode-safe UIA walker helper
# --------------------------------------------------------------------------- #

def _safe_walk_control(root_ctrl, includeTop=False, maxDepth=14):
    """
    Unicode-safe UIA walker.

    Primary path: uiautomation's native module-level WalkControl() generator,
    which traverses the tree in the library's own (depth-managed) way. If the
    native walker fails at any point (e.g. WinUI 3 apps raising Unicode errors
    mid-walk), the traversal transparently continues with a manual GetChildren
    walk (deduplicated), so callers always get the deepest possible tree.

    NOTE: a previous revision called this wrapper recursively by mistake, so
    every call burned ~1000 stack frames until RecursionError before falling
    back -- measured ~55 ms per call vs ~23 ms for the direct manual walk.
    """
    def _manual_walk(c, depth=0, max_d=14):
        """Manual recursive GetChildren traversal as fallback."""
        if depth > max_d:
            return
        try:
            for ch in c.GetChildren():
                yield (ch, depth)
                yield from _manual_walk(ch, depth + 1, max_d)
        except Exception:
            return
    
    if auto is None or not hasattr(auto, "WalkControl"):
        return _manual_walk(root_ctrl, 0, maxDepth)

    try:
        native = auto.WalkControl(root_ctrl, includeTop=includeTop, maxDepth=maxDepth)
        first = next(native, None)
    except Exception as e:
        logger.info(f"[UIA] WalkControl failed (Unicode/Error: {type(e).__name__}), using manual GetChildren fallback")
        return _manual_walk(root_ctrl, 0, maxDepth)

    if first is None:
        # Native walker yielded nothing; give the manual walker a chance.
        return _manual_walk(root_ctrl, 0, maxDepth)

    def _chained():
        # Keep strong refs to every yielded control so CPython cannot reuse a
        # freed wrapper's id() for a NEW control (address reuse would make an
        # id()-based dedupe silently drop legitimate nodes).
        seen_refs = []

        def _key(ctrl):
            """Stable per-element key: UIA RuntimeId when the element exposes it."""
            try:
                rid = ctrl.GetRuntimeId()
                if rid:
                    return tuple(rid)
            except Exception:
                pass
            return id(ctrl)

        seen_refs.append(first[0])
        yield first
        try:
            for item in native:
                seen_refs.append(item[0])
                yield item
        except Exception as e:
            # WinUI 3 can abort mid-walk; continue with the manual walker over
            # the controls that were not yielded yet. RuntimeIds are computed
            # only on this rare path, so the happy path pays no extra COM calls.
            logger.info(f"[UIA] WalkControl aborted mid-walk ({type(e).__name__}); manual fallback for the remainder")
            seen_keys = set()
            for ctrl in seen_refs:
                seen_keys.add(_key(ctrl))
            for item in _manual_walk(root_ctrl, 0, maxDepth):
                k = _key(item[0])
                if k not in seen_keys:
                    seen_keys.add(k)
                    yield item

    return _chained()


def _deep_scan_max_depth() -> int:
    """Max UIA tree depth for deep scans (env-overridable, default 32)."""
    try:
        return max(1, int(os.environ.get("HOJAIGA_DEEP_SCAN_MAX_DEPTH", "32")))
    except ValueError:
        return 32


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
# Organ 31 (Eye: Visual Perception) & Organ 01/37 (Brain: Master Reasoning)
# --------------------------------------------------------------------------- #
try:
    from core_organs.organ_31_visual_perception import VisualPerceptionOrgan
except ImportError:
    VisualPerceptionOrgan = None

try:
    from core_organs.organ_37_llm_gateway import LLMGateway
except ImportError:
    LLMGateway = None

class EyeAndBrainOrchestrator:
    """
    Synergizes Organ 31 (Eye / Visual Perception) and Organ 01/37 (Brain / Reasoning Engine)
    to empower App Scanner when accessibility trees provide unlabeled icons or ambiguous popups.
    """
    def __init__(self):
        self.eye = None
        if VisualPerceptionOrgan is not None:
            try:
                self.eye = VisualPerceptionOrgan()
            except Exception as e:
                logging.getLogger("organ_30").debug("Visual Perception init failed: %s", e)
        
        self.llm = None
        if LLMGateway is not None:
            try:
                self.llm = LLMGateway()
            except Exception as e:
                logging.getLogger("organ_30").debug("LLM Gateway init failed: %s", e)

    def visually_inspect_control(self, box: Tuple[int, int, int, int]) -> Optional[str]:
        """Uses Eye (crop + OCR / Vision model) to read unlabeled icons or graphical buttons."""
        if not box:
            return None
        try:
            from PIL import ImageGrab
            import pytesseract
            # Crop exact bounding box with a 2px padding
            l, t, r, b = box
            crop_box = (max(0, l - 2), max(0, t - 2), r + 2, b + 2)
            img = ImageGrab.grab(bbox=crop_box)
            text = pytesseract.image_to_string(img).strip()
            if text and len(text) > 1:
                return text
        except Exception:
            pass
        return None

    def reason_about_action(self, app_name: str, control_name: str, control_type: str, box: Tuple[int, int, int, int]) -> Dict[str, Any]:
        """Consults Brain (LLM Gateway) when a control is ambiguous or safety is uncertain."""
        if not self.llm:
            return {"allow_click": True, "rationale": "Brain offline, defaulting to safe exploration"}
        prompt = (
            f"You are the Brain of the Hojaiga Automation OS. We are deeply scanning application '{app_name}'.\n"
            f"We encountered UI control '{control_name}' of type '{control_type}' at screen coordinates {box}.\n"
            f"Determine whether this control is safe to click during exploratory crawling.\n"
            f"Rules:\n"
            f"- Forbidden: destructive deletes, sign-out, formatting, closing the main window.\n"
            f"- Allowed: dialog triggers, settings, view options, palettes, formatting buttons, menus.\n"
            f"Respond ONLY in JSON format: {{\"allow_click\": true/false, \"suggested_alias\": \"...\", \"rationale\": \"...\"}}"
        )
        try:
            res = self.llm.execute_inference(
                system="You are the Cognitive Brain of Hojaiga Automation OS.",
                prompt=prompt,
                temperature=0.1,
                timeout=4.0
            )
            # Parse JSON
            m = re.search(r"\{.*\}", res, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    allow = data.get("allow_click", True)
                    alias = data.get("suggested_alias") or control_name
                    return {"allow_click": allow, "suggested_alias": alias, "rationale": data.get("rationale", "")}
        except Exception:
            pass
        return {"allow_click": True, "rationale": "Brain fast-path default"}

    def deep_scan_unknown_app(self, app_name: str = "", screenshot_b64: Optional[str] = None, target_hwnd: int = 0, quiet: bool = False) -> Dict[str, Any]:
        """
        DEEP SCAN: Learn a new app/interface completely.

        Phase 1: Find the target window
        Phase 2: Full UIA tree walk — find ALL controls (buttons, menus, text areas, panels)
        Phase 3: Menu exploration — open each menu, record every submenu item and shortcut
        Phase 4: VLM screenshot — understand context, purpose, current state
        Phase 5: Store comprehensive knowledge for future automation

        This is NOT a snapshot. This is LEARNING the app.
        """
        import base64, io

        # ── Phase 1: Find target window ──
        try:
            ensure_interactive_desktop()
            import win32gui

            # 1. Use pre-found hwnd from caller (most reliable — no race condition)
            if target_hwnd and win32gui.IsWindow(target_hwnd) and win32gui.IsWindowVisible(target_hwnd):
                logger.info("[DEEP SCAN] Using pre-found hwnd=%d", target_hwnd)
            else:
                target_hwnd = None

                # 2. Poll _last_launched_app for up to 4 seconds (race condition with launch)
                try:
                    import sys
                    sys.path.insert(0, r"D:\new_automation\All codes\core_organs")
                    from organ_01_crewai_engine import _last_launched_app
                    for _ in range(40):  # 4 seconds
                        h = _last_launched_app.get("hwnd", 0)
                        last_app = (_last_launched_app.get("app_name") or "").lower()
                        # CRITICAL: Only use _last_launched_app if it matches the requested app_name!
                        matches_app = not app_name or app_name.lower() in last_app or last_app in app_name.lower() or ("calc" in app_name.lower() and "calc" in last_app)
                        if h and win32gui.IsWindow(h) and win32gui.IsWindowVisible(h) and matches_app:
                            target_hwnd = h
                            app_name = _last_launched_app.get("app_name", app_name)
                            logger.info("[DEEP SCAN] Got hwnd=%d from _last_launched_app", h)
                            break
                        time.sleep(0.1)
                except Exception:
                    pass

                # 3. Search by app name
                if not target_hwnd and app_name:
                    app_lower = app_name.lower()
                    is_calc = "calc" in app_lower
                    candidates = []
                    def _find(h, _):
                        if not win32gui.IsWindowVisible(h):
                            return True
                        t = win32gui.GetWindowText(h) or ""
                        c = win32gui.GetClassName(h) or ""
                        cl = c.lower()
                        tl = t.lower()
                        if is_calc:
                            if "calculator" in tl or "calc" in tl or (cl == "applicationframewindow" and "calc" in tl):
                                candidates.append((h, t, c, 5))
                        elif app_lower == cl:
                            candidates.append((h, t, c, 3))
                        elif app_lower in cl:
                            candidates.append((h, t, c, 2))
                        elif app_lower in tl and "gdi" not in cl:
                            candidates.append((h, t, c, 1))
                        return True
                    try:
                        win32gui.EnumWindows(_find, None)
                    except Exception:
                        pass

                    # Poll for up to 5 seconds if not found (window may still be appearing)
                    if not candidates:
                        for _ in range(50):
                            time.sleep(0.1)
                            try:
                                win32gui.EnumWindows(_find, None)
                            except Exception:
                                pass
                            if candidates:
                                break

                    if candidates:
                        candidates.sort(key=lambda x: (x[3], x[0]), reverse=True)
                        target_hwnd = candidates[0][0]

                # 5. Fallback: Auto-launch application if not currently running
                if not target_hwnd and app_name:
                    app_lower = app_name.lower()
                    exe_map = {
                        "calculator": "calc.exe", "calc": "calc.exe",
                        "notepad": "notepad.exe", "paint": "mspaint.exe",
                        "wordpad": "wordpad.exe",
                    }
                    exe = exe_map.get(app_lower, f"{app_lower}.exe")
                    try:
                        logger.info("[DEEP SCAN] Target '%s' not open, auto-launching '%s'...", app_name, exe)
                        if app_lower in ("paint", "mspaint"):
                            try:
                                subprocess.Popen(['explorer.exe', r'shell:AppsFolder\Microsoft.Paint_8wekyb3d8bbwe!App'])
                            except Exception:
                                ctypes.windll.shell32.ShellExecuteW(None, "open", "mspaint.exe", None, None, 1)
                        else:
                            ctypes.windll.shell32.ShellExecuteW(None, "open", exe, None, None, 1)
                        time.sleep(2.5)
                        candidates = []
                        for _ in range(30):
                            time.sleep(0.1)
                            try:
                                win32gui.EnumWindows(_find, None)
                            except Exception:
                                pass
                            if candidates:
                                candidates.sort(key=lambda x: (x[3], x[0]), reverse=True)
                                target_hwnd = candidates[0][0]
                                logger.info("[DEEP SCAN] Found newly launched hwnd=%d for '%s'", target_hwnd, app_name)
                                break
                    except Exception as launch_err:
                        logger.debug("[DEEP SCAN] Auto-launch failed: %s", launch_err)

            if not target_hwnd:
                return {"status": "error", "message": f"Could not find window for '{app_name}'"}

            # VERIFY: check the title matches what we expect
            actual_title = win32gui.GetWindowText(target_hwnd) or ""
            actual_class = win32gui.GetClassName(target_hwnd) or ""
            logger.info("[DEEP SCAN] Selected window: hwnd=%d class='%s' title='%s'",
                        target_hwnd, actual_class, actual_title)

            # Ensure window is restored and brought to foreground so WinUI 3 / XAML / UWP controls are rendered
            is_uwp = actual_class == "ApplicationFrameWindow" or "calc" in actual_title.lower() or "calc" in actual_class.lower()
            stealth = os.environ.get("HOJAIGA_STEALTH_MODE", "1").strip().lower() in ("1", "true", "yes")
            try:
                needs_restore = win32gui.IsIconic(target_hwnd) or is_uwp
                if needs_restore:
                    if not stealth:
                        ctypes.windll.user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
                        time.sleep(0.3)
                    else:
                        ctypes.windll.user32.ShowWindow(target_hwnd, 4)  # SW_SHOWNOACTIVATE
                        time.sleep(0.2)
                if not stealth and (not quiet or is_uwp):
                    bring_to_foreground(target_hwnd)
                    time.sleep(0.5)
                    new_fg = win32gui.GetForegroundWindow()
                    if new_fg != target_hwnd:
                        logger.warning("[DEEP SCAN] Foreground mismatch: expected %d, got %d", target_hwnd, new_fg)
                        ctypes.windll.user32.SetForegroundWindow(target_hwnd)
                        time.sleep(0.3)
            except Exception:
                pass

        except Exception as e:
            return {"status": "error", "message": f"Window search failed: {e}"}

        # ── Phase 2: Full UIA tree walk — find ALL controls ──
        all_controls = []
        menu_headers = set()
        nodes_walked = 0      # total nodes yielded by the walker (pre-filter)
        max_depth_seen = 0    # deepest level actually reached
        try:
            if auto:
                if not quiet or is_uwp:
                    bring_to_foreground(target_hwnd)
                    time.sleep(0.3)
                root_ctrl = auto.ControlFromHandle(target_hwnd)
                if root_ctrl:
                    win_box = safe_bounding_rect(root_ctrl)

                    # Walk the full UIA tree — only from our target window
                    seen_sigs = set()
                    target_pid = win32process.GetWindowThreadProcessId(target_hwnd)[1]

                    # Use Unicode-safe walker for WinUI 3 compatibility.
                    # Deep scan walks the tree fully (env-overridable depth)
                    # so learned knowledge covers nested panels/ribbons too.
                    walker = _safe_walk_control(root_ctrl, includeTop=False, maxDepth=_deep_scan_max_depth())

                    # Track ribbon hierarchy, groups, and interactive canvas workspaces
                    ribbon_tabs = []
                    ribbon_groups = {}
                    detected_canvases = []
                    current_tab = ""
                    current_group = ""

                    for ctrl, depth in walker:
                        nodes_walked += 1
                        if depth > max_depth_seen:
                            max_depth_seen = depth
                        try:
                            box = safe_bounding_rect(ctrl)
                            if not box:
                                continue
                            # In quiet mode (minimized apps), skip on-screen check —
                            # controls exist in UIA tree even when off-screen
                            if not quiet and not is_onscreen(box):
                                continue
                            ctype = ctrl.ControlTypeName or ""

                            # Track ribbon tabs
                            if ctype in ("TabItemControl", "TabControl"):
                                t_name = (ctrl.Name or "").strip()
                                if t_name and t_name not in ribbon_tabs:
                                    ribbon_tabs.append(t_name)
                                    current_tab = t_name

                            # Track ribbon groups
                            if ctype in ("GroupControl", "ToolBarControl"):
                                g_name = (ctrl.Name or "").strip()
                                if g_name and g_name not in ribbon_groups:
                                    ribbon_groups[g_name] = {"tab": current_tab, "controls": []}
                                    current_group = g_name

                            # Detect interactive Canvas / Workspace area
                            if win_box and not quiet:
                                ctrl_w = box[2] - box[0]
                                ctrl_h = box[3] - box[1]
                                ctrl_area = ctrl_w * ctrl_h
                                win_w = max(1, win_box[2] - win_box[0])
                                win_h = max(1, win_box[3] - win_box[1])
                                win_area = win_w * win_h
                                ratio = ctrl_area / float(win_area)

                                ctrl_name_lower = (ctrl.Name or "").strip().lower()
                                ctrl_id_lower = (ctrl.AutomationId or "").strip().lower()
                                is_canvas_cand = (ratio > 0.20 and ctype in ("PaneControl", "CustomControl", "ImageControl", "DocumentControl"))
                                if is_canvas_cand and (any(k in ctrl_name_lower or k in ctrl_id_lower for k in ("canvas", "scrollviewer", "paint", "image", "draw", "viewport", "workspace", "document", "editor")) or not ctrl_name_lower):
                                    cx_c, cy_c = center_of(box)
                                    canvas_name = ctrl.Name or "Canvas Workspace"
                                    if not any(c.get("coords", {}).get("box") == list(box) for c in detected_canvases):
                                        detected_canvases.append({
                                            "name": canvas_name,
                                            "type": "Canvas",
                                            "coords": {"x": cx_c, "y": cy_c, "box": list(box)},
                                            "page_bounds": {"left": box[0], "top": box[1], "right": box[2], "bottom": box[3], "width": ctrl_w, "height": ctrl_h},
                                            "purpose": "CANVAS / DRAWING WORKSPACE — entire page area. Use virtual cursor drag / draw tools across any part of this page",
                                            "interactable": True,
                                        })

                            # FILTER: skip controls not in our target window's bounding box
                            # (WalkControl sometimes leaks into other windows)
                            # In quiet mode, skip this filter — minimized windows have no valid win_box
                            if win_box and not quiet:
                                cx_test, cy_test = center_of(box)
                                if (cx_test < win_box[0] or cx_test > win_box[2] or
                                    cy_test < win_box[1] or cy_test > win_box[3]):
                                    continue
                        except Exception:
                            continue

                        if not quiet and is_viewport_canvas(ctrl, box, win_box):
                            continue

                        is_actionable = ctype in ACTIONABLE_CONTROL_TYPES or ctype in ("MenuBarControl", "MenuControl")
                        if not is_actionable and ctype == "TextControl":
                            ctrl_name_lower = (ctrl.Name or "").strip().lower()
                            if any(k in ctrl_name_lower for k in ["display", "result", "status", "output", "value", "=", "+", "-", "*", "/"]) or re.search(r'\d+', ctrl_name_lower):
                                is_actionable = True
                        ctrl_pattern = ""
                        if not is_actionable:
                            try:
                                if hasattr(ctrl, "GetInvokePattern") and ctrl.GetInvokePattern() is not None:
                                    is_actionable, ctrl_pattern = True, "invoke"
                                elif hasattr(ctrl, "GetTogglePattern") and ctrl.GetTogglePattern() is not None:
                                    is_actionable, ctrl_pattern = True, "toggle"
                                elif hasattr(ctrl, "GetSelectionItemPattern") and ctrl.GetSelectionItemPattern() is not None:
                                    is_actionable, ctrl_pattern = True, "selection"
                                elif hasattr(ctrl, "GetExpandCollapsePattern") and ctrl.GetExpandCollapsePattern() is not None:
                                    is_actionable, ctrl_pattern = True, "expandcollapse"
                            except Exception:
                                pass
                        else:
                            # Record the strongest UIA pattern for actionable
                            # control types too (first match wins; usually one
                            # COM call for the common button/menuitem cases).
                            for _p_name, _p_get in (
                                ("invoke", "GetInvokePattern"),
                                ("toggle", "GetTogglePattern"),
                                ("selection", "GetSelectionItemPattern"),
                                ("expandcollapse", "GetExpandCollapsePattern"),
                            ):
                                try:
                                    _fn = getattr(ctrl, _p_get, None)
                                    if _fn and _fn() is not None:
                                        ctrl_pattern = _p_name
                                        break
                                except Exception:
                                    continue

                        if not is_actionable:
                            continue

                        name = resolve_control_name(ctrl, ctype, eye_brain=self)
                        if not name:
                            name = ctype

                        cx, cy = center_of(box)
                        sig = f"{name}:{ctype}:{box}"
                        if sig in seen_sigs:
                            continue
                        seen_sigs.add(sig)

                        ctrl_data = {
                            "name": name,
                            "type": ctype,
                            "coords": {"x": cx, "y": cy, "box": list(box)},
                            "ribbon_group": current_group if current_group else "",
                            "ribbon_tab": current_tab if current_tab else "",
                            "automation_id": ctrl.AutomationId or "",
                            "class_name": ctrl.ClassName or "",
                            "pattern": ctrl_pattern,
                            "depth": depth,
                        }
                        all_controls.append(ctrl_data)
                        if current_group and current_group in ribbon_groups:
                            if name not in ribbon_groups[current_group]["controls"]:
                                ribbon_groups[current_group]["controls"].append(name)

                    all_controls = sort_controls_spatially(all_controls)

                    # Identify menu headers
                    for item in all_controls:
                        name = (item.get("name") or "").strip()
                        ctype = item.get("type", "")
                        box = item.get("coords", {}).get("box", [-1, -1, -1, -1])
                        if ctype in ("MenuItemControl", "MenuBarControl"):
                            if name.lower() in DEFAULT_MENU_ACCELERATORS:
                                menu_headers.add(name)
                            elif win_box and box[1] < win_box[1] + 120:
                                menu_headers.add(name)

                    logger.info("[DEEP SCAN] UIA: %d nodes walked, %d actionable controls, %d menu headers (max depth %d) in '%s'",
                                nodes_walked, len(all_controls), len(menu_headers), max_depth_seen,
                                win32gui.GetWindowText(target_hwnd))
        except Exception as e:
            logger.warning("[DEEP SCAN] UIA scan failed: %s", e)

        # ── Phase 3: Menu exploration — discover ALL features (skip in quiet mode) ──
        menu_items = []
        if menu_headers and not quiet:
            try:
                scanner = MenuScanner(target_hwnd, menu_headers,
                                      root_ctrl=auto.ControlFromHandle(target_hwnd) if auto else None)
                for header in menu_headers:
                    items = scanner.scan_menu(header)
                    for item in items:
                        item["parent_menu"] = header
                    menu_items.extend(items)
                    logger.info("[DEEP SCAN] Menu '%s': %d items", header, len(items))
                    time.sleep(0.2)
            except Exception as e:
                logger.warning("[DEEP SCAN] Menu scan failed: %s", e)

        # ── Phase 4: VLM screenshot — SKIPPED for speed ──
        vlm_meta = {}

        # ── Phase 5: Build comprehensive knowledge ──
        seen = set()
        ui_elements = []

        # 1. Register detected interactive canvases / drawing workspaces first
        for c in detected_canvases:
            c_name = c.get("name", "Canvas Workspace")
            c_box = c.get("coords", {}).get("box", [])
            c_cx = c.get("coords", {}).get("x", 0)
            c_cy = c.get("coords", {}).get("y", 0)
            sig = f"canvas:{c_box}"
            if sig not in seen:
                seen.add(sig)
                ui_elements.append({
                    "name": c_name,
                    "type": "canvas",
                    "purpose": "CANVAS / DRAWING WORKSPACE — entire page area. Use virtual cursor drag / draw tools across any part of this page",
                    "interactable": True,
                    "keyboard_hint": "",
                    "click_coords": {"x": c_cx, "y": c_cy} if c_cx and c_cy else None,
                    "coords": c.get("coords", {}),
                    "page_bounds": c.get("page_bounds", {}),
                    "action_hint": "DRAW: Use 'Draw Shape On Canvas' or 'Draw On App Full Page' on this area",
                })

        for item in all_controls:
            name = item.get("name", "")
            if not name:
                continue
            sig = f"{name}:{item.get('type','')}"
            if sig in seen:
                continue
            seen.add(sig)
            ctype = item.get("type", "")

            purpose = ""
            keyboard_hint = ""
            if ctype == "EditControl":
                purpose = "TEXT INPUT AREA — type text here"
                keyboard_hint = "TypeText"
            elif ctype == "DocumentControl":
                purpose = "DOCUMENT/EDITOR — main content area"
                keyboard_hint = "TypeText"
            elif ctype == "ButtonControl":
                purpose = f"button: {name}"
            elif ctype in ("MenuItemControl", "MenuBarControl"):
                purpose = f"menu: {name}"
                keyboard_hint = DEFAULT_MENU_ACCELERATORS.get(name.lower(), "")
            elif ctype == "ComboBoxControl":
                purpose = f"dropdown: {name}"
            elif ctype == "CheckBoxControl":
                purpose = f"checkbox: {name}"
            elif ctype == "TabControl":
                purpose = f"tab group: {name}"
            elif ctype == "ToolBarControl":
                purpose = f"toolbar: {name}"
            elif ctype == "TitleBarControl":
                purpose = "title bar"
            elif ctype == "StatusBarControl":
                purpose = "status bar"
            elif ctype == "ListItemControl":
                purpose = f"item/tool: {name}"
            elif ctype == "RadioButtonControl":
                purpose = f"radio/selection: {name}"
            else:
                purpose = f"{ctype}: {name}"

            # Annotate with Ribbon Group / Tab if discovered
            ribbon_grp = item.get("ribbon_group", "")
            ribbon_tab = item.get("ribbon_tab", "")
            if ribbon_grp:
                purpose += f" [Ribbon Group: '{ribbon_grp}']"
                if ribbon_tab:
                    purpose += f" (Tab: '{ribbon_tab}')"

            # Add click coordinates and action hint for each element
            coords = item.get("coords", {})
            cx = coords.get("x", 0)
            cy = coords.get("y", 0)
            box = coords.get("box", [])

            action_hint = ""
            if ctype in ("ButtonControl", "ListItemControl", "RadioButtonControl"):
                action_hint = f"CLICK: Use 'Click Button By Name' or 'Visually Locate and Click' with element_description='{name}'"
            elif ctype in ("EditControl", "DocumentControl"):
                action_hint = "TYPE: Use 'Type Text Into Active Window'"
            elif ctype in ("MenuItemControl", "MenuBarControl"):
                action_hint = f"CLICK: Use 'Visually Locate and Click' with element_description='{name} (menuitem)'"
            elif ctype == "ComboBoxControl":
                action_hint = f"CLICK: Use 'Visually Locate and Click' with element_description='{name}'"
            elif ctype == "CheckBoxControl":
                action_hint = f"CLICK: Use 'Visually Locate and Click' with element_description='{name}'"

            el = {
                "name": name,
                "type": ctype.replace("Control", "").lower(),
                "purpose": purpose,
                "interactable": ctype in ACTIONABLE_CONTROL_TYPES,
                "keyboard_hint": keyboard_hint,
                "click_coords": {"x": cx, "y": cy} if cx and cy else None,
                "action_hint": action_hint,
                "ribbon_group": ribbon_grp,
                "ribbon_tab": ribbon_tab,
                "automation_id": item.get("automation_id", ""),
                "class_name": item.get("class_name", ""),
                "pattern": item.get("pattern", ""),
                "depth": item.get("depth", 0),
            }
            if coords:
                el["coords"] = coords
            ui_elements.append(el)

        for item in menu_items:
            name = item.get("name", "")
            if not name:
                continue
            parent = item.get("parent_menu", "")
            sig = f"{parent}>{name}"
            if sig in seen:
                continue
            seen.add(sig)
            el = {
                "name": name,
                "type": "menuitem",
                "purpose": f"menu item: {parent} > {name}",
                "interactable": True,
                "parent_menu": parent,
                "keyboard_hint": item.get("accelerator", ""),
            }
            coords = item.get("coords", {})
            if coords:
                el["coords"] = coords
            ui_elements.append(el)

        # Determine app interaction type from scan results
        has_text_area = any(el.get("type") in ("edit", "document") for el in ui_elements)
        button_count = sum(1 for el in ui_elements if el.get("type") in ("button", "listitem", "radiobutton"))
        has_only_buttons = button_count > 0 and not has_text_area

        if has_only_buttons:
            app_interaction = "BUTTON_APP"
            interaction_guide = (
                f"This is a BUTTON-BASED app with {button_count} buttons. "
                "DO NOT type text into it. Use 'Visually Locate and Click' to click buttons by name. "
                "Example: to press '1', use element_description='1'."
            )
        elif has_text_area:
            app_interaction = "TEXT_APP"
            interaction_guide = (
                "This app has a TEXT INPUT area. Use 'Type Text Into Active Window' to type. "
                "Use 'Press Key' for keyboard shortcuts."
            )
        else:
            app_interaction = "MIXED_APP"
            interaction_guide = (
                "This app has mixed controls. Use 'Scan App UI' results to decide "
                "whether to click buttons or type text for each action."
            )

        scan_data = {
            "app_name": vlm_meta.get("app_name", app_name or "unknown"),
            "app_type": vlm_meta.get("app_type", "desktop"),
            "app_interaction": app_interaction,
            "interaction_guide": interaction_guide,
            "current_state": vlm_meta.get("current_state", "unknown"),
            "ui_elements": ui_elements,
            "ribbon_tabs": ribbon_tabs,
            "ribbon_groups": ribbon_groups,
            "canvases": detected_canvases,
            "menu_headers": list(menu_headers),
            "blocking_elements": vlm_meta.get("blocking_elements", []),
            "suggested_first_action": vlm_meta.get("suggested_first_action", ""),
            "automation_notes": vlm_meta.get("automation_notes", ""),
            "total_controls": len(all_controls),
            "total_menu_items": len(menu_items),
            "total_elements": len(ui_elements),
            "tree_stats": {
                "nodes_walked": nodes_walked,
                "actionable_controls": len(all_controls),
                "max_depth_seen": max_depth_seen,
                "walk_max_depth": _deep_scan_max_depth(),
            },
            "status": "success" if ui_elements else "partial",
            "scan_timestamp": time.time(),
            "screenshot_b64_length": len(screenshot_b64) if screenshot_b64 else 0,
        }

        if ui_elements:
            self._store_app_knowledge(app_name or scan_data.get("app_name", "unknown"), scan_data)

        logger.info("[DEEP SCAN] %s: %d controls, %d menu items, %d total elements",
                    scan_data.get("app_name"), len(all_controls), len(menu_items), len(ui_elements))

        return scan_data

    def _store_app_knowledge(self, app_name: str, scan_data: Dict[str, Any]) -> None:
        """Store discovered app knowledge in the database for future automation."""
        try:
            from core_organs.organ_knowledge_manager import AppKnowledgeManager
            km = AppKnowledgeManager.get_instance()
            filepath = km.save_knowledge(app_name, scan_data)
            logger.info("[DEEP SCAN] App knowledge stored via AppKnowledgeManager: %s", filepath)
        except Exception as e:
            logger.debug("[DEEP SCAN] AppKnowledgeManager save failed: %s", e)
            try:
                knowledge_path = os.path.join(
                    os.path.dirname(__file__), "..", "var", "hojaiga", "app_knowledge"
                )
                os.makedirs(knowledge_path, exist_ok=True)
                safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", app_name.lower()).strip("_")
                filepath = os.path.join(knowledge_path, f"{safe_name}.json")
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(scan_data, f, indent=2, default=str)
                logger.info("[DEEP SCAN] App knowledge stored fallback: %s", filepath)
            except Exception as e2:
                logger.debug("[DEEP SCAN] Failed to store knowledge fallback: %s", e2)

    def discover_and_learn(self, hwnd: int = 0) -> Dict[str, Any]:
        """
        Auto-discover: take screenshot of whatever is on screen,
        identify the app, deep-scan it, store knowledge.
        Called when a NEW/unknown app is encountered.
        """
        import base64, io

        # Capture full screen
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            screenshot_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            return {"status": "error", "message": f"Screenshot failed: {e}"}

        # Deep scan with VLM
        result = self.deep_scan_unknown_app(screenshot_b64=screenshot_b64)
        return result

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logger = logging.getLogger("organ_30_app_scanner")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
if os.environ.get("HOJAIGA_QUIET_LOGS", "1") == "1":
    logger.setLevel(logging.WARNING)
else:
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
    "DocumentControl", "ListItemControl", "RadioButtonControl", "TabItemControl",
    "HyperlinkControl", "MenuItemControl", "SliderControl", "TreeItemControl",
    "SplitButtonControl", "AppBarButtonControl",
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

# Known native Win32 window classes for Office / major desktop apps.
# Used by find_app_hwnd() to prefer the correct top-level window over
# WebView2 overlays or satellite windows.
KNOWN_APP_WINDOW_CLASSES = {
    "excel": "XLMAIN",
    "microsoft excel": "XLMAIN",
    "word": "OpusApp",
    "microsoft word": "OpusApp",
    "winword": "OpusApp",
    "powerpoint": "PPTFrameClass",
    "microsoft powerpoint": "PPTFrameClass",
    "powerpnt": "PPTFrameClass",
    "outlook": "rctrl_renwnd32",
}


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


def _in_parked_window(l: int, t: int, r: int, b: int) -> bool:
    """True when the box lies inside a window background_window has parked off-screen. A parked
    (formerly minimized) window is laid out at real size but outside every monitor, so the
    'is it on screen' filters must treat its interior as valid coordinate space."""
    try:
        from core_organs import background_window as _bw
        return any(pl <= l and pt <= t and r <= pr + 2 and b <= pb + 2 for pl, pt, pr, pb in _bw.parked_rects())
    except Exception:
        return False


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
            if not _in_parked_window(l, t, rr, b):
                return None
        return (l, t, rr, b)
    except Exception:
        return None


def is_onscreen(box: Tuple[int, int, int, int]) -> bool:
    if not box:
        return False
    l, t, r, b = box
    cx, cy = (l + r) // 2, (t + b) // 2
    if _in_parked_window(l, t, r, b):
        return True
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
    if os.environ.get("HOJAIGA_STEALTH_MODE", "1").strip().lower() in ("1", "true", "yes"):
        return True
    ensure_interactive_desktop()
    for attempt in range(retries):
        try:
            if hasattr(ctypes.windll.user32, "SwitchToThisWindow"):
                ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
            win32gui.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.05)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            logger.debug("SetForegroundWindow attempt %d failed: %s", attempt + 1, e)
            try:
                if win32api:
                    win32api.keybd_event(VK_MENU, 0, 0, 0)
                    win32api.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.1)
                win32gui.SetForegroundWindow(hwnd)
                return True
            except Exception:
                time.sleep(0.15)
    return False


def _probe_input_capability() -> bool:
    """Input capability probe without moving hardware mouse."""
    return True


# Keyboard injection enabled (keybd_event). Mouse is ALWAYS virtual (PostMessage — never moved).
CAN_INJECT_INPUT = True
logger.info("Input mode: KEYBOARD via keybd_event + MOUSE via PostMessage (cursor never moves)")


def uia_activate(ctrl, fallback_coords: Optional[Tuple[int, int]] = None, target_hwnd: int = 0) -> bool:
    """
    Activates an actionable control using UIA patterns first (Invoke, Expand, Select, Toggle),
    gracefully falling back to virtual click (PostMessage — no cursor movement) if available.
    Runs pat.Invoke in a daemon worker thread with 0.35s timeout to prevent COM
    synchronous lockups when a modal dialog enters a nested message loop.
    """
    if ctrl is None:
        if fallback_coords:
            hwnd = target_hwnd or (getattr(ctrl, 'NativeWindowHandle', 0) if ctrl else 0)
            if hwnd:
                return virtual_click(hwnd, fallback_coords[0], fallback_coords[1])
            elif CAN_INJECT_INPUT:
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


def virtual_click(hwnd: int, x: int, y: int, ctrl=None, settle: float = 0.15) -> bool:
    """
    Virtual mouse click via PostMessage — does NOT move the real mouse cursor.
    Sends WM_LBUTTONDOWN/WM_LBUTTONUP to the target window at (x, y) in client coords.
    Falls back to UIA patterns if PostMessage fails.
    """
    user32 = ctypes.windll.user32
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    MK_LBUTTON = 0x0001
    lparam = MAKELPARAM(x, y)

    try:
        # Convert screen coords to client coords if needed
        pt = ctypes.wintypes.POINT(x, y)
        ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(pt))
        lparam = MAKELPARAM(pt.x, pt.y)

        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        time.sleep(0.05)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
        time.sleep(settle)
        return True
    except Exception as e:
        logger.debug("virtual_click PostMessage failed at hwnd=%d: %s", hwnd, e)

    # Fallback: UIA pattern
    if ctrl is not None:
        return uia_activate(ctrl, fallback_coords=(x, y))

    return False


def MAKELPARAM(lo: int, hi: int) -> int:
    """Pack two 16-bit values into a 32-bit lParam."""
    return (hi << 16) | (lo & 0xFFFF)


def physical_click(x: int, y: int, ctrl=None, settle: float = 0.15) -> bool:
    """
    Virtual mouse click via background PostMessage and visual cursor animation.
    NEVER moves or steals the user's physical mouse.
    """
    ensure_interactive_desktop()

    if ctrl is not None:
        activated = uia_activate(ctrl, fallback_coords=(x, y))
        if activated:
            return True

    # Use virtual_click targeting the window under (x, y)
    user32 = ctypes.windll.user32
    pt = ctypes.wintypes.POINT(int(x), int(y))
    hwnd = user32.WindowFromPoint(pt)
    if hwnd:
        return virtual_click(hwnd, x, y, ctrl=ctrl, settle=settle)

    try:
        from core_organs.visual_cursor import click_visual
        click_visual(x, y)
        return True
    except Exception:
        pass

    return False


def sort_controls_spatially(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda it: (it["coords"]["box"][1], it["coords"]["box"][0]))


def send_keys(*vks_and_pauses, target_hwnd: int = 0):
    """Deliver key presses to ``target_hwnd`` as posted window messages (headless).

    The physical keyboard is never used. With no target window the keys are NOT sent
    (undeliverable) - they would otherwise land in whatever the user has in front."""
    from core_organs import headless_input as _hin
    if not target_hwnd:
        logger.warning("send_keys: no target_hwnd; refusing to send keys blind")
        return False
    vks = [v for v in vks_and_pauses if isinstance(v, int)]
    # A leading modifier + key is one chord (e.g. Ctrl+N); otherwise each key is its own press.
    if len(vks) == 2 and vks[0] in (0x11, 0x10, 0x12):
        return _hin.post_vk_chord(target_hwnd, vks)[0]
    ok = True
    for vk in vks:
        ok = _hin.post_vk_chord(target_hwnd, [vk])[0] and ok
        time.sleep(0.05)
    return ok


def send_alt_sequence(accel: str, target_hwnd: int = 0):
    """Alt+key accelerator sequence, posted to ``target_hwnd`` (headless)."""
    from core_organs import headless_input as _hin
    if not accel.startswith("%") or not target_hwnd:
        return False
    ok = True
    for ch in accel[1:]:
        ok = _hin.post_vk_chord(target_hwnd, [0x12, ord(ch.upper())])[0] and ok
        time.sleep(0.08)
    return ok


def virtual_send_text(text: str, target_hwnd: int):
    """Send text characters to a window via PostMessage WM_CHAR — no real keyboard input."""
    user32 = ctypes.windll.user32
    WM_CHAR = 0x0102
    for ch in text:
        try:
            user32.PostMessageW(target_hwnd, WM_CHAR, ord(ch), 0)
            time.sleep(0.02)
        except Exception:
            pass


def bypass_office_start_screen(hwnd: int, app_name: str = "Excel") -> None:
    """Dismisses the Office Start Screen (template chooser) to reach active document.

    Office apps (Excel, Word, PowerPoint) show a Start Screen on launch (Backstage).
    The window title is the bare app name (e.g. 'Excel') without a document name.
    Clicks 'Blank workbook' / 'Blank document' via UIA, or falls back to Escape/Ctrl+N.
    """
    if not win32gui or not hwnd:
        return
    try:
        title = (win32gui.GetWindowText(hwnd) or "").strip()
    except Exception:
        return
    bare_names = {"excel", "word", "powerpoint", "microsoft excel",
                  "microsoft word", "microsoft powerpoint"}
    norm_app = app_name.strip().lower()
    if title.lower() in bare_names or "excel" in norm_app or "word" in norm_app or "powerpoint" in norm_app:
        logger.info("[START SCREEN] Checking Office Start Screen for '%s' (title: '%s')...", app_name, title)
        bring_to_foreground(hwnd)
        time.sleep(0.5)

        # 1. Try UIA template selection ("Blank workbook" / "Blank document" / "Blank Presentation")
        if auto:
            try:
                win = auto.ControlFromHandle(hwnd)
                if win:
                    full = win.PaneControl(ClassName="FullpageUIHost")
                    if full.Exists(1.0):
                        logger.info("[START SCREEN] Found FullpageUIHost (Backstage). Locating blank template...")
                        target_templates = ("Blank workbook", "Blank document", "Blank Presentation", "Blank")
                        for t_name in target_templates:
                            item = full.ListItemControl(Name=t_name)
                            if item.Exists(0.5):
                                logger.info("[START SCREEN] Invoking template '%s'", t_name)
                                pat = item.GetInvokePattern()
                                if pat:
                                    pat.Invoke()
                                else:
                                    item.Click()
                                time.sleep(2.0)
                                break
            except Exception as e:
                logger.debug("[START SCREEN] UIA template click exception: %s", e)

        # 2. Check if still on bare start screen
        try:
            curr_title = (win32gui.GetWindowText(hwnd) or "").strip()
        except Exception:
            curr_title = ""

        if curr_title.lower() in bare_names:
            logger.info("[START SCREEN] Still on Start Screen, sending VK_ESCAPE (virtual)...")
            send_keys(0x1B, target_hwnd=hwnd)  # VK_ESCAPE
            time.sleep(1.5)

        try:
            curr_title = (win32gui.GetWindowText(hwnd) or "").strip()
        except Exception:
            curr_title = ""

        if curr_title.lower() in bare_names:
            logger.info("[START SCREEN] Sending Ctrl+N for new blank document (virtual)...")
            send_keys(0x11, ord('N'), target_hwnd=hwnd)
            time.sleep(2.0)

        try:
            new_title = (win32gui.GetWindowText(hwnd) or "").strip()
            logger.info("[START SCREEN] Final window title: '%s'", new_title)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Smart Control Label & Name Extractor (Web & Desktop)
# --------------------------------------------------------------------------- #
def resolve_control_name(ctrl, ctype: str, eye_brain: Optional[EyeAndBrainOrchestrator] = None) -> str:
    """
    Extracts a rich semantic label for any desktop or web control.
    If direct ctrl.Name is empty, inspects:
    1. Child TextControl elements (e.g. HTML button with inner text span)
    2. HelpText (tooltip/title)
    3. AutomationId (e.g. data-testid or DOM ID)
    4. ValuePattern.Value
    5. AriaRole / LocalizedControlType
    6. Organ 31 (Eye / Visual Perception): Optical character recognition on icon pixels
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

        # 6. Organ 31 (Eye): Visual inspection of control bounding rectangle
        if eye_brain:
            try:
                box = safe_bounding_rect(ctrl)
                if box:
                    visual_label = eye_brain.visually_inspect_control(box)
                    if visual_label:
                        logger.info("[EYE] Visual perception identified label: '%s' for %s", visual_label, ctype)
                        return visual_label
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
        cls = (win32gui.GetClassName(hwnd) or "").strip()
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

    # Universally awaken Chromium accessibility bridge by dispatching WM_GETOBJECT
    # with OBJID_CLIENT to all child windows (e.g. Chrome_RenderWidgetHostHWND)
    try:
        user32 = ctypes.windll.user32
        OBJID_CLIENT = 0xFFFFFFFC
        WM_GETOBJECT = 0x003D
        if win32gui:
            def _wake_enum(child_h, _):
                try:
                    c_name = win32gui.GetClassName(child_h) or ""
                    w_text = win32gui.GetWindowText(child_h) or ""
                    if "render" in c_name.lower() or "legacy" in w_text.lower():
                        user32.SendMessageW(child_h, WM_GETOBJECT, 0, OBJID_CLIENT)
                except Exception:
                    pass
                return True
            win32gui.EnumChildWindows(hwnd, _wake_enum, None)
    except Exception:
        pass

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
            popup_hwnd = win32gui.GetWindow(main_hwnd, GW_ENABLEDPOPUP)
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
        if not hwnd or hwnd == main_hwnd:
            return False

        # Verify window validity and visibility safely even if win32gui is None
        if win32gui:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return False
        else:
            try:
                user32 = ctypes.windll.user32
                if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
                    return False
            except Exception:
                return False

        if is_dockable_hwnd(hwnd):
            return False

        if target_pid:
            pid = get_pid_for_hwnd(hwnd)
            if pid and pid != target_pid:
                return False

        try:
            if win32gui:
                style = win32gui.GetWindowLong(hwnd, GWL_STYLE)
                if style & WS_CHILD:
                    return False
                title = (win32gui.GetWindowText(hwnd) or "").strip().lower()
                if not title and not (style & WS_POPUP):
                    return False
                if title in KNOWN_DOCKABLE_NAMES:
                    return False
            else:
                user32 = ctypes.windll.user32
                style = user32.GetWindowLongW(hwnd, GWL_STYLE)
                if style & WS_CHILD:
                    return False
                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").strip().lower()
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
            for ctrl, depth in _safe_walk_control(root_ctrl, includeTop=False, maxDepth=14):
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

    def handle(self, hwnd: int, main_hwnd: int = 0) -> str:
        """Consult DB cache first, else alert CNS bridge (Organ 29) and safely dismiss popup."""
        title = win32gui.GetWindowText(hwnd) if win32gui else "Modal"
        norm_title = title.strip().lower()
        key = f"modal:{norm_title}"
        getter = getattr(self.db, "get_modal_resolution", None)
        cached = getter(key) if callable(getter) else None
        if cached:
            logger.info("Modal '%s' resolved from cache: %s", title, cached)
            self.dismiss_popup(hwnd, main_hwnd=main_hwnd)
            return str(cached)

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
            res_data = self.cns.wait_for_resolution(popup_id, timeout=1.5)
            if res_data:
                resolution = res_data.get("action", "dismiss")
                tx = int(res_data.get("x", cx))
                ty = int(res_data.get("y", cy))
                logger.info("[CNS BRIDGE] Organ 29 resolved popup '%s' -> action='%s' at (%d, %d)",
                            title, resolution, tx, ty)
            else:
                logger.warning("[CNS BRIDGE] Organ 29 resolution timed out. Defaulting to safe dismiss.")
        except Exception as e:
            logger.warning("[CNS BRIDGE] Popup alert across bridge failed: %s. Defaulting to safe dismiss.", e)

        setter = getattr(self.db, "store_modal_resolution", None)
        if callable(setter):
            try:
                setter(key, resolution)
            except Exception as e:
                logger.debug("Failed to store modal resolution in db: %s", e)

        self.dismiss_popup(hwnd, main_hwnd=main_hwnd)
        return resolution

    def dismiss_popup(self, hwnd: int, main_hwnd: int = 0):
        """Actively and safely dismisses a modal dialog or popup window without stalling."""
        if not hwnd or not win32gui or not win32gui.IsWindow(hwnd):
            return

        logger.info("[POPUP DISMISS] Dismissing modal window hwnd=%s", hwnd)
        
        # 1. Try cancellation and close messages only; never auto-confirm a change.
        try:
            win32gui.PostMessage(hwnd, 0x0111, 2, 0)  # WM_COMMAND, IDCANCEL
            time.sleep(0.08)
        except Exception:
            pass

        if win32gui.IsWindowVisible(hwnd):
            if CAN_INJECT_INPUT:
                send_keys(0x1B)  # VK_ESCAPE
                time.sleep(0.08)


        if win32gui.IsWindowVisible(hwnd):
            try:
                win32gui.PostMessage(hwnd, 0x0112, 0xF060, 0)  # WM_SYSCOMMAND, SC_CLOSE
                time.sleep(0.08)
            except Exception:
                pass

        if win32gui.IsWindowVisible(hwnd):
            try:
                win32gui.PostMessage(hwnd, 0x0010, 0, 0)  # WM_CLOSE
                time.sleep(0.1)
            except Exception:
                pass

        # 2. Hard fallback via EndDialog
        if win32gui.IsWindowVisible(hwnd):
            try:
                ctypes.windll.user32.EndDialog(hwnd, 2)
            except Exception:
                pass

        # 3. Always re-enable parent window if it was disabled by the modal
        if main_hwnd and win32gui.IsWindow(main_hwnd):
            try:
                ctypes.windll.user32.EnableWindow(main_hwnd, True)
                bring_to_foreground(main_hwnd)
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Qt-aware keyboard menu scanner
# --------------------------------------------------------------------------- #
class MenuScanner:
    def __init__(self, main_hwnd: int, menu_header_names: Set[str], root_ctrl=None):
        self.main_hwnd = main_hwnd
        self.menu_header_names = {n.strip().lower() for n in menu_header_names}
        self.root_ctrl = root_ctrl

    def scan_menu(self, header_name: str, ctrl_obj=None, max_items: int = 40) -> List[Dict[str, Any]]:
        """
        Open a menu via keyboard (Alt+letter), walk UIA tree WHILE menu is open
        to find all MenuItemControl/MenuFlyoutItem nodes, then close with Escape.
        Zero mouse movement. Handles Settings pages and popups by dismissing them first.
        """
        user32 = ctypes.windll.user32
        VK_ESCAPE = 0x1B

        accel = get_menu_accelerator(ctrl=ctrl_obj, header_name=header_name)
        if not accel:
            return self._scan_menu_via_uia(header_name, ctrl_obj=ctrl_obj)

        # Ensure target window is foreground
        bring_to_foreground(self.main_hwnd)
        time.sleep(0.2)

        # Dismiss any open Settings/Dialog pages by clicking Back or pressing Escape
        try:
            root = auto.ControlFromHandle(self.main_hwnd) if auto else None
            if root:
                for ctrl, depth in _safe_walk_control(root, includeTop=False, maxDepth=4):
                    try:
                        if ctrl.ControlTypeName == "ButtonControl" and (ctrl.Name or "").strip() == "Back":
                            uia_activate(ctrl, target_hwnd=self.main_hwnd)
                            time.sleep(0.5)
                            break
                    except Exception:
                        continue
        except Exception:
            pass

        # Press Escape via PostMessage to clear any open menus/dialogs
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        for _ in range(2):
            user32.PostMessageW(self.main_hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
            time.sleep(0.04)
            user32.PostMessageW(self.main_hwnd, WM_KEYUP, VK_ESCAPE, 0)
            time.sleep(0.15)

        # Re-ensure foreground after dismissing
        bring_to_foreground(self.main_hwnd)
        time.sleep(0.3)

        # Open menu bar via PostMessage (works even if not foreground)
        try:
            WM_KEYDOWN = 0x0100
            WM_KEYUP = 0x0101
            user32.PostMessageW(self.main_hwnd, WM_KEYDOWN, 0x12, 0)  # Alt
            time.sleep(0.08)
            for ch in accel[1:]:
                vk = ord(ch.upper())
                user32.PostMessageW(self.main_hwnd, WM_KEYDOWN, vk, 0)
                time.sleep(0.04)
                user32.PostMessageW(self.main_hwnd, WM_KEYUP, vk, 0)
                time.sleep(0.04)
            user32.PostMessageW(self.main_hwnd, WM_KEYUP, 0x12, 0)  # Alt up
            time.sleep(0.5)
        except Exception as e:
            logger.debug("Menu open failed: %s", e)
            return []

        # Find the menu header in UIA tree and expand it to show submenu items
        results = []
        seen_names = set()
        try:
            root = auto.ControlFromHandle(self.main_hwnd) if auto else None
            if root:
                # First, find and expand the menu header (e.g., "File")
                for ctrl, depth in _safe_walk_control(root, includeTop=False, maxDepth=8):
                    try:
                        ctype = ctrl.ControlTypeName or ""
                        name = (ctrl.Name or "").strip()
                        if ctype == "MenuItemControl" and name == header_name:
                            # Expand to open the flyout submenu
                            try:
                                pat = ctrl.GetExpandCollapsePattern()
                                if pat:
                                    pat.Expand()
                                    time.sleep(0.5)
                            except Exception:
                                pass
                            break
                    except Exception:
                        continue

                # Now walk tree to find MenuFlyoutItem submenu items
                for ctrl, depth in _safe_walk_control(root, includeTop=False, maxDepth=10):
                    try:
                        ctype = ctrl.ControlTypeName or ""
                        name = (ctrl.Name or "").strip()
                        cls = ctrl.ClassName or ""

                        # WinUI 3 uses MenuFlyoutItem, MenuFlyoutSubItem
                        if ctype == "MenuItemControl" and name:
                            if name in seen_names:
                                continue
                            if name.lower() in self.menu_header_names:
                                continue
                            if re.match(r"^desktop \d+$", name, re.IGNORECASE):
                                continue
                            if name == "System" and cls == "":
                                continue
                            # Skip the menu bar headers themselves
                            if "MenuBarItem" in cls:
                                continue

                            seen_names.add(name)
                            box = safe_bounding_rect(ctrl)
                            entry = {
                                "name": name,
                                "type": "MenuItem",
                                "coords": {
                                    "x": center_of(box)[0] if box else -1,
                                    "y": center_of(box)[1] if box else -1,
                                    "box": list(box) if box else [-1, -1, -1, -1],
                                },
                                "parent_menu": header_name,
                            }
                            # Read keyboard shortcut from sibling TextControl
                            try:
                                children = ctrl.GetChildren()
                                for child in children:
                                    cn = (child.Name or "").strip()
                                    if cn and cn != name and ("+" in cn or cn.startswith("Ctrl")):
                                        entry["accelerator"] = cn
                                        break
                            except Exception:
                                pass
                            results.append(entry)
                    except Exception:
                        continue
        except Exception as e:
            logger.debug("Menu tree walk failed: %s", e)

        # Close menu with Escape via PostMessage
        try:
            WM_KEYDOWN = 0x0100
            WM_KEYUP = 0x0101
            user32.PostMessageW(self.main_hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
            time.sleep(0.04)
            user32.PostMessageW(self.main_hwnd, WM_KEYUP, VK_ESCAPE, 0)
        except Exception:
            pass
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
                for ctrl, depth in _safe_walk_control(sroot, includeTop=False, maxDepth=6):
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

    def scan_dialog(self, dialog_hwnd: int, parent_button: str = "", main_hwnd: int = 0) -> List[Dict[str, Any]]:
        elements: List[Dict[str, Any]] = []
        if auto is None or not dialog_hwnd:
            return elements

        bring_to_foreground(dialog_hwnd)
        time.sleep(0.2)
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

                time.sleep(0.2)
                page_items = self._collect_controls(dlg_ctrl, parent_tab=tab_name, parent_dialog=dlg_title)
                elements.extend(page_items)
        else:
            elements.extend(self._collect_controls(dlg_ctrl, parent_dialog=dlg_title))

        self._close_safely(dlg_ctrl, dialog_hwnd, main_hwnd=main_hwnd)
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

        if not tabs and auto is not None and dlg_ctrl is not None:
            try:
                for ctrl, depth in _safe_walk_control(dlg_ctrl, includeTop=False, maxDepth=6):
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

        def _tab_sort_key(t):
            b = safe_bounding_rect(t)
            return b[1] if b is not None else 0

        tabs.sort(key=_tab_sort_key)
        return tabs

    def _collect_controls(self, dlg_ctrl, parent_tab: Optional[str] = None,
                          parent_dialog: Optional[str] = None) -> List[Dict[str, Any]]:
        found = []
        if auto is None or dlg_ctrl is None:
            return found
        seen_sigs = set()
        try:
            for ctrl, depth in _safe_walk_control(dlg_ctrl, includeTop=False, maxDepth=14):
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

                item_data = {
                    "name": name,
                    "type": ctype,
                    "coords": {"x": cx, "y": cy, "box": list(box)},
                    "parent_tab": parent_tab,
                    "parent_dialog": parent_dialog,
                }
                found.append(item_data)

                # Extract dropdown options for ComboBoxes inside dialogs
                if ctype == "ComboBoxControl":
                    try:
                        pat = getattr(ctrl, "GetExpandCollapsePattern", lambda: None)()
                        if pat:
                            pat.Expand()
                            time.sleep(0.15)
                        children = getattr(ctrl, "GetChildren", lambda: [])()
                        for ch in children:
                            c_type = getattr(ch, "ControlTypeName", "")
                            if c_type in ("ListItemControl", "MenuItemControl"):
                                ch_name = getattr(ch, "Name", "") or ""
                                ch_box = safe_bounding_rect(ch)
                                if ch_name and ch_box and is_onscreen(ch_box):
                                    ch_cx, ch_cy = center_of(ch_box)
                                    found.append({
                                        "name": ch_name,
                                        "type": c_type,
                                        "coords": {"x": ch_cx, "y": ch_cy, "box": list(ch_box)},
                                        "parent_combobox": name,
                                        "parent_dialog": parent_dialog,
                                    })
                        if pat:
                            pat.Collapse()
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Dialog control collection failed: %s", e)
        return found

    def _close_safely(self, dlg_ctrl, dialog_hwnd: int, main_hwnd: int = 0):
        """Safely dismisses dialog via Cancel, safe dismiss buttons, keyboard, or Win32 messages."""
        logger.info("[DIALOG EXIT] Safely dismissing dialog hwnd=%s", dialog_hwnd)
        closed = False
        
        # 1. Look for standard safe dismiss buttons (Cancel, Close, Dismiss, etc.)
        try:
            cancel_btn = dlg_ctrl.ButtonControl(Name="Cancel")
            if cancel_btn.Exists(0.4):
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

        if not closed and auto is not None and dlg_ctrl is not None:
            try:
                candidate_buttons = []
                for ctrl, depth in _safe_walk_control(dlg_ctrl, includeTop=False, maxDepth=8):
                    name = (ctrl.Name or "").strip().lower()
                    ctype = ctrl.ControlTypeName
                    if ctype == "ButtonControl":
                        candidate_buttons.append((name, ctrl))
                        if name in self.CLOSE_NAMES and name not in self.FORBIDDEN_CLOSE:
                            box = safe_bounding_rect(ctrl)
                            if box and is_onscreen(box):
                                cx, cy = center_of(box)
                                uia_activate(ctrl, fallback_coords=(cx, cy))
                                closed = True
                                break
                
                # If no cancel button, but this is an alert/message box with a single button (e.g., OK), click it
                if not closed and candidate_buttons:
                    # Filter out dangerous buttons
                    safe_candidates = [
                        (nm, c) for nm, c in candidate_buttons 
                        if not any(d in nm for d in ("delete", "remove", "save", "apply", "overwrite"))
                    ]
                    if safe_candidates:
                        # Only acknowledge clearly informational dialogs. Never choose
                        # Yes, Continue, Allow, Accept, or a lone unknown button.
                        target_btn = None
                        for nm, c in safe_candidates:
                            if nm in ("ok", "got it", "understood", "close", "dismiss"):
                                target_btn = c
                                break
                        
                        if target_btn:
                            box = safe_bounding_rect(target_btn)
                            if box and is_onscreen(box):
                                cx, cy = center_of(box)
                                uia_activate(target_btn, fallback_coords=(cx, cy))
                                closed = True
            except Exception as e:
                logger.debug("Close-button search failed: %s", e)

        time.sleep(0.1)
        
        # 2. Keyboard dismissal fallback (Escape, Return)
        if win32gui and win32gui.IsWindow(dialog_hwnd) and win32gui.IsWindowVisible(dialog_hwnd):
            if CAN_INJECT_INPUT:
                send_keys(0x1B)  # VK_ESCAPE
                time.sleep(0.08)

        # 3. Win32 dialog cancellation and close messages only
        if win32gui and win32gui.IsWindow(dialog_hwnd) and win32gui.IsWindowVisible(dialog_hwnd):
            try:
                win32gui.PostMessage(dialog_hwnd, 0x0111, 2, 0)  # WM_COMMAND, IDCANCEL
                time.sleep(0.08)
            except Exception:
                pass
                try:
                    win32gui.PostMessage(dialog_hwnd, 0x0112, 0xF060, 0)  # WM_SYSCOMMAND, SC_CLOSE
                    time.sleep(0.08)
                except Exception:
                    pass
                try:
                    win32gui.PostMessage(dialog_hwnd, 0x0010, 0, 0)  # WM_CLOSE
                    time.sleep(0.1)
                except Exception:
                    pass

        # 4. Hard fallback via EndDialog
        if win32gui and win32gui.IsWindow(dialog_hwnd) and win32gui.IsWindowVisible(dialog_hwnd):
            try:
                ctypes.windll.user32.EndDialog(dialog_hwnd, 2)
            except Exception:
                pass

        # 5. Always ensure parent window is re-enabled so the scanner never stalls
        if main_hwnd and win32gui and win32gui.IsWindow(main_hwnd):
            try:
                ctypes.windll.user32.EnableWindow(main_hwnd, True)
                bring_to_foreground(main_hwnd)
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
        self.eye_brain = EyeAndBrainOrchestrator()
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
        time.sleep(0.5)

        root_ctrl = None
        for attempt in range(5):
            try:
                root_ctrl = auto.ControlFromHandle(target_hwnd)
                if root_ctrl and root_ctrl.Exists(0.5):
                    break
            except Exception as e:
                logger.warning("Attach attempt %d to hwnd %s returned: %s. Retrying in 0.5s...", attempt + 1, target_hwnd, e)
                time.sleep(0.5)

        if not root_ctrl:
            logger.error("Could not attach to hwnd %s after multiple attempts.", target_hwnd)
            return {"status": "error", "message": f"Could not attach to hwnd {target_hwnd}",
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

        # 2. Identify desktop top menu headers universally
        def is_menu_header(it: Dict[str, Any]) -> bool:
            ctype = it.get("type", "")
            name = (it.get("name") or "").strip()
            norm = name.lower()
            box = it.get("coords", {}).get("box", [-1, -1, -1, -1])
            if norm == "system" or not name:
                return False
            if ctype in ("MenuItemControl", "MenuBarControl"):
                if norm in DEFAULT_MENU_ACCELERATORS:
                    return True
                if win_box and box[1] < win_box[1] + 120:
                    return True
            # Also catch top-bar items positioned in standard menu strip height
            if win_box and box[1] < win_box[1] + 80 and norm in DEFAULT_MENU_ACCELERATORS:
                return True
            return False

        menu_header_names = {it["name"] for it in raw_items if is_menu_header(it)}
        menu_scanner = MenuScanner(target_hwnd, menu_header_names, root_ctrl=root_ctrl)

        # Knowledge side by side with the scan (organ_48/49): read-only E0 map first, then every
        # control is consulted before it is touched. None => the scan runs exactly as before.
        ksess = None
        try:
            from core_organs import organ_49_scan_knowledge as _sk
            ksess = _sk.open_session(app_name, target_hwnd)
            if ksess is not None:
                e0 = ksess.start()
                logger.info("[SCAN-KNOWLEDGE] %s: E0 map %s", app_name,
                            {k: v for k, v in e0.items() if k != "methods"})
        except Exception as _ke:
            logger.debug("scan-knowledge unavailable: %s", _ke)
            ksess = None
        probing_stopped = False

        # Proactively persist any discovered control to SSMS
        def _persist_element(it: Dict[str, Any]):
            try:
                iname = it.get("name") or it.get("type", "Control")
                itype = it.get("type", "Control")
                icoords = it.get("coords", {})
                ix = icoords.get("x", 0) if icoords else 0
                iy = icoords.get("y", 0) if icoords else 0
                ihash = hashlib.md5(f"{iname}_{itype}_{ix}_{iy}".encode("utf-8")).hexdigest()[:16]
                self.db.log_new_pathway(
                    layout_hash=ihash,
                    element_name=iname,
                    x=ix,
                    y=iy,
                    action_type=itype,
                    parent_path=app_name,
                )
            except Exception:
                pass

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
                _persist_element(item)
                self.controls_scanned += 1
                continue

            # Safety Shield: Catalog broadcast actions (Start Streaming, etc.) but avoid live triggers
            if is_broadcast_action(name):
                logger.info("Safety shield: cataloged broadcast control '%s' (skipping click)", name)
                elements.append(item)
                _persist_element(item)
                self.controls_scanned += 1
                continue

            # Safety Shield: Protect browser navigation (Back, Reload, Close Tab) when in a browser
            if is_chromium and is_browser_nav_action(name):
                logger.info("Browser shield: cataloged browser chrome navigation '%s' (skipping click)", name)
                elements.append(item)
                _persist_element(item)
                self.controls_scanned += 1
                continue

            # Menu headers: Drive via keyboard accelerators or UIA tree
            if is_menu_header(item):
                try:
                    logger.info("[MENU SCAN] Traversing menu '%s'", name)
                    menu_items = ksess.menu_elements(name) if ksess is not None else []
                    if menu_items:
                        logger.info("[MENU SCAN] '%s' served from E0 knowledge map (%d items, no popup opened)",
                                    name, len(menu_items))
                    else:
                        menu_items = menu_scanner.scan_menu(name, ctrl_obj=ctrl_obj)
                    elements.append(item)
                    _persist_element(item)
                    for mi in menu_items:
                        _persist_element(mi)
                    elements.extend(menu_items)
                    self.controls_scanned += 1 + len(menu_items)
                except Exception as e:
                    logger.warning("Menu scan failed for '%s': %s", name, e)
                    self.controls_failed += 1
                continue

            # Knowledge consultation: graded risk (E2 never actuated), verified branches never
            # re-probed, and a yield-based stop rule: catalogue the rest once exploration flattens.
            k_decision = ksess.policy(item) if ksess is not None else None
            if k_decision is not None and k_decision.action in ("catalog_only", "skip_known"):
                logger.info("[SCAN-KNOWLEDGE] %s '%s': %s", k_decision.action, name, k_decision.reason)
                elements.append(item)
                _persist_element(item)
                self.controls_scanned += 1
                continue
            if ksess is not None and not probing_stopped:
                _why = ksess.should_stop()
                if _why:
                    probing_stopped = True
                    logger.info("[SCAN-KNOWLEDGE] exploration stopped (%s); cataloguing remaining controls", _why)
            if probing_stopped:
                elements.append(item)
                _persist_element(item)
                self.controls_scanned += 1
                continue

            # Child Dialog Triggers ("Settings", "Properties", "Filters", "Add", etc.)
            if norm_name in DIALOG_TRIGGER_NAMES:
                logger.info("[DIALOG TRIGGER] Activating '%s' to spawn child dialog", name)
                elements.append(item)
                _persist_element(item)
                self.controls_scanned += 1
                try:
                    _k_before = ksess.light_state() if ksess is not None else None
                    activated = uia_activate(ctrl_obj, fallback_coords=(cx, cy))
                    time.sleep(0.6)
                    child_hwnd = self._find_spawned_dialog(target_hwnd, target_pid)
                    if child_hwnd:
                        _dlg_title = win32gui.GetWindowText(child_hwnd) if win32gui else ""
                        dialog_elements = self.dialog_traversal.scan_dialog(child_hwnd, parent_button=name, main_hwnd=target_hwnd)
                        elements.extend(dialog_elements)
                        for de in dialog_elements:
                            _persist_element(de)
                        self.controls_scanned += len(dialog_elements)
                        if ksess is not None and _k_before is not None:
                            ksess.record_probe(item, _k_before, "dialog", len(dialog_elements),
                                               dialog_elements, dialog_title=_dlg_title, decision=k_decision)
                    else:
                        logger.debug("No child dialog detected after activating '%s'", name)
                        if ksess is not None and _k_before is not None:
                            ksess.record_probe(item, _k_before, "none", 0, decision=k_decision)
                except Exception as e:
                    logger.warning("Error interacting with dialog trigger '%s': %s", name, e)
                    self.controls_failed += 1
                bring_to_foreground(target_hwnd)
                continue

            # Generic Actionable Control: Deep Active Probing ("every button scanned should be clicked")
            elements.append(item)
            _persist_element(item)
            self.controls_scanned += 1

            # Brain Cognitive Consultation: If control is unclassified or ambiguous, ask Brain for semantic guidance
            if ctype in ("CustomControl", "GroupControl", "ButtonControl") and (not name or name == ctype or any(k in norm_name for k in ("button", "item", "view"))):
                if hasattr(self, "eye_brain") and self.eye_brain:
                    brain_decision = self.eye_brain.reason_about_action(app_name, name, ctype, box)
                    if not brain_decision.get("allow_click", True):
                        logger.info("[BRAIN SHIELD] Brain advised avoiding '%s': %s", name, brain_decision.get("rationale"))
                        continue
                    if brain_decision.get("suggested_alias"):
                        item["suggested_alias"] = brain_decision["suggested_alias"]
                        logger.info("[BRAIN] Assigned semantic alias: '%s' -> '%s'", name, brain_decision["suggested_alias"])

            _k_before = ksess.light_state() if ksess is not None else None
            _k_n0 = len(elements)
            try:
                logger.info("[ACTIVE PROBE] Clicking / Activating %s: '%s' at (%d, %d)", ctype, name, cx, cy)
                activated = uia_activate(ctrl_obj, fallback_coords=(cx, cy))
                time.sleep(0.35)

                # 1. Did a child dialog spawn from this click?
                child_hwnd = self._find_spawned_dialog(target_hwnd, target_pid)
                if child_hwnd:
                    logger.info("[ACTIVE PROBE] Child dialog spawned by '%s' (hwnd=%s)", name, child_hwnd)
                    _dlg_title = win32gui.GetWindowText(child_hwnd) if win32gui else ""
                    dialog_elements = self.dialog_traversal.scan_dialog(child_hwnd, parent_button=name, main_hwnd=target_hwnd)
                    elements.extend(dialog_elements)
                    for de in dialog_elements:
                        _persist_element(de)
                    self.controls_scanned += len(dialog_elements)
                    if ksess is not None and _k_before is not None:
                        ksess.record_probe(item, _k_before, "dialog", len(dialog_elements),
                                           dialog_elements, dialog_title=_dlg_title, decision=k_decision)
                    bring_to_foreground(target_hwnd)
                    continue

                # 2. Did a roadblock modal or in-window modal appear?
                modal_hwnd = self.popup_interceptor.detect_true_modal(target_hwnd, target_pid)
                if modal_hwnd:
                    logger.info("[ACTIVE PROBE] Top-level modal popup detected by '%s' (hwnd=%s)", name, modal_hwnd)
                    self._handle_possible_modal(target_hwnd, target_pid, elements)
                    if ksess is not None and _k_before is not None:
                        ksess.record_probe(item, _k_before, "modal", 0, decision=k_decision)
                    bring_to_foreground(target_hwnd)
                    continue

                # Check for in-window modals (WinUI 3 ContentDialog, web cookies, etc.)
                in_win_modals = self.popup_interceptor.detect_in_window_modals(root_ctrl)
                if in_win_modals:
                    logger.info("[ACTIVE PROBE] In-window modal detected by '%s'", name)
                    self._handle_in_window_modal(root_ctrl, in_win_modals, elements)
                    if ksess is not None and _k_before is not None:
                        ksess.record_probe(item, _k_before, "modal", 0, decision=k_decision)
                    bring_to_foreground(target_hwnd)
                    continue

                # 3. If ComboBox, inspect dropdown and collapse
                if ctype == "ComboBoxControl":
                    self._probe_combobox_items(ctrl_obj, name, elements, persist_fn=_persist_element)

                # 4. If TabItem, collect controls exposed by switching tab
                elif ctype == "TabItemControl":
                    new_tab_items = self._collect_actionable_controls(root_ctrl, win_box, is_web_app=is_chromium)
                    for t_item in new_tab_items:
                        sig = f"{t_item['name']}:{t_item['type']}:{t_item['coords']['box']}"
                        if sig not in seen_control_sigs:
                            seen_control_sigs.add(sig)
                            elements.append(t_item)
                            _persist_element(t_item)
                            self.controls_scanned += 1

                # 5. Safe right-click discovery for list/tree entries. This maps
                # contextual actions without opening arbitrary canvas/browser areas.
                if ctype in ("ListItemControl", "TreeItemControl"):
                    self._probe_context_menu(
                        target_hwnd, ctrl_obj, name, box, elements, persist_fn=_persist_element
                    )

                # Plain probe finished without a spawned window: record what (if anything) changed.
                if ksess is not None and _k_before is not None:
                    _gained = len(elements) - _k_n0
                    ksess.record_probe(item, _k_before, "expanded" if _gained > 0 else "none",
                                       max(_gained, 0), decision=k_decision)

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

        # Feed scan results to Visual Memory system
        try:
            from core_organs.organ_33_visual_memory import get_visual_memory
            vm = get_visual_memory()
            vm.deep_scan(
                app_name=app_name,
                window_title=app_name,
                scanner=None,  # Elements already collected
                mode="first_contact" if self.controls_scanned < 10 else "training",
                elements=cleaned_elements,
            )
        except Exception as e:
            logger.debug(f"Visual memory feed failed: {e}")

        result = {
            "status": "completed",
            "tree_hash": tree_hash,
            "controls_scanned": self.controls_scanned,
            "controls_failed": self.controls_failed,
            "elements": cleaned_elements,
        }
        if ksess is not None:
            try:
                result["knowledge"] = ksess.finish()
            except Exception as _kf:
                logger.debug("scan-knowledge finish failed: %s", _kf)
        return result

    # --- internals -----------------------------------------------------
    def _collect_actionable_controls(self, root_ctrl, win_box: Optional[Tuple[int, int, int, int]],
                                     is_web_app: bool = False) -> List[Dict[str, Any]]:
        """
        Deeply enumerates UI controls. Supports both desktop hierarchies and deep
        web application DOMs (up to depth 25 inside DocumentControl).
        """
        items: List[Dict[str, Any]] = []
        if auto is None or root_ctrl is None:
            return items
        seen_sigs: Set[str] = set()

        max_search_depth = 25 if is_web_app else 14

        try:
            walker = _safe_walk_control(root_ctrl, includeTop=False, maxDepth=max_search_depth)
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
            is_actionable = ctype in ACTIONABLE_CONTROL_TYPES or ctype in ("MenuBarControl", "MenuControl")

            # Check controls with actionable patterns (Invoke, Toggle, SelectionItem, ExpandCollapse)
            if not is_actionable:
                try:
                    if hasattr(ctrl, "GetInvokePattern") and ctrl.GetInvokePattern() is not None:
                        is_actionable = True
                    elif hasattr(ctrl, "GetTogglePattern") and ctrl.GetTogglePattern() is not None:
                        is_actionable = True
                    elif hasattr(ctrl, "GetSelectionItemPattern") and ctrl.GetSelectionItemPattern() is not None:
                        is_actionable = True
                    elif hasattr(ctrl, "GetExpandCollapsePattern") and ctrl.GetExpandCollapsePattern() is not None:
                        is_actionable = True
                except Exception:
                    pass

            # In Web applications, also check CustomControl / GroupControl with actionable AriaRoles
            if not is_actionable and is_web_app and ctype in ("CustomControl", "GroupControl"):
                try:
                    aria_role = getattr(ctrl, "AriaRole", "")
                    if aria_role in WEB_ACTIONABLE_ROLES:
                        is_actionable = True
                except Exception:
                    pass

            # Layout filler filter: Skip unnamed container panes
            if not is_actionable:
                continue

            name = resolve_control_name(ctrl, ctype, eye_brain=getattr(self, "eye_brain", None))
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
        time.sleep(0.15)

        if auto:
            try:
                for win in auto.GetRootControl().GetChildren():
                    h = getattr(win, "NativeWindowHandle", 0)
                    if h and h != main_hwnd:
                        wname = (win.Name or "").strip()
                        if not wname:
                            continue
                        rect = safe_bounding_rect(win)
                        if not rect or (rect[2] - rect[0] < 50) or (rect[3] - rect[1] < 50):
                            continue
                        pid = getattr(win, "ProcessId", 0)
                        norm_wname = wname.lower()
                        if (target_pid and pid == target_pid) or any(k in norm_wname for k in ("settings", "properties", "filters", "preferences", "dialog", "options")):
                            is_vis = win32gui.IsWindowVisible(h) if win32gui else True
                            if is_vis and not is_dockable_hwnd(h):
                                return h
            except Exception:
                pass

        if win32gui:
            try:
                pop = win32gui.GetWindow(main_hwnd, GW_ENABLEDPOPUP)
                if pop and pop != main_hwnd and win32gui.IsWindowVisible(pop) and not is_dockable_hwnd(pop):
                    t = win32gui.GetWindowText(pop).strip()
                    if t:
                        return pop
            except Exception:
                pass

            try:
                fg = win32gui.GetForegroundWindow()
                if fg and fg != main_hwnd and win32gui.IsWindowVisible(fg):
                    fg_pid = get_pid_for_hwnd(fg)
                    if (not target_pid or fg_pid == target_pid) and not is_dockable_hwnd(fg):
                        t = win32gui.GetWindowText(fg).strip()
                        if t:
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
        # Record the dialog surface before resolving it. The old order closed the
        # modal first, so traversal intermittently attached to an invalid handle.
        dialog_elements = self.dialog_traversal.scan_dialog(modal_hwnd, parent_button=title, main_hwnd=main_hwnd)
        elements.extend(dialog_elements)
        self.controls_scanned += len(dialog_elements)

        # DialogTraversal normally uses Cancel/Escape. Keep a bounded fallback
        # for windows that remain open, without treating an affirmative action as
        # consent for a destructive or permission-changing operation.
        if win32gui and win32gui.IsWindow(modal_hwnd) and win32gui.IsWindowVisible(modal_hwnd):
            self.popup_interceptor.handle(modal_hwnd, main_hwnd=main_hwnd)

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
                res = self.cns.wait_for_resolution(popup_id, timeout=1.5)
                if res and res.get("action") == "escape_fallback":
                    if CAN_INJECT_INPUT:
                        send_keys(0x1B)
                    cns_handled = True
            except Exception:
                pass

            # Safe dismissal attempt: recursively search for positive or safe buttons
            dismissed = False
            if auto is not None and modal_ctrl is not None:
                try:
                    dismiss_targets = {
                        "ok", "got it", "done", "cancel", "close", "dismiss",
                        "don't save", "dont save", "no thanks", "not now", "later", "x",
                    }
                    for ch, depth in _safe_walk_control(modal_ctrl, includeTop=False, maxDepth=6):
                        ctype = getattr(ch, "ControlTypeName", "")
                        if ctype not in ("ButtonControl", "HyperlinkControl", "CustomControl"):
                            continue
                        btext = resolve_control_name(ch, ctype).strip().lower()
                        aid = (getattr(ch, "AutomationId", "") or "").strip().lower()
                        cls_name = (getattr(ch, "ClassName", "") or "").strip().lower()

                        matched = False
                        if btext in dismiss_targets or any(k in btext for k in ("cancel", "close", "dismiss", "got it", "ok", "not now", "later")):
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

    def _probe_context_menu(self, main_hwnd: int, ctrl_obj, parent_name: str,
                            box: Tuple[int, int, int, int], elements: List[Dict[str, Any]],
                            persist_fn=None):
        """Discover one safe list/tree context menu and then close it.

        Right-clicking is deliberately limited to accessibility-identified list and
        tree entries. Buttons, free-form canvases, browser chrome, destructive
        controls, and unlabeled surface areas are never probed this way.
        """
        if (not win32gui or not auto or not box or is_dangerous(parent_name)
                or not is_onscreen(box)):
            return
        try:
            cx, cy = center_of(box)
            client_x, client_y = win32gui.ScreenToClient(main_hwnd, (cx, cy))
            lparam = (client_x & 0xFFFF) | ((client_y & 0xFFFF) << 16)
            bring_to_foreground(main_hwnd)
            win32gui.PostMessage(main_hwnd, 0x0204, 0x0002, lparam)  # WM_RBUTTONDOWN
            win32gui.PostMessage(main_hwnd, 0x0205, 0, lparam)       # WM_RBUTTONUP
            time.sleep(0.25)

            known = {
                (str(e.get("name", "")).lower(), tuple(e.get("coords", {}).get("box", [])))
                for e in elements
            }
            seen = set()
            for menu, depth in _safe_walk_control(auto.GetRootControl(), includeTop=False, maxDepth=5):
                if getattr(menu, "ControlTypeName", "") != "MenuItemControl":
                    continue
                menu_name = (getattr(menu, "Name", "") or "").strip()
                menu_box = safe_bounding_rect(menu)
                if not menu_name or not menu_box or not is_onscreen(menu_box):
                    continue
                sig = (menu_name.lower(), tuple(menu_box))
                if sig in known or sig in seen:
                    continue
                seen.add(sig)
                mx, my = center_of(menu_box)
                entry = {
                    "name": menu_name,
                    "type": "ContextMenuItem",
                    "coords": {"x": mx, "y": my, "box": list(menu_box)},
                    "parent_context": parent_name,
                    "discovery_method": "safe_right_click",
                }
                elements.append(entry)
                if persist_fn:
                    persist_fn(entry)
                self.controls_scanned += 1
        except Exception as exc:
            logger.debug("Context-menu probe failed for '%s': %s", parent_name, exc)
        finally:
            try:
                win32gui.PostMessage(main_hwnd, 0x0100, 0x1B, 0)  # WM_KEYDOWN Escape
                win32gui.PostMessage(main_hwnd, 0x0101, 0x1B, 0)  # WM_KEYUP Escape
            except Exception:
                pass
    def _probe_combobox_items(self, ctrl_obj, name: str, elements: List[Dict[str, Any]], persist_fn=None):
        try:
            if not ctrl_obj:
                return
            pat = getattr(ctrl_obj, "GetExpandCollapsePattern", lambda: None)()
            if pat and hasattr(pat, "Expand"):
                pat.Expand()
                time.sleep(0.15)
            children = getattr(ctrl_obj, "GetChildren", lambda: [])()
            for ch in children:
                c_type = getattr(ch, "ControlTypeName", "")
                if c_type in ("ListItemControl", "MenuItemControl"):
                    cname = getattr(ch, "Name", "") or ""
                    box = safe_bounding_rect(ch)
                    if cname and box and is_onscreen(box):
                        cx, cy = center_of(box)
                        item_entry = {
                            "name": cname,
                            "type": c_type,
                            "coords": {"x": cx, "y": cy, "box": list(box)},
                            "parent_combobox": name,
                        }
                        elements.append(item_entry)
                        if persist_fn:
                            persist_fn(item_entry)
                        self.controls_scanned += 1
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
    matching_hwnds = []

    def _enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = (win32gui.GetWindowText(hwnd) or "").strip()
        cls = (win32gui.GetClassName(hwnd) or "").strip()
        norm_title = title.lower()
        if any(bad in norm_title or bad in cls.lower() for bad in exclude_keywords):
            return True
        if substring.lower() in norm_title:
            matching_hwnds.append((hwnd, cls, title))
        return True

    try:
        win32gui.EnumWindows(_enum_handler, None)
    except Exception:
        pass

    if not matching_hwnds:
        return None

    # For UWP apps, prefer ApplicationFrameWindow over Windows.UI.Core.CoreWindow
    for h, c, t in matching_hwnds:
        if c == "ApplicationFrameWindow":
            return h

    return matching_hwnds[0][0]


KNOWN_UWP_APP_IDS = {
    "calculator": "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
    "calc": "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
    "notepad": "shell:AppsFolder\\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
    "paint": "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App",
    "snipping tool": "shell:AppsFolder\\Microsoft.ScreenSketch_8wekyb3d8bbwe!App",
    "snippingtool": "shell:AppsFolder\\Microsoft.ScreenSketch_8wekyb3d8bbwe!App",
    "settings": "ms-settings:",
}

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

    # 1.5 Prefer known Win32 window class for Office / major desktop apps
    #     This prevents matching WebView2 overlays or satellite windows.
    preferred_class = KNOWN_APP_WINDOW_CLASSES.get(norm_id)
    if preferred_class and win32gui:
        found_by_class = {"hwnd": None}
        def _class_enum_handler(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            try:
                if win32gui.GetClassName(hwnd) == preferred_class:
                    found_by_class["hwnd"] = hwnd
                    return False
            except Exception:
                pass
            return True
        try:
            win32gui.EnumWindows(_class_enum_handler, None)
        except Exception:
            pass
        if found_by_class["hwnd"]:
            return found_by_class["hwnd"]

    # 2. win32gui title substring search
    h = find_hwnd_by_title_substring(app_identifier)
    if h:
        return h

    # 2.5 Process name match
    proc_name = app_identifier if app_identifier.endswith(".exe") else f"{app_identifier}.exe"
    h = find_hwnd_by_process_name(proc_name)
    if h:
        return h

    # 3. UIA root window check
    if auto:
        try:
            for win in auto.GetRootControl().GetChildren():
                wname = (win.Name or "").strip()
                wcls = (win.ClassName or "").strip().lower()
                norm_wname = wname.lower()
                if (norm_id in norm_wname) or (norm_id in wcls):
                    h = getattr(win, "NativeWindowHandle", 0)
                    if h and (not win32gui or (win32gui.IsWindow(h) and win32gui.IsWindowVisible(h))):
                        return h
        except Exception:
            pass

    return None


def ensure_app_running(app_identifier: str, exe_path: Optional[str] = None) -> Optional[int]:
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

    norm_id = app_identifier.strip().lower()

    # Launch Windows 11 UWP Apps directly via shell:AppsFolder / URI
    if norm_id in KNOWN_UWP_APP_IDS:
        target_uri = KNOWN_UWP_APP_IDS[norm_id]
        logger.info("Launching Windows 11 UWP App '%s' via URI: %s", app_identifier, target_uri)
        if target_uri.startswith("ms-settings:"):
            subprocess.Popen(["cmd.exe", "/c", "start", "", target_uri])
        else:
            subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{target_uri}'"])
        time.sleep(2.5)
        for _ in range(15):
            hwnd = find_app_hwnd(app_identifier)
            if hwnd and win32gui and win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                bring_to_foreground(hwnd)
                return hwnd
            time.sleep(1.0)

    # Resolve executable path
    target_exe = None
    target_args = []
    if exe_path and os.path.isfile(exe_path):
        target_exe = os.path.abspath(exe_path)
    else:
        if "obs" in norm_id:
            known = [
                r"D:\obs-studio\bin\64bit\obs64.exe",
                r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
                r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe",
            ]
            target_exe = next((p for p in known if os.path.isfile(p)), None)
            target_args = ["--disable-shutdown-check", "--multi"]
        elif norm_id in ("code", "vscode", "visual studio code"):
            known_code = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
                r"C:\Program Files\Microsoft VS Code\Code.exe",
            ]
            target_exe = next((p for p in known_code if os.path.isfile(p)), None)
            target_args = ["--force-renderer-accessibility", "--new-window"]
        elif norm_id in ("notepad", "notepad.exe"):
            target_exe = r"C:\Windows\System32\notepad.exe"
        elif norm_id in ("calc", "calculator"):
            target_exe = r"C:\Windows\System32\calc.exe"
        elif norm_id in ("excel", "excel.exe", "microsoft excel"):
            known = [
                r"C:\Program Files\Microsoft Office\Root\Office16\EXCEL.EXE",
                r"C:\Program Files (x86)\Microsoft Office\Root\Office16\EXCEL.EXE",
            ]
            target_exe = next((p for p in known if os.path.isfile(p)), None)
        elif norm_id in ("word", "word.exe", "microsoft word", "winword"):
            known = [
                r"C:\Program Files\Microsoft Office\Root\Office16\WINWORD.EXE",
                r"C:\Program Files (x86)\Microsoft Office\Root\Office16\WINWORD.EXE",
            ]
            target_exe = next((p for p in known if os.path.isfile(p)), None)
        elif norm_id in ("powerpoint", "powerpoint.exe", "microsoft powerpoint", "powerpnt"):
            known = [
                r"C:\Program Files\Microsoft Office\Root\Office16\POWERPNT.EXE",
                r"C:\Program Files (x86)\Microsoft Office\Root\Office16\POWERPNT.EXE",
            ]
            target_exe = next((p for p in known if os.path.isfile(p)), None)
        elif norm_id in ("edge", "msedge"):
            known_edge = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]
            target_exe = next((p for p in known_edge if os.path.isfile(p)), None)
            target_args = ["--new-window", "about:blank"]
        elif norm_id in ("chrome", "google chrome"):
            known_chrome = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]
            target_exe = next((p for p in known_chrome if os.path.isfile(p)), None)
            target_args = ["--new-window", "about:blank"]
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
            subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", "Start-Process 'shell:AppsFolder\\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App'"])
        elif norm_id in ("paint", "mspaint", "mspaint.exe"):
            subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", "Start-Process 'shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App'"])
        elif norm_id in ("calc", "calculator", "calc.exe"):
            subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", "Start-Process 'shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App'"])
        elif norm_id in ("snippingtool", "snipping tool"):
            subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", "Start-Process 'shell:AppsFolder\\Microsoft.ScreenSketch_8wekyb3d8bbwe!App'"])
        else:
            subprocess.Popen([target_exe] + target_args, cwd=working_dir)
    except Exception as launch_err:
        logger.warning("Direct launch error: %s, falling back to shell start", launch_err)
        subprocess.Popen(['cmd.exe', '/c', 'start', '', target_exe] + target_args, cwd=working_dir)

    roadblock_keywords = ("crash", "qmessagebox", "safe mode", "unclean shutdown",
                          "restore previous session", "welcome", "tip of the day", "update available")
    safe_dismiss_buttons = ("Run in Normal Mode", "Run in Safe Mode", "Restore", "Continue",
                            "OK", "Close", "Cancel", "Later", "Don't Send", "No")

    norm_id = app_identifier.strip().lower()

    for second in range(25):
        time.sleep(1.0)
        hwnd = find_app_hwnd(app_identifier)
        if hwnd and win32gui and win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
            logger.info("Discovered main window for '%s' -> hwnd=%s (0x%x) in %d iteration(s)",
                        app_identifier, hwnd, hwnd, second + 1)
            bring_to_foreground(hwnd)
            return hwnd

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
                    elif norm_id in wname or norm_id in wcls:
                        h = getattr(win, "NativeWindowHandle", 0)
                        if h and (not win32gui or (win32gui.IsWindow(h) and win32gui.IsWindowVisible(h))):
                            logger.info("Discovered main window for '%s' -> hwnd=%s (0x%x) in %d iteration(s)",
                                        app_identifier, h, h, second + 1)
                            bring_to_foreground(h)
                            return h
                except Exception:
                    continue

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
        default="Notepad",
        help="Target app name or window title substring (default: 'Notepad')",
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

    # Bypass Office Start Screen if applicable (Excel, Word, PowerPoint)
    bypass_office_start_screen(hwnd, args.app)
    time.sleep(1.0)

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

# Alias for test compatibility
AppScannerOrgan = AppScanner
