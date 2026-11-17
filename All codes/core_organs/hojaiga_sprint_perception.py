"""
HOJAIGA SPRINT: Perception Engine
Real app structure scanning via the Windows UI Automation tree.

Why not win32 EnumChildWindows: modern apps (Notepad, Calculator, Office, Chrome,
Electron) draw their own controls inside ONE top-level window, so child-window
enumeration returns an empty list even when the app has 300 on-screen controls.
UIA is the only API that sees what the user sees.
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uiautomation as auto

MISSING = []
try:
    import mss
    import numpy as np
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment guard
    mss = np = Image = None
    MISSING.append(str(exc))

# Control types that can be acted on.
ACTIONABLE_TYPES = {
    "ButtonControl", "CheckBoxControl", "RadioButtonControl", "TabItemControl",
    "MenuItemControl", "SplitButtonControl", "HyperlinkControl", "ToggleButtonControl",
    "ListItemControl", "ThumbControl",
}
EDITABLE_TYPES = {"EditControl", "DocumentControl", "ComboBoxControl", "SpinnerControl"}

# Which UIA pattern each control type is driven through. Checked with ONE GetPattern
# call per element (uiautomation has no IsPatternSupported; asking for the pattern
# returns None when the control does not support it).
TYPE_TO_PATTERN = {
    "ButtonControl": auto.PatternId.InvokePattern,
    "MenuItemControl": auto.PatternId.InvokePattern,
    "HyperlinkControl": auto.PatternId.InvokePattern,
    "TabItemControl": auto.PatternId.SelectionItemPattern,
    "ListItemControl": auto.PatternId.SelectionItemPattern,
    "RadioButtonControl": auto.PatternId.SelectionItemPattern,
    "CheckBoxControl": auto.PatternId.TogglePattern,
    "SplitButtonControl": auto.PatternId.ExpandCollapsePattern,
    "ComboBoxControl": auto.PatternId.ExpandCollapsePattern,
    "EditControl": auto.PatternId.ValuePattern,
    "DocumentControl": auto.PatternId.ValuePattern,
    "SpinnerControl": auto.PatternId.ValuePattern,
}
ACTION_NAMES = {
    auto.PatternId.InvokePattern: "invoke",
    auto.PatternId.TogglePattern: "toggle",
    auto.PatternId.ExpandCollapsePattern: "expand",
    auto.PatternId.SelectionItemPattern: "select",
    auto.PatternId.ValuePattern: "type",
}


def _detect_action(ctrl):
    """One COM call: the action this control can be driven by, or None."""
    ctype = ctrl.ControlTypeName
    candidates = [TYPE_TO_PATTERN[ctype]] if ctype in TYPE_TO_PATTERN else []
    if not candidates:
        # Unknown type: ask the three cheap questions in order of likelihood.
        candidates = [auto.PatternId.InvokePattern, auto.PatternId.ExpandCollapsePattern,
                      auto.PatternId.TogglePattern]
    for pattern_id in candidates:
        try:
            if ctrl.GetPattern(pattern_id) is not None:
                return ACTION_NAMES[pattern_id]
        except Exception:
            continue
    return None


def _normalize(text):
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).strip()


def list_windows():
    """Visible top-level windows: [{hwnd, title, class, process, rect}]"""
    import psutil
    out = []
    for ctrl in auto.GetRootControl().GetChildren():
        try:
            rect = ctrl.BoundingRectangle
            if ctrl.ClassName in ("Shell_SecondLayer", "Windows.UI.Composition.DesktopWindowContentBridge") and not ctrl.Name:
                continue
            try:
                proc = psutil.Process(ctrl.ProcessId).name()
            except Exception:
                proc = ""
            out.append({
                "hwnd": ctrl.NativeWindowHandle,
                "title": ctrl.Name or "",
                "class": ctrl.ClassName or "",
                "process": proc,
                "pid": ctrl.ProcessId,
                "rect": (rect.left, rect.top, rect.width(), rect.height()),
            })
        except Exception:
            continue
    return out


def find_window(query, include_desktop=False):
    """Resolve a human string ('Notepad', 'untitled - notepad', 'calc.exe') to a window.

    Returns the best UIA WindowControl, or None. Scored so that a title match beats a
    process match and an exact title beats a substring.
    """
    q = _normalize(query).replace(".exe", "")
    if not q:
        return None
    terms = q.split()

    import psutil
    best, best_score = None, 0.0
    for ctrl in auto.GetRootControl().GetChildren():
        try:
            title = _normalize(ctrl.Name)
            cls = _normalize(ctrl.ClassName)
            try:
                proc = _normalize(psutil.Process(ctrl.ProcessId).name()).replace(".exe", "")
            except Exception:
                proc = ""
            rect = ctrl.BoundingRectangle
            visible = rect.width() > 1 and rect.height() > 1
            if not visible and not include_desktop:
                continue

            score = 0.0
            if title == q:
                score = 100
            elif all(t in title for t in terms):
                score = 60 + 20 * (len(q) / max(len(title), 1))
            elif any(t in title for t in terms):
                score = 35
            elif proc == q or q in proc:
                score = 45
            elif q in cls:
                score = 25
            if score > best_score:
                best, best_score = ctrl, score
        except Exception:
            continue
    return best


def ensure_foreground(window):
    """Raise a window to the true foreground; return True only if it ended up front.

    This is not cosmetic: mss/PIL capture reads whatever pixels are physically on
    screen, and OCR of a window that is not actually on top reads the app that IS on
    top - the wrong app entirely. window.SetActive() alone is not enough when another
    process holds the foreground, because Windows refuses SetForegroundWindow for a
    background process; attaching to the foreground thread's input queue lets the
    raise land. We never maximise or resize - only bring forward.
    """
    import ctypes
    try:
        u = ctypes.windll.user32
        hwnd = window.NativeWindowHandle
        if not hwnd:
            return False
        if u.IsIconic(hwnd):
            try:
                window.Restore()
            except Exception:
                pass
            time.sleep(0.3)
        if u.GetForegroundWindow() == hwnd:
            return True
        try:
            window.SetActive()
        except Exception:
            pass
        time.sleep(0.2)
        if u.GetForegroundWindow() == hwnd:
            return True
        fg = u.GetForegroundWindow()
        fg_tid = u.GetWindowThreadProcessId(fg, None)
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        attached = (bool(fg_tid) and fg_tid != cur_tid
                    and bool(u.AttachThreadInput(cur_tid, fg_tid, True)))
        try:
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
            u.SetActiveWindow(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(cur_tid, fg_tid, False)
        time.sleep(0.25)
        return u.GetForegroundWindow() == hwnd
    except Exception:
        return False


class HOJAIGAPerception:
    """Fast UIA-first perception of any window."""

    def __init__(self, enable_ocr=False):
        self.enable_ocr = enable_ocr
        self._ocr = None
        self._ocr_tried = False
        self._last_grab_origin = None  # (left, top) of the most recent window capture

    # ---- screenshots -----------------------------------------------------
    def grab_region(self, rect):
        """Screenshot a screen rectangle -> PIL Image (window-scoped, so state diffs
        are not polluted by the clock in the taskbar). Records the true (clamped)
        capture origin on self._last_grab_origin, because OCR boxes are measured from
        there - not from rect, which for a maximised window starts at -9."""
        self._last_grab_origin = None
        if mss is None:
            return None
        with mss.MSS() as sct:
            virtual = sct.monitors[0]  # union of all monitors, in API coordinates
            left = max(rect[0], virtual["left"])
            top = max(rect[1], virtual["top"])
            right = min(rect[0] + rect[2], virtual["left"] + virtual["width"])
            bottom = min(rect[1] + rect[3], virtual["top"] + virtual["height"])
            if right - left < 4 or bottom - top < 4:
                return None
            shot = sct.grab({"left": left, "top": top, "width": right - left, "height": bottom - top})
            self._last_grab_origin = (left, top)
            return Image.frombytes("RGB", shot.size, shot.rgb)

    # ---- UIA tree --------------------------------------------------------
    def _describe(self, ctrl, depth, window_rect):
        try:
            rect = ctrl.BoundingRectangle
        except Exception:
            return None
        try:
            name = (ctrl.Name or "").strip()
            aid = (ctrl.AutomationId or "").strip()
            ctype = ctrl.ControlTypeName
        except Exception:
            return None

        action = _detect_action(ctrl)
        if action == "type" and ctype not in EDITABLE_TYPES:
            action = None

        on_screen = rect.width() > 1 and rect.height() > 1
        if not name and aid:
            name = aid
        return {
            "label": (name or ctype.replace("Control", ""))[:80],
            "control_type": ctype.replace("Control", ""),
            "x": rect.left, "y": rect.top,
            "width": rect.width(), "height": rect.height(),
            "depth": depth,
            "action": action,
            "enabled": bool(ctrl.IsEnabled),
            "offscreen": not on_screen,
            "in_window": (rect.left >= window_rect[0] - 4 and rect.top >= window_rect[1] - 4
                          and rect.right <= window_rect[0] + window_rect[2] + 4
                          and rect.bottom <= window_rect[1] + window_rect[3] + 4),
        }

    def _extract_uia_tree(self, window_ctrl, window_rect, max_nodes=3000):
        elements = []

        def walk(ctrl, depth):
            if len(elements) >= max_nodes or depth > 24:
                return
            info = self._describe(ctrl, depth, window_rect)
            if info is not None:
                elements.append(info)
                if len(elements) >= max_nodes:
                    return
            try:
                for child in ctrl.GetChildren():
                    walk(child, depth + 1)
                    if len(elements) >= max_nodes:
                        return
            except Exception:
                pass

        walk(window_ctrl, 0)
        return elements

    # ---- OCR (fallback only) ---------------------------------------------
    def _get_ocr(self):
        """Return ("engine", reader) or None. easyocr is preferred: its models are
        self-contained, it does no document unwarping, and it runs offline once cached.
        PaddleOCR 3.x is a fallback - on this machine its model cache is permission-
        locked, and it loads orientation + unwarping models that cost ~130s first."""
        if self._ocr_tried:
            return self._ocr
        self._ocr_tried = True
        try:
            import easyocr
            reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            self._ocr = ("easyocr", reader)
            return self._ocr
        except Exception as exc:
            print(f"  (easyocr unavailable: {type(exc).__name__})")
        try:
            from paddleocr import PaddleOCR
            try:
                self._ocr = ("paddle", PaddleOCR(lang="en"))
            except TypeError:
                self._ocr = ("paddle", PaddleOCR(use_angle_cls=True, lang="en"))
        except Exception as exc:
            print(f"  (OCR unavailable: {type(exc).__name__})")
            self._ocr = None
        return self._ocr

    def _ocr_text(self, img):
        engine = self._get_ocr()
        if engine is None or img is None:
            return []
        kind, ocr = engine
        arr = np.array(img)
        regions = []
        try:
            if kind == "easyocr":
                for box, text, conf in ocr.readtext(arr, detail=True, paragraph=False):
                    pts = np.array(box)
                    x0, y0 = int(pts[:, 0].min()), int(pts[:, 1].min())
                    regions.append({
                        "text": text, "x": x0, "y": y0,
                        "width": int(pts[:, 0].max() - x0),
                        "height": int(pts[:, 1].max() - y0),
                        "confidence": float(conf),
                    })
                return [r for r in regions if r["confidence"] > 0.5]

            raw = ocr.ocr(arr, cls=False)
        except Exception as exc:
            print(f"  (OCR failed: {type(exc).__name__}: {str(exc)[:80]})")
            return []

        for page in raw or []:
            # PaddleOCR >= 3.x returns dict-like results; 2.x returned nested lists.
            if isinstance(page, dict):
                texts = page.get("rec_texts") or []
                scores = page.get("rec_scores") or []
                polys = page.get("dt_polys") or page.get("rec_polys") or []
                for text, poly in zip(texts, polys):
                    score = 0.9
                    try:
                        idx = texts.index(text)
                        score = float(scores[idx]) if idx < len(scores) else 0.9
                    except Exception:
                        pass
                    pts = np.array(poly)
                    regions.append({
                        "text": text, "x": int(pts[:, 0].min()), "y": int(pts[:, 1].min()),
                        "width": int(pts[:, 0].max() - pts[:, 0].min()),
                        "height": int(pts[:, 1].max() - pts[:, 1].min()),
                        "confidence": score,
                    })
            else:
                for line in page or []:
                    try:
                        pts = np.array(line[0])
                        text, score = line[1][0], float(line[1][1])
                    except Exception:
                        continue
                    regions.append({
                        "text": text, "x": int(pts[:, 0].min()), "y": int(pts[:, 1].min()),
                        "width": int(pts[:, 0].max() - pts[:, 0].min()),
                        "height": int(pts[:, 1].max() - pts[:, 1].min()),
                        "confidence": score,
                    })
        return [r for r in regions if r["confidence"] > 0.5]

    # ---- entry point -----------------------------------------------------
    def scan_app_fast(self, window, max_time_seconds=5, enable_ocr=None) -> dict:
        """window: a UIA WindowControl from find_window()."""
        use_ocr = self.enable_ocr if enable_ocr is None else enable_ocr
        start = time.time()

        rect = window.BoundingRectangle
        window_rect = (rect.left, rect.top, rect.width(), rect.height())

        uia_elements = self._extract_uia_tree(window, window_rect)
        clickable = [e for e in uia_elements if e["action"] and not e["offscreen"]]
        need_ocr = bool(use_ocr or len(clickable) < 5)
        # OCR reads screen pixels, so the target must physically be on top first, or we
        # would read whatever window happens to be in front (the wrong app).
        if need_ocr:
            ensure_foreground(window)
        img = self.grab_region(window_rect)

        ocr_results = []
        if need_ocr and img is not None:
            # UIA came back near-blind; read the screen for the names UIA never gave us.
            ocr_results = self._ocr_text(img)

        elapsed = time.time() - start
        return {
            "screenshot": img,
            "uia_elements": uia_elements,
            "ocr_results": ocr_results,
            "window_rect": window_rect,
            "capture_origin": self._last_grab_origin or (window_rect[0], window_rect[1]),
            "hwnd": window.NativeWindowHandle,
            "title": window.Name,
            "scan_time": elapsed,
        }
