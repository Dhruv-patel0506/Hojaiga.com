"""
popup_policy.py -- the ONE popup decision engine. Inspect, classify and resolve blocking popups, headless.

organ_29 (popup handler) is now only the ENUMERATION / DETECTION layer (find dialogs, in-window modals, the CNS
listener, the sentinel loop). Every decision about what to do with a popup lives here, behind one ladder:

    gate        popup_mode: a popup the running step EXPECTS is left alone; a popup our own scan probe opened is
                cancel-only (never accepted, never cached)
    escalate    elevation / credential / UAC and (unauthorised) destructive commits -> need_human. ZERO buttons are
                pressed and no key is sent, whatever any later tier could have done.
    T1 buttons  UIA read of the popup's own words and buttons (title, message, button captions / standard ids),
                category by a generic lexicon (no app names), the NON-destructive answer per category, delivered by
                UIA Invoke (fallback: a window message to the button's HWND). Never the physical pointer / keyboard.
    T2 cache    exact-title pathway, then the class + button FINGERPRINT (dynamic titles: error codes, counters and
                file names are normalised out, so 'Error 0x80070005 (attempt 3)' and '... 0x8007271D (attempt 17)'
                are one popup)
    T2.5 lexical  instant keyboard decision for a known category when no button could be read
    T3 gatekeeper local LLM, HARD-capped (<= 5 s) and guarded by a circuit breaker: one timeout and later cold popups
                skip T3 for HOJAIGA_POPUP_T3_BREAKER_S instead of each paying the cap again
    T4 escape   safe Escape fallback, cached so the repeat is a T2 hit

The whole cold path (button re-read + T3) shares one budget (HOJAIGA_POPUP_BUDGET_S, default 5 s).
`resolve_dialog` / `clear_blockers` (the loop-facing API) and organ_29's `resolve_and_mitigate` both call
`resolve_view`; there is no second implementation.
"""

import hashlib
import json
import logging
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core_organs import headless_input as hin

logger = logging.getLogger("hojaiga.popup_policy")

try:
    import uiautomation as auto
except Exception:  # pragma: no cover
    auto = None

# --------------------------------------------------------------------------------------------- limits
GATEKEEPER_URL = os.environ.get("HOJAIGA_GATEKEEPER_URL", "http://127.0.0.1:11435/api/chat")
GATEKEEPER_SECRET = "339680"
try:
    _t3 = float(os.environ.get("HOJAIGA_POPUP_TIER3_TIMEOUT_S", "5"))
except (TypeError, ValueError):
    _t3 = 5.0
GATEKEEPER_TIER3_TIMEOUT_S = max(0.5, min(5.0, _t3))      # clamped: Tier-3 can never stall the loop past 5 s
try:
    POPUP_BUDGET_S = max(1.0, min(8.0, float(os.environ.get("HOJAIGA_POPUP_BUDGET_S", "5"))))
except (TypeError, ValueError):
    POPUP_BUDGET_S = 5.0
try:
    T3_BREAKER_S = max(0.0, float(os.environ.get("HOJAIGA_POPUP_T3_BREAKER_S", "60")))
except (TypeError, ValueError):
    T3_BREAKER_S = 60.0
UNRENDERED_REREAD_S = 4.5          # a dialog whose UIA tree is still empty gets this long to paint (loaded machine)

# --------------------------------------------------------------------------------------------- lexicon
# Win32 standard dialog button ids -> role (stable across languages)
_ID_ROLE = {"1": "ok", "2": "cancel", "3": "abort", "4": "retry", "5": "ignore",
            "6": "yes", "7": "no", "8": "close", "9": "help", "10": "tryagain", "11": "continue"}

_PICKER_TITLES = ("save as", "save", "open", "export", "import", "browse", "select a file", "select file",
                  "choose file", "choose a file", "upload", "select folder", "browse for folder")
_OVERWRITE_CUES = ("already exists", "replace it", "overwrite", "confirm save as", "do you want to replace")
_SAVE_CHANGES_CUES = ("save changes", "do you want to save", "want to save", "unsaved changes",
                      "save your changes", "changes to")
_PERMISSION_CUES = ("user account control", "administrator", "elevat", "permission", "credential",
                    "password", "sign in", "authenticat", "allow this app to make changes")
_COOKIE_CUES = ("cookie", "consent", "gdpr", "privacy preferences", "we value your privacy")
_ERROR_CUES = ("error", "failed", "cannot", "can't", "could not", "unable", "not responding",
               "stopped working", "problem", "exception", "crash")
_INFO_CUES = ("information", "notice", "update", "welcome", "what's new", "tip", "complete",
              "success", "finished", "done")

# Generic, data-driven popup INTENT lexicon (UI *categories*, not per-app strings)
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
COOKIE_CONSENT_KEYWORDS = {
    "cookie", "cookies", "consent", "gdpr", "privacy preferences", "tracking",
    "accept cookies", "we value your privacy", "manage cookies", "cookie preferences",
}
BROWSER_PROMPT_KEYWORDS = {
    "wants to show notifications", "know your location", "use your microphone",
    "use your camera", "save password", "translate this page", "restore pages",
    "open in app", "install app", "add to home screen",
}

