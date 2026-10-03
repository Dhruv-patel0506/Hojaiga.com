"""
Organ 29 — Popup Handler (Desktop Interaction Manager)
Hojaiga Automation OS

HostAgent Component: Dedicated universal background popup mitigation layer.
Universally handles:
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

GATEKEEPER_URL = "http://127.0.0.1:11435/api/chat"
GATEKEEPER_SECRET = "339680"

# Tier-3 must NEVER stall the autonomy loop. A cold local model once took ~29.5s
# here; we hard-cap the query and fall through to the Tier-4 heuristic on timeout.
# Env can lower it, and the value is clamped to <= 5s so it cannot regress.
try:
    _t3 = float(os.environ.get("HOJAIGA_POPUP_TIER3_TIMEOUT_S", "5"))
except (TypeError, ValueError):
    _t3 = 5.0
GATEKEEPER_TIER3_TIMEOUT_S = max(0.5, min(5.0, _t3))

# Dynamic fragments (error codes, counters, hex ids, quoted file names) make the
# exact-title cache miss forever; normalise them so repeats map to one fingerprint.
_DYNAMIC_TITLE_RE = re.compile(r"0x[0-9a-f]+|\b[0-9a-f]{8,}\b|\d+|\"[^\"]*\"|'[^']*'", re.IGNORECASE)


def normalize_popup_title(title: str) -> str:
    return re.sub(r"\s+", " ", _DYNAMIC_TITLE_RE.sub("#", (title or "").lower())).strip()


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


# Semantic button categories
POSITIVE_DISMISS_NAMES = {
    "accept", "accept all", "agree", "i agree", "allow", "allow all", "ok", "yes",
    "continue", "got it", "done", "confirm", "proceed", "keep", "run in normal mode",
    "restore", "restore previous session", "save", "save and continue", "understand",
    "i understand", "enable", "turn on", "always allow", "allow while using app",
    "only this time", "apply", "submit", "next", "finish",
}

SAFE_DISMISS_NAMES = {
    "cancel", "close", "dismiss", "don't save", "dont save", "no thanks", "not now",
    "later", "no", "reject", "reject all", "reject non-essential", "decline", "remind me later",
    "don't send", "dont send", "close tab", "x", "never", "block", "deny", "ignore", "skip",
    "ask me later", "discard", "abort",
}

COOKIE_CONSENT_KEYWORDS = {
    "cookie", "cookies", "consent", "gdpr", "privacy preferences", "tracking",
    "accept cookies", "we value your privacy", "manage cookies", "cookie preferences",
}

# ── Generic, data-driven popup INTENT lexicon (Tier-2.5 fast heuristic) ──────
# These are UI *categories*, not per-app strings: they let a novel popup be
# resolved instantly by keyboard, without paying for the slow Tier-3 LLM.
ELEVATION_KEYWORDS = {
    "user account control", "uac", "elevate", "administrator", "for administration",
    "password", "passphrase", "pin", "credential", "sign in", "sign-in", "log on",
    "windows security", "authentication required", "unauthorized", "unlock",
    "permission to", "wants to make changes", "access your",
}
DESTRUCTIVE_COMMIT_KEYWORDS = {
    "save changes", "do you want to save", "unsaved changes", "before closing",
    "discard", "overwrite", "replace", "delete", "remove", "empty", "format",
    "permanent", "cannot be undone", "are you sure", "close without saving",
    "yes, delete", "permanently delete",
}
CRASH_KEYWORDS = {
    "has stopped working", "not responding", "send error report", "crash",
    "restart", "check for solution", "debug",
}

BROWSER_PROMPT_KEYWORDS = {
    "wants to show notifications", "know your location", "use your microphone",
    "use your camera", "save password", "translate this page", "restore pages",
    "open in app", "install app", "add to home screen",
}

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
    """
    Universally extracts label / display text from a control across
    Win32, Qt, WinUI 3, WPF, and Chromium/Web DOM.
    """
    if not ctrl:
        return ""
    try:
        name = (getattr(ctrl, "Name", "") or "").strip()
        if name:
            return name

        # Inspect immediate children for TextControl elements (WinUI 3 & modern web)
        try:
            for ch in getattr(ctrl, "GetChildren", lambda: [])():
                if getattr(ch, "ControlTypeName", "") == "TextControl":
                    cname = (getattr(ch, "Name", "") or "").strip()
                    if cname:
                        return cname
        except Exception:
            pass

        help_text = (getattr(ctrl, "HelpText", "") or "").strip()
        if help_text:
            return help_text

        aid = (getattr(ctrl, "AutomationId", "") or "").strip()
        if aid:
            return aid

        try:
            val_pat = ctrl.GetValuePattern()
            if val_pat and hasattr(val_pat, "Value"):
                val = (val_pat.Value or "").strip()
                if val:
                    return val
        except Exception:
            pass

        return ""
    except Exception:
        return ""


def _matches_button_semantic(text: str, is_consent_or_prompt: bool) -> bool:
    """
    Fuzzy semantic match for button labels, icons, and automation IDs.
    """
    norm = text.strip().lower()
    if not norm:
        return False

    # Close icons
    if not is_consent_or_prompt and norm in ("x", "\u2715", "\u00d7", "\u2716", "close", "dismiss"):
        return True

    target_set = POSITIVE_DISMISS_NAMES if is_consent_or_prompt else (SAFE_DISMISS_NAMES | {"ok", "close"})

    if norm in target_set:
        return True

    words = set(re.findall(r"\w+", norm))
    for target in target_set:
        twords = set(re.findall(r"\w+", target))
        if twords and twords.issubset(words):
            return True
        if len(target) >= 3 and (target in norm or norm.startswith(target) or norm.endswith(target)):
            return True

    return False


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
        """1-token ping so the first REAL Tier-3 query isn't a cold model load.
        Bounded by the same hard cap as Tier-3; failures are silent (Tier-4 covers)."""
        try:
            payload = {"model": "llama3", "stream": False,
                       "messages": [{"role": "user", "content": "ping"}],
                       "options": {"num_predict": 1}}
            req = urllib.request.Request(
                GATEKEEPER_URL, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "X-Hojaiga-Validation": GATEKEEPER_SECRET}, method="POST")
            t0 = time.perf_counter()
            with urllib.request.urlopen(req, timeout=GATEKEEPER_TIER3_TIMEOUT_S) as resp:
                resp.read(64)
            logger.info("[HOST AGENT] Gatekeeper pre-warmed in %.2fs", time.perf_counter() - t0)
        except Exception as exc:
            logger.debug("[HOST AGENT] Gatekeeper pre-warm skipped: %s", exc)
        finally:
            self._prewarm_done.set()

    @staticmethod
    def _button_labels(node: "WindowNode") -> List[str]:
        """Cheap, bounded read of the popup's button captions (for the fingerprint)."""
        pre = node.extra_data.get("buttons") if isinstance(node.extra_data, dict) else None
        if pre:
            return sorted(str(b).strip().lower() for b in pre if str(b).strip())
        if auto is None:
            return []
        try:
            root = node.ctrl_obj
            if root is None and node.handle and win32gui and win32gui.IsWindow(node.handle):
                root = auto.ControlFromHandle(node.handle)
            if root is None:
                return []
            labels = []
            for ctrl, _d in auto.WalkControl(root, includeTop=False, maxDepth=6):
                if (ctrl.ControlTypeName or "") == "ButtonControl":
                    t = _resolve_button_text(ctrl).strip().lower()
                    if t:
                        labels.append(t)
                if len(labels) >= 12:
                    break
            return sorted(set(labels))
        except Exception:
            return []

    def popup_fingerprint(self, node: "WindowNode") -> str:
        """class + win_type + normalised title + button set -> stable across dynamic titles."""
        key = "|".join([
            (node.class_name or "").lower(), node.win_type.value,
            normalize_popup_title(node.title), ",".join(self._button_labels(node)),
        ])
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    def _log_pathway(self, node: "WindowNode", x: int, y: int, action: str, parent_path: str) -> None:
        try:
            self.db.log_new_pathway(
                layout_hash=self.db.generate_layout_hash(node.title), element_name=node.title,
                x=x, y=y, action_type=action, parent_path=parent_path,
                fingerprint=self.popup_fingerprint(node))
        except Exception:
            pass

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

    def _try_semantic_button_dismiss(self, node: WindowNode) -> Optional[Tuple[int, int, str]]:
        """
        Tier 1: Fast Heuristic / Semantic Button Dismissal.
        Inspects the popup's UIA hierarchy for known confirm or safe-dismiss buttons
        and executes direct InvokePattern or physical click.
        """
        if auto is None:
            return None

        search_roots = []
        if node.ctrl_obj:
            search_roots.append(node.ctrl_obj)
        elif node.handle and win32gui and win32gui.IsWindow(node.handle):
            try:
                search_roots.append(auto.ControlFromHandle(node.handle))
            except Exception:
                pass

        if not search_roots:
            return None

        is_consent = node.win_type in (WindowType.COOKIE_BANNER, WindowType.BROWSER_PROMPT)

        for sroot in search_roots:
            try:
                for ctrl, depth in auto.WalkControl(sroot, includeTop=False, maxDepth=10):
                    ctype = ctrl.ControlTypeName or ""
                    if ctype not in ("ButtonControl", "HyperlinkControl", "CustomControl", "PaneControl", "ImageControl"):
                        continue

                    btext = _resolve_button_text(ctrl)
                    aid = (getattr(ctrl, "AutomationId", "") or "").strip()
                    cls_name = (getattr(ctrl, "ClassName", "") or "").strip()

                    is_actionable = ctype in ("ButtonControl", "HyperlinkControl")
                    if not is_actionable:
                        try:
                            has_invoke = hasattr(ctrl, "GetInvokePattern") and ctrl.GetInvokePattern() is not None
                            if has_invoke or getattr(ctrl, "AriaRole", "") in ("button", "link"):
                                is_actionable = True
                        except Exception:
                            pass
                    if not is_actionable:
                        continue

                    matched = False
                    if not is_consent and any(k in (aid + " " + cls_name).lower() for k in ("closebutton", "dismissbutton", "part_closebutton", "btn-close", "modal-close")):
                        matched = True
                    elif _matches_button_semantic(btext, is_consent):
                        matched = True

                    if matched:
                        box = _safe_bounding_box(ctrl)
                        if box:
                            cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2

                            # Try InvokePattern
                            invoked = False
                            try:
                                if hasattr(ctrl, "GetInvokePattern"):
                                    pat = ctrl.GetInvokePattern()
                                    if pat:
                                        def _do():
                                            try:
                                                pat.Invoke()
                                            except Exception:
                                                pass
                                        t = threading.Thread(target=_do, daemon=True)
                                        t.start()
                                        t.join(timeout=0.3)
                                        invoked = True
                            except Exception:
                                pass

                            if not invoked and node.handle:
                                try:
                                    invoked = hin.post_click(node.handle, cx, cy)[0]
                                except Exception:
                                    pass

                            label = btext or aid or "button"
                            logger.info("[HOST AGENT] Tier 1 Semantic Button '%s' activated at (%d, %d)", label, cx, cy)
                            return cx, cy, f"click_{label}"
            except Exception as e:
                logger.debug("Semantic button crawl error: %s", e)

        return None

    @staticmethod
    def _execute_key_intent(action: str, hwnd: int = 0) -> bool:
        """Deliver the key encoded in a 'key:escape' / 'key:enter' intent to the popup's own
        window as posted messages. Never touches the physical keyboard; without a target
        window the intent is undeliverable (False) rather than sent blind."""
        if not action or not action.startswith("key:"):
            return False
        key = action.split(":", 1)[1].strip().lower()
        if not key or not hwnd:
            return False
        try:
            ok, note = hin.post_key_combo(hwnd, key)
            time.sleep(0.08)
            if not ok:
                logger.warning("[HOST AGENT] key intent '%s' undeliverable: %s", key, note)
            return ok
        except Exception as e:
            logger.debug("Key intent '%s' failed: %s", key, e)
            return False

    def _replay_cached_action(self, action: str, target_x: int, target_y: int,
                              default_x: int, default_y: int, hwnd: int = 0) -> Tuple[bool, int, int, str]:
        """
        Rehydrate a stored mitigation. Keyboard intents ('key:*') are pressed
        (no coordinates needed); anything else is a hardware click at the cached point.
        """
        if action and action.startswith("key:"):
            ok = self._execute_key_intent(action, hwnd)
            logger.info("[HOST AGENT] Replayed cached key intent '%s' (ok=%s)", action, ok)
            return ok, (target_x or default_x), (target_y or default_y), action
        try:
            if target_x > 0 and target_y > 0:
                if not hwnd:
                    return False, target_x, target_y, action
                ok, note = hin.post_click(hwnd, target_x, target_y)
                logger.info("Headless mitigation replay at (%d, %d): %s", target_x, target_y, note)
                return ok, target_x, target_y, action
            return True, target_x, target_y, action
        except Exception as click_err:
            logger.error("Headless mitigation failure: %s", click_err)
            return False, target_x, target_y, action

    def _lexical_intent_decision(self, node: WindowNode) -> Optional[Tuple[str, bool]]:
        """
        Tier-2.5: Data-driven intent classifier over popup text/class/type.
        Returns (action, need_human) or None when the popup is genuinely ambiguous
        (only then do we pay for the slow Tier-3 LLM). It NEVER auto-accepts
        elevation/credential or destructive-commit prompts — those escalate to a
        human. This is a generic UI *category* matcher, not per-app hardcoding.
        """
        blob = " ".join(filter(None, [
            node.title or "",
            node.text_content or "",
            node.class_name or "",
        ])).lower()
        wtype = node.win_type

        # Elevation / credentials: always human-in-the-loop, never auto-accept.
        if wtype == WindowType.AUTHENTICATION or any(k in blob for k in ELEVATION_KEYWORDS):
            return "key:escape", True

        # Destructive commit prompts: auto-confirm risks data loss -> escalate.
        if any(k in blob for k in DESTRUCTIVE_COMMIT_KEYWORDS):
            return "key:escape", True

        # Crash reporters / error dialogs: safe to dismiss with Escape.
        if wtype == WindowType.CRASH_REPORTER or any(k in blob for k in CRASH_KEYWORDS):
            return "key:escape", False

        # Consent / cookie / browser prompts with no actionable button: Escape is safe.
        if (wtype in (WindowType.COOKIE_BANNER, WindowType.BROWSER_PROMPT)
                or any(k in blob for k in COOKIE_CONSENT_KEYWORDS)
                or any(k in blob for k in BROWSER_PROMPT_KEYWORDS)):
            return "key:escape", False

        # Plain informational message boxes (OK/Acknowledge): Enter dismisses them.
        if wtype in (WindowType.MESSAGE_BOX, WindowType.NOTIFICATION):
            return "key:enter", False

        return None

    def resolve_and_mitigate(self, node: WindowNode) -> Tuple[bool, int, int, str]:
        """
        Universal resolution pipeline:
        1. Tier 1: Fast Semantic Button Extraction (UIA Invoke on 'Accept', 'Allow', 'OK', 'Cancel', etc.)
        2. Tier 2: SSMS Database History Cache (`check_popup_history`, replays click OR key: intents)
        2.5 Tier 2.5: Lexical intent classifier (instant keyboard decision for known UI
           categories; elevation/destructive prompts escalate to human, never auto-accepted)
        3. Tier 3: Brain Gatekeeper LLM Proxy (port 11435, hard-capped <=5s)
        4. Tier 4: Safe Keyboard Dismiss Fallback (Escape) — result cached so repeats
           short-circuit at Tier 2
        Returns (success, target_x, target_y, action).
        """
        b = node.bounds
        default_x = (b.left + b.right) // 2 if b else 0
        default_y = (b.top + b.bottom) // 2 if b else 0

        # ------------------------------------------------------------------ #
        # Tier 1: Fast Semantic Button Extraction
        # ------------------------------------------------------------------ #
        sem_res = self._try_semantic_button_dismiss(node)
        if sem_res:
            tx, ty, act = sem_res
            self._log_pathway(node, tx, ty, act, "organ_29_tier1_semantic")
            return True, tx, ty, act

        # ------------------------------------------------------------------ #
        # Tier 2: Check SSMS Database Manager History Cache
        # ------------------------------------------------------------------ #
        cached_fix = self.db.check_popup_history(node.title)
        if not cached_fix:
            # Dynamic-title fallback: same class + button set + normalised title.
            cached_fix = self.db.check_popup_fingerprint(self.popup_fingerprint(node))
            if cached_fix:
                logger.info("[HOST AGENT] Tier 2 FINGERPRINT cache hit for '%s'", node.title)
        if cached_fix:
            logger.info("[HOST AGENT] Tier 2 Database Cache Hit for '%s'!", node.title)
            target_x = int(cached_fix.get("x", default_x))
            target_y = int(cached_fix.get("y", default_y))
            action = cached_fix.get("action", "click")
            return self._replay_cached_action(action, target_x, target_y, default_x, default_y, node.handle)

        # ------------------------------------------------------------------ #
        # Tier 2.5: Data-driven lexical intent (fast, no LLM, no coordinates)
        # ------------------------------------------------------------------ #
        lex = self._lexical_intent_decision(node)
        if lex is not None:
            lex_action, lex_need_human = lex
            if lex_need_human:
                logger.warning(
                    "[HOST AGENT] Tier 2.5 lexical => ELEVATION/DESTRUCTIVE prompt '%s'; "
                    "refusing to auto-accept, escalating to human (no auto-keystroke).",
                    node.title)
                return False, default_x, default_y, "need_human"
            fired = self._execute_key_intent(lex_action, node.handle)
            self._log_pathway(node, 0, 0, lex_action, "organ_29_tier2_5_lexical")
            logger.info("[HOST AGENT] Tier 2.5 lexical resolved '%s' via %s (fired=%s) — "
                        "skipped the slow Tier-3 LLM.", node.title, lex_action, fired)
            return fired, default_x, default_y, lex_action

        # ------------------------------------------------------------------ #
        # Tier 3: Query Gatekeeper Proxy for Visual/Text Reasoning
        # ------------------------------------------------------------------ #
        logger.warning("[HOST AGENT] Tier 3 Gatekeeper Query for '%s' at %s...", node.title, GATEKEEPER_URL)

        system_instructions = (
            "You are a universal Windows desktop and web application popup solver. "
            "Analyze the popup/modal data and output STRICTLY valid JSON with keys: action, target_x, target_y."
        )

        user_prompt = (
            f"Window Title: '{node.title}'\nClass: '{node.class_name}'\nType: '{node.win_type.value}'\n"
            f"Discovered Content: '{node.text_content}'\n"
            f"Bounds Center: ({default_x}, {default_y})\n"
            "Provide the safest coordinates and action to dismiss or proceed past this blocking barrier."
        )

        payload = {
            "model": "llama3",
            "messages": [
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False
        }

        target_x, target_y, action = default_x, default_y, "dismiss"
        try:
            req = urllib.request.Request(
                GATEKEEPER_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Hojaiga-Validation": GATEKEEPER_SECRET
                },
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=GATEKEEPER_TIER3_TIMEOUT_S) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                response_content = res_data.get("message", {}).get("content", "")

                match = re.search(r"\{.*\}", response_content, re.DOTALL)
                if match:
                    decision = json.loads(match.group(0))
                    target_x = int(decision.get("target_x", default_x))
                    target_y = int(decision.get("target_y", default_y))
                    action = decision.get("action", "click")

                    logger.info("[HOST AGENT] Gatekeeper Decision: Action='%s' Coordinates (%d, %d)", action, target_x, target_y)

                    if target_x > 0 and target_y > 0 and node.handle:
                        hin.post_click(node.handle, target_x, target_y)

                    self._log_pathway(node, target_x, target_y, action, "organ_29_gatekeeper")
                    return True, target_x, target_y, action
        except Exception as gate_err:
            logger.error("[HOST AGENT] Gatekeeper proxy failed/timed-out (cap=%.1fs): %s — "
                         "falling through to Tier-4 heuristic",
                         GATEKEEPER_TIER3_TIMEOUT_S, gate_err)

        # ------------------------------------------------------------------ #
        # Tier 4: Keyboard Safe Dismiss Fallback
        # ------------------------------------------------------------------ #
        logger.warning("[HOST AGENT] Tier 4 Safe Keyboard Fallback for '%s'", node.title)
        try:
            if self._execute_key_intent("key:escape", node.handle):
                # Cache the escape so a REPEAT of this unknown popup hits Tier-2 instantly
                # instead of re-paying the slow Tier-3 LLM on every encounter.
                self._log_pathway(node, 0, 0, "key:escape", "organ_29_tier4_escape_cached")
                return True, default_x, default_y, "escape_fallback"
            logger.warning("[HOST AGENT] Tier 4 escape undeliverable for '%s' (no window handle)", node.title)
        except Exception:
            pass

        return False, target_x, target_y, action

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
                    # Policy engine first (reads the dialog's words, picks the NON-destructive
                    # button, headless). It also leaves a Save/Open picker alone while a task owns it.
                    try:
                        from core_organs import popup_policy as _pp
                        ctx = _pp.TASK
                        res = _pp.resolve_dialog(hwnd, mode=ctx.mode, task_paths=ctx.paths,
                                                 allow_destructive=ctx.allow_destructive)
                        if res.action == "owned-by-task" or res.need_human or res.handled:
                            logger.info("[SENTINEL] policy: %s -> %s", res.dialog, res.action)
                            continue
                    except Exception as _pe:
                        logger.debug("[SENTINEL] policy pass failed: %s", _pe)
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
                    self.resolve_and_mitigate(node)
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
