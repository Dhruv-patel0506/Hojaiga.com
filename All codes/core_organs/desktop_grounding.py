"""
desktop_grounding.py — General Desktop Autonomy Loop (Workstreams 1-5 of the
Desktop Autonomy & Robustness Master Plan).

One closed loop that makes ANY desktop app operable without per-app hardcoding:

    perceive (tiered grounding ladder)
      -> decide (constrained forced-choice judge, never open-ended ReAct)
      -> act (UIA patterns first, PostMessage second, physical input last)
      -> verify (structural + filesystem + pixel-delta postconditions)
      -> recover (retry ladder, popup triage, native file picker)
      -> checkpoint (resumable state) and learn (recipe distillation to organ_04)

Design rules:
- No per-app branches. Everything is data-driven from the live UI tree.
- Every tier degrades gracefully and REPORTS which tiers ran, so tests and
  users always know the real capability state of the machine (e.g. vision
  tier is skipped when torch is not installed — never silently faked).
- Never destroys user data: destructive element names require a checkpoint
  snapshot of the affected file or an explicit allow_destructive opt-in (HITL).

Dependency pins (do NOT "upgrade to fix" -- verified with `pip check`):
- transformers==4.51.3  (Florence-2 in OmniParser breaks on 5.x; organ_13 voice
  path and timm/tokenizers were import-swept against this pin)
- pydantic-settings==2.15.0: `pip check` reports crewai-cli wanting ~=2.10.1, but litellm needs
  >=2.14.1 -- mutually unsatisfiable; 2.15.0 is the working side (crewai imports/runs fine).
  Do NOT downgrade to 'fix' pip check: it breaks litellm.
- torch CPU wheels; easyocr is imported lazily and its model download is
  triggered once by DesktopGrounding.warmup_vision().
"""

import os
import re
import json
import time
import uuid
import ctypes
import hashlib
import logging
import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.desktop_grounding")

from core_organs import headless_input as hin  # the ONLY input-delivery layer (no physical input)

_IS_WINDOWS = os.name == "nt"

# ---------------------------------------------------------------------------
# Environment-derived capability flags (probed once, never assumed)
# ---------------------------------------------------------------------------