# Preference order of button ROLES per category (first available wins). All non-destructive and all
# privacy-preserving: a cookie / browser-permission prompt is REJECTED or dismissed, never accepted.
POLICY: Dict[str, Tuple[str, ...]] = {
    "overwrite_confirm": ("no", "cancel"),
    "save_changes": ("cancel", "no"),           # keep the document; never 'Don't save' / 'Save' blind
    "file_picker": ("cancel",),
    "error": ("ok", "close", "continue", "ignore", "cancel"),
    "info": ("ok", "close", "continue", "yes", "cancel"),
    "cookie_consent": ("reject", "decline", "no", "close", "cancel", "ok"),
    "browser_prompt": ("block", "ignore", "no", "cancel", "close"),
    "unknown": ("cancel", "close", "no", "ok"),
}
_ROLE_WORDS = {
    "ok": ("ok", "okay", "got it", "done", "understood", "i understand", "dismiss"),
    "cancel": ("cancel", "abort"),
    "yes": ("yes",),
    "no": ("no", "don't save", "dont save", "do not save"),
    "close": ("close", "exit"),
    "continue": ("continue", "next", "proceed"),
    "ignore": ("ignore", "skip", "not now", "later", "remind me later", "no thanks"),
    "retry": ("retry", "try again"),
    "reject": ("reject all", "reject", "decline", "necessary only", "only necessary", "deny", "refuse"),
    "decline": ("decline", "deny", "refuse"),
    "block": ("block", "deny", "don't allow", "dont allow", "never allow", "never"),
}
_KIND_CATEGORY = {"cookie_banner": "cookie_consent", "browser_prompt": "browser_prompt",
                  "crash_reporter": "error", "authentication": "permission"}

# Kinds that are known-benign categories (a browser's "Save password?" bubble, a cookie banner) mention words such as
# "password" / "sign in" constantly. They escalate only on the unmistakable elevation phrases; everything else about
# them is answered by the privacy-preserving policy (reject / block / dismiss).
_STRICT_ELEVATION = ("user account control", "administrator", "elevat", "allow this app to make changes",
                     "wants to make changes", "windows security", "credential")
_BENIGN_KINDS = ("cookie_banner", "browser_prompt")

# Dynamic fragments (error codes, counters, hex ids, quoted file names) make the exact-title cache miss forever;
# normalise them so repeats map to one fingerprint.
_DYNAMIC_TITLE_RE = re.compile(r"0x[0-9a-f]+|\b[0-9a-f]{8,}\b|\d+|\"[^\"]*\"|'[^']*'", re.IGNORECASE)


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", _DYNAMIC_TITLE_RE.sub("#", (title or "").lower())).strip()


def _has(blob: str, keywords) -> bool:
    """Substring match for phrases; whole-word match for short tokens ('pin', 'uac') so 'mapping' / 'spinner' do not
    read as credentials."""
    for k in keywords:
        if len(k) <= 4:
            if re.search(r"\b" + re.escape(k) + r"\b", blob):
                return True
        elif k in blob:
            return True
    return False


# --------------------------------------------------------------------------------------------- data
@dataclass
class TaskContext:
    """What the running task owns. Set by the autonomy loop; read by every dialog handler
    (including organ_29's background sentinel) so they never cancel a picker the task needs."""
    paths: Tuple[str, ...] = ()
    allow_destructive: bool = False
    mode: str = "inflight"


TASK = TaskContext()


@dataclass
class DialogInfo:
    hwnd: int
    title: str = ""
    class_name: str = ""
    texts: List[str] = field(default_factory=list)
    buttons: List[Tuple[str, str, object]] = field(default_factory=list)  # (name, automation_id, ctrl)
    category: str = "unknown"

    @property
    def message(self) -> str:
        return " ".join(self.texts)

    def brief(self) -> str:
        return (f"'{self.title}' [{self.category}] msg='{self.message[:70]}' "
                f"buttons={[b[0] for b in self.buttons]}")


@dataclass
class Resolution:
    handled: bool
    need_human: bool
    action: str
    dialog: str
    note: str = ""


@dataclass
class PopupView:
    """A popup, described neutrally (organ_29's WindowNode, a raw hwnd, or an in-window modal all map onto this)."""
    hwnd: int = 0
    title: str = ""
    class_name: str = ""
    kind: str = "modal_window"            # organ_29 WindowType value
    text: str = ""
    buttons: Sequence[str] = ()           # pre-read captions (optional)
    ctrl: Any = None                      # UIA root of an in-window modal (no hwnd)
    bounds: Tuple[int, int, int, int] = (0, 0, 0, 0)

    @property
    def center(self) -> Tuple[int, int]:
        l, t, r, b = self.bounds
        return (l + r) // 2, (t + b) // 2


@dataclass
class Decision:
    handled: bool
    need_human: bool
    action: str
    tier: str
    x: int = 0
    y: int = 0
    dialog: str = ""
    note: str = ""
    ms: float = 0.0


def _norm(s: str) -> str:
    return re.sub(r"[&‎‏]", "", (s or "")).strip().lower()


def _title_of(hwnd: int) -> str:
    return hin.safe_window_text(hwnd)


