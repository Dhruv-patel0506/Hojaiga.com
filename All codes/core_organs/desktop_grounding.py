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
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.desktop_grounding")

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

# Actionable control type families (generic UIA roles — not app specific).
ACTIONABLE_ROLES = {
    "button", "edit", "combobox", "dropdownbutton", "splitbutton", "menuitem",
    "checkbox", "radiobutton", "tabitem", "listitem", "treeitem", "hyperlink",
    "slider", "spinner", "group", "pane", "document", "thumb",
}

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
        self._dap = None

    @property
    def dap_core(self):
        if self._dap is None:
            self._dap = get_dap_core()
        return self._dap

    # ---- window location (dynamic, name-substring based like organ_24) ----
    def find_window(self, app_hint: str) -> Optional[int]:
        user32 = ctypes.windll.user32
        if not _IS_WINDOWS:
            return None
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.lower()
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cname = cls_buf.value.lower()
            hint = (app_hint or "").lower()
            # Skip infrastructure windows, same spirit as organ_01 filters.
            if cname in ("shell_traywnd", "progman", "workerw", "mintaskswnd",
                         "shell_dock", "topmosttoplevelwindowclass"):
                return True
            if any(bad in title for bad in ("visual studio", "antigravity", " - editor")):
                return True
            token = hint.split()[0] if hint else ""
            if token and (token in title or token in cname):
                found.append((hwnd, title, cname))
            return True

        try:
            user32.EnumWindows(_cb, 0)
        except Exception as exc:
            logger.debug("[grounding] EnumWindows failed: %s", exc)
            return None
        if not found:
            return None
        # Prefer the matched window whose title or class looks like the app.
        for hwnd, title, cname in found:
            if app_hint.lower() in title or app_hint.lower() in cname:
                return hwnd
        return found[0][0]

    def window_title(self, hwnd: int) -> str:
        if not (_IS_WINDOWS and hwnd):
            return ""
        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

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

        def _visit(c, depth: int):
            nonlocal count
            if depth > max_depth or count > max_nodes:
                return
            try:
                role = (c.ControlTypeName or "").lower().replace("control", "")
                name = (c.Name or "").strip()
                rect = c.BoundingRectangle
                bbox = (rect.left, rect.top, rect.right, rect.bottom)
                enabled = bool(getattr(c, "IsEnabled", True))
                visible = bool(getattr(c, "IsOffscreen", False)) is False
                if (role in ACTIONABLE_ROLES and (name or role in ("edit", "pane"))
                        and visible and enabled
                        and bbox[2] > bbox[0] and bbox[3] > bbox[1]):
                    value = ""
                    try:
                        vp = c.GetValuePattern()
                        if vp:
                            value = (vp.Value or "")[:80]
                    except Exception:
                        pass
                    elements.append(GroundedElement(
                        id=_element_id(root_hwnd, role, name, bbox),
                        name=name or role, role=role, bbox=bbox, tier="uia",
                        confidence=0.9 if name else 0.55,
                        hwnd=root_hwnd, value=value))
                    count += 1
                for child in c.GetChildren():
                    _visit(child, depth + 1)
            except Exception:
                return

        _visit(ctrl, 0)
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
        if not (HAS_PIL and _IS_WINDOWS and hwnd):
            return None
        try:
            from PIL import ImageGrab
            import ctypes.wintypes as wt
            rr = wt.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
            if rr.right <= rr.left or rr.bottom <= rr.top:
                return None
            img = ImageGrab.grab(bbox=(rr.left, rr.top, rr.right, rr.bottom))
            path = os.path.join(os.environ.get("TEMP", "."), f"hj_ground_{hwnd}_{int(time.time()*1000)}.png")
            img.save(path, format="PNG")
            return path
        except Exception as exc:
            logger.debug("[grounding] window capture failed: %s", exc)
            return None

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
            out: List[GroundedElement] = []
            for i, text in enumerate(data["text"]):
                text = (text or "").strip()
                conf = float(data["conf"][i] or -1)
                if len(text) >= 2 and conf > 60:
                    x, y, w, hgt = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    bbox = (x, y, x + w, y + hgt)
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

    def _walk_vision(self, hwnd: int) -> List[GroundedElement]:
        if not (HAS_TORCH and os.path.isdir(OMNI_LOCAL_REPO) and HAS_PIL):
            return []
        path = self._window_png(hwnd)
        if not path:
            return []
        try:
            # Singleton: cold-load once, reuse forever.
            if not DesktopGrounding._vision_parser_init_tried:
                DesktopGrounding._vision_parser_init_tried = True
                from core_organs.organ_44_enhanced_scanner import OmniParserScanner
                parser = OmniParserScanner()
                parser._init_model()
                if getattr(parser, "_available", False):
                    DesktopGrounding._vision_parser = parser
            parser = DesktopGrounding._vision_parser
            if parser is None or not getattr(parser, "_available", False):
                return []
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
            return out
        except Exception as exc:
            logger.debug("[grounding] vision pass unavailable: %s", exc)
            return []
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

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
                  "escalated": False}
        if not hwnd:
            report["reason"] = "window-not-found"
            return None, [], report

        elements: List[GroundedElement] = []
        if HAS_UIA:
            elements = self._walk_uia(hwnd)
            report["tiers_ran"].append("uia")
        else:
            report["tiers_skipped"].append("uia:no-uiautomation")

        if not elements and max_tier >= 2:
            elements = self._walk_win32(hwnd)
            report["tiers_ran"].append("win32")

        need_target = bool(target_text)
        structural_miss = not any(target_text.lower() in e.name.lower() for e in elements)

        if need_target and structural_miss:
            report["escalated"] = True
            if HAS_PYTESSERACT and HAS_PIL and max_tier >= 3:
                ocr = self._walk_ocr(hwnd)
                report["tiers_ran"].append("ocr")
                elements.extend(ocr)
            elif max_tier >= 3:
                report["tiers_skipped"].append("ocr:engine-missing")
                if max_tier < 4:
                    report["tiers_skipped"].append("ocr:cap")
            if HAS_TORCH and max_tier >= 4:
                vis = self._walk_vision(hwnd)
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