def _module_available(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False

HAS_UIA = _module_available("uiautomation")
HAS_PIL = _module_available("PIL")
HAS_PYTESSERACT = _module_available("pytesseract")
HAS_TORCH = _module_available("torch")

OMNI_LOCAL_REPO = r"D:\new_automation\OmniParser"

# Vision (OmniParser) is far slower than UIA on CPU, so it is budgeted per goal
# and cached per window pixel-signature. Both are env-tunable.
VISION_MAX_CALLS = int(os.environ.get("HOJAIGA_VISION_MAX_CALLS", "2"))
VISION_CACHE_TTL_S = float(os.environ.get("HOJAIGA_VISION_CACHE_TTL_S", "2.0"))

# Actionable control type families (generic UIA roles — not app specific).
ACTIONABLE_ROLES = {
    "button", "edit", "combobox", "dropdownbutton", "splitbutton", "menuitem",
    "checkbox", "radiobutton", "tabitem", "listitem", "treeitem", "hyperlink",
    "slider", "spinner", "group", "pane", "document", "thumb",
    "datagrid", "table", "dataitem",
}
# Roles accepted even with an EMPTY Name. A spreadsheet's document grid is a custom UIA control whose Name is empty
# (or a generic 'Grid'); it is recognised by what it IS (DataGrid / Table), not by what it is called.
UNNAMED_OK_ROLES = ("edit", "pane", "datagrid", "table")
# A grid exposes every cell as a DataItem (Excel: ~500 on the first screen). They are sampled, not enumerated, so
# they cannot crowd the real controls out of the judge's shortlist; the totals are reported (never silently cut).
GRID_CELL_CAP = int(os.environ.get("HOJAIGA_GRID_CELL_CAP", "120"))

# Verbs the constrained judge is allowed to choose. Keeping this tiny is what
# stops the 7B model from hallucinating tool calls (the old flailing failure).
LEGAL_VERBS = ("click", "type", "key", "invoke", "scroll", "wait", "done")

# A learned shortcut this confident is executed directly, skipping the LLM
# judge entirely — this is the "pro muscle memory" path (Ctrl+S to save, etc.).
PRO_SHORTCUT_CONF = float(os.environ.get("HOJAIGA_PRO_SHORTCUT_CONF", "0.70"))

# Destructive patterns are generic word cues, not per-app hardcodes.
DESTRUCTIVE_CUES = ("delete", "remove", "format", "overwrite", "discard", "erase")

BRAINS_CHAT_URL = os.environ.get("HOJAIGA_BRAIN_URL", "http://127.0.0.1:11434/api/chat")
JUDGE_MODEL = os.environ.get("HOJAIGA_JUDGE_MODEL", "qwen2.5:7b")
JUDGE_TIMEOUT_S = float(os.environ.get("HOJAIGA_JUDGE_TIMEOUT_S", "12"))
MAX_JUDGE_ELEMENTS = 8
INVALID_CHOICE_LIMIT = 3
CHECKPOINT_DIR = os.path.join(os.environ.get("TEMP", "."), "hojaiga_desktop_checkpoints")

# Readiness backoff: heavy apps (Blender, Office, Electron) show a splash and
# expose controls seconds after the window first appears. Poll the live tree
# with growing waits so the loop never mistakes 'still booting' for 'wrong
# state'. Bounded so a genuinely broken app still escalates to HITL promptly.
READY_TIMEOUT_S = float(os.environ.get("HOJAIGA_READY_TIMEOUT_S", "10"))
READY_BACKOFF_S = float(os.environ.get("HOJAIGA_READY_BACKOFF_S", "0.35"))
READY_BACKOFF_MAX_S = float(os.environ.get("HOJAIGA_READY_BACKOFF_MAX_S", "1.5"))
# The 10 s above is the deadline for an app that shows NO sign of starting. While the app visibly IS starting
# (its window set changes - splash -> login -> main frame - or its processes keep burning CPU) the deadline is
# pushed out by READY_GRACE_S at a time, never past READY_HARD_CAP_S. Measured on this host: Steam shows a 199x34
# update splash for ~39 s, then a login window from a DIFFERENT process 12 s later; a flat 10 s gave up on it.
READY_GRACE_S = float(os.environ.get("HOJAIGA_READY_GRACE_S", "12"))
READY_HARD_CAP_S = float(os.environ.get("HOJAIGA_READY_HARD_CAP_S", "90"))
READY_RICH_ELEMENTS = 8        # a window with this many controls is a real UI, not a splash: no stability poll needed


# ---------------------------------------------------------------------------
# Unified grounding contract (same mental model as the web side)
# ---------------------------------------------------------------------------

@dataclass
class GroundedElement:
    id: str                       # stable-ish per-tree hash
    name: str                     # visible label / UIA name / OCR text
    role: str                     # button | edit | menuitem | ...
    bbox: Tuple[int, int, int, int]
    tier: str                     # "uia" | "win32" | "ocr" | "vision"
    confidence: float = 0.9
    hwnd: int = 0
    automation_id: str = ""
    value: str = ""
    enabled: bool = True

    @property
    def center(self) -> Tuple[int, int]:
        return ((self.bbox[0] + self.bbox[2]) // 2, (self.bbox[1] + self.bbox[3]) // 2)

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "role": self.role,
                "bbox": list(self.bbox), "tier": self.tier,
                "confidence": round(self.confidence, 3),
                "center": list(self.center)}


def _is_parked_offscreen(hwnd: int) -> bool:
    """True for a window that background_window has moved fully off every monitor (its parked rectangle sits at
    the park origin, far outside any real screen)."""
    if not (_IS_WINDOWS and hwnd):
        return False
    try:
        import ctypes.wintypes as wt
        r = wt.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
        return r.right <= -10000 and r.bottom <= -10000
    except Exception:
        return False


def _element_id(hwnd: int, role: str, name: str, bbox: Tuple[int, int, int, int]) -> str:
    raw = f"{hwnd}|{role}|{name.strip().lower()}|{bbox}"
    return "el_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


def _get_intel():
    """Lazily reach the app-intelligence organ (W8). Returns None if it is not
    importable — the loop then runs on pure perception, never crashes."""
    try:
        from core_organs.organ_47_app_intelligence import get_intel
        return get_intel()
    except Exception as exc:  # pragma: no cover - environmental
        logger.debug("[intel] organ_47 unavailable: %s", exc)
        return None


def get_dap_core():
    """Lazily reach DAPRuntimeCore from organ_24_dap (Workstream 1 facade)."""
    try:
        from core_organs.organ_24_dap import DAPRuntimeCore
        return DAPRuntimeCore()
    except Exception as exc:
        logger.debug("[dap] organ_24 DAPRuntimeCore unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# W1 — DesktopGrounding: tiered perception ladder
# ---------------------------------------------------------------------------

class DesktopGrounding:
    """Grounds one app window into a unified list of actionable elements.

    Ladder (stops at the first tier that yields confident candidates, unless
    the caller demands a specific target text and earlier tiers missed it):
      Tier 1  UIA tree walk via uiautomation (deep, proven on this host)
      Tier 2  Win32 child enumeration + window text (no deps, always works)
      Tier 3  OCR over a window screenshot (only when pytesseract present)
      Tier 4  OmniParser vision (only when local repo + torch present)
    Every call reports tiers_ran + tiers_skipped so nothing is silently faked.
    """

    def __init__(self):
        self.last_report: Dict[str, Any] = {}
        self.last_walk: Dict[str, Any] = {}
        self._dap = None
        self._vision_calls = 0
        # (hwnd, window-signature) -> (monotonic ts, elements)
        self._vision_cache: Dict[Tuple[int, str], Tuple[float, List[GroundedElement]]] = {}

    def reset_vision_budget(self) -> None:
        """Called at the start of every goal so one goal cannot run OmniParser N times."""
        self._vision_calls = 0

    @property
    def dap_core(self):
        if self._dap is None:
            self._dap = get_dap_core()
        return self._dap

    # ---- window location (dynamic, name-substring based like organ_24) ----
    _BROWSER_PROCS = frozenset({"chrome", "msedge", "firefox", "brave", "opera", "vivaldi",
                                "iexplore", "arc", "chromium"})

    @staticmethod
    def _process_stem(hwnd: int) -> str:
        """Lower-case exe stem of the window's owning process ('' when unreadable)."""
        try:
            import ctypes.wintypes as wt
            k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
            pid = wt.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            k32.OpenProcess.restype = ctypes.c_void_p
            h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(520)
                size = wt.DWORD(520)
                k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wt.DWORD,
                                                           ctypes.c_wchar_p, ctypes.POINTER(wt.DWORD)]
                if k32.QueryFullProcessImageNameW(ctypes.c_void_p(h), 0, buf, ctypes.byref(size)):
                    return os.path.splitext(os.path.basename(buf.value))[0].lower()
            finally:
                k32.CloseHandle(ctypes.c_void_p(h))
        except Exception:
            pass
        return ""

    def find_window(self, app_hint: str, all_candidates: bool = False):
        """Locate the target app window. Ranked, NOT first-substring-wins:

          5  owning process image name matches the hint   (notepad.exe for 'notepad')
          4  window class matches the hint
          3  title is '<hint>' / ends with ' - <hint>' (classic document-window title)
          1  hint merely appears somewhere in the title

        Browser windows are excluded unless the hint itself names a browser: a Chrome/Edge
        tab titled 'Windows Notepad - Search' must never be mistaken for Notepad (a live
        E2E run once typed a haiku into the user's browser because of exactly that).
        """
        user32 = ctypes.windll.user32
        if not _IS_WINDOWS:
            return [] if all_candidates else None
        hint = (app_hint or "").lower().strip()
        token = hint.split()[0] if hint else ""
        hint_is_browser = any(b in hint for b in self._BROWSER_PROCS) or "browser" in hint
        found: List[Tuple[int, int]] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            title = hin.safe_window_text(int(hwnd)).lower()      # never blocks on a window whose thread does not pump messages
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cname = cls_buf.value.lower()
            # Skip infrastructure windows, same spirit as organ_01 filters.
            if cname in ("shell_traywnd", "progman", "workerw", "mintaskswnd",
                         "shell_dock", "topmosttoplevelwindowclass"):
                return True
            # A UWP app's CoreWindow is its content host, not an app window: it cannot be minimized, parked or
            # closed on its own (its ApplicationFrameWindow is the real top level, and UIA on the frame already
            # contains the content). Matching it by PROCESS NAME (CalculatorApp.exe) used to beat the frame, so
            # the loop grounded and tried to park a window that cannot be parked.
            if cname == "windows.ui.core.corewindow":
                return True
            if any(bad in title for bad in ("visual studio", "antigravity", " - editor")):
                return True
            if not token or not (token in title or token in cname or token in self._process_stem_cached(hwnd)):
                return True
            proc = self._process_stem_cached(hwnd)
            if proc in self._BROWSER_PROCS and not hint_is_browser:
                return True
            if token in proc:
                score = 5
            elif token in cname:
                score = 4
            elif title == hint or title.endswith(" - " + hint) or title.startswith(hint + " "):
                score = 3
            else:
                score = 1
            # Skip cloaked (hidden UWP/virtual-desktop) and tiny helper windows; among the
            # rest the largest window of the best-scoring class is the real app frame.
            try:
                import ctypes.wintypes as _wt
                cloaked = ctypes.c_int(0)
                ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    _wt.HWND(hwnd), 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
                if cloaked.value and not hin.is_minimized(hwnd):
                    return True
                rr = _wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rr))
                w, h = rr.right - rr.left, rr.bottom - rr.top
            except Exception:
                w = h = 1000
            if not hin.is_minimized(hwnd) and (w < 120 or h < 80):
                return True  # (minimized windows report a tiny parked rect; they are still real)
            found.append((score * 10_000_000 + w * h, hwnd))
            return True

        self._proc_cache = {}
        try:
            user32.EnumWindows(_cb, 0)
        except Exception as exc:
            logger.debug("[grounding] EnumWindows failed: %s", exc)
            return [] if all_candidates else None
        if not found:
            return [] if all_candidates else None
        found.sort(key=lambda t: -t[0])  # stable: Z-order preserved among equal scores
        if all_candidates:
            return [h for _s, h in found]
        return found[0][1]

    def family_activity(self, app_hint: str) -> Tuple[frozenset, float]:
        """(window-set signature, CPU seconds) of everything that looks like this app. A change in the window
        set (a splash replaced by a login window, a main frame appearing) or CPU still being spent means the
        app is still STARTING; both flat means it is either ready or not starting at all."""
        sig = frozenset((h, self.window_title(h)) for h in self.find_window(app_hint, all_candidates=True))
        cpu = 0.0
        token = (app_hint or "").lower().split()[0] if (app_hint or "").strip() else ""
        if token:
            try:
                import psutil
                for pr in psutil.process_iter(["name", "cpu_times"]):
                    nm = (pr.info.get("name") or "").lower()
                    ct = pr.info.get("cpu_times")
                    if token in nm and ct:
                        cpu += float(ct.user + ct.system)
            except Exception:
                pass
        return sig, cpu

    def _process_stem_cached(self, hwnd: int) -> str:
        cache = getattr(self, "_proc_cache", None)
        if cache is None:
            cache = self._proc_cache = {}
        if hwnd not in cache:
            cache[hwnd] = self._process_stem(hwnd)
        return cache[hwnd]

    def window_title(self, hwnd: int) -> str:
        if not (_IS_WINDOWS and hwnd):
            return ""
        return hin.safe_window_text(int(hwnd))

    # ---- Tier 1: UIA ----
    def _walk_uia(self, root_hwnd: int, max_depth: int = 12, max_nodes: int = 900) -> List[GroundedElement]:
        if not HAS_UIA:
            return []
        import uiautomation as auto
        elements: List[GroundedElement] = []
        try:
            ctrl = auto.ControlFromHandle(root_hwnd)
        except Exception:
            return []
        if ctrl is None:
            return []
        count = 0
        cells_seen = cells_kept = 0
        # A minimized window reports every control as off-screen with bogus (-32000) rects, but
        # its UIA patterns still work. Keep them (addressable by pattern, not by coordinates).
        # A window PARKED off-screen (background_window) behaves the same for UWP/WinUI apps: they do not lay out
        # content that is entirely off every monitor, so their controls report IsOffscreen / empty rectangles
        # while Invoke / Value / Toggle patterns work. Treat it like minimized.
        mini = hin.is_minimized(root_hwnd) or _is_parked_offscreen(root_hwnd)

        def _visit(c, depth: int):
            nonlocal count, cells_seen, cells_kept
            if depth > max_depth or count > max_nodes:
                return
            try:
                role = (c.ControlTypeName or "").lower().replace("control", "")
                name = (c.Name or "").strip()
                rect = c.BoundingRectangle
                bbox = (rect.left, rect.top, rect.right, rect.bottom)
                enabled = bool(getattr(c, "IsEnabled", True))
                visible = mini or bool(getattr(c, "IsOffscreen", False)) is False
                if role == "dataitem":
                    cells_seen += 1
                    if cells_kept >= GRID_CELL_CAP:
                        return                       # sampled: counted above, not surfaced
                if (role in ACTIONABLE_ROLES and (name or role in UNNAMED_OK_ROLES)
                        and visible and enabled
                        and (mini or (bbox[2] > bbox[0] and bbox[3] > bbox[1]))):
                    value = ""
                    if role != "dataitem" or cells_kept < 40:      # a value read is one COM round trip per cell
                        try:
                            vp = c.GetValuePattern()
                            if vp:
                                value = (vp.Value or "")[:80]
                        except Exception:
                            pass
                    if role == "dataitem":
                        cells_kept += 1
                    label = name or (str(getattr(c, "AutomationId", "") or "").strip()
                                     if role in ("datagrid", "table") else "") or role
                    elements.append(GroundedElement(
                        id=_element_id(root_hwnd, role, name or label, bbox),
                        name=label, role=role, bbox=bbox, tier="uia",
                        confidence=0.9 if name else 0.55,
                        hwnd=root_hwnd, value=value))
                    count += 1
                for child in c.GetChildren():
                    _visit(child, depth + 1)
            except Exception:
                return

        _visit(ctrl, 0)
        self.last_walk = {"grid_cells_seen": cells_seen, "grid_cells_surfaced": cells_kept,
                          "grid_cells_sampled_out": max(0, cells_seen - cells_kept)}
        return elements

    # ---- Tier 2: Win32 children ----
    def _walk_win32(self, root_hwnd: int) -> List[GroundedElement]:
        if not _IS_WINDOWS:
            return []
        user32 = ctypes.windll.user32
        elements: List[GroundedElement] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(child, _l):
            try:
                if not user32.IsWindowVisible(child):
                    return True
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(child, cls_buf, 256)
                cname = cls_buf.value.lower()
                length = user32.GetWindowTextLengthW(child)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(child, buf, length + 1)
                name = buf.value.strip()
                role = ""
                if "button" in cname:
                    role = "button"
                elif "edit" in cname:
                    role = "edit"
                elif "combobox" in cname:
                    role = "combobox"
                elif "syslistview" in cname or "list" in cname:
                    role = "listitem"
                if not role or (not name and role != "edit"):
                    return True
                r = ctypes.wintypes.RECT() if hasattr(ctypes, "wintypes") else None
                import ctypes.wintypes as wt
                rr = wt.RECT()
                user32.GetWindowRect(child, ctypes.byref(rr))
                bbox = (rr.left, rr.top, rr.right, rr.bottom)
                if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                    return True
                elements.append(GroundedElement(
                    id=_element_id(root_hwnd, role, name, bbox),
                    name=name or role, role=role, bbox=bbox, tier="win32",
                    confidence=0.75, hwnd=child))
            except Exception:
                pass
            return True

        try:
            user32.EnumChildWindows(root_hwnd, _cb, 0)
        except Exception as exc:
            logger.debug("[grounding] EnumChildWindows failed: %s", exc)
        return elements

    # ---- Tier 3: OCR ----
    def _window_png(self, hwnd: int) -> Optional[str]:
        """Capture the window's OWN pixels (PrintWindow): correct while covered or partly
        off-screen. Minimized windows cannot be rendered by Windows -> None + honest note."""
        self._capture_note = ""
        if not (HAS_PIL and _IS_WINDOWS and hwnd):
            self._capture_note = "no-PIL-or-non-windows"
            return None
        img, why = hin.capture_window(hwnd)
        self._capture_note = why
        if img is None:
            logger.debug("[grounding] window capture unavailable: %s", why)
            return None
        if self._unpainted(img):
            # GPU / DirectComposition UIs (CEF clients such as Steam, many Electron shells) are composited only while
            # the window is actually visible: PrintWindow of a hidden one returns just the native frame. OCR and a
            # 46 s vision parse of that would read nothing - say so instead of pretending a tier ran.
            self._capture_note = "unpainted (the window's content was not painted into the capture; it is composited only while visible)"
            logger.debug("[grounding] %s", self._capture_note)
            return None
        try:
            path = os.path.join(os.environ.get("TEMP", "."), f"hj_ground_{hwnd}_{int(time.time()*1000)}.png")
            img.save(path, format="PNG")
            return path
        except Exception as exc:
            self._capture_note = f"save-error: {exc}"
            return None

    @staticmethod
    def _unpainted(img) -> bool:
        """True for a capture that carries no content: near-zero contrast and only a few brightness bands. Measured on
        this host: the unpainted Steam login window = stddev 3.9 / 4 bands; Paint 109 / 27; the plain Win32 test window
        71 / 20."""
        try:
            from PIL import ImageStat
            g = img.convert("L")
            bands = len({v // 8 for v in g.resize((48, 48)).getdata()})
            return ImageStat.Stat(g).stddev[0] < 8.0 and bands <= 6
        except Exception:
            return False

    def _window_origin(self, hwnd: int) -> Tuple[int, int]:
        try:
            import ctypes.wintypes as wt
            rr = wt.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
            return rr.left, rr.top
        except Exception:
            return 0, 0

    def _walk_ocr(self, hwnd: int) -> List[GroundedElement]:
        if not (HAS_PYTESSERACT and HAS_PIL):
            return []
        path = self._window_png(hwnd)
        if not path:
            return []
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(path)
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            ox, oy = self._window_origin(hwnd)
            out: List[GroundedElement] = []
            for i, text in enumerate(data["text"]):
                text = (text or "").strip()
                conf = float(data["conf"][i] or -1)
                if len(text) >= 2 and conf > 60:
                    x, y, w, hgt = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    bbox = (x + ox, y + oy, x + w + ox, y + hgt + oy)
                    out.append(GroundedElement(
                        id=_element_id(hwnd, "text", text, bbox),
                        name=text, role="text", bbox=bbox, tier="ocr",
                        confidence=conf / 100.0, hwnd=hwnd))
            return out
        except Exception as exc:
            logger.debug("[grounding] OCR pass failed: %s", exc)
            return []
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    # ---- Tier 4: OmniParser vision (honest availability only) ----
    # Module-level singleton so the expensive Florence-2 + YOLO load happens ONCE
    # across the entire process lifetime, not on every _walk_vision call.
    _vision_parser = None
    _vision_parser_init_tried = False
    # Background warmup: the 20-250 s model load must never sit in a goal's path.
    _warm: Dict[str, Any] = {"state": "idle", "result": None, "started": 0.0}
    _warm_lock = threading.Lock()

    @classmethod
    def start_warmup(cls) -> str:
        """Kick off the one-time OmniParser load (+ easyocr model fetch) in a daemon thread."""
        if os.environ.get("HOJAIGA_VISION_WARMUP", "1") == "0":
            return "disabled"
        with cls._warm_lock:
            if cls._warm["state"] != "idle":
                return cls._warm["state"]
            cls._warm.update(state="warming", started=time.time())

        def _run():
            res = cls.warmup_vision()
            with cls._warm_lock:
                cls._warm.update(state="ready" if res.get("warmed") else "failed", result=res)
            logger.info("[vision-warmup] %s", res)

        threading.Thread(target=_run, daemon=True, name="vision-warmup").start()
        return "warming"

    @classmethod
    def wait_vision_ready(cls, timeout_s: float = 300.0) -> bool:
        """For tests / explicit callers only; the loop itself never blocks on this."""
        cls.start_warmup()
        end = time.time() + timeout_s
        while time.time() < end:
            if cls._warm["state"] in ("ready", "failed"):
                break
            time.sleep(0.5)
        return cls._warm["state"] == "ready"

    @staticmethod
    def _png_signature(path: str) -> str:
        """Cheap pixel signature (16x16 grayscale hash): same window state => same key."""
        try:
            from PIL import Image
            img = Image.open(path).convert("L").resize((16, 16))
            return hashlib.md5(img.tobytes()).hexdigest()
        except Exception:
            return ""

    @classmethod
    def _get_vision_parser(cls):
        """Process-wide OmniParserScanner singleton (model init is 17-24 s)."""
        if not cls._vision_parser_init_tried:
            cls._vision_parser_init_tried = True
            from core_organs.organ_44_enhanced_scanner import OmniParserScanner
            parser = OmniParserScanner()
            parser._init_model()
            if getattr(parser, "_available", False):
                cls._vision_parser = parser
        p = cls._vision_parser
        return p if p is not None and getattr(p, "_available", False) else None

    @classmethod
    def warmup_vision(cls) -> Dict[str, Any]:
        """One-time warmup: load models AND trigger the lazy easyocr model download on a
        small PNG so no later goal pays a hidden multi-minute stall. Returns timing."""
        t0 = time.time()
        if not (HAS_TORCH and HAS_PIL and os.path.isdir(OMNI_LOCAL_REPO)):
            return {"warmed": False, "reason": "vision-prereqs-missing", "ms": 0}
        path = os.path.join(os.environ.get("TEMP", "."), f"hj_warm_{uuid.uuid4().hex[:6]}.png")
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (240, 90), "white")      # real text so OCR + detector + captioner all run
            dr = ImageDraw.Draw(img)
            dr.rectangle([10, 20, 110, 60], outline="black")
            dr.text((30, 33), "File", fill="black")
            dr.rectangle([125, 20, 225, 60], outline="black")
            dr.text((150, 33), "Save", fill="black")
            img.save(path, format="PNG")
            parser = cls._get_vision_parser()
            if parser is None:
                return {"warmed": False, "reason": "parser-unavailable",
                        "ms": int((time.time() - t0) * 1000)}
            parser.parse_screenshot(path)
            return {"warmed": True, "ms": int((time.time() - t0) * 1000)}
        except Exception as exc:
            return {"warmed": False, "reason": f"{type(exc).__name__}: {exc}",
                    "ms": int((time.time() - t0) * 1000)}
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def _walk_vision(self, hwnd: int, report: Optional[Dict[str, Any]] = None) -> List[GroundedElement]:
        report = report if report is not None else {}
        if not (HAS_TORCH and os.path.isdir(OMNI_LOCAL_REPO) and HAS_PIL):
            return []
        self._vision_ran = False
        state = DesktopGrounding._warm["state"]
        if state in ("idle", "warming"):
            DesktopGrounding.start_warmup()
            report.setdefault("tiers_skipped", []).append("vision:warming-up")
            return []
        if state == "failed" and DesktopGrounding._vision_parser is None:
            report.setdefault("tiers_skipped", []).append("vision:warmup-failed")
            return []
        if self._vision_calls >= VISION_MAX_CALLS:
            report.setdefault("tiers_skipped", []).append("vision:budget-exhausted")
            return []
        path = self._window_png(hwnd)
        if not path:
            return []
        try:
            key = (hwnd, self._png_signature(path))
            hit = self._vision_cache.get(key)
            if hit and key[1] and (time.monotonic() - hit[0]) <= VISION_CACHE_TTL_S:
                report["vision_cache_hit"] = True
                self._vision_ran = True
                return list(hit[1])
            parser = self._get_vision_parser()
            if parser is None:
                return []
            self._vision_calls += 1
            self._vision_ran = True
            elements = parser.parse_screenshot(path)
            # parse_screenshot returns image-pixel bounds; the window PNG is a grab
            # of the window rect, so add the window origin to get SCREEN coords.
            ox = oy = 0
            try:
                import ctypes.wintypes as wt
                rr = wt.RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
                ox, oy = rr.left, rr.top
            except Exception:
                pass
            out: List[GroundedElement] = []
            for e in elements:
                b = e.bounds
                screen_bbox = (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy)
                out.append(GroundedElement(
                    id=_element_id(hwnd, e.role, e.text, screen_bbox),
                    name=e.text or "vision", role=e.role, bbox=screen_bbox,
                    tier="vision", confidence=float(e.confidence or 0.35), hwnd=hwnd))
            if key[1]:
                self._vision_cache[key] = (time.monotonic(), list(out))
                if len(self._vision_cache) > 8:
                    self._vision_cache.pop(next(iter(self._vision_cache)))
            return out
        except Exception as exc:
            logger.debug("[grounding] vision pass unavailable: %s", exc)
            return []
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    # ---- capture-restore-capture rung for MINIMIZED windows ----
    def _await_paint(self, hwnd: int, timeout_s: float = 3.0) -> float:
        """A window that was just un-minimized off-screen needs a moment before PrintWindow returns real
        pixels (XAML / Chromium repaint lazily). Poll with a small growing delay, bounded; returns seconds."""
        t0 = time.perf_counter()
        delay = 0.15
        while time.perf_counter() - t0 < timeout_s:
            img, _why = hin.capture_window(hwnd)
            if img is not None:
                break
            time.sleep(delay)
            delay = min(delay * 1.5, 0.5)
        return time.perf_counter() - t0

    def _ground_offscreen(self, hwnd: int, report: Dict[str, Any], max_tier: int,
                          target_text: str = "") -> Tuple[List[GroundedElement], bool]:
        """Perception for a MINIMIZED window whose structure missed the target. The window is PARKED off-screen
        (background_window: restored, never on a monitor, never activated), read, then re-minimized exactly as it
        was. Never a visible restore.

          1. UIA again, now that the window is laid out (a parked tree is far richer than a minimized one:
             measured 22 -> 56+ controls for the same Notepad). If the target is there, stop - no pixels needed.
          2. otherwise OCR, then vision, over the window's OWN pixels (PrintWindow).

        Guards: a window the user can currently SEE that we did not launch is not touched - the rung refuses and
        the report says to escalate. Everything measured goes into report['offscreen'].
        Returns (elements, replace_structural)."""
        from core_organs import background_window as bw
        rep: Dict[str, Any] = {"used": False}
        report["offscreen"] = rep
        out: List[GroundedElement] = []
        t_all = time.perf_counter()
        if not bw.ENABLED:
            rep["refused"] = "parking-disabled(HOJAIGA_PARK_MINIMIZED=0)"
            report["tiers_skipped"] += ["ocr:offscreen-disabled", "vision:offscreen-disabled"]
            return out, False
        rep["ours"] = bw.is_ours(hwnd)
        if not rep["ours"] and bw.user_can_see(hwnd):
            rep.update(refused="user-can-see", escalate_to_human=True)
            report["tiers_skipped"] += ["ocr:offscreen-refused(user-can-see)", "vision:offscreen-refused(user-can-see)"]
            return out, False
        replace = False
        with bw.BackgroundSession(hwnd) as sess:
            rep["mode"] = sess.mode
            rep["park_ms"] = round((time.perf_counter() - t_all) * 1000, 1)
            if sess.mode != "parked":
                rep["refused"] = f"could not park ({sess.mode})"
                report["tiers_skipped"] += [f"ocr:offscreen-{sess.mode}", f"vision:offscreen-{sess.mode}"]
            else:
                rep["used"] = True
                rep["paint_wait_ms"] = round(self._await_paint(hwnd) * 1000, 1)
                via: List[str] = []
                resolved = False
                if HAS_UIA:
                    _t = time.perf_counter()
                    parked = self._walk_uia(hwnd)
                    for w in hin.popup_windows(hwnd)[:10]:
                        parked.extend(self._walk_uia(w, max_depth=8, max_nodes=300))
                    report["tier_ms"]["uia@offscreen"] = round((time.perf_counter() - _t) * 1000, 1)
                    report["tiers_ran"].append("uia@offscreen")
                    rep["uia_parked_elements"] = len(parked)
                    if parked:
                        out, replace = parked, True
                    resolved = bool(target_text) and any(target_text.lower() in e.name.lower() for e in parked)
                    if resolved:
                        rep["resolved_by"] = "uia-parked"
                        via.append("uia:offscreen-capture")
                if not resolved:
                    if HAS_PYTESSERACT and HAS_PIL:
                        _t = time.perf_counter()
                        ocr_els = self._walk_ocr(hwnd)
                        report["tier_ms"]["ocr"] = round((time.perf_counter() - _t) * 1000, 1)
                        if str(getattr(self, "_capture_note", "")).startswith("unpainted"):
                            rep["content_painted"] = False
                            rep["escalate_to_human"] = True
                            report["tiers_skipped"] += ["ocr:offscreen-capture(content not painted: composited only while visible)",
                                                        "vision:offscreen-capture(content not painted)"]
                            max_tier = min(max_tier, 3)             # do not spend a 46 s vision parse on an empty frame
                        else:
                            out = out + ocr_els
                            report["tiers_ran"].append("ocr")
                            via.append("ocr:offscreen-capture")
                    else:
                        report["tiers_skipped"].append("ocr:engine-missing")
                    if rep.get("content_painted") is False:
                        pass                                        # already reported above
                    elif max_tier >= 4 and HAS_TORCH:
                        _t = time.perf_counter()
                        vis = self._walk_vision(hwnd, report)
                        report["tier_ms"]["vision"] = round((time.perf_counter() - _t) * 1000, 1)
                        if getattr(self, "_vision_ran", False):
                            report["tiers_ran"].append("vision")
                            via.append("vision:offscreen-capture")
                        else:
                            report["tiers_skipped"].append("vision:offscreen-capture(not run: see vision:* reason)")
                        out = out + vis
                    elif max_tier >= 4:
                        report["tiers_skipped"].append("vision:torch-missing")
                    else:
                        report["tiers_skipped"].append("vision:offscreen-capture(cap)")
                rep["tiers_via"] = via
        rep["round_trip_ms"] = round((time.perf_counter() - t_all) * 1000, 1)     # includes the verified re-minimize
        rep["ended_minimized"] = hin.is_minimized(hwnd)
        if rep["used"] and not rep["ended_minimized"]:
            report["tiers_skipped"].append("offscreen:NOT-reminimized")           # loud: the window is somewhere it should not be
        return out, replace

    # ---- public API ----
    def ground(self, app_hint: str, target_text: str = "",
               max_tier: int = 2) -> Tuple[Optional[int], List[GroundedElement], Dict[str, Any]]:
        """Returns (hwnd, elements, ladder_report).

        max_tier: 1 uia only, 2 +win32 (default; ms-level fast), 3 +ocr, 4 +vision.
        Escalation past tier 2 happens automatically ONLY when the caller is
        looking for target_text and the structural tiers found no match — this
        is the 'after 2 UIA misses' rule from the plan.
        """
        hwnd = self.find_window(app_hint)
        report = {"app_hint": app_hint, "hwnd": hwnd, "tiers_ran": [], "tiers_skipped": [],
                  "escalated": False, "tier_ms": {}}
        if not hwnd:
            report["reason"] = "window-not-found"
            return None, [], report

        elements: List[GroundedElement] = []
        if HAS_UIA:
            _t = time.perf_counter()
            elements = self._walk_uia(hwnd)
            report["tier_ms"]["uia"] = round((time.perf_counter() - _t) * 1000, 1)
            report["tiers_ran"].append("uia")
        else:
            report["tiers_skipped"].append("uia:no-uiautomation")

        # Menus, flyouts and dialogs are separate top-level windows of the SAME process; a UIA
        # walk of the main frame cannot see them. Ground them too (bounded).
        if HAS_UIA:
            extra = hin.popup_windows(hwnd)[:10]
            for w in extra:
                elements.extend(self._walk_uia(w, max_depth=8, max_nodes=300))
            if extra:
                report["popup_windows"] = len(extra)
        report["window_state"] = hin.window_state(hwnd).get("state")
        lw = getattr(self, "last_walk", None)
        if lw and lw.get("grid_cells_seen"):
            report["grid"] = dict(lw)          # honest: how many grid cells exist vs how many were surfaced

        if not elements and max_tier >= 2:
            _t = time.perf_counter()
            elements = self._walk_win32(hwnd)
            report["tier_ms"]["win32"] = round((time.perf_counter() - _t) * 1000, 1)
            report["tiers_ran"].append("win32")

        need_target = bool(target_text)
        structural_miss = not any(target_text.lower() in e.name.lower() for e in elements)

        if need_target and structural_miss and report["window_state"] == "minimized":
            # Windows does not render a minimized window, so a pixel tier cannot read it AS IT IS. It can read it
            # off-screen: park it (restored, never on a monitor, never activated), capture, re-minimize exactly as
            # it was. Only reached when UIA/Win32 already missed the target - an app grounded structurally never
            # pays this round trip.
            report["escalated"] = True
            if max_tier >= 3:
                extra, replace = self._ground_offscreen(hwnd, report, max_tier, target_text)
                if replace:
                    elements = extra          # the parked window's own UIA tree supersedes the degraded minimized one
                else:
                    elements.extend(extra)
            else:
                report["tiers_skipped"] += ["ocr:window-minimized", "vision:window-minimized"]
        elif need_target and structural_miss:
            report["escalated"] = True
            if HAS_PYTESSERACT and HAS_PIL and max_tier >= 3:
                _t = time.perf_counter()
                ocr = self._walk_ocr(hwnd)
                report["tier_ms"]["ocr"] = round((time.perf_counter() - _t) * 1000, 1)
                report["tiers_ran"].append("ocr")
                elements.extend(ocr)
            elif max_tier >= 3:
                report["tiers_skipped"].append("ocr:engine-missing")
                if max_tier < 4:
                    report["tiers_skipped"].append("ocr:cap")
            if HAS_TORCH and max_tier >= 4:
                _t = time.perf_counter()
                vis = self._walk_vision(hwnd, report)
                report["tier_ms"]["vision"] = round((time.perf_counter() - _t) * 1000, 1)
                if getattr(self, "_vision_ran", False):
                    report["tiers_ran"].append("vision")
                elements.extend(vis)
            elif max_tier >= 4:
                report["tiers_skipped"].append("vision:torch-missing")

        # Dedup by id, sort confident-first then top-to-bottom.
        uniq: Dict[str, GroundedElement] = {}
        for e in elements:
            if e.id not in uniq or e.confidence > uniq[e.id].confidence:
                uniq[e.id] = e
        final = sorted(uniq.values(), key=lambda e: (-e.confidence, e.bbox[1]))
        report["element_count"] = len(final)
        self.last_report = report
        return hwnd, final, report


# ---------------------------------------------------------------------------
# W2 — DesktopVerifier: outcome assertions (the trust core)
# ---------------------------------------------------------------------------

# Pixel-delta tolerance. The window is reduced to a small grayscale thumbnail quantized into
# REGION_LEVEL_BANDS brightness bands, and a change only counts when at least
# REGION_MIN_CHANGED_FRACTION of the cells moved. Two reasons, both measured on real windows:
# an exact-byte hash of a screen grab let a blinking caret / ticking clock read as "the app
# reacted", and it hashed whatever window was ON TOP of the target. The measured fraction always
# goes into the evidence string, so a suppressed small change stays visible to a human.
REGION_THUMB_SIZE = (48, 48)
REGION_LEVEL_BANDS = 16
REGION_MIN_CHANGED_FRACTION = 0.02


@dataclass
class Snapshot:
    title: str
    element_ids: List[str]
    region_hash: str = ""
    region_thumb: bytes = b""
    region_source: str = ""
    text: str = ""
    names: List[str] = field(default_factory=list)   # EVERY UIA name (text/labels too); filled only when a postcondition asks

    def signature(self) -> str:
        return hashlib.md5(("|".join(sorted(self.element_ids)) + self.title).encode("utf-8")).hexdigest()


class DesktopVerifier:
    def snapshot(self, hwnd: int, elements: List[GroundedElement], text: str = "") -> Snapshot:
        snap = Snapshot(title=_quick_title(hwnd), element_ids=[e.id for e in elements], text=text)
        snap.region_hash, snap.region_thumb, snap.region_source = self._region_capture(hwnd)
        return snap

    def _region_capture(self, hwnd: int) -> Tuple[str, bytes, str]:
        """(hash, quantized thumbnail, capture source) of the window's OWN pixels.

        PrintWindow is tried first because a screen grab of the window rect hashes whatever is on
        top, so an occluded app could fake both a change and a no-change. A screen grab is still
        used as a fallback (some GPU windows return no PrintWindow content) but the source tag
        says so — the fallback is never silent. Minimized windows are not rendered by Windows, so
        no fallback happens there: grabbing their parked 1x1 rect would be meaningless noise.
        """
        if not (HAS_PIL and _IS_WINDOWS and hwnd):
            return "", b"", "unavailable"
        img, why = None, "no-capture"
        try:
            img, why = hin.capture_window(hwnd)
        except Exception as exc:
            img, why = None, f"error({type(exc).__name__})"
        if img is not None:
            return self._thumb_pair(img, "printwindow")
        if why == "window-minimized":
            return "", b"", "window-minimized"
        try:
            from PIL import ImageGrab
            import ctypes.wintypes as wt
            rr = wt.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
            if rr.right - rr.left < 8 or rr.bottom - rr.top < 8:
                return "", b"", f"no-usable-rect({why})"
            img = ImageGrab.grab(bbox=(rr.left, rr.top, rr.right, rr.bottom))
        except Exception as exc:
            return "", b"", f"capture-failed({why}/{type(exc).__name__})"
        if img is None:
            return "", b"", f"capture-failed({why})"
        return self._thumb_pair(img, "screen-grab-fallback")

    @staticmethod
    def _thumb_pair(img, source: str) -> Tuple[str, bytes, str]:
        try:
            thumb = DesktopVerifier._region_thumb(img)
        except Exception as exc:
            return "", b"", f"thumb-error({type(exc).__name__})"
        return hashlib.md5(thumb).hexdigest(), thumb, source

    @staticmethod
    def _region_thumb(img) -> bytes:
        """Grayscale, fixed 48x48, quantized into REGION_LEVEL_BANDS bands."""
        gray = img.convert("L").resize(REGION_THUMB_SIZE)
        band = 256 // REGION_LEVEL_BANDS
        return bytes(min(REGION_LEVEL_BANDS - 1, px // band) for px in gray.getdata())

    def _region_hash(self, hwnd: int) -> str:
        """Kept as the hash-only entry point (organ_48 uses it)."""
        return self._region_capture(hwnd)[0]

    @staticmethod
    def pixels_changed(before: Snapshot, after: Snapshot) -> Tuple[bool, str]:
        """Tolerance-based pixel delta -> (changed, evidence carrying the measured fraction)."""
        if not (before.region_hash and after.region_hash):
            # Name the side that failed and why, so 'no pixel evidence' is never mistaken for
            # 'pixels proved nothing changed' (a minimized window is not rendered by Windows).
            missing = before if not before.region_hash else after
            which = "before" if missing is before else "after"
            return False, f"region pixel-delta unavailable({which}:{missing.region_source or 'no-capture'})"
        b, a = before.region_thumb, after.region_thumb
        if b and a and len(b) == len(a):
            moved = sum(1 for x, y in zip(b, a) if x != y)
            fraction = moved / float(len(b))
            ok = fraction >= REGION_MIN_CHANGED_FRACTION
            return ok, (f"region pixel-delta {fraction:.3f} of cells via "
                        f"{after.region_source or before.region_source} "
                        + ("detected" if ok else "below tolerance"))
        ok = before.region_hash != after.region_hash
        return ok, "region pixel-delta " + ("detected" if ok else "none")

    def check_expect(self, expect: Dict[str, Any], before: Snapshot,
                     after: Snapshot, elements_now: List[GroundedElement]) -> Tuple[bool, str]:
        """Evaluate a postcondition dict. Returns (ok, evidence)."""
        if not expect:
            # Default postcondition: something about the UI changed. Three independent signals: the structure of
            # the actionable controls, the window's own pixels (tolerance-based), and the set of EVERY UIA name
            # (read-outs and labels included - pressing an operator key on a keypad changes a text label and
            # almost no pixels, which the first two cannot see). Still "something changed", still reported weak.
            pixel_changed, pixel_evidence = self.pixels_changed(before, after)
            nb, na = set(before.names or ()), set(after.names or ())
            names_changed = bool(nb and na and nb != na)
            changed = before.signature() != after.signature() or pixel_changed or names_changed
            name_note = f"; names +{len(na - nb)}/-{len(nb - na)}" if names_changed else ""
            return changed, f"ui-{'changed' if changed else 'unchanged'}; {pixel_evidence}{name_note}"

        checks: List[Tuple[bool, str]] = []
        if "title_contains" in expect:
            ok = str(expect["title_contains"]).lower() in after.title.lower()
            checks.append((ok, f"title={'has' if ok else 'missing'}'{expect['title_contains']}'"))
        if "element_appeared" in expect:
            want = str(expect["element_appeared"]).lower()
            ok = any(want in (e.name or "").lower() for e in elements_now)
            checks.append((ok, f"element '{want}' {'present' if ok else 'absent'}"))
        if "element_disappeared" in expect:
            want = str(expect["element_disappeared"]).lower()
            ok = not any(want in (e.name or "").lower() for e in elements_now)
            checks.append((ok, f"element '{want}' {'gone' if ok else 'still-present'}"))
        if "text_contains" in expect:
            want = str(expect["text_contains"])
            hay = after.text or ""
            # Compare WORDS, not line-break bytes: Notepad's RichEdit stores a typed "\n" as "\r" (and other editors as
            # "\r\n"), so a multi-line haiku was reported MISSING right after it had been typed in, and the retry then
            # typed it again (the document filled with duplicates).
            _flat = lambda t: re.sub(r"\s+", " ", t).strip().lower()
            ok = bool(want) and _flat(want) in _flat(hay)
            checks.append((ok, f"text {'has' if ok else 'MISSING'} '{want[:24]}'"
                          + ("" if hay else " (control text unreadable)")
                          + f" [read {len(hay)} chars]"))
        if "name_visible" in expect:
            # Some control on screen (labels and read-outs included, not just actionable ones) carries this text.
            # A number must match as a whole number: '56' is not satisfied by 'Display is 156'.
            want = str(expect["name_visible"]).strip().lower()
            pat = (re.compile(r"(?<![\d.,])" + re.escape(want) + r"(?![\d]|[.,]\d)")
                   if re.fullmatch(r"-?[\d.,]+", want or "") else None)
            ok = bool(want) and any((pat.search(n) if pat else want in n) for n in (after.names or []))
            checks.append((ok, f"name '{want[:24]}' {'visible' if ok else 'NOT visible'} among {len(after.names or [])} UIA names"))
        if "file_created" in expect or "file_saved" in expect:
            target_path = expect.get("file_created") or expect.get("file_saved")
            p = os.path.abspath(str(target_path))
            ok = os.path.exists(p)
            _end = time.time() + 3.0          # bounded: apps (esp. packaged ones) write asynchronously
            while not ok and time.time() < _end:
                time.sleep(0.25)
                ok = os.path.exists(p)
            checks.append((ok, f"file {os.path.basename(p)} {'exists' if ok else 'MISSING'}"))
        if "region_changed" in expect and bool(expect["region_changed"]):
            checks.append(self.pixels_changed(before, after))
        return all(c[0] for c in checks), "; ".join(c[1] for c in checks) or "no-expect"

    def verdict(self, expect: Dict[str, Any], before: Snapshot, after: Snapshot,
                elements_now: List[GroundedElement]) -> Tuple[str, str]:
        """PASS / NO_CHANGE / WRONG_STATE with evidence."""
        ok, evidence = self.check_expect(expect, before, after, elements_now)
        if ok:
            return "PASS", evidence
        pixel_moved, _ = self.pixels_changed(before, after)
        structurally_dead = before.signature() == after.signature() and not pixel_moved
        if expect and structurally_dead:
            return "NO_CHANGE", evidence
        if structurally_dead:
            return "NO_CHANGE", evidence
        return "WRONG_STATE", evidence


# Module-level verifier facade alias per Workstream 2
desktop_verifier = DesktopVerifier()


def _quick_title(hwnd: int) -> str:
    if not (_IS_WINDOWS and hwnd):
        return ""
    try:
        import ctypes.wintypes as wt
        return hin.safe_window_text(int(hwnd))
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# W3 — ConstrainedJudge: forced choice, never open-ended generation
# ---------------------------------------------------------------------------

class ConstrainedJudge:
    """Asks the local model to pick ONE numbered element + ONE legal verb.

    A multiple-choice answer is a task 7B models do reliably; free-form tool
    selection (what caused the live-run flailing) is not. Invalid answers are
    surfaced, and the loop escalates to HITL after INVALID_CHOICE_LIMIT misses.
    """

    model: Optional[str] = None   # per-instance override of JUDGE_MODEL (used by model benchmarks)
    _TYPE_WORDS = ("type", "write", "enter", "input", "compose", "fill", "paste", "text")
    _TEXT_ROLES = ("edit", "document", "combobox")
    _STOP = frozenset({"the", "a", "an", "to", "in", "into", "on", "of", "and", "then", "it",
                       "for", "with", "as", "at", "by", "from", "this", "that", "my"})

    @classmethod
    def rank_candidates(cls, goal: str, elements: List[GroundedElement],
                        pro_hint: Optional[Dict[str, Any]] = None) -> List[Tuple[int, GroundedElement]]:
        return [(i, e) for _sc, i, e in cls.rank_scored(goal, elements, pro_hint)]

    @classmethod
    def rank_scored(cls, goal: str, elements: List[GroundedElement],
                    pro_hint: Optional[Dict[str, Any]] = None) -> List[Tuple[float, int, GroundedElement]]:
        """Goal-aware shortlist. Truncating to the first N by confidence/y hid the very
        control the goal named (a 58-element Notepad tree never offered its text area).
        Score = lexical overlap(goal, element name) + role affinity for the goal's intent
        + expert-hint match + the grounding confidence as a tie-break. Generic: no app names.
        """
        g = re.sub(r"[a-z]:[\\/][^\s'<>|?*]+", " ", (goal or "").lower())  # a path's tokens are not UI words
        gtoks = {t for t in re.findall(r"[a-z0-9]+", g) if t not in cls._STOP and len(t) > 1}
        save_as = bool(re.search(r"\bsave\b.{0,40}\bas\b", g)) or bool(re.search(r"\bsave as\b", g)) or (bool(re.search(r"\bsave\b", (goal or "").lower())) and bool(re.search(r"[a-z]:[\\/]", (goal or "").lower())))
        file_verb = bool(re.search(r"\b(save|open|export|import|print|close|exit)\b", g))
        wants_text = bool(re.search(r"\b(" + "|".join(cls._TYPE_WORDS) + r")\b", g))
        hint_segments = [x.strip().lower() for x in ((pro_hint or {}).get("menu_path") or "").split(">") if x.strip()]
        if not hint_segments and (pro_hint or {}).get("element_name"):
            hint_segments = [pro_hint["element_name"].strip().lower()]
        hint_name = ((pro_hint or {}).get("element_name") or (pro_hint or {}).get("menu_path") or "").lower()
        scored = []
        for i, e in enumerate(elements):
            name = (e.name or "").lower()
            ntoks = set(re.findall(r"[a-z0-9]+", name))
            score = 3.0 * len(gtoks & ntoks)
            score += 1.5 * sum(1 for t in gtoks if len(t) > 3 and t in name and t not in ntoks)
            if save_as and e.role == "menuitem" and name.startswith("save as"):
                score += 7.0   # an explicit target path/name means Save AS, not in-place Save
            if save_as and e.role == "menuitem" and name == "save":
                score -= 3.0
            if file_verb and e.role == "menuitem" and name == "file":
                score += 5.0   # universal UI convention: file operations live under the File menu
            if wants_text and e.role in cls._TEXT_ROLES:
                score += 4.0 + (1.0 if e.role in ("edit", "document") else 0.0)
            if hint_name and hint_name in name:
                score += 3.0
            # Follow the expert's menu path ('File > Save As'): a segment that exactly names this
            # element is the next step to take, earlier segments first (menus open one level at a time).
            for depth, seg in enumerate(hint_segments):
                if save_as and name == "save":
                    break  # explicit target => never the in-place Save, whatever an old hint says
                if name == seg or (name.startswith(seg + " ") and len(seg) > 3):
                    score += 6.0 - min(depth, 3)
                    break
            score += 0.5 * float(e.confidence or 0.0)
            scored.append((score, -e.bbox[1], i, e))
        scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
        return [(sc, i, e) for sc, _y, i, e in scored]

    _DECISIVE_TEXT_MARGIN = 2.5
    _DECISIVE_PATH_MARGIN = 4.0

    @classmethod
    def _wants_text(cls, goal: str) -> bool:
        return bool(re.search(r"\b(" + "|".join(cls._TYPE_WORDS) + r")\b", (goal or "").lower()))

    _CLICK_ROLES = ("button", "menuitem", "tabitem", "listitem", "hyperlink", "checkbox", "radiobutton",
                    "splitbutton", "dropdownbutton", "treeitem")
    _PRESS_RE = re.compile(r"^(?:please\s+)?(?:press|click|tap|hit|select|choose|push|invoke|toggle|activate)"
                           r"\s+(?:on\s+)?(?:the\s+)?[\"'“]?(.+?)[\"'”]?(?:\s+(?:button|key|control|tab|item))?\s*$", re.I)

    @classmethod
    def _norm_label(cls, s: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()

    @classmethod
    def _exact_named_target(cls, goal: str, scored: List[Tuple[float, int, "GroundedElement"]]):
        """(score, index, element) of the clickable control whose whole name equals the object of a 'press X'
        style goal, else None. Digits match their word form ('6' == 'Six'), the way Calculator-style UIs label keys."""
        m = cls._PRESS_RE.match((goal or "").strip())
        if not m:
            return None
        obj = cls._norm_label(m.group(1))
        if not obj or len(obj.split()) > 4:
            return None
        try:
            from core_organs.task_runner import _DIGIT_WORDS
            obj = _DIGIT_WORDS.get(obj, obj)
        except Exception:
            pass
        hits = [c for c in scored if c[2].role in cls._CLICK_ROLES and cls._norm_label(c[2].name) == obj]
        return hits[0] if hits else None

    def _compose_text(self, goal: str) -> str:
        """Small LLM call used ONLY to author the text for a typing goal (the element was chosen
        deterministically). A quoted string in the goal wins without any LLM call."""
        m = re.search(r"[\"'“]([^\"'”]{2,300})[\"'”]", goal or "")
        if m:
            return m.group(1)
        payload = {"model": JUDGE_MODEL, "stream": False,
                   "messages": [{"role": "user", "content":
                                 "Return ONLY the exact text to type for this instruction, with no "
                                 f"quotes or commentary.\nINSTRUCTION: {goal}"}],
                   "options": {"temperature": 0.7, "num_predict": 80}}
        try:
            import urllib.request
            req = urllib.request.Request(BRAINS_CHAT_URL, data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=JUDGE_TIMEOUT_S) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return ((body.get("message", {}) or {}).get("content", "") or "").strip().strip('"')
        except Exception as exc:
            logger.debug("[judge] compose_text failed: %s", exc)
            return ""

    def decisive(self, goal: str, elements: List[GroundedElement],
                 pro_hint: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Deterministic pick when the evidence is overwhelming; None => ask the LLM judge.

          * typing goal + a clearly-best editable control   -> type (LLM only writes the text)
          * the next segment of the expert's menu path is an exact on-screen match -> click
        A 7B model chose a tab titled like the typed text over the editor; decisive evidence must
        never be left to it."""
        scored = self.rank_scored(goal, elements, pro_hint)
        if not scored:
            return None
        top = scored[0]
        # The goal NAMES one control exactly ("press Six", "click 'Save'", "select the Settings tab") and exactly
        # such a clickable control is on screen: that is a lookup, not a judgement. Skipping the 7B here removed
        # every invalid-choice strike a correct, unambiguous goal could earn (it said "type Six" on a button).
        exact = self._exact_named_target(goal, scored)
        if exact is not None:
            return {"choice": exact[1], "verb": "click", "text": "", "why": "decisive: goal names this control exactly",
                    "element_index": exact[1], "element": exact[2].as_dict(), "decisive": True}
        # the same control is often exposed twice (hidden + popup copy): measure the margin against
        # the best candidate with a DIFFERENT name
        rival = next((c[0] for c in scored[1:] if (c[2].name or "").strip().lower()
                      != (top[2].name or "").strip().lower()), 0.0)
        margin = top[0] - rival
        g = (goal or "").lower()
        if re.search(r"\b(" + "|".join(self._TYPE_WORDS) + r")\b", g):
            # Typing goal: only an editable control can receive text, so the candidate set IS the
            # editable controls (a tab/label/button that merely shares a word must never win).
            texty = [c for c in scored if c[2].role in self._TEXT_ROLES]
            if texty and (len(texty) == 1 or texty[0][0] - texty[1][0] >= 1.0):
                text = self._compose_text(goal)
                if text:
                    return {"choice": texty[0][1], "verb": "type", "text": text,
                            "why": "decisive: editable control", "element_index": texty[0][1],
                            "element": texty[0][2].as_dict(), "decisive": True}
        if top[0] >= 10.0 and margin >= 4.0 and top[2].role in ("menuitem", "button", "tabitem", "listitem",
                                                                  "hyperlink", "checkbox", "radiobutton"):
            return {"choice": top[1], "verb": "click", "text": "", "why": "decisive: overwhelming match",
                    "element_index": top[1], "element": top[2].as_dict(), "decisive": True}
        segs = [x.strip().lower() for x in ((pro_hint or {}).get("menu_path") or "").split(">") if x.strip()]
        if segs and margin >= self._DECISIVE_PATH_MARGIN and (top[2].name or "").strip().lower() in segs:
            return {"choice": top[1], "verb": "click", "text": "", "why": "decisive: expert menu path",
                    "element_index": top[1], "element": top[2].as_dict(), "decisive": True}
        return None

    def decide(self, goal: str, elements: List[GroundedElement],
               app_hint: str = "", history: List[str] = None,
               pro_hint: Optional[Dict[str, Any]] = None, use_decisive: bool = True) -> Optional[Dict[str, Any]]:
        fast = self.decisive(goal, elements, pro_hint) if use_decisive else None
        if fast is not None:
            return fast
        ranked = self.rank_candidates(goal, elements, pro_hint)
        picks = [e for _i, e in ranked[:MAX_JUDGE_ELEMENTS]]
        orig_index = [i for i, _e in ranked[:MAX_JUDGE_ELEMENTS]]
        if not picks:
            return None
        lines = []
        for i, e in enumerate(picks):
            cx, cy = e.center
            lines.append(f"{i}. [{e.role}] \"{e.name[:48]}\" at {cx},{cy} ({e.tier})")
        tried = "\n".join(f"- {h}" for h in (history or [])[-4:]) or "- (none yet)"
        pro_block = ""
        if pro_hint:
            if pro_hint.get("kind") == "element":
                label = pro_hint.get("menu_path") or pro_hint.get("element_name") or ""
                hv = pro_hint.get("verb", "click")
                if hv == "type" and not self._wants_text(goal):
                    hv = "click"      # a hint must not tell the model to type when the goal never asked for text
                hv = "key" if hv == "shortcut" else hv  # 'shortcut' is not a legal verb; 'key' is
                key_note = ""  # posted keys do not reach every UI framework; never advertise them
                hv = "click" if hv == "key" else hv
                pro_block = (
                    "EXPERT HINT (from prior verified runs on this app, prefer "
                    f"matching it): aim for \"{label}\" using verb "
                    f"{hv}. This is guidance, not a "
                    f"guarantee — still pick the numbered element that matches it.{key_note}\n")
            elif pro_hint.get("shortcut"):
                pro_block = (f"EXPERT HINT: shortcut {pro_hint['shortcut']} is known "
                             "for this goal.\n")
        prompt = (
            "You are a precise desktop automation executor. Pick EXACTLY ONE numbered "
            "on-screen element and ONE verb that best advances the goal RIGHT NOW.\n"
            f"GOAL: {goal}\nAPP: {app_hint}\n{pro_block}"
            f"ALREADY TRIED (do not repeat):\n{tried}\n"
            "ELEMENTS:\n" + "\n".join(lines) + "\n"
            f"VERBS: {', '.join(LEGAL_VERBS)}\n"
            "RULES: prefer click / type / invoke on a LISTED element. Use verb key ONLY for an "
            "explicit keyboard shortcut named in the goal, never on a tab or document.\n"
            "Return STRICT JSON: {\"choice\": <number>, \"verb\": \"<verb>\", "
            "\"text\": \"<only for type>\", \"why\": \"<5 words>\"}"
        )
        payload = {
            "model": self.model or JUDGE_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_predict": 120},
        }
        try:
            import urllib.request
            req = urllib.request.Request(
                BRAINS_CHAT_URL, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=JUDGE_TIMEOUT_S) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body.get("message", {}).get("content", "") or body.get("response", "")
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if not m:
                return None
            decision = json.loads(m.group(0))
            idx = int(decision.get("choice", -1))
            verb = str(decision.get("verb", "")).lower().strip()
            if 0 <= idx < len(picks) and verb == "type" and picks[idx].role not in self._TEXT_ROLES:
                if self._wants_text(goal):
                    return {"invalid": True, "raw": decision, "why": "type on a non-editable control"}
                # The goal never asked for typing and the element is a plain control: the model picked the right
                # control and the wrong verb (a low-trust 'distilled' hint said "type" and it echoed it). That is
                # not a hallucinated choice and must not count toward the 3-strike human escalation; click it.
                # The postcondition verifier still decides whether the click achieved anything.
                decision["verb"] = verb = "click"
                decision["coerced"] = "type->click: goal has no typing intent and the target is not editable"
            if idx < 0 or idx >= len(picks) or verb not in LEGAL_VERBS:
                return {"invalid": True, "raw": decision}
            # element_index always refers to the ORIGINAL grounded list (callers index into it)
            decision.update({"element": picks[idx].as_dict(), "element_index": orig_index[idx]})
            return decision
        except Exception as exc:
            logger.debug("[judge] call failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Action primitives: UIA patterns -> PostMessage -> physical input (cursor-clip aware)
# ---------------------------------------------------------------------------

def _uia_act(elem: GroundedElement, verb: str, text: str):
    """UIA pattern delivery. Returns (result|None, native_hwnd). Runs on _UIA_EXEC's thread."""
    native = 0
    if elem.tier == "uia" and HAS_UIA:
        import uiautomation as auto
        try:
            uroot = auto.ControlFromHandle(elem.hwnd)
            target = _find_control_by_identity(uroot, elem)
            if target is not None:
                native = int(getattr(target, "NativeWindowHandle", 0) or 0)
                if verb == "locate":
                    # Resolution only: the caller posts characters to the real control hwnd, which
                    # appends at the caret instead of replacing the value like SetValue does.
                    return None, native
                if verb == "read":
                    # What the control actually holds right now. The structure hash and the coarse
                    # pixel hash both miss typing: a short line into a document changes no element id
                    # and can move well under 2% of the pixels.
                    for getter, extractor in (("GetValuePattern", lambda p: p.Value),
                                              ("GetTextPattern", lambda p: p.DocumentRange.GetText(-1))):
                        try:
                            pat = getattr(target, getter)()
                            if pat:
                                return True, str(extractor(pat) or "")
                        except Exception:
                            continue
                    return None, native
                if verb == "type":
                    for getter, setter in (("GetValuePattern", "SetValue"),
                                           ("GetLegacyIAccessiblePattern", "SetValue")):
                        try:
                            pat = getattr(target, getter)()
                            if pat:
                                getattr(pat, setter)(text)
                                return True, "uia-SetValue"
                        except Exception:
                            continue
                else:  # click family
                    _errs: List[str] = []
                    for pattern_name, attempts in (("GetInvokePattern", "invoke"),
                                                   ("GetLegacyIAccessiblePattern", "do-default"),
                                                   ("GetSelectionItemPattern", "select"),
                                                   ("GetTogglePattern", "toggle"),
                                                   ("GetExpandCollapsePattern", "expand")):
                        try:
                            try:
                                pat = getattr(target, pattern_name)()
                            except AttributeError:
                                # the wrapper class (e.g. PaneControl) has no typed getter, but the
                                # underlying element may still support the pattern: ask UIA directly
                                import uiautomation as _ua
                                pid = getattr(_ua.PatternId, pattern_name[3:], None)
                                pat = target.GetPattern(pid) if pid else None
                            if pat is None:
                                continue
                            {"invoke": lambda: pat.Invoke(),
                             "do-default": lambda: pat.DoDefaultAction(),
                             "select": lambda: pat.Select(),
                             "toggle": lambda: pat.Toggle(),
                             "expand": lambda: pat.Expand()}[attempts]()
                            return True, f"uia-{attempts}" + (f" (after {','.join(_errs)})" if _errs else "")
                        except Exception as _e:
                            _errs.append(f"{attempts}:{type(_e).__name__}:{str(_e)[:40]}")
                            continue
        except Exception as exc:
            logger.debug("[act] uia path failed: %s", exc)

    return None, native


_UIA_EXEC = None


def _uia_thread_init():
    # a dedicated thread with its OWN properly initialised COM apartment: the UIA client state of
    # the calling thread is shared with every other organ (organ_30, pywin32...), and a different
    # apartment/initialisation there made Invoke silently degrade to DoDefaultAction.
    try:
        import uiautomation as _a
        _a.UIAutomationInitializerInThread().__enter__()
    except Exception:
        pass


def _uia_dispatch(elem: GroundedElement, verb: str, text: str):
    global _UIA_EXEC
    if _UIA_EXEC is None:
        from concurrent.futures import ThreadPoolExecutor
        _UIA_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia-act", initializer=_uia_thread_init)
    try:
        return _UIA_EXEC.submit(_uia_act, elem, verb, text).result(timeout=10)
    except Exception as exc:
        logger.debug("[act] uia worker failed: %s", exc)
        return None, 0


def _root_of(hwnd: int) -> int:
    """Top-level (GA_ROOT) window for a possibly-child hwnd."""
    try:
        return int(hin._u32.GetAncestor(hwnd, 2) or hwnd)
    except Exception:
        return hwnd


def _act_on_element(elem: GroundedElement, verb: str, text: str = "") -> Tuple[bool, str]:
    """Deliver one action to ``elem`` WITHOUT touching the physical pointer or keyboard and
    without changing which window is in front. Ladder: window messages to the exact HWND for
    typing (append at the caret), UIA pattern otherwise, then the other rung. When nothing can
    deliver, returns (False, 'UNDELIVERABLE: <why>') - there is deliberately no physical-input
    rung (product law)."""
    if verb == "wait":
        time.sleep(min(2.0, 0.8))
        return True, "waited"
    if verb == "done":
        return True, "declared-done"
    root = _root_of(elem.hwnd) if elem.hwnd else 0

    if verb in ("key", "shortcut"):
        combo = text or elem.name
        return hin.post_key_combo(root, combo)

    if verb == "scroll":
        cx, cy = elem.center
        return hin.post_scroll(root, cx, cy, -3)

    if verb == "invoke":
        verb = "click"  # invoke is the UIA-safe synonym handled by the click ladder

    if verb == "type" and text:
        # Typing is the one verb where the UIA pattern is wrong by default: ValuePattern.SetValue
        # REPLACES the control's content, so the second 'type' goal of a multi-part entry silently
        # deletes the first (a real unattended Notepad run wrote line 2 over line 1 and line 3 over
        # line 2, each still 'verified' because the UI did change). Posting characters to the
        # control's own hwnd appends at the caret instead, so it goes first; SetValue stays as the
        # fallback for controls that ignore posted characters. Neither is trusted - the verifier
        # judges the postcondition either way.
        native = 0
        if elem.tier == "uia" and HAS_UIA:
            out = _uia_dispatch(elem, "locate", "")
            native = out[1] if out else 0
        ok, note = hin.post_text(native or elem.hwnd, text)
        if ok:
            return True, f"append:{note}"

    res, native = (None, 0)
    if elem.tier == "uia" and HAS_UIA:
        out = _uia_dispatch(elem, verb, text)
        if out and out[0] is True:      # delivered by a UIA pattern: (True, 'uia-...')
            return out
        native = out[1] if out and out[0] is None else 0

    # Window messages to the exact HWND (works while covered / partly off-screen).
    if verb == "click" and root:
        cx, cy = elem.center
        if elem.tier in ("ocr", "vision") and hin.is_minimized(root):
            # A pixel-found element has screen coordinates, which only mean something while the window is laid
            # out. Deliver the click while it is parked off-screen (same rect the capture used), let the app
            # handle the message, then it is re-minimized as it was. Never a visible restore.
            from core_organs import background_window as bw
            with bw.BackgroundSession(root) as sess:
                if sess.mode == "parked":
                    ok, note = hin.post_click(root, cx, cy)
                    time.sleep(0.4)
                    return ok, note + " [delivered while parked off-screen]"
            return False, f"{hin.UNDELIVERABLE}: pixel-found element in a minimized window and it could not be parked ({sess.mode})"
        return hin.post_click(root, cx, cy)
    if verb == "type" and (native or elem.hwnd):
        ok, note = hin.post_text(native or elem.hwnd, text)
        if ok:
            return True, note
        return False, note
    return False, f"{hin.UNDELIVERABLE}: no UIA pattern and no addressable HWND for '{elem.name}' ({verb})"


def _find_control_by_identity(root, elem: GroundedElement):
    """Re-locate the grounded control in the live tree (trees go stale, and apps often expose the
    same control twice - a hidden duplicate without patterns plus the real one). Every name match is
    scored: exact name+role, same on-screen box, and actually supporting an invoke-style pattern."""
    want_name = (elem.name or "").lower()
    cands = []

    def _visit(c, depth, budget=[0]):
        if depth > 14 or budget[0] > 1500:
            return
        budget[0] += 1
        try:
            cname = (c.Name or "").strip().lower()
            crole = (c.ControlTypeName or "").lower().replace("control", "")
            if cname and (cname == want_name or (len(want_name) > 3 and (want_name in cname or cname in want_name))):
                r = c.BoundingRectangle
                sc = 0.0
                sc += 3.0 if (cname == want_name and crole == elem.role) else (1.0 if crole == elem.role else 0.0)
                if abs(r.left - elem.bbox[0]) < 6 and abs(r.top - elem.bbox[1]) < 6:
                    sc += 3.0
                try:
                    if c.GetInvokePattern() is not None or c.GetSelectionItemPattern() is not None                             or c.GetTogglePattern() is not None or c.GetExpandCollapsePattern() is not None:
                        sc += 2.0
                except Exception:
                    pass
                if sc >= 3.0:
                    cands.append((sc, len(cands), c))
            for ch in c.GetChildren():
                _visit(ch, depth + 1)
        except Exception:
            return

    _visit(root, 0, [0])
    if not cands:
        return None
    cands.sort(key=lambda t: (-t[0], t[1]))
    return cands[0][2]


def _postmessage_action(elem: GroundedElement, verb: str, text: str) -> bool:
    """Headless retry rung used by the NO_CHANGE ladder: post straight to the element's HWND."""
    if not _IS_WINDOWS or not elem.hwnd:
        return False
    root = _root_of(elem.hwnd)
    if verb == "click":
        cx, cy = elem.center
        return hin.post_click(root, cx, cy)[0]
    if verb == "type":
        return hin.post_text(elem.hwnd, text)[0]
    return False


def _token_to_vk(tok: str) -> Optional[int]:
    return hin.token_to_vk(tok)


def _send_shortcut(combo: str, hwnd: int = 0) -> Tuple[bool, str]:
    """Deliver a key combo to ``hwnd`` as posted window messages (never physical keys)."""
    if not hwnd:
        return False, f"{hin.UNDELIVERABLE}: no target window for '{combo}'"
    return hin.post_key_combo(_root_of(hwnd), combo)


# ---------------------------------------------------------------------------
# W4 — DesktopAutonomyLoop: the closed perceive->decide->act->verify loop
# ---------------------------------------------------------------------------

@dataclass
class StepTrace:
    goal: str
    element: str
    verb: str
    verdict: str
    method: str
    evidence: str
    tiers: List[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {"goal": self.goal, "element": self.element, "verb": self.verb,
                "verdict": self.verdict, "method": self.method,
                "evidence": self.evidence, "tiers": self.tiers, "ts": self.ts}


_FILE_DIALOG_TITLES = ("save as", "save", "open", "export", "import", "browse", "select a file",
                       "select file", "choose file", "choose a file", "upload")
_OVERWRITE_CUES = ("confirm save as", "overwrite", "replace", "already exists")


def _is_file_dialog_title(title: str) -> bool:
    """A Save/Open picker is a TASK STEP the file-dialog rung resolves, not a roadblock."""
    low = (title or "").strip().lower()
    if any(c in low for c in _OVERWRITE_CUES):
        return False
    return any(low == w or low.startswith(w + " ") or low.endswith(" " + w) for w in _FILE_DIALOG_TITLES)


def _is_overwrite_confirm(title: str) -> bool:
    low = (title or "").lower()
    return any(c in low for c in _OVERWRITE_CUES)


class DesktopAutonomyLoop:
    def __init__(self, grounding: Optional[DesktopGrounding] = None,
                 verifier: Optional[DesktopVerifier] = None,
                 judge: Optional[ConstrainedJudge] = None,
                 capsule_cb: Optional[Callable[[str, str], None]] = None,
                 cursor_cb: Optional[Callable[[float, float], None]] = None,
                 session_id: Optional[str] = None):
        self.grounding = grounding or DesktopGrounding()
        self.verifier = verifier or DesktopVerifier()
        self.judge = judge or ConstrainedJudge()
        self.capsule_cb = capsule_cb or (lambda state, text: None)
        # cursor_cb drives the blue-arrow virtual cursor (magnet detaches on act)
        self.cursor_cb = cursor_cb
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self.trace: List[StepTrace] = []
        self.invalid_streak = 0
        self.awaiting_human = False
        self._history: List[str] = []
        # consecutive non-PASS attempts per goal; drives the keyboard-route recovery rung
        self._goal_fails: Dict[str, int] = {}
        self._shortcut_tried: set = set()
        self._dap = None
        # Windows kept parked off-screen for the current run (hwnd -> BackgroundSession), apps WE started, run nesting
        self._held: Dict[int, Any] = {}
        self._launched_apps: set = set()
        self._run_depth = 0
        self._last_window_mode = "not-needed"
        # W8 app-intelligence organ (None => run on perception alone)
        self.intel = _get_intel()

    @property
    def dap_core(self):
        if self._dap is None:
            self._dap = get_dap_core()
        return self._dap

    # ---- popup triage (organ_29 + generic Win32/UIA dialogs) ----
    def _triage_popups(self, app_hint: str, mode: str = "inflight") -> List[str]:
        """Resolve blocking dialogs of the target app (popup_policy), then let organ_29 take any
        remaining system-level modal. Headless; destructive/elevation prompts escalate to a human."""
        handled: List[str] = []
        if not _IS_WINDOWS:
            return handled
        from core_organs import popup_policy as pp
        hwnd = self.grounding.find_window(app_hint)
        if hwnd:
            try:
                pp.TASK.paths = tuple(getattr(self, "_task_paths", ()))
                pp.TASK.allow_destructive = bool(getattr(self, "_allow_destructive", False))
                pp.TASK.mode = mode
                res = pp.clear_blockers(hwnd, mode=mode, task_paths=getattr(self, "_task_paths", ()),
                                        allow_destructive=getattr(self, "_allow_destructive", False))
                handled.extend(res["handled"])
                if res["need_human"]:
                    self.awaiting_human = True
                    self.capsule_cb("input_needed", "A dialog needs your decision")
            except Exception as exc:
                logger.debug("[popups] policy pass note: %s", exc)

        # organ_29: anything else on top of the desktop that is not a dialog of this app
        try:
            from core_organs.organ_29_popup_handler import DesktopInteractionManager
            if getattr(self, "_o29", None) is None:
                self._o29 = DesktopInteractionManager()
            ph = self._o29
            for mhwnd, title, _cls in ph._detect_desktop_top_modals():
                low = (title or "").lower()
                if any(k in low for k in ("uac", "user account control", "elevate", "password", "administrator")):
                    self.awaiting_human = True
                    self.capsule_cb("input_needed", "Approval dialog needs you")
                    handled.append(f"uac-shield->HITL '{title[:30]}'")
                    continue
                if hwnd and hin.window_pid(mhwnd) == hin.window_pid(hwnd):
                    continue  # already handled by the policy engine
                if _is_file_dialog_title(title) or _is_overwrite_confirm(title):
                    continue
                node = ph.wrap_hwnd(mhwnd)
                if node:
                    success, _, _, action = ph.resolve_and_mitigate(node)
                    if success:
                        handled.append(f"organ29-dismissed '{title[:30]}' via '{action}'")
        except Exception as exc:
            logger.debug("[popups] organ_29 triage note: %s", exc)
        return handled

    def _click_dialog_button(self, hwnd: int, wanted: Tuple[str, ...]) -> Optional[str]:
        if not HAS_UIA:
            return False
        import uiautomation as auto
        try:
            ctrl = auto.ControlFromHandle(hwnd)
            if ctrl is None:
                return None
            stack = [ctrl]
            while stack:
                c = stack.pop()
                try:
                    role = (c.ControlTypeName or "").lower()
                    name = (c.Name or "").strip().lower()
                    if "button" in role and any(w in name for w in wanted):
                        try:
                            c.GetInvokePattern().Invoke()
                            return name
                        except Exception:
                            r = c.BoundingRectangle
                            ok, _n = hin.post_click(hwnd, (r.left + r.right) // 2, (r.top + r.bottom) // 2)
                            return name if ok else None
                    stack.extend(c.GetChildren())
                except Exception:
                    continue
        except Exception:
            pass
        return None

    # ---- native Open/Save dialog driver (organ_24 NativeFilePicker + UIA) ----
    def handle_native_file_dialog(self, path: str, confirm_words: Tuple[str, ...] =
                                  ("save", "open", "ok"),
                                  owner_hwnd: int = 0) -> Tuple[bool, str]:
        """Runs on the dedicated, initialised UIA thread (same as every other UIA action).

        ``owner_hwnd`` scopes the rung to the app being driven: a Save/Open picker belonging to
        some other still-open app must never be filled in and confirmed."""
        global _UIA_EXEC
        if _UIA_EXEC is None:
            from concurrent.futures import ThreadPoolExecutor
            _UIA_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia-act", initializer=_uia_thread_init)
        try:
            return _UIA_EXEC.submit(self._handle_native_file_dialog_impl, path, confirm_words,
                                    owner_hwnd).result(timeout=25)
        except Exception as exc:
            return False, f"file-dialog worker failed: {type(exc).__name__}: {exc}"

    def _handle_native_file_dialog_impl(self, path: str, confirm_words: Tuple[str, ...] =
                                  ("save", "open", "ok"), owner_hwnd: int = 0) -> Tuple[bool, str]:
        if not _IS_WINDOWS:
            return False, "non-windows"
        want_proc = self.grounding._process_stem_cached(owner_hwnd) if owner_hwnd else ""

        # Try organ_24 NativeFilePicker when available
        try:
            dap = self.dap_core
            if dap and hasattr(dap, "file_picker") and dap.file_picker:
                dlg = dap.file_picker.locate_dialog()
                dlg_proc = (self.grounding._process_stem_cached(int(getattr(dlg, "hwnd", 0) or 0))
                            if dlg is not None and want_proc else "")
                if dlg and not (want_proc and dlg_proc != want_proc):
                    dap.file_picker.select_path(dlg, path)
                    dap.file_picker.confirm(dlg)
                    return True, f"organ_24 file-picker selected '{path}'"
        except Exception as exc:
            logger.debug("[file-picker] organ_24 note: %s", exc)

        user32 = ctypes.windll.user32
        target = None
        foreign: List[str] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(hwnd, _l):
            nonlocal target
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value == "#32770" and user32.IsWindowVisible(hwnd):
                t = _quick_title(hwnd).lower()
                if any(w in t for w in ("save", "open", "export", "browse")):
                    if want_proc:
                        proc = self.grounding._process_stem_cached(hwnd)
                        if proc != want_proc:
                            # Somebody else's picker: never type a path into it, never click Save.
                            foreign.append(f"'{_quick_title(hwnd)}'({proc or 'unknown-proc'})")
                            return True
                    target = hwnd
            return True

        user32.EnumWindows(_cb, 0)
        if not target:
            if foreign:
                return False, (f"file-dialog belongs to another app, not the target "
                               f"({', '.join(foreign[:3])}) -> not touched")
            return False, "no-file-dialog-visible"
        if HAS_UIA:
            import uiautomation as auto
            try:
                ctrl = auto.ControlFromHandle(target)
                edits, buttons = [], []
                stack = [ctrl]
                while stack:
                    c = stack.pop()
                    try:
                        role = (c.ControlTypeName or "").lower()
                        if "edit" in role:
                            edits.append(c)
                        if "button" in role:
                            buttons.append(c)
                        stack.extend(c.GetChildren())
                    except Exception:
                        continue

                def _aid(c) -> str:
                    return (getattr(c, "AutomationId", "") or "").strip()

                # The filename box is the Edit with AutomationId 1001 / name 'File name'. The
                # first Edit in the tree is usually a file-LIST CELL ('System.ItemNameDisplay'),
                # and writing the path into that silently does nothing.
                fname = next((c for c in edits if _aid(c) == "1001"), None)                     or next((c for c in edits if "file name" in (c.Name or "").lower()
                             and not _aid(c).startswith("System.")), None)                     or next((c for c in edits if not _aid(c).startswith("System.")
                             and not (c.Name or "").lower() in ("name", "date modified", "type", "size")), None)
                if fname is None:
                    return False, "file-dialog: filename field not found"
                # Type it the way the dialog expects (real EN_CHANGE events), headless: select-all,
                # clear, then one WM_CHAR per character to the edit's own HWND. A programmatic
                # SetValue/WM_SETTEXT changes the visible text but Save keeps the old default name.
                eh = int(getattr(fname, "NativeWindowHandle", 0) or 0)
                if eh:
                    _res = ctypes.c_size_t(0)
                    hin._u32.SendMessageTimeoutW(eh, 0x00B1, 0, -1, 0x2, 800, ctypes.byref(_res))   # EM_SETSEL(0,-1)
                    hin._u32.SendMessageTimeoutW(eh, 0x0303, 0, 0, 0x2, 800, ctypes.byref(_res))    # WM_CLEAR
                    for _ch in path:
                        hin._u32.PostMessageW(eh, 0x0102, ord(_ch), 1)                                # WM_CHAR
                    time.sleep(0.6)
                else:
                    fname.GetValuePattern().SetValue(path)
                try:
                    got = fname.GetValuePattern().Value
                    if os.path.basename(path).lower() not in (got or "").lower():
                        return False, f"file-dialog: filename field did not take the value (has '{got}')"
                except Exception:
                    pass
                # Vista-style dialogs commit the typed name on an Enter delivered to the edit itself (a
                # programmatic set alone leaves the dialog's internal 'current name' untouched). Post
                # Enter to the edit's HWND; if the dialog is still up afterwards, fall back to Save.
                if eh:
                    hin.post_key_combo(eh, "enter")
                    _end = time.time() + 1.5
                    while time.time() < _end:
                        time.sleep(0.15)
                        if not hin.is_alive(target) or not hin._u32.IsWindowVisible(target):
                            return True, "file-dialog name set + Enter posted to the filename edit"
                confirm = next((b for b in buttons if _aid(b) == "1"), None)                     or next((b for b in buttons if (b.Name or "").strip().lower() in confirm_words), None)                     or next((b for b in buttons if any(w == (b.Name or "").strip().lower() for w in confirm_words)), None)
                if confirm is None:
                    return False, "file-dialog: confirm button not found"
                confirm.GetInvokePattern().Invoke()
                return True, f"file-dialog name set + clicked '{(confirm.Name or '').strip()}'"
            except Exception as exc:
                return False, f"file-dialog uia failed: {exc}"
        return False, "no-uia-for-dialog"

    # ---- W8: consult app intelligence (the "pro knowledge" layer) ----
    def _consult_intel(self, app_hint: str, goal: str) -> Optional[Dict[str, Any]]:
        """Ask organ_47 what an expert would do for this goal in this app.

        Returns a normalized dict, or None when intel is unavailable/blank:
          {kind: 'shortcut', shortcut, confidence, source, step_id}
          {kind: 'element', element_name, element_role, menu_path, confidence, ...}
        A confident LEARNED shortcut is executed directly; everything else is
        handed to the judge as a ranked hint (never as an authoritative answer).
        """
        if self.intel is None:
            return None
        try:
            pb = self.intel.playbook(app_hint, goal, allow_llm_briefing=True)
        except Exception as exc:
            logger.debug("[intel] playbook failed: %s", exc)
            return None
        if not pb or not pb.hints:
            return None
        top = pb.hints[0]
        # Best non-destructive keyboard route among ALL hints (the top hint may be an element
        # click with no shortcut, which would hide the keyboard route from the recovery rung).
        kb_route = next((h.shortcut for h in pb.hints if h.shortcut and not h.destructive), "")
        # Only a genuinely-verified shortcut may skip the judge. An unverified
        # archetype guess must never take direct control of the machine.
        if (top.shortcut and top.source == "learned"
                and top.confidence >= PRO_SHORTCUT_CONF and not top.destructive):
            return {"kind": "shortcut", "shortcut": top.shortcut,
                    "confidence": top.confidence, "source": top.source,
                    "step_id": top.step_id, "goal": goal, "kb_route": kb_route}
        return {"kind": "element", "kb_route": kb_route, "element_name": top.element_name,
                "element_role": top.element_role, "menu_path": top.menu_path,
                "verb": top.verb, "shortcut": top.shortcut,
                "confidence": top.confidence, "source": top.source,
                "step_id": top.step_id, "goal": goal}

    def _reinforce(self, app_hint: str, goal: str, pro: Optional[Dict[str, Any]],
                   verdict: str) -> None:
        """Feed the outcome back into organ_47. PASS climbs, anything else erodes."""
        if self.intel is None or not pro:
            return
        try:
            self.intel.record_step(
                app_hint, goal, pro.get("verb", "click"),
                element_name=pro.get("element_name", ""),
                element_role=pro.get("element_role", ""),
                shortcut=pro.get("shortcut", ""),
                menu_path=pro.get("menu_path", ""),
                outcome="PASS" if verdict == "PASS" else "FAIL",
                source="learned")
        except Exception as exc:
            logger.debug("[intel] reinforce failed: %s", exc)

    def _recipe_hint_for(self, goal: str) -> Optional[Dict[str, Any]]:
        """Turn the recalled organ_04 recipe into a soft judge hint for THIS goal.

        distill_recipe writes: "VERB on 'element' (method) to achieve: goal THEN ...".
        We extract the element name whose 'to achieve' clause best matches the goal and
        hand it to the ranker as an element_name hint (never as an authoritative shortcut,
        so the postcondition verifier stays the only thing that can produce a PASS)."""
        recipe = getattr(self, "_recalled_recipe", "") or ""
        if not recipe or " to achieve: " not in recipe:
            return None
        gl = (goal or "").lower().strip()
        best_name, best_score = "", 0.0
        for verb, name, achieved in re.findall(
                r"([A-Za-z_]+) on '([^']*)' \([^)]*\) to achieve:\s*(.*?)(?= THEN | \||$)", recipe):
            a = (achieved or "").lower().strip()
            gtokens = set(re.findall(r"[a-z]+", gl))
            atokens = set(re.findall(r"[a-z]+", a))
            score = len(gtokens & atokens) / (len(gtokens | atokens) or 1)
            if score > best_score:
                best_name, best_score = name, score
        if best_score < 0.34 or not best_name:
            return None
        return {"kind": "element", "element_name": best_name, "menu_path": "",
                "kb_route": "", "shortcut": "", "verb": "click",
                "confidence": round(min(0.6, best_score + 0.2), 2),
                "source": "recipe", "step_id": "", "goal": goal}

    # ---- one closed-loop step ----
    def is_app_crashed_or_hung(self, hwnd: int) -> bool:
        if not (_IS_WINDOWS and hwnd):
            return False
        try:
            if ctypes.windll.user32.IsHungAppWindow(hwnd):
                return True
            t = _quick_title(hwnd).lower()
            if "not responding" in t or "(hung)" in t:
                return True
        except Exception:
            pass
        return False

    def step(self, goal: str, app_hint: str, expect: Optional[Dict[str, Any]] = None,
             allow_destructive: bool = False, max_tier: int = 2) -> Dict[str, Any]:
        expect = expect or {}
        self._run_depth += 1                       # a bare step() (no run()) releases what it parked when it returns
        try:
            return self._step_impl(goal, app_hint, expect, allow_destructive, max_tier)
        finally:
            self._run_depth -= 1
            if self._run_depth == 0:
                self._release_held()

    def _step_impl(self, goal: str, app_hint: str, expect: Dict[str, Any],
                   allow_destructive: bool, max_tier: int) -> Dict[str, Any]:
        self._hold_hidden(app_hint)
        self._triage_popups(app_hint)

        hwnd, elements, ladder = self.grounding.ground(app_hint,
                                                      target_text=str(expect.get("element_appeared", "")),
                                                      max_tier=max_tier)

        # Crash / "Not Responding" detection: relaunch via organ_40 and resume
        if hwnd and self.is_app_crashed_or_hung(hwnd):
            logger.warning("[autonomy] App %s (hwnd=%s) is hung/crashed. Relaunching...", app_hint, hwnd)
            self.capsule_cb("working", f"Relaunching {app_hint} (not responding)")
            try:
                from core_organs.organ_40_app_launcher import resolve_and_launch
                resolve_and_launch(app_hint)
                time.sleep(2.0)
                hwnd, elements, ladder = self._wait_for_ready(app_hint)
            except Exception as e_relaunch:
                logger.error("[autonomy] Relaunch failed: %s", e_relaunch)

        if not elements:
            self.capsule_cb("working", f"Scanning {app_hint} (no controls yet)")
            entry = StepTrace(goal, "-", "-", "WRONG_STATE", "ground",
                              f"no elements; ladder={ladder}", ladder["tiers_ran"])
            self.trace.append(entry)
            return self._step_result(entry, elements=[])

        before = self.verifier.snapshot(hwnd, elements)
        if not expect:
            before.names = self._all_names(hwnd)      # the default postcondition also compares every UIA name

        # ---- Native file dialog rung: a goal naming an absolute path + a visible
        # Save/Open dialog is resolved deterministically (type path, confirm), not by the LLM.
        path_m = re.search(r"[A-Za-z]:[\\/][^\s'<>|?*]+", goal or "")
        if path_m:
            fd_ok, fd_note = self.handle_native_file_dialog(path_m.group(0), owner_hwnd=hwnd)
            logger.info("[autonomy] file-dialog rung: ok=%s note=%s", fd_ok, fd_note)
            if fd_ok:
                time.sleep(0.6)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                verdict, evidence = self.verifier.verdict(
                    expect, before, self._snap(hwnd, after_elements, expect), after_elements)
                self._history.append(f"file-dialog {path_m.group(0)} -> {verdict}")
                entry = StepTrace(goal, "file-dialog", "file-dialog", verdict, "native-file-dialog",
                                  f"{fd_note}; {evidence}", ladder["tiers_ran"])
                self.trace.append(entry)
                self._write_checkpoint(entry)
                self.capsule_cb("working", f"[{app_hint}] file dialog -> {verdict}")
                return self._step_result(entry, elements=after_elements)

        # ---- W8 PRO PATH: a confidently-learned shortcut beats the LLM ----
        pro = self._consult_intel(app_hint, goal)
        # W5 learned re-run: with no organ_47 route, fall back to the distilled recipe hint
        # (soft ranking hint only - never takes direct control, only nudges the judge).
        if pro is None:
            pro = self._recipe_hint_for(goal)
        # Recovery rung: after 2 failed attempts on this goal the element route is evidently
        # not reachable (menus often live in a popup host the UIA tree cannot see), so try the
        # expert hint's keyboard route ONCE. Non-destructive only, focus proven, and the result
        # is still judged by the postcondition (an unverified guess never counts as success).
        kb_key = (pro.get("shortcut") or pro.get("kb_route") or "") if pro is not None else ""
        kb_recovery = (pro is not None and pro["kind"] == "element" and bool(kb_key)
                       and self._goal_fails.get(goal, 0) >= 4
                       and (goal, kb_key) not in self._shortcut_tried)
        if kb_recovery:
            pro = dict(pro, shortcut=kb_key)
            self._shortcut_tried.add((goal, kb_key))
        if pro is not None and (pro["kind"] == "shortcut" or kb_recovery):
            self.capsule_cb("working", f"[{app_hint}] {pro['shortcut']} ("
                            + ("recovery" if kb_recovery else "learned pro") + ")")
            ok, method = _send_shortcut(pro["shortcut"], hwnd)
            time.sleep(0.8)  # let a dialog/menu open before verifying
            after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
            verdict, evidence = self.verifier.verdict(
                expect, before, self._snap(hwnd, after_elements, expect), after_elements)
            if verdict != "PASS" and hin.is_xaml_host(_root_of(hwnd)):
                evidence += " [XAML/WinUI host: posted keys are not delivered to XAML input - the shortcut cannot work headless; use the element route]"
                method += "+xaml-ignores-posted-keys"
            self._reinforce(app_hint, goal, pro, verdict)
            self._goal_fails[goal] = 0 if verdict == "PASS" else self._goal_fails.get(goal, 0) + 1
            self._history.append(f"shortcut {pro['shortcut']} -> {verdict}")
            entry = StepTrace(goal, f"shortcut:{pro['shortcut']}", "shortcut", verdict,
                              method, evidence + " [intel:shortcut]", ladder["tiers_ran"])
            self.trace.append(entry)
            self._write_checkpoint(entry)
            if verdict == "PASS":
                self.capsule_cb("working", f"[{app_hint}] Verified: shortcut executed")
            return self._step_result(entry, elements=after_elements)

        decision = self.judge.decide(goal, elements, app_hint=app_hint, history=self._history,
                                     pro_hint=pro)
        if not decision or decision.get("invalid"):
            self.invalid_streak += 1
            evidence = f"invalid judge choice x{self.invalid_streak}"
            if self.invalid_streak >= INVALID_CHOICE_LIMIT:
                self.awaiting_human = True
                self.capsule_cb("input_needed", "Agent needs your input")
                entry = StepTrace(goal, "-", "-", "HITL", "judge", evidence, ladder["tiers_ran"])
                self.trace.append(entry)
                return self._step_result(entry)
            entry = StepTrace(goal, "-", "-", "NO_CHANGE", "judge", evidence, ladder["tiers_ran"])
            self.trace.append(entry)
            return self._step_result(entry)
        self.invalid_streak = 0

        elem = elements[decision["element_index"]]
        verb = decision["verb"]
        text = str(decision.get("text", ""))
        if verb == "type" and text and "text_contains" not in expect:
            # A typed payload is verified by CONTENT, not by a hash: the text the judge actually
            # delivered becomes the postcondition, so a keystroke that landed cannot be called
            # NO_CHANGE (which used to make the ladder type it again) and text that went into the
            # wrong control cannot be called PASS (a path once went into 'Save as type:' and still
            # 'verified' because the dialog's pixels moved).
            expect = dict(expect, text_contains=text)

        if verb == "done":
            entry = StepTrace(goal, elem.name, "done", "PASS", "judge", "declared-done",
                              ladder["tiers_ran"])
            self.trace.append(entry)
            self.capsule_cb("working", f"[{app_hint}] Verified: goal completed")
            return self._step_result(entry)

        # Blast radius guard: destructive element names need explicit opt-in.
        if any(cue in (elem.name or "").lower() for cue in DESTRUCTIVE_CUES) \
                and not allow_destructive:
            self.awaiting_human = True
            self.capsule_cb("input_needed", f"About to '{elem.name[:30]}' — confirm?")
            entry = StepTrace(goal, elem.name, verb, "HITL", "safety",
                              "destructive cue without allow_destructive", ladder["tiers_ran"])
            self.trace.append(entry)
            return self._step_result(entry)

        self.capsule_cb("working", f"[{app_hint}] {verb} '{elem.name[:30]}'")
        if self.cursor_cb:
            try:
                cx, cy = elem.center
                self.cursor_cb(float(cx), float(cy))
            except Exception:
                pass

        ok, method = _act_on_element(elem, verb, text)
        if not ok:
            # Delivery itself failed, so nothing that the UI does afterwards may be read as success.
            # A real run once "PASSed" a type whose window had already gone (UNDELIVERABLE), because
            # an unrelated structure change satisfied the default postcondition. Force NO_CHANGE and
            # re-ground on the next attempt; the retry ladder below is skipped on purpose, since
            # re-delivering into a control that refused the first time is how text got duplicated.
            self._goal_fails[goal] = self._goal_fails.get(goal, 0) + 1
            self._history.append(f"{verb} '{elem.name}' undeliverable")
            entry = StepTrace(goal, elem.name, verb, "NO_CHANGE", method,
                              "action not delivered -> never a PASS regardless of UI diff",
                              ladder["tiers_ran"])
            self.trace.append(entry)
            self._write_checkpoint(entry)
            self.capsule_cb("working", f"[{app_hint}] not delivered: {method[:44]}")
            return self._step_result(entry, elements=elements)
        if ok and verb in ("click", "invoke", "key", "shortcut"):
            self._settle(hwnd)

        # Verification step
        after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
        verdict, evidence = self.verifier.verdict(expect, before,
                                                  self._snap(hwnd, after_elements, expect),
                                                  after_elements)

        # NO_CHANGE retry ladder through organ_24 RecoveryEngine sequence:
        # wait/reinvoke -> PostMessage -> physical click
        if verdict == "NO_CHANGE" and ok:
            # 1. Brief wait + re-invoke
            time.sleep(0.3)
            _act_on_element(elem, "invoke" if verb == "click" else verb, text)
            after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
            after_re = self._snap(hwnd, after_elements, expect)
            verdict, evidence = self.verifier.verdict(expect, before, after_re, after_elements)
            method += "+retry-invoke"

            # 2. If still NO_CHANGE, try PostMessage
            if verdict == "NO_CHANGE" and elem.hwnd:
                _postmessage_action(elem, verb, text)
                time.sleep(0.2)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                after_pm = self._snap(hwnd, after_elements, expect)
                verdict, evidence = self.verifier.verdict(expect, before, after_pm, after_elements)
                method += "+retry-postmessage"

            # 3. If still NO_CHANGE, post a coordinate click to the exact window (headless)
            if verdict == "NO_CHANGE":
                cx, cy = elem.center
                hin.post_click(_root_of(elem.hwnd or hwnd), cx, cy)
                time.sleep(0.25)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                after2 = self._snap(hwnd, after_elements, expect)
                verdict, evidence = self.verifier.verdict(expect, before, after2, after_elements)
                method += "+retry-postclick"

        # A posted KEY into a XAML/WinUI host is not delivered by that UI stack: say so (and keep the verdict honest)
        # instead of letting it look like an unexplained NO_CHANGE.
        if verb in ("key", "shortcut") and verdict != "PASS" and hin.is_xaml_host(_root_of(hwnd)):
            evidence += " [XAML/WinUI host: posted keys are not delivered to XAML input - use a UIA-invokable element instead]"
            method += "+xaml-ignores-posted-keys"
            self._history.append(f"{verb} ignored by a XAML host")

        # On WRONG_STATE, triage popups first to dismiss unexpected roadblocks, then re-check
        if verdict == "WRONG_STATE":
            popup_notes = self._triage_popups(app_hint)
            if popup_notes:
                evidence += " | cleared: " + "; ".join(popup_notes)
                time.sleep(0.2)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                after_pop = self._snap(hwnd, after_elements, expect)
                verdict, evidence = self.verifier.verdict(expect, before, after_pop, after_elements)

        if verdict == "PASS":
            popup_notes = self._triage_popups(app_hint)
            if popup_notes:
                evidence += " | popups: " + "; ".join(popup_notes)
            # Capsule reports verified outcome, never bare "clicked"
            outcome_desc = evidence.replace(";", ",") if evidence else f"{verb} completed"
            self.capsule_cb("working", f"[{app_hint}] Verified: {outcome_desc[:36]}")

        # Reinforce the app-intelligence organ with the verified (or failed)
        # outcome, so the next run against this app gets a stronger honest prior.
        self._reinforce(app_hint, goal, {"kind": "element", "verb": verb,
                        "element_name": elem.name, "element_role": elem.role}, verdict)

        self._goal_fails[goal] = 0 if verdict == "PASS" else self._goal_fails.get(goal, 0) + 1
        self._history.append(f"{verb} '{elem.name}' -> {verdict}")
        entry = StepTrace(goal, elem.name, verb, verdict, method, evidence, ladder["tiers_ran"])
        self.trace.append(entry)
        self._write_checkpoint(entry)
        return self._step_result(entry, elements=after_elements)

    def _control_text(self, elements: List[GroundedElement]) -> str:
        """Longest readable text among the editable controls (UIA value/text pattern)."""
        best = ""
        checked = 0
        for e in elements:
            if (e.role or "").lower() not in ("edit", "document", "text", "richedit", "combobox"):
                continue
            if e.tier != "uia" or checked >= 6:
                continue
            checked += 1
            out = _uia_dispatch(e, "read", "")
            got = out[1] if out and out[0] is True else ""
            if isinstance(got, str) and len(got) > len(best):
                best = got
            if len(best) >= 4000:
                break
        return best[:8000]

    def _snap(self, hwnd: int, elements: List[GroundedElement],
              expect: Optional[Dict[str, Any]] = None) -> Snapshot:
        """Snapshot, reading control text only when a postcondition actually asks for it (the UIA
        value read costs a round trip per editable control)."""
        want_text = bool((expect or {}).get("text_contains"))
        snap = self.verifier.snapshot(hwnd, elements,
                                      text=self._control_text(elements) if want_text else "")
        if (expect or {}).get("name_visible") or not expect:
            snap.names = self._all_names(hwnd)
        return snap

    def _all_names(self, hwnd: int) -> List[str]:
        """Lower-cased name of EVERY UIA node of the window and its popups (one bulk CacheRequest snapshot)."""
        names: List[str] = []
        try:
            from core_organs import fast_uia
            for w in [hwnd] + hin.popup_windows(hwnd)[:6]:
                names += [(n.name or "").lower() for n in (fast_uia.snapshot(w, timeout_ms=3000) or []) if n.name]
        except Exception as exc:
            logger.debug("[verify] name read failed: %s", exc)
        return names

    def _settle(self, hwnd: int, timeout_s: float = 1.6, interval_s: float = 0.22) -> int:
        """Wait (bounded) until the app's element tree - popups/menus/dialogs included - stops
        changing. Menus and flyouts populate after the click returns; grounding too early sees
        the old UI and the loop would act on stale state (it re-clicked 'File' forever)."""
        if not HAS_UIA:
            time.sleep(0.4)
            return 0

        def _sig() -> Tuple[int, int, int]:
            main = len(self.grounding._walk_uia(hwnd, max_depth=8, max_nodes=300))
            extra = hin.popup_windows(hwnd)[:10]
            return main, len(extra), sum(len(self.grounding._walk_uia(w, max_depth=6, max_nodes=120)) for w in extra)

        deadline = time.time() + timeout_s
        last, stable, polls = _sig(), 0, 1
        while time.time() < deadline and stable < 2:
            time.sleep(interval_s)
            cur = _sig()
            polls += 1
            stable = stable + 1 if cur == last else 0
            last = cur
        return polls

    def resume_session(self, session_id: str, app_hint: str = "") -> Optional[Dict[str, Any]]:
        """Resume execution from a persisted checkpoint: relaunch app, restore trace, re-ground."""
        cp = self.load_checkpoint(session_id)
        if not cp:
            return None
        self.session_id = session_id
        recent = cp.get("recent", [])
        if recent:
            self.trace = [
                StepTrace(goal=t["goal"], element=t["element"], verb=t["verb"],
                          verdict=t["verdict"], method=t["method"],
                          evidence=t["evidence"], tiers=t.get("tiers", []))
                for t in recent
            ]
        if app_hint and not self.grounding.find_window(app_hint):
            try:
                from core_organs.organ_40_app_launcher import resolve_and_launch
                resolve_and_launch(app_hint)
                time.sleep(1.5)
            except Exception:
                pass
            self._wait_for_ready(app_hint)
        return cp

    def _hold_hidden(self, app_hint: str) -> Optional[int]:
        """Find the app's window and, when it is MINIMIZED, keep it parked off-screen (laid out, never on a monitor,
        focus untouched) until this run ends. A window of an app WE started that has just appeared on the user's
        screen (the splash -> main-frame handoff) is minimized first. A window the user is looking at, and any
        window of an app we did not start, is left exactly where it is."""
        hwnd = self.grounding.find_window(app_hint)
        if not hwnd:
            return None
        if hwnd in self._held:
            return hwnd
        from core_organs import background_window as bw
        ours = bw.is_ours(hwnd) or (app_hint or "").lower() in self._launched_apps
        if ours:
            bw.mark_ours(hwnd)
            if not hin.is_minimized(hwnd) and hin.is_alive(hwnd) and bw.user_can_see(hwnd):
                ctypes.windll.user32.ShowWindow(hwnd, 7)            # SW_SHOWMINNOACTIVE: put it away, take no focus
                time.sleep(0.12)
        if hin.is_minimized(hwnd):
            sess = bw.BackgroundSession(hwnd)
            sess.__enter__()
            self._last_window_mode = sess.mode or "failed"
            if sess.mode == "parked":
                self._held[hwnd] = sess
                logger.info("[autonomy] %s hwnd=%s held parked off-screen", app_hint, hwnd)
            else:
                sess.__exit__(None, None, None)
        return hwnd

    def _release_held(self) -> None:
        for hwnd, sess in list(self._held.items()):
            try:
                sess.__exit__(None, None, None)
            except Exception:
                pass
        self._held.clear()
        # "apps we started" is PER-RUN state: the loop is a process-wide singleton, and a window the USER opens later
        # under the same app name must never be treated as ours (minimized / parked). Windows we created stay known
        # precisely, by handle, through background_window.is_ours().
        self._launched_apps.clear()

    def _tame_family(self, app_hint: str) -> None:
        """Cheap sweep during an extended startup wait: any visible window of an app WE started goes straight back
        to minimized (a splash chain keeps creating new top-levels)."""
        if (app_hint or "").lower() not in self._launched_apps:
            return
        try:
            from core_organs import background_window as bw
            for h in self.grounding.find_window(app_hint, all_candidates=True):
                if hin.is_alive(h) and not hin.is_minimized(h) and h not in self._held and bw.user_can_see(h):
                    ctypes.windll.user32.ShowWindow(h, 7)
                    bw.mark_ours(h)
        except Exception:
            pass

    def _wait_for_ready(self, app_hint: str, target_text: str = "",
                        max_tier: int = 2) -> Tuple[Optional[int], List[GroundedElement], Dict[str, Any]]:
        """Readiness poll: bring up the target and wait (bounded, growing waits) until it exposes a live control
        tree. Prevents 'still booting' from being misread as an empty/wrong state on heavy apps.

        The deadline is READY_TIMEOUT_S for an app that shows no sign of starting; while its window set changes or
        its processes keep working the deadline slides out by READY_GRACE_S, never beyond READY_HARD_CAP_S. A tiny
        window is not 'ready' until it has stayed the same for a poll (a splash vanishes; a real UI does not)."""
        t0 = time.time()
        deadline = t0 + READY_TIMEOUT_S
        hard = t0 + READY_HARD_CAP_S
        delay = READY_BACKOFF_S
        hwnd, elements, report = None, [], {}
        last_sig, last_cpu, stable, extended = None, 0.0, 0, 0.0
        while True:
            self._hold_hidden(app_hint)
            hwnd, elements, report = self.grounding.ground(
                app_hint, target_text=target_text, max_tier=max_tier)
            if hwnd and len(elements) >= READY_RICH_ELEMENTS:
                break                                  # a real UI is up: skip the (slower) startup-activity probe
            sig, cpu = self.grounding.family_activity(app_hint)
            progressing = (last_sig is not None and sig != last_sig) or (last_sig is not None and cpu - last_cpu > 0.15)
            if progressing and time.time() < hard:
                new_deadline = min(hard, time.time() + READY_GRACE_S)
                if new_deadline > deadline:
                    extended += new_deadline - deadline
                    deadline = new_deadline
            stable = 0 if (last_sig is not None and sig != last_sig) else stable + 1
            last_sig, last_cpu = sig, cpu
            if hwnd and elements and stable >= 1:
                break
            if time.time() >= deadline:
                break
            self.capsule_cb("working", f"Waiting for {app_hint} to be ready")
            end = time.time() + delay
            while time.time() < end:                 # sleep in slices so a new splash-chain window is put away fast
                time.sleep(0.1)
                self._tame_family(app_hint)
            delay = min(delay * 1.6, READY_BACKOFF_MAX_S)
        report = dict(report or {})
        report["ready_wait_s"] = round(time.time() - t0, 2)
        if extended:
            report["ready_deadline_extended_s"] = round(extended, 1)
        return hwnd, elements, report

    def run(self, goals: List[str], app_hint: str, max_steps_per_goal: int = 4,
            allow_destructive: bool = False,
            expect_map: Optional[Dict[int, Dict[str, Any]]] = None,
            max_tier: int = 2) -> Dict[str, Any]:
        """Execute ordered micro-goals. Each goal gets up to max_steps_per_goal
        closed-loop attempts; a PASS or declared-done advances to the next goal. A minimized target is held parked
        off-screen for the whole run and put back as it was when the run ends."""
        self._run_depth += 1
        try:
            return self._run_impl(goals, app_hint, max_steps_per_goal, allow_destructive, expect_map, max_tier)
        finally:
            self._run_depth -= 1
            if self._run_depth == 0:
                self._release_held()

    def _run_impl(self, goals: List[str], app_hint: str, max_steps_per_goal: int,
                  allow_destructive: bool,
                  expect_map: Optional[Dict[int, Dict[str, Any]]], max_tier: int) -> Dict[str, Any]:
        expect_map = expect_map or {}
        # The loop object is a process-wide singleton: per-RUN state must not leak from the previous run
        # (stale 'already tried' history made the judge avoid exactly the steps that had worked).
        self._history = []
        self._goal_fails = {}
        self._shortcut_tried = set()
        self.invalid_streak = 0
        self.awaiting_human = False
        self._task_paths = tuple(m.group(0) for g_ in goals
                                 for m in re.finditer(r"[A-Za-z]:[\\/][^\s'<>|?*]+", g_ or ""))
        self._allow_destructive = bool(allow_destructive)
        # W5 learned re-run: pull the distilled recipe for this task once. It is a soft hint
        # only - the postcondition verifier still judges every step, so a stale/wrong recall
        # can never fake a PASS; it just points the judge at the element that worked last time.
        self._recalled_recipe = self.recall_recipe(" / ".join(goals), app_hint) or ""
        if self._recalled_recipe:
            logger.info("[learn] recalled recipe for %s: %s", app_hint, self._recalled_recipe[:160])
        # Clear the deck: stale dialogs from earlier runs must not be mistaken for task UI.
        cleared = self._triage_popups(app_hint, mode="preflight")
        if cleared:
            logger.info("[autonomy] preflight cleared: %s", cleared)
        # Readiness backoff up front: never start acting on an app that is still
        # booting or was never brought up — surface to human instead of flailing.
        _rhwnd, _relts, _rrep = self._wait_for_ready(app_hint)
        if not _rhwnd or not _relts:
            self.awaiting_human = True
            self.capsule_cb("input_needed", f"{app_hint} not ready (no controls)")
            reason = (_rrep or {}).get("reason", "no-controls-within-ready-window")
            return {"completed": False, "blocked_at_goal": 0, "steps": 0,
                    "awaiting_human": True, "ready_reason": reason,
                    "trace": [t.as_dict() for t in self.trace]}
        results = []
        for gi, goal in enumerate(goals):
            advanced = False
            self.grounding.reset_vision_budget()
            for _ in range(max_steps_per_goal):
                res = self.step(goal, app_hint, expect=expect_map.get(gi),
                                allow_destructive=allow_destructive, max_tier=max_tier)
                results.append(res)
                if res["verdict"] == "PASS" or self.awaiting_human:
                    advanced = True
                    break
            if self.awaiting_human:
                break
            if not advanced:
                return {"completed": False, "blocked_at_goal": gi, "steps": len(results),
                        "trace": [t.as_dict() for t in self.trace]}
        return {"completed": not self.awaiting_human, "steps": len(results),
                "trace": [t.as_dict() for t in self.trace],
                "awaiting_human": self.awaiting_human}

    # ---- checkpoint + resume ----
    def _checkpoint_path(self) -> str:
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        return os.path.join(CHECKPOINT_DIR, f"{self.session_id}.json")

    def _write_checkpoint(self, entry: StepTrace) -> None:
        try:
            payload = {"session_id": self.session_id, "steps": len(self.trace),
                       "last": entry.as_dict(),
                       "recent": [t.as_dict() for t in self.trace[-25:]]}
            with open(self._checkpoint_path(), "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
        except Exception as exc:
            logger.debug("[checkpoint] write failed: %s", exc)

    @staticmethod
    def load_checkpoint(session_id: str) -> Optional[Dict[str, Any]]:
        p = os.path.join(CHECKPOINT_DIR, f"{session_id}.json")
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    # ---- W5: skill distillation to organ_04 knowledge ----------------------
    def distill_recipe(self, task_goal: str, app_name: str) -> Tuple[bool, str]:
        passes = [t for t in self.trace if t.verdict == "PASS"]
        if len(passes) < 2:
            return False, "not enough verified steps to distill"
        lines = []
        for t in passes:
            lines.append(f"{t.verb.upper()} on '{t.element}' ({t.method}) to achieve: {t.goal}")
        recipe = (f"SKILL[{app_name}] goal='{task_goal}': " + " THEN ".join(lines)
                  + f" | tiers={sorted({tt for t in passes for tt in t.tiers})}")
        try:
            from core_organs.organ_04_knowledge import KnowledgeOrgan, QueryDispatcher
            root = os.environ.get("HOJAIGA_KNOWLEDGE_ROOT",
                                  os.path.join(r"D:\new_automation", "organ_04_knowledge"))
            organ = KnowledgeOrgan(root_dir=root)

            async def _flow():
                await organ.start()
                res = await organ.dispatcher.dispatch(
                    QueryDispatcher.OP_INGEST_KNOWLEDGE,
                    {"doc_type": "skill_recipe", "content_text": recipe})
                await organ.stop()
                return res
            res = asyncio.run(_flow())
            return bool(res.get("ingested_chunks", 0) > 0), f"recipe ingested to organ_04 ({len(lines)} verified steps)"
        except Exception as exc:
            logger.debug("[learn] distill failed: %s", exc)
            return False, f"distill unavailable: {exc}"

    @staticmethod
    def recall_recipe(goal: str, app_name: str) -> str:
        """Retrieve learned recipe text for a similar goal (empty when none)."""
        try:
            from core_organs.organ_04_knowledge import KnowledgeOrgan, QueryDispatcher
            root = os.environ.get("HOJAIGA_KNOWLEDGE_ROOT",
                                  os.path.join(r"D:\new_automation", "organ_04_knowledge"))
            organ = KnowledgeOrgan(root_dir=root)

            async def _flow():
                await organ.start()
                res = await organ.dispatcher.dispatch(
                    QueryDispatcher.OP_SEARCH_KNOWLEDGE,
                    {"text": f"SKILL {app_name} {goal}", "limit": 3})
                await organ.stop()
                matches = res.get("matches", []) if isinstance(res, dict) else []
                for h in matches:
                    content = (h.get("snippet") or h.get("content") or h.get("chunk") or h.get("text") or "") if isinstance(h, dict) else str(h)
                    if content.startswith("SKILL["):
                        return content
                return ""
            return asyncio.run(_flow())
        except Exception as exc:
            logger.debug("[learn] recall unavailable: %s", exc)
            return ""

    def _step_result(self, entry: StepTrace, elements: List[GroundedElement] = None) -> Dict[str, Any]:
        return {"verdict": entry.verdict, "element": entry.element, "verb": entry.verb,
                "method": entry.method, "evidence": entry.evidence,
                "tiers_ran": entry.tiers, "awaiting_human": self.awaiting_human,
                "seen_elements": len(elements or []), "session": self.session_id}


_WEBAPP_WATCHER = None
_LOOP_SINGLETON: Optional[DesktopAutonomyLoop] = None


def split_goals(goals: str) -> List[str]:
    """Newline / semicolon / lowercase-comma separated micro-goals -> ordered list."""
    return [g.strip() for g in re.split(r"[\n;]+|(?<=[a-z]),\s", goals or "") if g and g.strip()]


def operate_app(app_name: str, goals, allow_destructive: bool = False,
                capsule_cb=None, cursor_cb=None, max_steps_per_goal: int = 5,
                expect_map: Optional[Dict[int, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The whole 'leave the bot working' flow in one callable (the CrewAI
    operate_desktop_tool delegates here, and the E2E suite calls it directly):

      self-sufficient launch -> closed-loop run -> recipe distillation on success.

    Returns the loop result dict plus: goals, launched, recipe, elapsed_s.
    """
    t0 = time.perf_counter()
    goal_list = list(goals) if isinstance(goals, (list, tuple)) else split_goals(goals)
    if not goal_list:
        return {"completed": False, "steps": 0, "trace": [], "goals": [],
                "error": "no goals provided"}
    loop = get_loop(capsule_cb=capsule_cb, cursor_cb=cursor_cb)
    loop.trace = []  # one trace per operate_app call (the loop is a shared singleton)
    loop.awaiting_human = False
    launched = _launch_if_missing(loop, app_name, capsule_cb)
    if launched:
        loop._launched_apps.add((app_name or "").lower())
    # No fixed sleep after the launch: run() starts with _wait_for_ready (bounded, growing waits, polling the live
    # control tree), which is what a slow starter (Steam's splash chain, Office, packaged apps) actually needs.
    # A minimized window is held parked off-screen by the loop for the whole run (laid out, never on a monitor,
    # focus untouched) and put back exactly as it was; a window the user can see is left exactly where it is.
    loop._last_window_mode = "not-needed"
    result = loop.run(goal_list, app_name, max_steps_per_goal=max_steps_per_goal,
                      allow_destructive=allow_destructive, expect_map=expect_map)
    result["window_mode"] = loop._last_window_mode
    try:
        if result.get("completed"):
            ok, note = loop.distill_recipe(" / ".join(goal_list), app_name)
            result["recipe"] = note
            result["recipe_ingested"] = bool(ok)
    except Exception:
        pass
    hwnd = loop.grounding.find_window(app_name) or 0
    if launched and hwnd:
        _mark_ours(hwnd)
    result.update(goals=goal_list, launched=launched, hwnd=hwnd,
                  window_title=loop.grounding.window_title(hwnd) if hwnd else "",
                  elapsed_s=round(time.perf_counter() - t0, 2))
    return result


def _mark_ours(hwnd: int) -> None:
    try:
        from core_organs import background_window as bw
        bw.mark_ours(hwnd)
    except Exception:
        pass


def _launch_if_missing(loop: "DesktopAutonomyLoop", app_name: str, capsule_cb=None) -> bool:
    """Start the app only when no window for it exists (single instance, never a second copy).

    Launched MINIMIZED and unfocused (universal_scan.launch_hidden: every new window is minimized the instant it
    appears) so a task never pops a window onto the user's screen. Only an app the Start menu does not know falls
    back to the organ_40 resolver (aliases / catalog / crawl)."""
    try:
        if loop.grounding.find_window(app_name):
            return False
        if capsule_cb:
            capsule_cb("working", f"Launching {app_name}")
        try:
            from core_organs import universal_scan as us
            info = us.launch_hidden(app_name, timeout_s=30.0)
            if info.get("hwnd"):
                return True
            if not any("not in the Start menu" in n for n in info.get("notes", [])):
                return True          # it was started but showed no window yet: poll for it, never start a second copy
        except Exception as exc:
            logger.debug("[operate_app] hidden launch unavailable: %s", exc)
        from core_organs.organ_40_app_launcher import resolve_and_launch
        resolve_and_launch(app_name)
        return True
    except Exception as exc:
        logger.debug("[operate_app] auto-launch note: %s", exc)
        return False


def prepare_app(app_name: str, capsule_cb=None, cursor_cb=None) -> Dict[str, Any]:
    """Bring an app to a usable state WITHOUT choosing or performing any UI action: launch if missing, clear stale
    dialogs, then wait (bounded, backoff) for a live control tree. Used for a command that only says 'open X'."""
    t0 = time.perf_counter()
    loop = get_loop(capsule_cb=capsule_cb, cursor_cb=cursor_cb)
    loop.awaiting_human = False
    launched = _launch_if_missing(loop, app_name, capsule_cb)
    if launched:
        loop._launched_apps.add((app_name or "").lower())
    loop._run_depth += 1
    try:
        try:
            loop._triage_popups(app_name, mode="preflight")
        except Exception as exc:
            logger.debug("[prepare_app] preflight note: %s", exc)
        hwnd, elements, report = loop._wait_for_ready(app_name)
    finally:
        loop._run_depth -= 1
        if loop._run_depth == 0:
            loop._release_held()
    if launched and hwnd:
        _mark_ours(hwnd)
    ready = bool(hwnd and elements) and not loop.awaiting_human
    return {"ready": ready, "hwnd": hwnd or 0, "launched": launched, "elements": len(elements or []),
            "window_title": loop.grounding.window_title(hwnd) if hwnd else "",
            "awaiting_human": loop.awaiting_human,
            "ready_reason": "" if ready else (report or {}).get("reason", "no-controls-within-ready-window"),
            "elapsed_s": round(time.perf_counter() - t0, 2)}


def get_loop(capsule_cb=None, cursor_cb=None) -> DesktopAutonomyLoop:
    global _LOOP_SINGLETON
    if _LOOP_SINGLETON is None:
        _LOOP_SINGLETON = DesktopAutonomyLoop(capsule_cb=capsule_cb, cursor_cb=cursor_cb)
        DesktopGrounding.start_warmup()   # load OmniParser once, off the goal path
        if os.environ.get("HOJAIGA_WEBAPP_WATCH", "1") != "0":
            try:   # learn every NEW web app origin (gmail, linkedin, ...) the moment Chrome shows it
                from core_organs import app_scan
                global _WEBAPP_WATCHER
                _WEBAPP_WATCHER = app_scan.WebAppWatcher()
                _WEBAPP_WATCHER.start()
            except Exception as exc:
                logger.debug("webapp watcher not started: %s", exc)
    else:
        if capsule_cb:
            _LOOP_SINGLETON.capsule_cb = capsule_cb
        if cursor_cb:
            _LOOP_SINGLETON.cursor_cb = cursor_cb
    return _LOOP_SINGLETON