def control_text(ctrl) -> str:
    """Label of a control across Win32 / Qt / WinUI / WPF / Chromium: Name, else a TextControl child, else help text,
    AutomationId, ValuePattern."""
    if not ctrl:
        return ""
    try:
        name = (getattr(ctrl, "Name", "") or "").strip()
        if name:
            return name
        try:
            for ch in getattr(ctrl, "GetChildren", lambda: [])():
                if getattr(ch, "ControlTypeName", "") == "TextControl":
                    cname = (getattr(ch, "Name", "") or "").strip()
                    if cname:
                        return cname
        except Exception:
            pass
        for attr in ("HelpText", "AutomationId"):
            v = (getattr(ctrl, attr, "") or "").strip()
            if v:
                return v
        try:
            vp = ctrl.GetValuePattern()
            if vp and hasattr(vp, "Value"):
                return (vp.Value or "").strip()
        except Exception:
            pass
    except Exception:
        pass
    return ""


# --------------------------------------------------------------------------------------------- inspection (T1 input)
def _inspect_root(root, info: DialogInfo, deep: bool) -> DialogInfo:
    try:
        is_picker = _norm(info.title) in _PICKER_TITLES
        if is_picker or not deep:
            # Only the confirm/cancel buttons matter for a picker: find them by stable ids.
            for aid in ("1", "2"):
                try:
                    b = root.ButtonControl(AutomationId=aid, searchDepth=8)
                    if b.Exists(0.4, 0.05):
                        info.buttons.append((b.Name or "", aid, b))
                except Exception:
                    pass
            return info
        nodes = 0
        stack = [(root, 0)]
        while stack and nodes < 300:
            c, d = stack.pop()
            nodes += 1
            try:
                t = c.ControlTypeName or ""
                nm = (c.Name or "").strip()
                if t == "TextControl" and nm and nm not in info.texts:
                    info.texts.append(nm)
                elif t in ("ButtonControl", "HyperlinkControl"):
                    info.buttons.append((control_text(c) or nm, str(getattr(c, "AutomationId", "") or ""), c))
                elif t in ("CustomControl", "PaneControl", "ImageControl"):
                    # web banners / XAML flyouts expose their buttons as invokable custom controls
                    try:
                        if c.GetInvokePattern() is not None and (control_text(c) or "").strip():
                            info.buttons.append((control_text(c), str(getattr(c, "AutomationId", "") or ""), c))
                    except Exception:
                        pass
                if d < 7:
                    for ch in reversed(c.GetChildren()):
                        stack.append((ch, d + 1))
            except Exception:
                continue
    except Exception as exc:  # noqa: BLE001
        logger.debug("[popup] inspect failed: %s", exc)
    return info


class _NativeButton:
    """A classic Win32 push button shaped like the UIA control the rest of this module handles, so choose_button and
    _deliver treat both alike. Its press is a POSTED BM_CLICK (no pointer, no keyboard, no focus change)."""
    native = True

    def __init__(self, hwnd: int, caption: str, ctrl_id: int):
        self.hwnd, self.Name, self.AutomationId, self.NativeWindowHandle = hwnd, caption, str(ctrl_id), hwnd

    @property
    def BoundingRectangle(self):
        r = hin.wt.RECT()
        hin._u32.GetWindowRect(self.hwnd, hin.ctypes.byref(r))
        return r

    def GetInvokePattern(self):
        return self

    def Invoke(self):
        ok, note = hin.post_button_click(self.hwnd)
        if not ok:
            raise RuntimeError(note)


def _inspect_native(info: DialogInfo) -> bool:
    """Fill ``info`` from the dialog's own Win32 children (see hin.native_dialog_parts). True when at least one push
    button was read - i.e. this IS a classic dialog and nothing more has to be asked of UI Automation."""
    buttons, texts = hin.native_dialog_parts(info.hwnd)
    if not buttons:
        return False
    info.texts.extend(t for t in texts if t not in info.texts)
    info.buttons.extend((cap, str(cid), _NativeButton(h, cap, cid)) for h, cap, cid in buttons)
    return True


def inspect_dialog(hwnd: int, deep: bool = True) -> DialogInfo:
    """Read what the dialog SAYS, bounded. A classic Win32 dialog (#32770 message box) is read from its own child
    windows - milliseconds and independent of machine load; everything else (WinUI, WPF, Qt, web banners) through UI
    Automation, which is also the fallback when a classic dialog turns out to hold no push buttons (a common-dialog
    picker draws its list in a DirectUI host). Pickers skip the deep walk (hundreds of cells)."""
    info = DialogInfo(hwnd=hwnd, title=_title_of(hwnd), class_name=hin._class_name(hwnd))
    if (info.class_name == "#32770" and _norm(info.title) not in _PICKER_TITLES
            and hin.is_alive(hwnd) and _inspect_native(info)):
        return info
    if auto is None:
        return info
    try:
        root = auto.ControlFromHandle(hwnd)
        if root is None:
            return info
        return _inspect_root(root, info, deep)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[popup] inspect failed: %s", exc)
    return info


def inspect_view(view: PopupView, deep: bool = True) -> DialogInfo:
    if view.ctrl is not None and auto is not None:
        info = DialogInfo(hwnd=view.hwnd, title=view.title, class_name=view.class_name)
        return _inspect_root(view.ctrl, info, deep)
    if view.hwnd and hin.is_alive(view.hwnd):
        return inspect_dialog(view.hwnd, deep)
    return DialogInfo(hwnd=view.hwnd, title=view.title, class_name=view.class_name,
                      texts=[view.text] if view.text else [])