@dataclass
class Snapshot:
    title: str
    element_ids: List[str]
    region_hash: str = ""

    def signature(self) -> str:
        return hashlib.md5(("|".join(sorted(self.element_ids)) + self.title).encode("utf-8")).hexdigest()


class DesktopVerifier:
    def snapshot(self, hwnd: int, elements: List[GroundedElement]) -> Snapshot:
        snap = Snapshot(title=_quick_title(hwnd), element_ids=[e.id for e in elements])
        snap.region_hash = self._region_hash(hwnd)
        return snap

    def _region_hash(self, hwnd: int) -> str:
        if not (HAS_PIL and _IS_WINDOWS and hwnd):
            return ""
        try:
            from PIL import ImageGrab
            import ctypes.wintypes as wt
            rr = wt.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
            img = ImageGrab.grab(bbox=(rr.left, rr.top, rr.right, rr.bottom))
            img = img.resize((64, 64))
            return hashlib.md5(img.tobytes()).hexdigest()
        except Exception:
            return ""

    def check_expect(self, expect: Dict[str, Any], before: Snapshot,
                     after: Snapshot, elements_now: List[GroundedElement]) -> Tuple[bool, str]:
        """Evaluate a postcondition dict. Returns (ok, evidence)."""
        if not expect:
            # Default postcondition: something about the UI changed.
            changed = before.signature() != after.signature() or (
                before.region_hash and after.region_hash and before.region_hash != after.region_hash)
            return changed, ("ui-changed" if changed else "ui-unchanged")

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
        if "file_created" in expect or "file_saved" in expect:
            target_path = expect.get("file_created") or expect.get("file_saved")
            p = os.path.abspath(str(target_path))
            ok = os.path.exists(p)
            checks.append((ok, f"file {os.path.basename(p)} {'exists' if ok else 'MISSING'}"))
        if "region_changed" in expect and bool(expect["region_changed"]):
            ok = bool(before.region_hash and after.region_hash and before.region_hash != after.region_hash)
            checks.append((ok, "region pixel-delta " + ("detected" if ok else "none")))
        return all(c[0] for c in checks), "; ".join(c[1] for c in checks) or "no-expect"

    def verdict(self, expect: Dict[str, Any], before: Snapshot, after: Snapshot,
                elements_now: List[GroundedElement]) -> Tuple[str, str]:
        """PASS / NO_CHANGE / WRONG_STATE with evidence."""
        ok, evidence = self.check_expect(expect, before, after, elements_now)
        if ok:
            return "PASS", evidence
        structurally_dead = (before.signature() == after.signature()
                             and (not before.region_hash or before.region_hash == after.region_hash))
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
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
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

    def decide(self, goal: str, elements: List[GroundedElement],
               app_hint: str = "", history: List[str] = None,
               pro_hint: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        picks = elements[:MAX_JUDGE_ELEMENTS]
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
                pro_block = (
                    "EXPERT HINT (from prior verified runs on this app, prefer "
                    f"matching it): aim for \"{label}\" using verb "
                    f"{pro_hint.get('verb','click')}. This is guidance, not a "
                    "guarantee — still pick the numbered element that matches it.\n")
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
            "Return STRICT JSON: {\"choice\": <number>, \"verb\": \"<verb>\", "
            "\"text\": \"<only for type>\", \"why\": \"<5 words>\"}"
        )
        payload = {
            "model": JUDGE_MODEL,
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
            if idx < 0 or idx >= len(picks) or verb not in LEGAL_VERBS:
                return {"invalid": True, "raw": decision}
            decision.update({"element": picks[idx].as_dict(), "element_index": idx})
            return decision
        except Exception as exc:
            logger.debug("[judge] call failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Action primitives: UIA patterns -> PostMessage -> physical input (cursor-clip aware)
# ---------------------------------------------------------------------------

def _act_on_element(elem: GroundedElement, verb: str, text: str = "") -> Tuple[bool, str]:
    if verb == "wait":
        time.sleep(min(2.0, 0.8))
        return True, "waited"
    if verb == "done":
        return True, "declared-done"
    # A key/shortcut verb acts on the combo string, not on the element rect.
    if verb in ("key", "shortcut"):
        combo = text or elem.name
        ok, note = _send_shortcut(combo)
        if ok:
            return True, note
    if verb == "invoke":
        verb = "click"  # invoke is the UIA-safe synonym handled by the click ladder

    if elem.tier == "uia" and HAS_UIA:
        import uiautomation as auto
        try:
            root = auto.ControlFromHandle(elem.hwnd)
            target = _find_control_by_identity(root, elem)
            if target is not None:
                if verb == "type":
                    try:
                        vp = target.GetValuePattern()
                        if vp:
                            vp.SetValue(text)
                            return True, "uia-SetValue"
                    except Exception:
                        pass
                    try:
                        target.SetFocus()
                        time.sleep(0.05)
                        _paste_text(text)
                        return True, "uia-focus-typed"
                    except Exception:
                        pass
                else:  # click family
                    for pattern_name, attempts in (("GetInvokePattern", "invoke"),
                                                   ("GetLegacyIAccessiblePattern", "do-default"),
                                                   ("GetSelectionItemPattern", "select"),
                                                   ("GetTogglePattern", "toggle"),
                                                   ("GetExpandCollapsePattern", "expand")):
                        try:
                            pat = getattr(target, pattern_name)()
                            if pat is None:
                                continue
                            {"invoke": lambda: pat.Invoke(),
                             "do-default": lambda: pat.DoDefaultAction(),
                             "select": lambda: pat.Select(),
                             "toggle": lambda: pat.Toggle(),
                             "expand": lambda: pat.Expand()}[attempts]()
                            return True, f"uia-{attempts}"
                        except Exception:
                            continue
        except Exception as exc:
            logger.debug("[act] uia path failed: %s", exc)

    # PostMessage path (works WITHOUT cursor ownership — immune to cursor clips)
    if verb in ("click", "type") and elem.hwnd:
        ok = _postmessage_action(elem, verb, text)
        if ok:
            return True, "postmessage-" + verb

    # Last resort: physical input. Auto-degrade under foreign cursor clips.
    cx, cy = elem.center
    if verb == "type":
        _focus_and_type(cx, cy, text)
        return True, "physical-type"
    return _physical_click(cx, cy)


def _find_control_by_identity(root, elem: GroundedElement):
    """Best-effort re-locate of a UIA control by name/role/rect (trees go stale)."""
    import uiautomation as auto
    best = None
    try:
        for c in root.GetChildren():
            try:
                cname = (c.Name or "").strip().lower()
                crole = (c.ControlTypeName or "").lower().replace("control", "")
                r = c.BoundingRectangle
                if cname == elem.name.lower() and crole == elem.role:
                    return c
                if best is None and (elem.name.lower() in cname or cname in elem.name.lower()) \
                        and abs(r.left - elem.bbox[0]) < 6:
                    best = c
                deeper = _find_control_by_identity(c, elem)
                if deeper is not None:
                    return deeper
            except Exception:
                continue
    except Exception:
        return None
    return best


def _postmessage_action(elem: GroundedElement, verb: str, text: str) -> bool:
    if not _IS_WINDOWS:
        return False
    user32 = ctypes.windll.user32
    hwnd = elem.hwnd
    try:
        if verb == "click":
            # Map screen center to client coords of the CHILD hwnd itself.
            import ctypes.wintypes as wt
            pt = wt.POINT(elem.center[0], elem.center[1])
            user32.ScreenToClient(hwnd, ctypes.byref(pt))
            lparam = (pt.y & 0xFFFF) << 16 | (pt.x & 0xFFFF)
            user32.PostMessageW(hwnd, 0x0201, 0x0001, lparam)  # WM_LBUTTONDOWN
            time.sleep(0.03)
            user32.PostMessageW(hwnd, 0x0202, 0, lparam)       # WM_LBUTTONUP
            return True
        if verb == "type":
            import ctypes.wintypes as wt
            buf = ctypes.create_unicode_buffer(text)
            user32.SendMessageW(elem.hwnd, 0x000C, 0, buf)     # WM_SETTEXT
            return True
    except Exception as exc:
        logger.debug("[act] postmessage failed: %s", exc)
    return False


def _cursor_clip_active() -> bool:
    """Detect the 'foreign thread clipped the pointer' condition (Clicky case)."""
    if not _IS_WINDOWS:
        return False
    try:
        rect = ctypes.wintypes.RECT() if _import_wintypes_ok() else None
        ctypes.windll.user32.GetClipCursor(ctypes.byref(rect))
        # Empty rect => no clip. Full-screen but smaller-than-desktop => clip.
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        if rect.left == 0 and rect.top == 0 and rect.right == 0 and rect.bottom == 0:
            return False
        return not (rect.left <= 0 and rect.top <= 0 and rect.right >= sw and rect.bottom >= sh)
    except Exception:
        return False


def _import_wintypes_ok():
    import ctypes.wintypes  # noqa: F401
    return True


def _physical_click(x: int, y: int) -> Tuple[bool, str]:
    if not _IS_WINDOWS:
        return False, "non-windows"
    if _cursor_clip_active():
        return False, "BLOCKED: another app clipped the OS pointer (cursor clip); use PostMessage path"
    user32 = ctypes.windll.user32
    try:
        import ctypes.wintypes as wt
        user32.SetCursorPos(int(x), int(y))
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        if (pt.x, pt.y) != (int(x), int(y)):
            return False, "NO_EFFECT: SetCursorPos ignored (foreign clip) — not retried"
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.04)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        return True, "physical-click"
    except Exception as exc:
        return False, f"physical-error: {exc}"


def _focus_and_type(x: int, y: int, text: str) -> None:
    _physical_click(x, y)
    time.sleep(0.05)
    _paste_text(text)


# Modifier + named-key virtual code table (generic Windows VK codes, no app logic)
_VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "menu": 0x12,
    "win": 0x5C, "meta": 0x5C, "super": 0x5C,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "back": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def _token_to_vk(tok: str) -> Optional[int]:
    tok = tok.strip().lower()
    if not tok:
        return None
    if tok in _VK:
        return _VK[tok]
    if len(tok) == 1 and ("a" <= tok <= "z" or "0" <= tok <= "9"):
        return ord(tok.upper())
    return None


def _send_shortcut(combo: str) -> Tuple[bool, str]:
    """Press a key combo like 'ctrl+shift+s' via keybd_event. Generic VK codes
    only — nothing app specific. Degrades honestly off Windows."""
    if not _IS_WINDOWS:
        return False, "non-windows"
    toks = [t for t in re.split(r"[+\-]", combo) if t.strip()]
    # a literal '-' passed alone, or multi-char names, are handled by the table
    vks = [_token_to_vk(t) for t in toks]
    if any(v is None for v in vks):
        return False, f"unknown-key in '{combo}'"
    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    try:
        for vk in vks:
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.01)
        for vk in reversed(vks):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.01)
        return True, f"shortcut:{combo}"
    except Exception as exc:
        return False, f"shortcut-error: {exc}"


