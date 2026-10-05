"""
Organ 29 — Popup Handler (Desktop Interaction Manager)
Hojaiga Automation OS

HostAgent Component: popup ENUMERATION / DETECTION layer. Every DECISION about what to do with a popup now lives in
popup_policy.py (one ladder: gate -> escalate -> UIA buttons -> pathway cache -> lexical -> capped gatekeeper -> safe
Escape). This module finds popups (classic dialogs, in-window modals, unsolicited desktop modals, CNS events) and
hands each one to that engine through thin delegates.
Universally detects:
- Native Win32 popups (#32770, MessageBox, DialogBox, DirectUIHWND)
- Qt/Qt6 modals (QMessageBox, QDialog, QFileDialog, custom dialogs)
- WinUI 3 / XAML / UWP in-window modals (ContentDialog, Flyout, Popup, PopupHost, StandardPopupHost)
- Chromium & Electron popups (permission bubbles, notification prompts, save password, Chrome_WidgetWin)
- In-page web modals (HTML <dialog>, cookie consent banners, newsletter overlays, aria-modal, SweetAlert, Material UI)
- Native JavaScript alerts (alert, confirm, prompt)
- Unsolicited system/crash dialogs (WerFault, Application Error, Fatal Exception)
"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from core_organs import headless_input as hin  # headless delivery only

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

# Ensure interactive desktop is attached before COM/UIA initialization
try:
    user32 = ctypes.windll.user32
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)
except Exception:
    pass

try:
    import uiautomation as auto
except ImportError:
    auto = None

try:
    import win32api
    import win32con
    import win32gui
    import win32process
except ImportError:
    win32api = win32con = win32gui = win32process = None

from core_organs.database_manager import DatabaseManager
from core_organs.cns_bridge import CNSPopupInterceptor

logger = logging.getLogger("hojaiga.organ29.popup_handler")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

# The decision engine and its limits live in popup_policy; these names stay importable from here (tests, other organs).
from core_organs import popup_policy as pp
from core_organs.popup_policy import (  # noqa: E402,F401
    GATEKEEPER_URL, GATEKEEPER_SECRET, GATEKEEPER_TIER3_TIMEOUT_S, normalize_title as normalize_popup_title,
)


SCREEN_W = win32api.GetSystemMetrics(0) if win32api else 1920
SCREEN_H = win32api.GetSystemMetrics(1) if win32api else 1080


class WindowType(str, Enum):
    MAIN_WINDOW = "main_window"
    CHILD_WINDOW = "child_window"
    MODAL_WINDOW = "modal_window"
    MESSAGE_BOX = "message_box"
    CONFIRMATION = "confirmation"
    AUTHENTICATION = "authentication"
    CRASH_REPORTER = "crash_reporter"
    NOTIFICATION = "notification"
    IN_WINDOW_MODAL = "in_window_modal"
    WEB_MODAL = "web_modal"
    COOKIE_BANNER = "cookie_banner"
    BROWSER_PROMPT = "browser_prompt"
    UNKNOWN = "unknown"


@dataclass
class WindowRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> Tuple[int, int]:
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)


@dataclass
class WindowNode:
    handle: int
    parent_handle: Optional[int]
    owner_handle: Optional[int]
    process_id: int
    title: str
    class_name: str
    win_type: WindowType
    bounds: WindowRect
    is_visible: bool = True
    has_focus: bool = False
    text_content: str = ""
    ctrl_obj: Any = None
    extra_data: Dict[str, Any] = field(default_factory=dict)


# Popup lexicon: owned by popup_policy (re-exported here because detection below and older callers use these names).
from core_organs.popup_policy import (  # noqa: E402,F401
    COOKIE_CONSENT_KEYWORDS, ELEVATION_KEYWORDS, DESTRUCTIVE_COMMIT_KEYWORDS, CRASH_KEYWORDS, BROWSER_PROMPT_KEYWORDS,
)

FRAMEWORK_MODAL_CLASSES = {
    "contentdialog", "flyout", "menuflyout", "popuphost", "standardpopuphost",
    "teachingtip", "messagedialog", "chrome_widgetwin", "bubblesyncpromo",
    "extensionpopup", "permissionpromptbubbleview", "qdialog", "qmessagebox",
    "qfiledialog", "qprogressdialog", "modal", "dialog", "backdrop", "overlay",
    "swal2", "muidialog", "chakra-modal", "ant-modal", "reactmodal",
}


def _safe_bounding_box(ctrl) -> Optional[Tuple[int, int, int, int]]:
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


def _resolve_button_text(ctrl) -> str:
    """Label of a control across Win32 / Qt / WinUI 3 / WPF / Chromium (shared with the decision engine)."""
    return pp.control_text(ctrl)


class DesktopInteractionManager:
    """
    Organ 29 Public Interface Layer (HostAgent Role).
    Intercepts application popup threads, references historical SSMS indices,
    and deploys hardware click resolutions via PyAutoGUI and direct UIA InvokePattern.
    Universally handles native Win32, Qt, WinUI 3, WPF, Chromium, and Web modals.
    """

    def __init__(self, cns_port: int = 11436) -> None:
        self.db = DatabaseManager()
        self.cns = CNSPopupInterceptor(role="HostAgent", port=cns_port)
        self._cns_started = False
        self._running = False
        self._prewarm_done = threading.Event()
        if os.environ.get("HOJAIGA_POPUP_PREWARM", "1") != "0":
            threading.Thread(target=self._prewarm_gatekeeper, daemon=True,
                             name="popup-gatekeeper-prewarm").start()

    def _prewarm_gatekeeper(self) -> None:
        """1-token ping so the first REAL Tier-3 query is not a cold model load (the engine owns the ping)."""
        try:
            pp.prewarm_gatekeeper()
        finally:
            self._prewarm_done.set()

    @staticmethod
    def _view(node: "WindowNode") -> "pp.PopupView":
        """Describe a detected popup to the decision engine."""
        extra = node.extra_data if isinstance(node.extra_data, dict) else {}
        b = node.bounds
        return pp.PopupView(
            hwnd=int(node.handle or 0), title=node.title or "", class_name=node.class_name or "",
            kind=node.win_type.value, text=node.text_content or "", buttons=tuple(extra.get("buttons") or ()),
            ctrl=node.ctrl_obj, bounds=(b.left, b.top, b.right, b.bottom) if b else (0, 0, 0, 0))

    @staticmethod
    def _button_labels(node: "WindowNode") -> List[str]:
        return pp.button_labels(DesktopInteractionManager._view(node))

    def popup_fingerprint(self, node: "WindowNode") -> str:
        """class + win_type + normalised title + button set -> stable across dynamic titles."""
        return pp.fingerprint(self._view(node))

    def _log_pathway(self, node: "WindowNode", x: int, y: int, action: str, parent_path: str) -> None:
        pp.log_pathway(self.db, self._view(node), x, y, action, parent_path)

    def _on_cns_popup(self, message: Dict[str, Any]):
        """Handler invoked by CNS bridge when an AppAgent detects a popup."""
        title = message.get("title") or "Unknown Popup"
        layout_hash = message.get("layout_hash") or ""
        x = int(message.get("x", 0))
        y = int(message.get("y", 0))
        popup_id = message.get("popup_id") or f"{layout_hash}_{int(time.time()*1000)}"
        win_type_str = message.get("win_type", "modal_window")

        try:
            wtype = WindowType(win_type_str)
        except ValueError:
            wtype = WindowType.MODAL_WINDOW

        logger.info("[HOST AGENT] CNS message POPUP_DETECTED received: '%s' (%s) type=%s at (%d, %d)",
                    title, popup_id, wtype.value, x, y)

        node = WindowNode(
            handle=int(message.get("hwnd", 0)),
            parent_handle=None,
            owner_handle=None,
            process_id=int(message.get("pid", 0)),
            title=title,
            class_name=message.get("class_name", ""),
            win_type=wtype,
            bounds=WindowRect(left=max(0, x - 100), top=max(0, y - 50), right=x + 100, bottom=y + 50),
            is_visible=True,
            has_focus=True,
            text_content=message.get("text_content", title),
            extra_data=message,
        )

        success, target_x, target_y, action = self.resolve_and_mitigate(node)
        self.cns.send_resolution(popup_id=popup_id, action=action, x=target_x, y=target_y)
        logger.info("[HOST AGENT] Dispatched POPUP_RESOLUTION for %s: action=%s at (%d, %d) success=%s",
                    popup_id, action, target_x, target_y, success)

    async def start_event_monitoring(self) -> bool:
        self._running = True
        try:
            if hasattr(self.cns, 'start'):
                self.cns.start(on_popup_detected=self._on_cns_popup)
            self._cns_started = True
            logger.info("[HOST AGENT] CNS Interceptor Bridge linked successfully on port %d.", self.cns.port)
            return True
        except Exception as e:
            logger.error("[HOST AGENT] Critical CNS binding failure: %s", e)
            return False

    def find_in_window_modals(self, target_hwnd_or_ctrl) -> List[WindowNode]:
        """
        Universally discovers in-window modals, flyouts, and web overlays that do not
        have a separate Win32 HWND. Handles:
        - WinUI 3 / XAML ContentDialog, Flyout, Popup, PopupHost, StandardPopupHost
        - Chromium & Electron permission prompt bubbles (Chrome_WidgetWin)
        - HTML <dialog> elements, aria-modal="true", cookie consent banners, SweetAlert, Material UI
        """
        discovered: List[WindowNode] = []
        if auto is None:
            return discovered

        root_ctrl = None
        if isinstance(target_hwnd_or_ctrl, int):
            try:
                root_ctrl = auto.ControlFromHandle(target_hwnd_or_ctrl)
            except Exception:
                return discovered
        else:
            root_ctrl = target_hwnd_or_ctrl

        if not root_ctrl:
            return discovered

        try:
            for ctrl, depth in auto.WalkControl(root_ctrl, includeTop=False, maxDepth=16):
                try:
                    ctype = ctrl.ControlTypeName or ""
                    ccls = (ctrl.ClassName or "").strip()
                    cname = (ctrl.Name or "").strip()
                    aid = (ctrl.AutomationId or "").strip()
                    arole = (getattr(ctrl, "AriaRole", "") or "").strip().lower()

                    is_modal = False
                    try:
                        is_modal = getattr(ctrl, "IsModal", False) or arole in ("dialog", "alertdialog")
                    except Exception:
                        pass

                    norm_cls = ccls.lower()
                    norm_text = f"{cname} {aid} {ccls}".lower()

                    # Detect WinUI/XAML & Framework modal containers
                    if any(k in norm_cls for k in FRAMEWORK_MODAL_CLASSES):
                        is_modal = True

                    # Detect Web Dialog / Cookie Banner
                    if any(k in norm_text for k in COOKIE_CONSENT_KEYWORDS) and ctype in ("PaneControl", "GroupControl", "CustomControl", "WindowControl"):
                        is_modal = True

                    if any(k in norm_text for k in BROWSER_PROMPT_KEYWORDS):
                        is_modal = True

                    if is_modal:
                        box = _safe_bounding_box(ctrl)
                        if box:
                            l, t, r, b = box
                            if (r - l) < 40 or (b - t) < 30:
                                continue

                            wtype = WindowType.IN_WINDOW_MODAL
                            if any(k in norm_text for k in COOKIE_CONSENT_KEYWORDS):
                                wtype = WindowType.COOKIE_BANNER
                            elif any(k in norm_text for k in BROWSER_PROMPT_KEYWORDS) or "chrome_widgetwin" in norm_cls:
                                wtype = WindowType.BROWSER_PROMPT

                            discovered.append(WindowNode(
                                handle=0,
                                parent_handle=getattr(root_ctrl, "NativeWindowHandle", 0),
                                owner_handle=None,
                                process_id=getattr(ctrl, "ProcessId", 0),
                                title=cname or aid or ccls or "In-Window Modal",
                                class_name=ccls,
                                win_type=wtype,
                                bounds=WindowRect(left=l, top=t, right=r, bottom=b),
                                is_visible=True,
                                has_focus=True,
                                text_content=f"{cname} {aid} {ccls}",
                                ctrl_obj=ctrl,
                            ))
                except Exception:
                    continue
        except Exception as e:
            logger.debug("In-window modal crawl notice: %s", e)

        return discovered

    @staticmethod
    def _execute_key_intent(action: str, hwnd: int = 0) -> bool:
        """Deliver the key encoded in a 'key:escape' / 'key:enter' intent to the popup's own window as posted
        messages. Never touches the physical keyboard; without a target window the intent is undeliverable (False)
        rather than sent blind. (Delivery primitive only - which key to send is decided by popup_policy.)"""
        return pp._default_key_sender(action, hwnd)

    def _lexical_intent_decision(self, node: WindowNode) -> Optional[Tuple[str, bool]]:
        """Tier-2.5 intent for a detected popup: (action, need_human) or None. Pure delegate to the engine."""
        return pp.lexical_intent(self._view(node))

    def resolve_and_mitigate(self, node: WindowNode) -> Tuple[bool, int, int, str]:
        """Resolve a detected popup. ONE implementation: popup_policy.resolve_view runs the whole ladder (gate ->
        escalate -> UIA buttons -> pathway cache -> lexical -> capped gatekeeper -> safe Escape). This only supplies the
        instance's own pathway DB and key-delivery primitive (looked up at call time, so a test's stand-in is honoured).
        Returns (success, target_x, target_y, action)."""
        ctx = pp.TASK
        d = pp.resolve_view(self._view(node), db=self.db, key_sender=self._execute_key_intent,
                            mode=ctx.mode, task_paths=ctx.paths, allow_destructive=ctx.allow_destructive)
        self.last_decision = d
        if d.action == "owned-by-task":
            return True, d.x, d.y, "owned_by_task"
        if d.need_human:
            logger.warning("[HOST AGENT] '%s' needs a human (%s) - nothing was pressed.", node.title, d.note)
            return False, d.x, d.y, "need_human"
        return d.handled, d.x, d.y, d.action

    async def intercept_popup(self, node: WindowNode) -> bool:
        logger.info("[HOST AGENT] Intercept event caught for window: '%s'", node.title)
        success, _, _, _ = self.resolve_and_mitigate(node)
        return success

    def scan_and_resolve_any(self, target_hwnd_or_ctrl) -> int:
        """
        One-shot synchronous scanner that discovers and resolves any roadblock popup,
        native modal, or in-window flyout on the target application.
        Returns the count of popups mitigated.
        """
        modals = self.find_in_window_modals(target_hwnd_or_ctrl)
        mitigated = 0
        for m in modals:
            logger.info("[ONE-SHOT] Mitigating in-window modal '%s' (type=%s)", m.title, m.win_type.value)
            success, _, _, _ = self.resolve_and_mitigate(m)
            if success:
                mitigated += 1
        return mitigated

    def wrap_hwnd(self, hwnd: int) -> Optional["WindowNode"]:
        """Build a WindowNode for an arbitrary dialog window handle (None when it is gone)."""
        if not (win32gui and hwnd and win32gui.IsWindow(hwnd)):
            return None
        try:
            r = win32gui.GetWindowRect(hwnd)
            title = win32gui.GetWindowText(hwnd) or "Modal Dialog"
            return WindowNode(
                handle=hwnd, parent_handle=win32gui.GetParent(hwnd) or None,
                owner_handle=(win32gui.GetWindow(hwnd, win32con.GW_OWNER) or None) if win32con else None,
                process_id=win32process.GetWindowThreadProcessId(hwnd)[1] if win32process else 0,
                title=title, class_name=win32gui.GetClassName(hwnd) or "",
                win_type=WindowType.MODAL_WINDOW,
                bounds=WindowRect(left=r[0], top=r[1], right=r[2], bottom=r[3]),
                is_visible=True, has_focus=False, text_content=title)
        except Exception as exc:
            logger.debug("wrap_hwnd failed: %s", exc)
            return None

    def _detect_desktop_top_modals(self) -> List[Tuple[int, str, str]]:
        """
        Scans for unsolicited system dialogs, message boxes, and crash windows
        across all running processes.
        """
        results = []
        if not win32gui:
            return results

        def _enum(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return
                cls = win32gui.GetClassName(hwnd) or ""
                title = win32gui.GetWindowText(hwnd) or ""
                norm_title = title.lower()

                # Target #32770 dialogs, WerFault crash dialogs, or error boxes
                is_modal = False
                if cls == "#32770":
                    is_modal = True
                elif any(k in norm_title for k in ("error", "fatal", "crash", "stopped working", "werfault", "exception", "security alert")):
                    is_modal = True

                if is_modal:
                    if any(ig in norm_title for ig in ("visual studio code", "antigravity", "powershell", "task manager", "program manager")):
                        return
                    results.append((hwnd, title, cls))
            except Exception:
                pass

        try:
            win32gui.EnumWindows(_enum, None)
        except Exception:
            pass
        return results

    async def _autonomous_desktop_sentinel(self):
        """
        Autonomous desktop watchdog: resolves unsolicited top-level modal dialogs
        (#32770, crash reporters, unprompted warning boxes) so automated runs never freeze.
        """
        logger.info("[HOST AGENT] Autonomous Desktop Sentinel active (sweep interval: 2.0s).")
        while self._running:
            try:
                top_modals = self._detect_desktop_top_modals()
                for hwnd, title, cls in top_modals:
                    logger.warning("[SENTINEL] Unsolicited roadblock detected: HWND=%d Title='%s' Class='%s'", hwnd, title, cls)
                    # (one engine: resolve_and_mitigate below runs the whole ladder, including the task-owned
                    # picker rule and the non-destructive button policy)
                    r = win32gui.GetWindowRect(hwnd) if win32gui else (0, 0, 400, 300)
                    node = WindowNode(
                        handle=hwnd,
                        parent_handle=win32gui.GetParent(hwnd) if win32gui else None,
                        owner_handle=win32gui.GetWindow(hwnd, win32con.GW_OWNER) if win32con and win32gui else None,
                        process_id=win32process.GetWindowThreadProcessId(hwnd)[1] if win32process and win32gui else 0,
                        title=title or "Modal Dialog",
                        class_name=cls,
                        win_type=WindowType.MODAL_WINDOW,
                        bounds=WindowRect(left=r[0], top=r[1], right=r[2], bottom=r[3]),
                        is_visible=True,
                        has_focus=True,
                        text_content=title,
                    )
                    ok, _x, _y, act = self.resolve_and_mitigate(node)
                    logger.info("[SENTINEL] %s -> %s (handled=%s)", title, act, ok)
            except Exception as e:
                logger.debug("Sentinel error: %s", e)
            await asyncio.sleep(2.0)

    async def run_listener_loop(self) -> None:
        await self.start_event_monitoring()
        sentinel_task = asyncio.create_task(self._autonomous_desktop_sentinel())
        logger.info("[HOST AGENT] Active universal defensive shield & sentinel tracking loop initialized.")
        try:
            while self._running:
                await asyncio.sleep(1.0)
        finally:
            sentinel_task.cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    manager = DesktopInteractionManager()
    manager._running = True

    try:
        asyncio.run(manager.run_listener_loop())
    except KeyboardInterrupt:
        logger.info("[HOST AGENT] Defensive shield deactivated safely.")