def classify(info: DialogInfo, kind: str = "") -> str:
    title = _norm(info.title)
    blob = _norm(info.title + " " + info.message)
    cues = _STRICT_ELEVATION if kind in _BENIGN_KINDS else _PERMISSION_CUES
    if _KIND_CATEGORY.get(kind) == "permission" or any(c in blob for c in cues):
        return "permission"
    if any(c in blob for c in _OVERWRITE_CUES):
        return "overwrite_confirm"
    if title in _PICKER_TITLES or any(title.startswith(p + " ") for p in ("save as", "open", "browse")):
        return "file_picker"
    if any(c in blob for c in _SAVE_CHANGES_CUES):
        return "save_changes"
    if kind in _KIND_CATEGORY:
        return _KIND_CATEGORY[kind]
    if any(c in blob for c in _COOKIE_CUES):
        return "cookie_consent"
    if any(c in blob for c in BROWSER_PROMPT_KEYWORDS):
        return "browser_prompt"
    if any(c in blob for c in _ERROR_CUES):
        return "error"
    if any(c in blob for c in _INFO_CUES):
        return "info"
    return "unknown"


def _button_role(name: str, aid: str) -> str:
    n = _norm(name)
    for role, words in _ROLE_WORDS.items():
        if n in words:
            return role
    return _ID_ROLE.get(aid, "")


def choose_button(info: DialogInfo, roles: Sequence[str]):
    """First available button whose ROLE (caption or standard control id) matches the preference."""
    by_role: Dict[str, Tuple[str, str, object]] = {}
    for name, aid, ctrl in info.buttons:
        r = _button_role(name, aid)
        if r and r not in by_role:
            by_role[r] = (name, aid, ctrl)
        if aid in _ID_ROLE and _ID_ROLE[aid] not in by_role:
            by_role[_ID_ROLE[aid]] = (name, aid, ctrl)
    for role in roles:
        if role in by_role:
            return role, by_role[role]
    return None, None