def _paste_text(text: str) -> None:
    """Type via unicode SendInput; fallback clipboard paste."""
    if _IS_WINDOWS:
        try:
            from ctypes import wintypes
            inputs = []
            for ch in text:
                for flag, data in ((0x0004, ord(ch)), (0x0004 | 0x0002, 0)):
                    class MI(ctypes.Structure):
                        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                                    ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                                    ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
                    class KI(ctypes.Structure):
                        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
                    class Uni(ctypes.Union):
                        _fields_ = [("ki", KI), ("mi", MI)]
                    class INP(ctypes.Structure):
                        _fields_ = [("type", ctypes.c_ulong), ("u", Uni)]
                    inp = INP()
                    inp.type = 1
                    inp.u.ki.wVk = 0
                    inp.u.ki.wScan = data if flag & 0x0004 and data else 0
                    inp.u.ki.dwFlags = 0x0010 | flag  # UNICODE
                    inputs.append(inp)
            for inp in inputs:
                ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
            return
        except Exception:
            pass
    try:
        import uiautomation as auto
        auto.SetClipboardText(text)
        auto.SendKeys("{Ctrl}v")
    except Exception:
        pass


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
        self._dap = None
        # W8 app-intelligence organ (None => run on perception alone)
        self.intel = _get_intel()

    @property
    def dap_core(self):
        if self._dap is None:
            self._dap = get_dap_core()
        return self._dap

    # ---- popup triage (organ_29 + generic Win32/UIA dialogs) ----
    def _triage_popups(self, app_hint: str) -> List[str]:
        handled: List[str] = []
        if not _IS_WINDOWS:
            return handled

        # 1. Dedicated universal popup mitigation via Organ 29
        try:
            from core_organs.organ_29_popup_handler import PopupHandler
            ph = PopupHandler()
            top_modals = ph._detect_desktop_top_modals()
            for hwnd, title, _cls in top_modals:
                low = (title or "").lower()
                if any(k in low for k in ("uac", "user account control", "elevate", "password", "administrator")):
                    self.awaiting_human = True
                    self.capsule_cb("input_needed", "Approval dialog needs you")
                    handled.append(f"uac-shield->HITL '{title[:30]}'")
                    continue
                node = ph.wrap_hwnd(hwnd)
                if node:
                    success, _, _, action = ph.resolve_and_mitigate(node)
                    if success:
                        handled.append(f"organ29-dismissed '{title[:30]}' via '{action}'")
        except Exception as exc:
            logger.debug("[popups] organ_29 triage note: %s", exc)

        # 2. Native Win32 / UIA dialog walk
        user32 = ctypes.windll.user32
        dialogs = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(hwnd, _l):
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value == "#32770" and user32.IsWindowVisible(hwnd):
                dialogs.append(hwnd)
            return True

        try:
            user32.EnumWindows(_cb, 0)
        except Exception:
            return handled
        for dlg in dialogs:
            title = _quick_title(dlg).lower()
            if any(k in title for k in ("uac", "user account control", "elevate", "password")):
                # Never auto-accept permission shields: surface to human.
                self.awaiting_human = True
                self.capsule_cb("input_needed", "Approval dialog needs you")
                handled.append(f"uac-shield->HITL '{title[:30]}'")
                continue
            # Safe buttons by generic labels via UIA on the dialog.
            clicked = self._click_dialog_button(dlg, ("ok", "close", "cancel", "continue",
                                                      "try again", "dismiss", "yes"))
            if clicked:
                handled.append(f"dismissed '{title[:30]}' via '{clicked}'")
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
                            _physical_click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                            return name
                    stack.extend(c.GetChildren())
                except Exception:
                    continue
        except Exception:
            pass
        return None

    # ---- native Open/Save dialog driver (organ_24 NativeFilePicker + UIA) ----
    def handle_native_file_dialog(self, path: str, confirm_words: Tuple[str, ...] =
                                  ("save", "open", "ok")) -> Tuple[bool, str]:
        if not _IS_WINDOWS:
            return False, "non-windows"

        # Try organ_24 NativeFilePicker when available
        try:
            dap = self.dap_core
            if dap and hasattr(dap, "file_picker") and dap.file_picker:
                dlg = dap.file_picker.locate_dialog()
                if dlg:
                    dap.file_picker.select_path(dlg, path)
                    dap.file_picker.confirm(dlg)
                    return True, f"organ_24 file-picker selected '{path}'"
        except Exception as exc:
            logger.debug("[file-picker] organ_24 note: %s", exc)

        user32 = ctypes.windll.user32
        target = None

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(hwnd, _l):
            nonlocal target
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value == "#32770" and user32.IsWindowVisible(hwnd):
                t = _quick_title(hwnd).lower()
                if any(w in t for w in ("save", "open", "export", "browse")):
                    target = hwnd
            return True

        user32.EnumWindows(_cb, 0)
        if not target:
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
                if edits:
                    edits[0].GetValuePattern().SetValue(path)
                for b in buttons:
                    if any(w in (b.Name or "").lower() for w in confirm_words):
                        b.GetInvokePattern().Invoke()
                        return True, f"file-dialog typed + clicked '{(b.Name or '').strip()}'"
                return True, "file-dialog typed (no confirm button found)"
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
        # Only a genuinely-verified shortcut may skip the judge. An unverified
        # archetype guess must never take direct control of the machine.
        if (top.shortcut and top.source == "learned"
                and top.confidence >= PRO_SHORTCUT_CONF and not top.destructive):
            return {"kind": "shortcut", "shortcut": top.shortcut,
                    "confidence": top.confidence, "source": top.source,
                    "step_id": top.step_id, "goal": goal}
        return {"kind": "element", "element_name": top.element_name,
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

        # ---- W8 PRO PATH: a confidently-learned shortcut beats the LLM ----
        pro = self._consult_intel(app_hint, goal)
        if pro is not None and pro["kind"] == "shortcut":
            self.capsule_cb("working", f"[{app_hint}] {pro['shortcut']} (learned pro)")
            ok, method = _send_shortcut(pro["shortcut"])
            after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
            verdict, evidence = self.verifier.verdict(
                expect, before, self.verifier.snapshot(hwnd, after_elements), after_elements)
            self._reinforce(app_hint, goal, pro, verdict)
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

        # Verification step
        after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
        verdict, evidence = self.verifier.verdict(expect, before,
                                                  self.verifier.snapshot(hwnd, after_elements),
                                                  after_elements)

        # NO_CHANGE retry ladder through organ_24 RecoveryEngine sequence:
        # wait/reinvoke -> PostMessage -> physical click
        if verdict == "NO_CHANGE" and ok:
            # 1. Brief wait + re-invoke
            time.sleep(0.3)
            _act_on_element(elem, "invoke" if verb == "click" else verb, text)
            after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
            after_re = self.verifier.snapshot(hwnd, after_elements)
            verdict, evidence = self.verifier.verdict(expect, before, after_re, after_elements)
            method += "+retry-invoke"

            # 2. If still NO_CHANGE, try PostMessage
            if verdict == "NO_CHANGE" and elem.hwnd:
                _postmessage_action(elem, verb, text)
                time.sleep(0.2)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                after_pm = self.verifier.snapshot(hwnd, after_elements)
                verdict, evidence = self.verifier.verdict(expect, before, after_pm, after_elements)
                method += "+retry-postmessage"

            # 3. If still NO_CHANGE, physical click
            if verdict == "NO_CHANGE":
                cx, cy = elem.center
                _physical_click(cx, cy)
                time.sleep(0.25)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                after2 = self.verifier.snapshot(hwnd, after_elements)
                verdict, evidence = self.verifier.verdict(expect, before, after2, after_elements)
                method += "+retry-physical"

        # On WRONG_STATE, triage popups first to dismiss unexpected roadblocks, then re-check
        if verdict == "WRONG_STATE":
            popup_notes = self._triage_popups(app_hint)
            if popup_notes:
                evidence += " | cleared: " + "; ".join(popup_notes)
                time.sleep(0.2)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                after_pop = self.verifier.snapshot(hwnd, after_elements)
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

        self._history.append(f"{verb} '{elem.name}' -> {verdict}")
        entry = StepTrace(goal, elem.name, verb, verdict, method, evidence, ladder["tiers_ran"])
        self.trace.append(entry)
        self._write_checkpoint(entry)
        return self._step_result(entry, elements=after_elements)

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

    def _wait_for_ready(self, app_hint: str, target_text: str = "",
                        max_tier: int = 2) -> Tuple[Optional[int], List[GroundedElement], Dict[str, Any]]:
        """Readiness backoff poll: bring up the target and wait (bounded, growing
        waits) until it exposes a live control tree. Prevents 'still booting' from
        being misread as an empty/wrong state on heavy apps."""
        deadline = time.time() + READY_TIMEOUT_S
        delay = READY_BACKOFF_S
        hwnd, elements, report = None, [], {}
        while True:
            hwnd, elements, report = self.grounding.ground(
                app_hint, target_text=target_text, max_tier=max_tier)
            if hwnd and elements:
                break
            if time.time() >= deadline:
                break
            self.capsule_cb("working", f"Waiting for {app_hint} to be ready")
            time.sleep(delay)
            delay = min(delay * 1.6, READY_BACKOFF_MAX_S)
        return hwnd, elements, report

    def run(self, goals: List[str], app_hint: str, max_steps_per_goal: int = 4,
            allow_destructive: bool = False,
            expect_map: Optional[Dict[int, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Execute ordered micro-goals. Each goal gets up to max_steps_per_goal
        closed-loop attempts; a PASS or declared-done advances to the next goal."""
        expect_map = expect_map or {}
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
            for _ in range(max_steps_per_goal):
                res = self.step(goal, app_hint, expect=expect_map.get(gi),
                                allow_destructive=allow_destructive)
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


_LOOP_SINGLETON: Optional[DesktopAutonomyLoop] = None


def get_loop(capsule_cb=None, cursor_cb=None) -> DesktopAutonomyLoop:
    global _LOOP_SINGLETON
    if _LOOP_SINGLETON is None:
        _LOOP_SINGLETON = DesktopAutonomyLoop(capsule_cb=capsule_cb, cursor_cb=cursor_cb)
    else:
        if capsule_cb:
            _LOOP_SINGLETON.capsule_cb = capsule_cb
        if cursor_cb:
            _LOOP_SINGLETON.cursor_cb = cursor_cb
    return _LOOP_SINGLETON