def _deliver(button) -> Tuple[bool, str]:
    name, aid, ctrl = button
    if ctrl is None:
        return False, "no-control"
    try:
        ctrl.GetInvokePattern().Invoke()
        return True, "bm-click" if getattr(ctrl, "native", False) else "uia-invoke"
    except Exception:
        pass
    try:
        r = ctrl.BoundingRectangle
        h = int(getattr(ctrl, "NativeWindowHandle", 0) or 0)
        if h:
            ok, note = hin.post_click(hin._u32.GetAncestor(h, 2) or h, (r.left + r.right) // 2,
                                      (r.top + r.bottom) // 2)
            return ok, note
    except Exception:
        pass
    return False, "undeliverable"


# --------------------------------------------------------------------------------------------- fingerprint, cache
def button_labels(view: PopupView) -> List[str]:
    """Cheap, bounded read of the popup's button captions (for the fingerprint)."""
    if view.buttons:
        return sorted(str(b).strip().lower() for b in view.buttons if str(b).strip())
    if view.hwnd and view.ctrl is None and hin.is_alive(view.hwnd):
        native, _texts = hin.native_dialog_parts(view.hwnd)         # classic dialog: no UIA walk needed
        if native:
            return sorted({_norm(cap) for _h, cap, _i in native})
    if auto is None:
        return []
    try:
        root = view.ctrl
        if root is None and view.hwnd and hin.is_alive(view.hwnd):
            root = auto.ControlFromHandle(view.hwnd)
        if root is None:
            return []
        labels = []
        for ctrl, _d in auto.WalkControl(root, includeTop=False, maxDepth=6):
            if (ctrl.ControlTypeName or "") == "ButtonControl":
                t = control_text(ctrl).strip().lower()
                if t:
                    labels.append(t)
            if len(labels) >= 12:
                break
        return sorted(set(labels))
    except Exception:
        return []


def fingerprint(view: PopupView, buttons: Optional[List[str]] = None) -> str:
    """class + kind + normalised title + button set -> stable across dynamic titles."""
    key = "|".join([(view.class_name or "").lower(), view.kind, normalize_title(view.title),
                    ",".join(button_labels(view) if buttons is None else buttons)])
    return hashlib.md5(key.encode("utf-8")).hexdigest()


_DEFAULT_DB = None


def _default_db():
    global _DEFAULT_DB
    if _DEFAULT_DB is None:
        try:
            from core_organs.database_manager import DatabaseManager
            _DEFAULT_DB = DatabaseManager()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[popup] no pathway database: %s", exc)
            _DEFAULT_DB = False
    return _DEFAULT_DB or None


def _inside_window(hwnd: int, x: int, y: int) -> bool:
    r = hin.wt.RECT()
    hin._u32.GetWindowRect(hwnd, hin.ctypes.byref(r))
    return r.left <= x <= r.right and r.top <= y <= r.bottom


def _closed_after_key(hwnd: int, wait_s: float = 0.5) -> bool:
    """True when the popup's window is gone (or hidden) within ``wait_s`` of a delivered key. A popup with no window
    handle to watch (an in-window modal) cannot be checked here and counts as closed - its caller verifies."""
    if not hwnd:
        return True
    end = time.perf_counter() + wait_s
    while True:
        if not hin.is_alive(hwnd) or not hin._u32.IsWindowVisible(hwnd):
            return True
        if time.perf_counter() >= end:
            return False
        time.sleep(0.05)


def log_pathway(db, view: PopupView, x: int, y: int, action: str, parent_path: str,
                labels: Optional[List[str]] = None) -> None:
    if db is None:
        return
    try:
        db.log_new_pathway(layout_hash=db.generate_layout_hash(view.title), element_name=view.title,
                           x=x, y=y, action_type=action, parent_path=parent_path, fingerprint=fingerprint(view, labels))
    except Exception:
        pass


def _default_key_sender(action: str, hwnd: int = 0) -> bool:
    """Deliver 'key:escape' / 'key:enter' to the popup's own window as posted messages (never the physical keyboard)."""
    if not action or not action.startswith("key:") or not hwnd:
        return False
    key = action.split(":", 1)[1].strip().lower()
    try:
        ok, note = hin.post_key_combo(hwnd, key)
        time.sleep(0.08)
        if not ok:
            logger.warning("[popup] key intent '%s' undeliverable: %s", key, note)
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.debug("[popup] key intent '%s' failed: %s", key, exc)
        return False


# --------------------------------------------------------------------------------------------- T2.5 lexical
def lexical_intent(view: PopupView) -> Optional[Tuple[str, bool]]:
    """Data-driven intent classifier over popup text / class / kind. Returns (action, need_human) or None when the
    popup is genuinely ambiguous (only then do we pay for T3). It NEVER auto-accepts elevation / credential or
    destructive-commit prompts - those escalate to a human."""
    blob = " ".join(filter(None, [view.title or "", view.text or "", view.class_name or ""])).lower()
    kind = view.kind
    if kind == "authentication" or _has(blob, _STRICT_ELEVATION if kind in _BENIGN_KINDS else ELEVATION_KEYWORDS):
        return "key:escape", True
    if _has(blob, DESTRUCTIVE_COMMIT_KEYWORDS):
        return "key:escape", True
    if kind == "crash_reporter" or _has(blob, CRASH_KEYWORDS):
        return "key:escape", False
    if kind in ("cookie_banner", "browser_prompt") or _has(blob, COOKIE_CONSENT_KEYWORDS) \
            or _has(blob, BROWSER_PROMPT_KEYWORDS):
        return "key:escape", False
    if kind in ("message_box", "notification"):
        return "key:enter", False
    return None


# --------------------------------------------------------------------------------------------- T3 gatekeeper
_T3_STATE = {"down_until": 0.0, "fails": 0, "last_ms": 0.0}


def tier3_available() -> bool:
    return time.time() >= _T3_STATE["down_until"]


def _gatekeeper_listening(timeout_s: float = 0.15) -> bool:
    """Is anything accepting connections on the gatekeeper port? MEASURED on this host: a connect to a CLOSED local
    port does not fail fast on Windows - it takes ~2.0 s to come back 'refused' - so every unseen popup used to pay
    2 s before even reaching the safe fallback. A live local service answers a SYN in about a millisecond; if nothing
    answers inside ``timeout_s`` it is not there."""
    import socket
    from urllib.parse import urlparse
    u = urlparse(GATEKEEPER_URL)
    try:
        socket.create_connection((u.hostname or "127.0.0.1", u.port or 80), timeout=timeout_s).close()
        return True
    except Exception:
        return False


def reset_tier3_breaker() -> None:
    _T3_STATE.update(down_until=0.0, fails=0)


def prewarm_gatekeeper() -> None:
    """1-token ping so the first REAL Tier-3 query is not a cold model load. Bounded by the Tier-3 cap; silent on failure."""
    try:
        payload = {"model": "llama3", "stream": False, "messages": [{"role": "user", "content": "ping"}],
                   "options": {"num_predict": 1}}
        req = urllib.request.Request(GATEKEEPER_URL, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json",
                                              "X-Hojaiga-Validation": GATEKEEPER_SECRET}, method="POST")
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=GATEKEEPER_TIER3_TIMEOUT_S) as resp:
            resp.read(64)
        logger.info("[popup] gatekeeper pre-warmed in %.2fs", time.perf_counter() - t0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[popup] gatekeeper pre-warm skipped: %s", exc)


def _tier3(view: PopupView, timeout_s: float, llm: Optional[Callable[..., Dict[str, Any]]] = None
           ) -> Optional[Tuple[int, int, str]]:
    """(x, y, action) from the local gatekeeper, or None (timeout / error / unusable answer). A failure trips the
    breaker so later cold popups do not each wait the cap again."""
    cx, cy = view.center
    system_instructions = (
        "You are a universal Windows desktop and web application popup solver. "
        "Analyze the popup/modal data and output STRICTLY valid JSON with keys: action, target_x, target_y.")
    user_prompt = (
        f"Window Title: '{view.title}'\nClass: '{view.class_name}'\nType: '{view.kind}'\n"
        f"Discovered Content: '{view.text}'\nBounds Center: ({cx}, {cy})\n"
        "Provide the safest coordinates and action to dismiss or proceed past this blocking barrier.")
    t0 = time.perf_counter()
    if llm is None and not _gatekeeper_listening():
        _T3_STATE["last_ms"] = (time.perf_counter() - t0) * 1000
        _T3_STATE["fails"] += 1
        _T3_STATE["down_until"] = time.time() + min(T3_BREAKER_S, 15.0)     # short: a gatekeeper started soon is noticed
        logger.info("[popup] gatekeeper not listening (probed in %.0f ms); T3 skipped for %.0fs, safe Escape used",
                    _T3_STATE["last_ms"], min(T3_BREAKER_S, 15.0))
        return None
    try:
        if llm is not None:
            decision = llm(view=view, system=system_instructions, user=user_prompt, timeout_s=timeout_s)
        else:
            payload = {"model": "llama3", "stream": False,
                       "messages": [{"role": "system", "content": system_instructions},
                                    {"role": "user", "content": user_prompt}]}
            req = urllib.request.Request(GATEKEEPER_URL, data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json",
                                                  "X-Hojaiga-Validation": GATEKEEPER_SECRET}, method="POST")
            with urllib.request.urlopen(req, timeout=timeout_s) as response:
                res_data = json.loads(response.read().decode("utf-8"))
            content = res_data.get("message", {}).get("content", "")
            m = re.search(r"\{.*\}", content, re.DOTALL)
            decision = json.loads(m.group(0)) if m else None
        _T3_STATE["last_ms"] = (time.perf_counter() - t0) * 1000
        if decision:
            _T3_STATE["fails"] = 0
            return (int(decision.get("target_x", cx)), int(decision.get("target_y", cy)),
                    str(decision.get("action", "click")))
        raise ValueError("no usable decision in the answer")
    except Exception as exc:  # noqa: BLE001
        _T3_STATE["last_ms"] = (time.perf_counter() - t0) * 1000
        _T3_STATE["fails"] += 1
        _T3_STATE["down_until"] = time.time() + T3_BREAKER_S
        logger.error("[popup] gatekeeper failed/timed-out after %.2fs (cap %.1fs): %s - breaker open for %.0fs, falling "
                     "through to the safe Escape", _T3_STATE["last_ms"] / 1000, timeout_s, exc, T3_BREAKER_S)
        return None


# --------------------------------------------------------------------------------------------- gate / cancel-only
def cancel_only(view: PopupView, key_sender: Callable[[str, int], bool]) -> Decision:
    """Probe-time dismissal: Escape -> IDCANCEL -> WM_CLOSE, verified gone. Never accepts a change, never queries the
    LLM, never writes the pathway cache (a cached 'escape' for this title would later cancel the very dialog a real
    task needs)."""
    h = view.hwnd
    cx, cy = view.center
    if not h:
        return Decision(False, False, "cancel_only_no_handle", "gate", cx, cy, view.title)
    steps = (lambda: key_sender("key:escape", h),
             lambda: hin._u32.PostMessageW(h, 0x0111, 2, 0),        # WM_COMMAND IDCANCEL
             lambda: hin._u32.PostMessageW(h, 0x0010, 0, 0))        # WM_CLOSE
    for i, fire in enumerate(steps):
        try:
            fire()
        except Exception:
            continue
        time.sleep(0.12)
        if not hin.is_alive(h) or not hin._u32.IsWindowVisible(h):
            logger.info("[popup] probe-mode cancel-only closed '%s' (rung %d)", view.title, i + 1)
            return Decision(True, False, "cancel_only", "gate", cx, cy, view.title)
    return Decision(False, False, "cancel_only_failed", "gate", cx, cy, view.title)


# --------------------------------------------------------------------------------------------- THE engine
def resolve_view(view: PopupView, *, db=None, key_sender: Optional[Callable[[str, int], bool]] = None,
                 mode: Optional[str] = None, task_paths: Sequence[str] = (), allow_destructive: Optional[bool] = None,
                 llm: Optional[Callable[..., Dict[str, Any]]] = None, budget_s: Optional[float] = None) -> Decision:
    """Resolve ONE popup through the whole ladder (see the module docstring). Dependencies are injected per call
    (`db`, `key_sender`, `llm`) so organ_29's instance state - and a test's stand-ins - are honoured."""
    t_start = time.perf_counter()
    budget = POPUP_BUDGET_S if budget_s is None else budget_s
    mode = mode or TASK.mode
    paths = [p.lower() for p in (task_paths or TASK.paths) if p]
    allow_destructive = TASK.allow_destructive if allow_destructive is None else allow_destructive
    key_sender = key_sender or _default_key_sender
    if db is None:
        db = _default_db()
    cx, cy = view.center

    def done(handled, need_human, action, tier, x=None, y=None, note="", dialog=None) -> Decision:
        d = Decision(handled, need_human, action, tier, cx if x is None else x, cy if y is None else y,
                     dialog or view.title, note, round((time.perf_counter() - t_start) * 1000, 1))
        logger.info("[popup] '%s' -> %s via %s in %.0f ms", view.title[:40], action, tier, d.ms)
        return d

    # ---- gate: expected popups are left alone; probe-mode popups are cancel-only
    try:
        from core_organs import popup_mode as _pm
        if _pm.is_expected(view.title):
            return done(True, False, "expected_keep", "gate", note="popup the running step expects")
        if _pm.current_policy() == "probe":
            c = cancel_only(view, key_sender)
            c.ms = round((time.perf_counter() - t_start) * 1000, 1)
            return c
    except Exception as exc:  # noqa: BLE001
        logger.debug("[popup] popup_mode unavailable: %s", exc)

    # ---- T1: read the popup's own words and buttons (escalation is decided on that reading, before any button)
    info = inspect_view(view)
    info.category = classify(info, view.kind)
    lex_blob = " ".join([view.title or "", view.text or "", info.message]).lower()
    brief = info.brief()
    cat = info.category

    elev_words = _STRICT_ELEVATION if view.kind in _BENIGN_KINDS else ELEVATION_KEYWORDS
    if cat == "permission" or view.kind == "authentication" or _has(lex_blob, elev_words):
        return done(False, True, "need_human", "escalate", note="elevation/credential prompt: never auto-accepted", dialog=brief)

    if cat == "file_picker" and mode == "inflight" and paths:
        return done(False, False, "owned-by-task", "escalate", note="task names a path; file-dialog rung drives it", dialog=brief)

    if cat == "overwrite_confirm":
        names = [p.replace("/", "\\").rsplit("\\", 1)[-1] for p in paths]
        ours = any(n and n in _norm(info.message) for n in names)
        if ours and allow_destructive:
            role, btn = choose_button(info, ("yes",))
            if btn:
                ok, how = _deliver(btn)
                return done(ok, False, f"yes({how})", "T1", note="explicitly authorised overwrite of the task's own file", dialog=brief)
        if mode == "inflight" and ours:
            return done(False, True, "need_human", "escalate",
                        note="task's own target already exists: overwrite needs explicit allow_destructive", dialog=brief)
        # Not ours / not authorised: the non-destructive answer is 'No' (nothing is replaced).

    role, btn = choose_button(info, POLICY.get(cat, POLICY["unknown"]))
    # A dialog that has only just appeared may not have rendered yet (UIA then shows only the title bar's Close).
    # Re-read, bounded, ONLY while its tree is still empty; one that has content but no safe button goes straight on.
    unrendered = lambda i: (not i.texts) and len([b for b in i.buttons if _norm(b[0]) not in ("close", "")]) == 0
    if btn is None and (view.hwnd and hin.is_alive(view.hwnd)) and unrendered(info):
        end = time.perf_counter() + min(UNRENDERED_REREAD_S, max(0.0, budget - (time.perf_counter() - t_start)))
        while btn is None and time.perf_counter() < end:
            time.sleep(0.4)
            info = inspect_view(view)
            info.category = classify(info, view.kind)
            cat, brief = info.category, info.brief()
            lex_blob = " ".join([view.title or "", view.text or "", info.message]).lower()
            if cat == "permission" or _has(lex_blob, elev_words):
                return done(False, True, "need_human", "escalate", note="elevation/credential prompt: never auto-accepted", dialog=brief)
            role, btn = choose_button(info, POLICY.get(cat, POLICY["unknown"]))
            if not unrendered(info):
                break
    if btn is not None:
        ok, how = _deliver(btn)
        if ok:
            try:
                r = btn[2].BoundingRectangle
                bx, by = (r.left + r.right) // 2, (r.top + r.bottom) // 2
            except Exception:
                bx, by = cx, cy
            return done(True, False, f"{role}({how})", "T1", bx, by, dialog=brief)
        logger.debug("[popup] T1 button '%s' undeliverable (%s); falling through", btn[0], how)

    # ---- T2: pathway cache - exact title, then the class + button fingerprint
    labels = button_labels(view)                    # ONE reading feeds both the lookup and every later log
    fp = fingerprint(view, labels)
    cached = None
    if db is not None:
        try:
            cached = db.check_popup_history(view.title)
            if not cached:
                cached = db.check_popup_fingerprint(fp)
                if cached:
                    logger.info("[popup] T2 FINGERPRINT cache hit for '%s'", view.title)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[popup] cache lookup failed: %s", exc)
    if cached:
        action = cached.get("action", "click")
        tx, ty = int(cached.get("x", cx)), int(cached.get("y", cy))
        if action.startswith("key:"):
            ok = key_sender(action, view.hwnd)
            if ok:
                return done(True, False, action, "T2", tx or cx, ty or cy)
        elif tx > 0 and ty > 0 and view.hwnd and hin.is_alive(view.hwnd) and _inside_window(view.hwnd, tx, ty):
            # A remembered click point is only replayed when it still falls INSIDE this popup's window; a stale point
            # from another session would otherwise click whatever is under it now.
            ok, _note = hin.post_click(view.hwnd, tx, ty)
            if ok:
                return done(True, False, action, "T2", tx, ty)
        logger.info("[popup] T2 cached action '%s' is not deliverable for '%s'; continuing down the ladder", action, view.title)

    # ---- T2.5: lexical intent (no LLM, no coordinates)
    lex = lexical_intent(PopupView(view.hwnd, view.title, view.class_name, view.kind,
                                   (view.text + " " + info.message).strip(), view.buttons, view.ctrl, view.bounds))
    if lex is not None:
        lex_action, lex_need_human = lex
        if lex_need_human:
            logger.warning("[popup] T2.5 lexical => ELEVATION/DESTRUCTIVE prompt '%s'; escalating to a human "
                           "(no keystroke).", view.title)
            return done(False, True, "need_human", "T2.5", note="elevation / destructive-commit prompt", dialog=brief)
        fired = key_sender(lex_action, view.hwnd)
        if fired and _closed_after_key(view.hwnd):          # a pathway is learned only from an answer that WORKED
            log_pathway(db, view, 0, 0, lex_action, "popup_policy_t2_5_lexical", labels)
        elif fired:
            logger.info("[popup] T2.5 %s delivered to '%s' but it stayed open: not cached", lex_action, view.title)
        return done(fired, False, lex_action, "T2.5")

    # ---- T3: gatekeeper (capped by the shared budget, guarded by the breaker)
    remaining = budget - (time.perf_counter() - t_start)
    if tier3_available() and remaining >= 0.3:
        got = _tier3(view, min(GATEKEEPER_TIER3_TIMEOUT_S, remaining), llm)
        if got is not None:
            tx, ty, action = got
            if tx > 0 and ty > 0 and view.hwnd:
                hin.post_click(view.hwnd, tx, ty)
            log_pathway(db, view, tx, ty, action, "popup_policy_gatekeeper", labels)
            return done(True, False, action, "T3", tx, ty)
    elif not tier3_available():
        logger.info("[popup] T3 skipped: gatekeeper circuit breaker is open")

    # ---- T4: safe Escape, cached so a repeat is a T2 hit
    if key_sender("key:escape", view.hwnd):
        if _closed_after_key(view.hwnd):
            log_pathway(db, view, 0, 0, "key:escape", "popup_policy_t4_escape_cached", labels)
            return done(True, False, "escape_fallback", "T4")
        # Escape was delivered and IGNORED (a Yes/No box has no Cancel to map it to): caching it would replay a dead
        # answer on every repeat, so it is not learned and the caller sees the popup still open.
        logger.info("[popup] T4 Escape delivered to '%s' but it stayed open: not cached", view.title)
        return done(True, False, "escape_fallback", "T4", note="Escape delivered; the popup stayed open")
    logger.warning("[popup] T4 escape undeliverable for '%s' (no window handle)", view.title)
    return done(False, False, "dismiss", "T4", note="no safe, deliverable answer")


# --------------------------------------------------------------------------------------------- loop-facing API
def resolve_dialog(hwnd: int, *, mode: str = "inflight", task_paths: Sequence[str] = (),
                   allow_destructive: bool = False, **kw) -> Resolution:
    """Handle ONE dialog window through the unified ladder. mode='preflight' = stale cleanup before a run (pickers are
    cancelled); mode='inflight' = a picker the task itself needs (goal names a path) is left to the file-dialog rung."""
    view = PopupView(hwnd=hwnd, title=_title_of(hwnd), class_name=hin._class_name(hwnd))
    d = resolve_view(view, mode=mode, task_paths=task_paths, allow_destructive=allow_destructive, **kw)
    return Resolution(d.handled, d.need_human, d.action, d.dialog, d.note)


def blocking_dialogs(root_hwnd: int, exclude: Sequence[int] = ()) -> List[int]:
    """Visible dialog windows owned by the target's process (#32770 and friends), topmost first."""
    out = []
    skip = set(exclude)
    for h in hin.process_windows(root_hwnd, include_hidden=False):
        if h == root_hwnd or h in skip:
            continue
        if hin._class_name(h) == "#32770":
            out.append(h)
    return out


def clear_blockers(root_hwnd: int, *, mode: str = "inflight", task_paths: Sequence[str] = (),
                   allow_destructive: bool = False, max_rounds: int = 6,
                   exclude: Sequence[int] = ()) -> Dict[str, object]:
    """Unwind stacked dialogs top-down. Returns {handled:[...], need_human:bool, left:[...]}"""
    handled: List[str] = []
    need_human = False
    left: List[str] = []
    seen_stuck: Dict[int, int] = {}
    for _ in range(max_rounds):
        dialogs = blocking_dialogs(root_hwnd, exclude)
        if not dialogs:
            break
        progressed = False
        for hwnd in dialogs:
            if seen_stuck.get(hwnd, 0) >= 2:
                continue
            res = resolve_dialog(hwnd, mode=mode, task_paths=task_paths, allow_destructive=allow_destructive)
            if res.need_human:
                need_human = True
                handled.append(f"HUMAN:{res.dialog} ({res.note})")
                seen_stuck[hwnd] = 9
                continue
            if res.action == "owned-by-task":
                seen_stuck[hwnd] = 9
                continue
            gone = False
            end = time.time() + 1.6          # bounded wait for the dialog to actually close
            while time.time() < end:
                time.sleep(0.12)
                if not hin.is_alive(hwnd) or not hin._u32.IsWindowVisible(hwnd):
                    gone = True
                    break
            handled.append(f"{res.action}:{res.dialog}" + ("" if gone else " [still open]"))
            if gone:
                progressed = True
            else:
                seen_stuck[hwnd] = seen_stuck.get(hwnd, 0) + 1
        if not progressed:
            break
    left = [_title_of(h) for h in blocking_dialogs(root_hwnd, exclude) if seen_stuck.get(h, 0) < 9]
    return {"handled": handled, "need_human": need_human, "left": left}
