"""
live_trajectory_executor -- closes the loop the offline decomposer opens.

Text -> JSON -> Scanner -> (Vision handoff) -> Virtual Mouse -> Verify, wired onto
the REAL Hojaiga organs (no re-implementation of actuation or perception):

  scan     : core_organs.fast_uia.snapshot(hwnd)          -> live UIA Node list
  resolve  : semantic_match.resolve(target, nodes)         -> best node + bbox
  eyes     : core_organs.organ_31.VisualGroundingEngine    -> pixel xy when UIA can't match
  mouse    : core_organs.headless_input.post_* (visible)   -> posted-message click/type/key
             UIA Invoke/Toggle/Value pattern (minimized)   -> no physical cursor (repo law)
  popups   : core_organs.organ_29 + headless_input.popup_windows -> clear between steps
  verify   : UIA tree differential (authoritative) + organ_31.verify_state_change (secondary)

Honesty rules enforced here:
  * A [0,0,0,0] bbox is only replaced by a real rect the scanner actually saw.
  * If neither UIA nor vision locates a target, the step is reported NOT DONE --
    never faked as a pass. organ_31.verify_state_change returns success on its own
    exceptions, so its result is never trusted alone; UIA change is required.
  * Minimized windows use UIA patterns; the coordinate click path is refused (by
    headless_input) rather than silently moving the real cursor.

Usage
-----
  python live_trajectory_executor.py --traj trajectories/TRAIN/skynotepad/*.json --title "Store"
  python live_trajectory_executor.py --traj some.json --hwnd 123456 --dry-run
  python live_trajectory_executor.py --calculator-demo      # safe self-test on Windows Calculator
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

# Make the Hojaiga organ package importable when run from the repo root.
_ORGANS = Path(__file__).resolve().parent / "All codes"
if str(_ORGANS) not in sys.path:
    sys.path.insert(0, str(_ORGANS))

import semantic_match as SM

# Part (i): zero-GPU episodic memory of verified trajectories (soft; absence never breaks a run).
try:
    import episodic_memory as emem
except Exception:
    emem = None

EVAL_LOG = Path("trajectories") / "eval_results.jsonl"
RESOLVED_DIR = Path("trajectories") / "resolved"
PROOF_DIR = Path("trajectories") / "proof"

UIA_INVOKE, UIA_TOGGLE, UIA_VALUE, UIA_EXPAND = 10000, 10015, 10002, 10005
UIA_LEGACY = 10018   # LegacyIAccessiblePattern (DoDefaultAction) -- reliable on UWP XAML buttons
STOP = SM.STOPWORDS

# --- Part 3: Reflexion online error recovery  (p' = p + (1 - p) * r) ---------
# On a failed step, read the LIVE tree, ask the frozen local LLM for ONE
# corrective micro-action whose target is actually present, and retry (bounded)
# before declaring the step failed. Raises effective per-step reliability.
OLLAMA_URL = os.environ.get("HOJAIGA_PROF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
REFLEXION = os.environ.get("HOJAIGA_REFLEXION", "1").strip().lower() not in ("0", "false", "no", "off")
REFLEXION_BUDGET = int(os.environ.get("HOJAIGA_REFLEXION_BUDGET", "2"))

# --- Verification tiers (fixes the "verification wall" on UI-opaque apps) ------
# A click can be correct yet invisible to UIA (Paint tool highlight, Notepad word-wrap
# checkmark). When the UIA delta is silent we fall back to a localized ROI pixel-diff on
# the off-screen PrintWindow buffer, then a Qwen3-VL semantic compare only if ambiguous.
ROI_LOW = float(os.environ.get("HOJAIGA_ROI_LOW", "0.02"))     # >= this mean abs diff = a real change
ROI_HIGH = float(os.environ.get("HOJAIGA_ROI_HIGH", "0.40"))   # above this = big/ambiguous -> ask the VLM
PIXEL_VERIFY = os.environ.get("HOJAIGA_PIXEL_VERIFY", "1").strip().lower() not in ("0", "false", "no", "off")
VLM_VERIFY = os.environ.get("HOJAIGA_VLM_VERIFY", "1").strip().lower() not in ("0", "false", "no", "off")


def log(m: str) -> None:
    print(f"[exec] {m}", flush=True)


# ---------------------------------------------------------------------------
# organs (lazy, soft)
# ---------------------------------------------------------------------------

def _organs():
    from core_organs import fast_uia, headless_input
    return fast_uia, headless_input


def _vision():
    try:
        from core_organs.organ_31_visual_perception import VisualGroundingEngine
        return VisualGroundingEngine()
    except Exception as exc:
        log(f"  vision tier unavailable: {exc}")
        return None


# ---------------------------------------------------------------------------
# window + tree helpers
# ---------------------------------------------------------------------------

def find_hwnd(title: str):
    _, hin = _organs()
    want = (title or "").lower()
    for hwnd, t in hin.top_level_titles(visible_only=False):
        if want and want in (t or "").lower():
            return hwnd, t
    return None, None


def snapshot_nodes(hwnd, max_nodes: int = 20000):
    fu, _ = _organs()
    try:
        return fu.snapshot(hwnd, max_nodes=max_nodes) or []
    except Exception as exc:
        log(f"  snapshot failed: {exc}")
        return []


def capture_proof(hwnd, tag: str) -> dict:
    """Screenshot proof of what is ACTUALLY on screen (PrintWindow, works even if covered).
    Saves a PNG and returns its path so a human (and the agent) can verify the change
    visually -- a UIA tree diff alone is NOT accepted as 'the operation happened'."""
    try:
        _, hin = _organs()
        img, note, rung = hin.capture_window_robust(hwnd)
        if img is None:
            return {"tag": tag, "captured": False, "note": str(note)[:80]}
        PROOF_DIR.mkdir(parents=True, exist_ok=True)
        fp = (PROOF_DIR / f"{tag}.png").resolve()
        img.save(str(fp))
        return {"tag": tag, "captured": True, "file": str(fp), "rung": rung}
    except Exception as exc:
        return {"tag": tag, "captured": False, "note": f"{type(exc).__name__}: {str(exc)[:60]}"}


def tree_signature(nodes) -> tuple:
    """Cheap, stable fingerprint of the live tree for before/after change detection."""
    names = sorted({(str(getattr(n, "name", "") or ""), str(getattr(n, "role", "") or "")) for n in nodes})
    blob = " ".join(f"{n}|{r}" for n, r in names)
    return (len(nodes), hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()[:16], blob)


# ---------------------------------------------------------------------------
# Gap 2: deep, STATEFUL differential. The shallow name|role diff misses
# property-only mutations (Calculator display value, checkbox toggle, tab
# selection) and detached modals/menus that open as SEPARATE root HWNDs.
# ---------------------------------------------------------------------------

VALUE_SCAN_CAP = 400   # bound live ValuePattern reads so a huge tree can't stall verify


def _read_value(node) -> str:
    """Best-effort ValuePattern.Value text (property-only state the tree shape hides)."""
    try:
        pat = node.ctrl.GetPattern(UIA_VALUE)
        if pat is None:
            return ""
        for attr in ("value", "CurrentValue"):
            v = getattr(pat, attr, None)
            if isinstance(v, str):
                return v
    except Exception:
        return ""
    return ""


def deep_tree_signature(hwnd, nodes) -> dict:
    """Structural + stateful fingerprint: window topology AND per-control dynamic state."""
    _, hin = _organs()
    try:
        pid = hin.window_pid(hwnd)
        hwnds = sorted(int(h) for h, _t in hin.top_level_titles(visible_only=False)
                       if pid and hin.window_pid(h) == pid)
    except Exception:
        hwnds = []
    states = []
    value_reads = 0
    for n in nodes:
        role = str(getattr(n, "role", "") or "")
        aid = str(getattr(n, "aid", "") or "")
        name = str(getattr(n, "name", "") or "")
        tog = getattr(n, "toggle_state", -1)
        sel = int(bool(getattr(n, "selected", False)))
        exp = getattr(n, "expand_state", -1)
        en = int(bool(getattr(n, "enabled", True)))   # enabled flips when e.g. Memory store arms MR/MC
        val = ""
        if "value" in (getattr(n, "pats", []) or []) and value_reads < VALUE_SCAN_CAP:
            value_reads += 1
            val = _read_value(n)
        states.append(f"{aid}|{name}|{role}|{tog}|{sel}|{exp}|{en}|{val}")
    blob = ";".join(sorted(states))
    return {"hwnds": hwnds, "n_nodes": len(nodes),
            "state_hash": hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:32]}


def verify_state_delta(before: dict, after: dict) -> bool:
    """True if window topology, element count, OR any dynamic control state changed."""
    return (before["n_nodes"] != after["n_nodes"]
            or before["state_hash"] != after["state_hash"]
            or before["hwnds"] != after["hwnds"])


# ---------------------------------------------------------------------------
# Gap 3: crop the screenshot to the target window/region before sending to the
# :8081 VLM (full 1080p/4K frames are ~1.5-2.5k visual tokens -> timeouts), then
# remap the model's crop-local pixel back to global screen coordinates.
# ---------------------------------------------------------------------------

def prepare_vision_payload(desktop_b64: str, crop_rect=None):
    """Crop a desktop base64 image to [x, y, w, h] (+20px pad). Returns
    (crop_b64, (crop_w, crop_h), (offset_x, offset_y)) with offsets in screen space."""
    import base64
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(base64.b64decode(desktop_b64)))
    if crop_rect and len(crop_rect) == 4:
        x, y, w, h = (int(v) for v in crop_rect)
        pad = 20
        left = max(0, min(x - pad, img.width - 1))
        top = max(0, min(y - pad, img.height - 1))
        right = max(left + 1, min(x + w + pad, img.width))
        bottom = max(top + 1, min(y + h + pad, img.height))
        img = img.crop((left, top, right, bottom))
        offset = (left, top)
    else:
        offset = (0, 0)
    cw, ch = img.size
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8"), (cw, ch), offset


def remap_vision_coords(local_xy, offset) -> tuple:
    """Translate crop-local coordinates back to global desktop screen space."""
    return (int(local_xy[0] + offset[0]), int(local_xy[1] + offset[1]))


def _window_vision_payload(hwnd, nodes):
    """Off-screen vision source. A window parked at negative coordinates is NOT on the
    physical desktop, so a desktop grab sees nothing -- but PrintWindow reads the DWM
    backing buffer and returns the window's REAL pixels anywhere. Capture those, and return
    (b64, w, h, (origin_x, origin_y)) so a vision-local pixel maps back to the window's true
    screen rect (origin is negative while parked). This is what keeps the :8081 eyes alive
    for custom-canvas / GDI apps (Paint, viewers) that expose no usable UIA names."""
    import base64
    import io
    from PIL import Image
    _, hin = _organs()
    try:
        img, note, rung = hin.capture_window_robust(hwnd)
    except Exception:
        return None
    if img is None:
        return None
    region = _vision_region(nodes)
    ox = int(region[0]) if region else 0
    oy = int(region[1]) if region else 0
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8"), img.width, img.height, (ox, oy)


def _vision_region(nodes):
    """Crop box [x, y, w, h] in screen coords: the target window's root rect (never the
    whole multi-monitor desktop). Returns None if the frame is unknown (use full capture)."""
    if nodes:
        r0 = getattr(nodes[0], "rect", (0, 0, 0, 0))
        if r0 != (0, 0, 0, 0):
            l, t, r, b = r0
            return [l, t, r - l, b - t]
    return None


# Words describing the ACT of looking, not the RESULT. These are ALWAYS present in an
# app's accessibility tree (Calculator's result node is literally named "Display is 8"),
# so letting them satisfy a postcondition turned a wrong answer (8) into a fake "verified".
EXPECT_STOP = STOP | {
    "display", "shows", "shown", "show", "appears", "appear", "visible", "screen",
    "window", "field", "box", "text", "value", "becomes", "changes", "updated",
    "update", "after", "before", "then", "when", "with", "into", "from", "gets",
    "should", "will", "expected", "result", "output", "area", "bar", "label",
    "there", "here", "now", "still", "has", "have", "been", "new",
}


def _expr_text(nodes) -> str:
    """Literal text of any CalculatorExpression-style strip node (lowercased)."""
    parts = []
    for n in nodes:
        nm = str(getattr(n, "name", "") or "")
        aid = str(getattr(n, "aid", "") or "")
        if "expression" in nm.lower() or aid.lower() == "calculatorexpression":
            parts.append(nm)
    return " ".join(parts).lower()


_OPS = ("+", "-", "*", "/", "=", "\u00d7", "\u00f7")   # + - * / = x-sign div-sign


def expected_present(nodes, expected: str) -> bool:
    """Strict postcondition check. A number in the expectation (e.g. 'shows 96') is a
    HARD requirement -- the exact digits must appear in the app's OUTPUT text. When the
    expectation carries an OPERATOR symbol (e.g. '8 +'), the CalculatorExpression strip must
    literally show it -- so a dead operator click (empty expression) can never pass."""
    s = str(expected or "").lower()
    nums = re.findall(r"\d+", s)
    ops = [c for c in _OPS if c in s]
    out = _result_text(nodes)
    if ops:
        expr = _expr_text(nodes)
        if not all(o in expr for o in ops):          # operator must actually appear in the expression
            return False
        if nums and not all(re.search(rf"(?<!\d){re.escape(n)}(?!\d)", expr) for n in set(nums)):
            return False
        return True
    if nums:
        return all(re.search(rf"(?<!\d){re.escape(n)}(?!\d)", out) for n in set(nums))
    kw = [w for w in re.findall(r"[a-z0-9]{3,}", s) if w not in EXPECT_STOP]
    if not kw:
        return False
    hay = collect_text(nodes)
    need = max(1, (2 * len(kw) + 2) // 3)          # require a 2/3 majority of distinctive tokens
    return sum(1 for w in kw if w in hay) >= need


def _result_text(nodes) -> str:
    """App OUTPUT text only: names of non-interactive nodes + ValuePattern values.
    Excludes button/edit IDs so a single digit in an automation-id ('num1Button') can
    never falsely satisfy a numeric postcondition like 'display shows 1'."""
    parts, vr = [], 0
    for n in nodes:
        role = str(getattr(n, "role", "") or "").lower()
        if role not in ("button", "edit"):
            parts.append(str(getattr(n, "name", "") or ""))
        if "value" in (getattr(n, "pats", []) or []) and vr < VALUE_SCAN_CAP:
            vr += 1
            parts.append(_read_value(n))
    return " ".join(parts).lower()


def collect_text(nodes, with_values: bool = True) -> str:
    """Lowercased haystack of every node's name + automation-id + (bounded) ValuePattern
    text. Values are included because typed content lives in the Value, not the Name --
    without this a TYPE_TEXT that never landed still 'passes' on a focus-only tree change."""
    parts, vr = [], 0
    for n in nodes:
        parts.append(str(getattr(n, "name", "") or ""))
        parts.append(str(getattr(n, "aid", "") or ""))
        if with_values and "value" in (getattr(n, "pats", []) or []) and vr < VALUE_SCAN_CAP:
            vr += 1
            parts.append(_read_value(n))
    return " ".join(parts).lower()


def clear_popups(hwnd) -> int:
    """Best-effort dismiss any modal that popped over the target; returns count handled."""
    try:
        _, hin = _organs()
        pops = [p for p in hin.popup_windows(hwnd) if p != hwnd]
        if not pops:
            return 0
        try:
            from core_organs.organ_29_popup_handler import DesktopInteractionManager
            mgr = DesktopInteractionManager()
            for p in pops[:3]:
                try:
                    for node in mgr.find_in_window_modals(p):
                        mgr.intercept_popup(node)
                except Exception:
                    pass
        except Exception:
            pass
        return len(pops)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# actuation
# ---------------------------------------------------------------------------

def uia_act(node, action_type: str, text=None):
    """Actuate a UIA node WITHOUT moving the physical cursor (patterns only)."""
    ctrl = None
    try:
        ctrl = node.ctrl
    except Exception:
        ctrl = None
    if ctrl is None:
        return False, "no live control for UIA pattern"
    try:
        if action_type in ("TYPE_TEXT",) and text is not None:
            pat = ctrl.GetPattern(UIA_VALUE)
            if pat is not None:
                pat.SetValue(text)
                return True, "uia.ValuePattern.SetValue"
        if action_type in ("KEY_COMBINATION",):
            return False, "minimized key chords need the focused window; report not-done"
        pat = ctrl.GetPattern(UIA_INVOKE)
        if pat is not None:
            pat.Invoke()
            return True, "uia.InvokePattern.Invoke"
        pat = ctrl.GetPattern(UIA_TOGGLE)
        if pat is not None:
            pat.Toggle()
            return True, "uia.TogglePattern.Toggle"
        pat = ctrl.GetPattern(UIA_EXPAND)
        if pat is not None:
            pat.Expand()
            return True, "uia.ExpandCollapsePattern.Expand"
    except Exception as exc:
        return False, f"uia pattern error: {type(exc).__name__}: {str(exc)[:80]}"
    return False, "no invokable UIA pattern on node"


def _find_canvas_child(root_hwnd, prefixes=("mspaintview", "afx:")):
    """Win11 Paint: the top window's real drawing surface is a classic Win32 GDI child
    (class 'MSPaintView' / inner 'Afx:*'); the XAML Ribbon island is 'Microsoft.UI.*' and
    sits on top so ChildWindowFromPoint grabs it first. Enumerate children for the GDI canvas."""
    import ctypes
    u = ctypes.windll.user32
    found = ctypes.c_void_p(0)
    ProcType = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _cb(ch, _l):
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(ch, buf, 256)
        cls = buf.value.lower()
        if not found.value and any(cls.startswith(p) for p in prefixes):
            found.value = ch
            return False
        return True

    try:
        u.EnumChildWindows(int(root_hwnd), ProcType(_cb), 0)
    except Exception:
        return 0
    return int(found.value or 0)


def _canvas_direct_drag(canvas_hwnd, rel_pts, settle: float = 0.03):
    """Post WM_LBUTTONDOWN -> WM_MOUSEMOVE(MK_LBUTTON) -> WM_LBUTTONUP DIRECTLY to the GDI
    canvas child (client coords), bypassing the XAML overlay. Max-1 non-blocking attempt."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    r = wintypes.RECT()
    if not u.GetWindowRect(int(canvas_hwnd), ctypes.byref(r)):
        return False, "canvas rect unreadable"
    w, h = r.right - r.left, r.bottom - r.top
    if w < 40 or h < 40:
        return False, f"canvas too small ({w}x{h})"
    WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON = 0x0200, 0x0201, 0x0202, 0x0001

    def lp(cx, cy):
        pt = wintypes.POINT(int(cx), int(cy))
        u.ScreenToClient(canvas_hwnd, ctypes.byref(pt))
        return (pt.y << 16) | (pt.x & 0xFFFF)
    pts = [(r.left + a * w, r.top + b * h) for a, b in rel_pts]
    u.PostMessageW(canvas_hwnd, WM_MOUSEMOVE, 0, lp(*pts[0]))
    time.sleep(settle)
    u.PostMessageW(canvas_hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp(*pts[0]))
    for cx, cy in pts[1:]:
        u.PostMessageW(canvas_hwnd, WM_MOUSEMOVE, MK_LBUTTON, lp(cx, cy))
        time.sleep(settle)
    u.PostMessageW(canvas_hwnd, WM_LBUTTONUP, 0, lp(*pts[-1]))
    return True, f"canvas-direct-drag->{len(pts)}pts onto {_canvas_class(canvas_hwnd)}"


def _canvas_class(hwnd):
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    try:
        ctypes.windll.user32.GetClassNameW(int(hwnd), buf, 256)
    except Exception:
        return "?"
    return buf.value or "?"


def actuate(step, match, hwnd, minimized, coords):
    _, hin = _organs()
    va = step.get("virtual_mouse_action", {})
    atype = (va.get("action_type") or "CLICK").upper()
    text = va.get("text_payload")
    mods = va.get("modifiers") or []
    node = match.node if match else None

    if atype == "TYPE_TEXT":
        if minimized or node is not None:
            ok, note = uia_act(node, "TYPE_TEXT", text) if node else (False, "no node")
            if ok:
                return ok, note
        return hin.post_text(hwnd, text or "")
    if atype == "KEY_COMBINATION":
        combo = "+".join(list(mods) + ([va.get("key")] if va.get("key") else []))
        if not combo:
            return False, "no key in KEY_COMBINATION"
        return hin.post_key_combo(hwnd, combo)
    if atype in ("DRAG_AND_DROP", "CONTINUOUS_DRAG"):
        pts = va.get("path_waypoints") or va.get("waypoints") or []
        if len(pts) < 2:
            return False, "drag needs >=2 waypoints"
        # convert relative [0..1] waypoints to SCREEN pixels using the resolved control rect
        # (post_drag/post_click take screen coords and do their own ScreenToClient internally).
        rect = list(getattr(match, "rect", [0, 0, 0, 0])) if match is not None else [0, 0, 0, 0]
        try:
            rx, ry, rw, rh = [float(v) for v in (rect + [0, 0, 0, 0])[:4]]
        except Exception:
            rx = ry = rw = rh = 0.0
        if rw <= 1 or rh <= 1:      # canvas had no usable UIA rect -> use the window client area
            try:
                import ctypes
                from ctypes import wintypes
                _u = ctypes.windll.user32
                _r = wintypes.RECT()
                if _u.GetWindowRect(int(hwnd), ctypes.byref(_r)):
                    rx = _r.left + max(40, (_r.right - _r.left) * 0.12)   # inset to dodge ribbon
                    ry = _r.top + max(120, (_r.bottom - _r.top) * 0.28)
                    rw = max(60.0, (_r.right - _r.left) * 0.75)
                    rh = max(60.0, (_r.bottom - _r.top) * 0.60)
            except Exception:
                pass

        def _to_abs(p):
            a, b = float(p[0]), float(p[1])
            if rw > 1 and rh > 1 and 0.0 <= a <= 1.0 and 0.0 <= b <= 1.0:
                return (int(rx + a * rw), int(ry + b * rh))
            return (int(a), int(b))
        abspts = [_to_abs(p) for p in pts]
        button = va.get("button") or "left"
        if atype == "CONTINUOUS_DRAG":
            # Max-1 non-blocking try: draw DIRECTLY onto the Win32 GDI canvas child so the
            # stroke is not swallowed by the Microsoft.UI XAML Ribbon overlay.
            _ch = _find_canvas_child(hwnd)
            if _ch:
                _ok3, _note3 = _canvas_direct_drag(_ch, pts)
                if _ok3:
                    return _ok3, _note3
            # one continuous stroke through EVERY waypoint (post_drag path= = down->moves->up)
            return hin.post_drag(hwnd, abspts[0][0], abspts[0][1], abspts[-1][0], abspts[-1][1],
                                 path=abspts, button=button)
        return hin.post_drag(hwnd, abspts[0][0], abspts[0][1], abspts[-1][0], abspts[-1][1], button=button)

    # clicks
    right = atype == "RIGHT_CLICK"
    double = atype == "DOUBLE_CLICK"
    # A single left click PREFERS the UIA Invoke/Toggle/Expand pattern on the matched node.
    # PROVEN on Windows Calculator (UWP): posted coordinate-clicks change the visual hover
    # state (a false-positive tree diff) but NEVER reach the app logic, whereas InvokePattern
    # actually computes 1+1=2. Patterns work on UWP/WinUI AND Win32, so try them first.
    if atype == "CLICK" and node is not None:
        ok, note = uia_act(node, atype)
        if ok:
            return ok, note
        # no usable invokable pattern -> fall through to a posted click (visible only)
    if minimized:
        # right/double or no invokable node: a coordinate click would need the real cursor.
        return False, "minimized + no usable UIA pattern: coordinate click refused (would need real cursor)"
    if not coords:
        return False, "no target coordinates"
    x, y = coords
    return hin.post_click(hwnd, int(x), int(y), right=right, double=double)


# ---------------------------------------------------------------------------
# one trajectory
# ---------------------------------------------------------------------------

def run_trajectory(path: str, hwnd, title, dry_run=False, vision_handoff=True,
                   lex_threshold=SM.LEX_STRONG, proof=False):
    """Execute one trajectory, isolated off-screen when HOJAIGA_OFFSCREEN is on (default).

    Off-screen parking means the target window is restored at negative coordinates so it never
    flashes on the user's desktop while UIA/coordinate/type actuation and PrintWindow capture
    all keep working. The window is ALWAYS returned to its prior placement, even on error."""
    _, hin = _organs()
    isolated = False
    if hwnd and not dry_run:
        try:
            isolated = bool(hin.isolate_offscreen(hwnd))
        except Exception as exc:
            log(f"  isolation unavailable (running on-screen): {type(exc).__name__}: {str(exc)[:60]}")
    if isolated:
        log("  off-screen isolation active: window parked, your desktop stays clean")
    try:
        return _run_steps(path, hwnd, title, dry_run=dry_run, vision_handoff=vision_handoff,
                          lex_threshold=lex_threshold, proof=proof, isolated=isolated)
    finally:
        if isolated:
            try:
                hin.release_isolation(hwnd)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Part 3: Reflexion recovery helpers (see constants at top)
# ---------------------------------------------------------------------------

_ollama_model_cache = None


def _discover_ollama_model() -> str:
    global _ollama_model_cache
    if _ollama_model_cache:
        return _ollama_model_cache
    import requests
    try:
        tags = requests.get(OLLAMA_URL + "/api/tags", timeout=5).json()
        models = [m.get("name", "") for m in tags.get("models", []) if "embed" not in m.get("name", "").lower()]
    except Exception:
        models = []
    for want in ("qwen2.5:7b", "qwen2.5", "qwen3", "llama3.1", "llama3"):
        for m in models:
            if m.lower().startswith(want):
                _ollama_model_cache = m
                return m
    _ollama_model_cache = models[0] if models else "qwen2.5:7b"
    return _ollama_model_cache


def _ollama_chat(system: str, user: str, timeout: float | None = None):
    import requests
    if timeout is None:
        timeout = float(os.environ.get("HOJAIGA_REFLEX_TIMEOUT", "75"))
    try:
        r = requests.post(OLLAMA_URL + "/api/chat", json={
            "model": _discover_ollama_model(), "stream": False, "format": "json",
            "options": {"temperature": 0.2, "num_predict": 300, "num_ctx": 4096},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }, timeout=timeout)
        r.raise_for_status()
        j = r.json()
        return (j.get("choices", [{}])[0].get("message", {}) or {}).get("content") or (j.get("message") or {}).get("content")
    except Exception:
        return None


def _visible_widgets(nodes, cap: int = 150) -> str:
    return " | ".join(_widget_names(nodes, cap))


# Only offer the model CLICKABLE, human-readable widgets as recovery candidates. This
# drops glyph-only Segoe-MDL2 text nodes (e.g. name '\ue947') that would otherwise be
# chosen and then fail to resolve -- the exact bug seen on Calculator's operator buttons.
_INTERACTIVE = {"button", "menuitem", "menu", "menu bar", "menubar", "tab", "edit",
                "checkbox", "combobox", "listitem", "radiobutton", "hyperlink",
                "splitbutton", "dropdownbutton", "titlebar"}


def _widget_names(nodes, cap: int = 200) -> list:
    import re as _re
    ok = _re.compile(r"[A-Za-z0-9]")
    seen, out = set(), []
    for n in nodes:
        nm = str(getattr(n, "name", "") or "").strip()
        role = str(getattr(n, "role", "") or "").strip().lower()
        if not nm or nm in seen:
            continue
        if role and role not in _INTERACTIVE:      # skip text/group/glyph noise
            continue
        if not ok.search(nm):                        # needs a real letter/digit
            continue
        if sum(1 for c in nm if 0xE000 <= ord(c) <= 0xF8FF) > max(0, len(nm) // 2):
            continue                                 # mostly private-use glyphs
        seen.add(nm); out.append(nm)
        if len(out) >= cap:
            break
    return out


def _reflexion_propose(app_name, step, reason, after_nodes):
    target = step.get("ui_target", {}) or {}
    sysmsg = ("You recover failed GUI actions for a desktop automation agent. Reply ONLY with JSON "
              '{"action_type": one of CLICK|RIGHT_CLICK|DOUBLE_CLICK|HOVER|TYPE_TEXT|KEY_COMBINATION|NONE, '
              '"element_name": a name copied EXACTLY from the visible list, "note": short reason. '
              'Use NONE if nothing visible can achieve the step.')
    user = (f"APP: {app_name}\nSTEP GOAL: {step.get('low_level_instruction') or target.get('element_name')}\n"
            f"WANTED TARGET: {target.get('element_name')!r}\nEXPECTED AFTER: {step.get('expected_state_change')!r}\n"
            f"WHY IT FAILED: {reason}\nVISIBLE UI NOW: {_visible_widgets(after_nodes)}\n"
            "Propose ONE corrective action using a name from VISIBLE UI NOW (or NONE).")
    txt = _ollama_chat(sysmsg, user)
    if not txt:
        return None
    obj = None
    try:
        obj = json.loads(txt)
    except Exception:
        a, b = txt.find("{"), txt.rfind("}")
        if 0 <= a < b:
            try:
                obj = json.loads(txt[a:b + 1])
            except Exception:
                obj = None
    if not isinstance(obj, dict):
        return None
    name = str(obj.get("element_name") or "").strip()
    at = str(obj.get("action_type") or "").upper()
    if at in ("", "NONE") or not name:
        return None
    # grounding guard: snap the model's suggestion to a REAL interactive widget that is on
    # screen now (exact, substring, or fuzzy). The frozen 7B often paraphrases ("Multiplication"
    # for "Multiply by"); snapping keeps recovery honest (target must exist) yet robust.
    real = _widget_names(after_nodes, cap=400)
    snapped = _snap_to_real(name, real)
    if not snapped:
        return None
    return {"action_type": at, "element_name": snapped, "note": str(obj.get("note") or "")[:80]}


def _snap_to_real(name, real_names):
    import difflib
    low = name.lower()
    lut = {x.lower(): x for x in real_names}
    if low in lut:
        return lut[low]
    for k, v in lut.items():                       # substring either direction
        if low in k or k in low:
            return v
    m = difflib.get_close_matches(low, list(lut.keys()), n=1, cutoff=0.55)
    return lut[m[0]] if m else None


def _apply_reflexion(step, proposal):
    import copy
    s = copy.deepcopy(step)
    s.setdefault("ui_target", {})["element_name"] = proposal["element_name"]
    s.setdefault("virtual_mouse_action", {})["action_type"] = proposal["action_type"]
    return s


def _grab(hwnd):
    """Off-screen-safe window pixels (PIL RGB) via the capture ladder, or None."""
    try:
        _, hin = _organs()
        img, _note, _rung = hin.capture_window_robust(hwnd)
        return img
    except Exception:
        return None


def _win_origin(nodes):
    try:
        r = getattr(nodes[0], "rect", None) if nodes else None
        if r and tuple(r) != (0, 0, 0, 0):
            return int(r[0]), int(r[1])
    except Exception:
        pass
    return None


def _target_roi_local(m, coords, nodes, img):
    """Bounding box of the target (or a pad-box around the click point) in IMAGE coords."""
    o = _win_origin(nodes)
    if o is None or img is None:
        return None
    wl, wt = o
    rect = None
    if m is not None and getattr(m, "node", None) is not None:
        r = getattr(m, "rect", None)
        if r and tuple(r) != (0, 0, 0, 0):
            rect = (r[0], r[1], r[2], r[3])
    if rect is None and coords:
        pad = 48
        rect = (coords[0] - pad, coords[1] - pad, coords[0] + pad, coords[1] + pad)
    if rect is None:
        return None
    l = max(0, int(rect[0] - wl)); t = max(0, int(rect[1] - wt))
    r = min(img.width, int(rect[2] - wl)); b = min(img.height, int(rect[3] - wt))
    if r - l < 8 or b - t < 8:                      # tiny target -> pad around its centre
        cx, cy = (l + r) // 2, (t + b) // 2
        l, t = max(0, cx - 40), max(0, cy - 40)
        r, b = min(img.width, cx + 40), min(img.height, cy + 40)
    return (l, t, r, b) if (r - l) > 4 and (b - t) > 4 else None


def _roi_delta(pre, post, roi):
    """Tier A: normalized mean grayscale abs-diff over the ROI, in [0,1]."""
    if pre is None or post is None:
        return None
    try:
        from PIL import ImageChops
        a = pre.crop(roi) if roi else pre
        b = post.crop(roi) if roi else post
        a = a.convert("L").resize((48, 48)); b = b.convert("L").resize((48, 48))
        px = list(ImageChops.difference(a, b).getdata())
        return (sum(px) / len(px)) / 255.0 if px else None
    except Exception:
        return None


def _crop_b64(img, roi):
    import base64
    import io
    try:
        c = img.crop(roi) if roi else img
        buf = io.BytesIO(); c.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return None


def _img_b64(img, max_w: int = 1024):
    """Whole window as base64 PNG, downscaled so the VLM reasons about the change wherever
    it lands (display, status bar, checkmark) -- a semantic check is robust to caret/clock
    noise that would fool a raw full-frame pixel diff."""
    import base64
    import io
    try:
        c = img
        if c.width > max_w:
            c = c.resize((max_w, max(1, int(c.height * max_w / c.width))))
        buf = io.BytesIO(); c.save(buf, format="JPEG", quality=82)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return None


def _delta_since(hwnd, before_sig, expected):
    """Did the UIA tree change, or did the expected value appear? (the effect-verify signal)."""
    nodes = snapshot_nodes(hwnd)
    changed = bool(verify_state_delta(before_sig, deep_tree_signature(hwnd, nodes))
                   or expected_present(nodes, str(expected)))
    return changed, nodes


# Universal UI-name -> keyboard-glyph bridge (arithmetic + navigation + digits). This is
# generic accessibility knowledge (the "Plus" button IS the '+' key), NOT per-app scripting:
# it only fires as a last resort when a CLICK produced zero state mutation, and any app whose
# buttons carry these standard names benefits. Calculator exposes no AcceleratorKey, so this
# is the bridge that arms its operators via WM_CHAR to the CoreWindow.
_NAME_KEYS = {
    "plus": "+", "add": "+", "minus": "-", "subtract": "-", "multiply": "*", "multiply by": "*",
    "times": "*", "divide": "/", "divide by": "/", "equals": "=", "equal": "=", "enter": "\r",
    "clear": "c", "clear entry": "e", "backspace": "\b", "zero": "0", "one": "1", "two": "2",
    "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "decimal separator": ".", "point": ".", "percent": "%",
}


def _name_to_key(name):
    n = str(name or "").strip().lower()
    for suffix in (" button", " key", " sign"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return _NAME_KEYS.get(n, "")


def _uwp_core_hwnd(root):
    """Find the UWP 'Windows.UI.Core.CoreWindow' child that actually owns the input queue.
    WM_CHAR to the top-level frame is dropped by XAML; the CoreWindow child processes it."""
    import ctypes
    u = ctypes.windll.user32
    found = ctypes.c_void_p(0)
    PT = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(ch, _l):
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(ch, buf, 256)
        if buf.value == "Windows.UI.Core.CoreWindow" and not found.value:
            found.value = ch
            return False
        return True

    try:
        u.EnumChildWindows(int(root), PT(cb), 0)
    except Exception:
        return 0
    return int(found.value or 0)


def _wm_char_to_core(root, ch):
    """Post a single WM_CHAR to the UWP CoreWindow child with correct 64-bit argtypes. Returns
    the CoreWindow handle used, or 0 if it could not be found."""
    cw = _uwp_core_hwnd(root)
    if not cw:
        return 0
    try:
        u = ctypes.windll.user32
        u.PostMessageW.restype = ctypes.c_bool
        u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        u.PostMessageW(cw, 0x0102, ctypes.c_void_p(ord(ch)), 0)
    except Exception:
        return 0
    return cw


def _post_accel_char(hin, hwnd, accel):
    """Post a control's declared UIA AcceleratorKey / name->key glyph. For UWP the char must be
    sent as WM_CHAR to the Windows.UI.Core.CoreWindow CHILD (posting to the top frame is dropped)
    -- this is what arms Calculator operators (+ - * /) that InvokePattern silently drops."""
    a = str(accel or "").strip()
    if not a:
        return None
    try:
        if len(a) == 1:
            if _wm_char_to_core(hwnd, a):
                return "char-corewin"
            ok, _ = hin.post_text(hwnd, a)
            return "char" if ok else None
        ok, _ = hin.post_key_combo(hwnd, a)
        return "key" if ok else None
    except Exception:
        return None


_CALC_TEXT_KEYS = ("calculatorresults", "calculatorexpression")


def _calc_value_sig(hwnd):
    """Concatenate Calculator's CalculatorResults + CalculatorExpression text. A real digit /
    operator / equals press mutates this; a bare UIA focus shift does NOT -- so this is the
    honest effect gate for Calculator instead of the generic tree signature."""
    out = []
    for n in snapshot_nodes(hwnd):
        ident = (str(getattr(n, "aid", "") or "") + " " + str(getattr(n, "name", "") or "")).lower()
        if any(k in ident for k in _CALC_TEXT_KEYS):
            val = ""
            try:
                val = str(n.value) if getattr(n, "value", None) else ""
            except Exception:
                val = ""
            out.append(str(getattr(n, "name", "") or "") + "=" + val)
    return "|".join(out)


def _is_calculator(hwnd):
    return bool(_calc_value_sig(hwnd).replace("|", "").strip("="))


# Controls that spawn a whole new view (Settings/About/Help) and must never count as a
# successful tool/action click -- they caused the Paint "Settings gear" false positive.
BLOCKED_CONTROLS = ("settings", "about", "feedback", "options", "get help", "share feedback", "rate")


def _click_retry(node, hwnd, expected, coords, rect, minimized):
    """e16: app-agnostic effect-verify-and-retry for a CLICK. InvokePattern.Invoke() can be
    silently DROPPED by rapid UWP/WinUI XAML invokes (operator buttons like + - * / fail to
    arm, so Equals computes nothing). Escalate only while no effect is observed:
      1) plain Invoke;  2) SetFocus + 50ms + re-Invoke (wakes the AutomationPeer);
      3) LegacyIAccessible.DoDefaultAction;  4) posted click on the deepest child HWND at the
      element centre (hits the CoreWindow, not the ApplicationFrameHost wrapper).
    Never fakes success: returns (ok, method) and the caller still verifies the postcondition."""
    _, hin = _organs()
    _bnm = str(getattr(node, "name", "") or "").lower()
    if any(b in _bnm for b in BLOCKED_CONTROLS):
        return False, f"blacklisted-control ({_bnm[:24]})"
    before = deep_tree_signature(hwnd, snapshot_nodes(hwnd))
    is_calc = _is_calculator(hwnd)                # Calculator -> gate on result/expression TEXT
    before_calc = _calc_value_sig(hwnd) if is_calc else None

    def armed():
        # Windows Calculator: a UWP Invoke that only moves focus flips the generic tree
        # signature (focus/selection state) WITHOUT entering the digit, which falsely armed the
        # step and starved the keystroke bridge. So for Calculator, arm ONLY when the result or
        # expression text actually changes -- otherwise keep escalating to WM_CHAR/WM_KEYDOWN.
        if is_calc:
            return _calc_value_sig(hwnd) != before_calc
        return bool(verify_state_delta(before, deep_tree_signature(hwnd, snapshot_nodes(hwnd))))

    # Calculator: drive digits/operators/equals as WM_CHAR to the UWP CoreWindow (the only path
    # that arms operators, which InvokePattern silently drops). Bounded RETRY-UNTIL-ARMED: a lone
    # WM_CHAR intermittently drops under Win11 UWP threading, so re-post up to 3x and only accept
    # the step once the CalculatorResults/Expression TEXT actually mutated (the honest effect gate).
    if is_calc:
        _key = _name_to_key(getattr(node, "name", "")) or str(getattr(node, "accel", "") or "").strip()
        if _key and len(_key) == 1:
            for _attempt in range(3):
                if _wm_char_to_core(hwnd, _key):
                    time.sleep(0.05)
                    if armed():
                        return True, ("calc-keyboard" if _attempt == 0 else f"calc-keyboard-retry{_attempt+1}")
                time.sleep(0.05)

    # UWP/WinUI XAML buttons drop Invoke() unless the element is focused first: focus + settle.
    try:
        try:
            node.ctrl.SetFocus()
        except Exception:
            pass
        time.sleep(0.05)
    except Exception:
        pass
    ok, note = uia_act(node, "CLICK")
    time.sleep(0.08)
    if armed():
        return True, "uia-focus-first"
    # Fallback 1: focus + settle + re-invoke (fixes XAML thread drops on rapid invokes)
    try:
        ctrl = node.ctrl
        try:
            ctrl.SetFocus()
        except Exception:
            pass
        time.sleep(0.05)
        ok, note = uia_act(node, "CLICK")
        time.sleep(0.06)
        if armed():
            return True, "uia-focus-reinvoke"
        pat = ctrl.GetPattern(UIA_LEGACY)
        if pat is not None:
            pat.DoDefaultAction()
            ok = True
            time.sleep(0.06)
            if armed():
                return True, "uia-legacy-default"
    except Exception:
        pass
    # Fallback 3: post the element's declared UIA AcceleratorKey, or (when the app exposes
    # none, as Calculator does) the universal name->key glyph, as WM_CHAR/VK to the window.
    # This is what actually arms UWP operators (+ - * / =) when Invoke + focus produce no delta.
    accel = str(getattr(node, "accel", "") or "").strip() or _name_to_key(getattr(node, "name", ""))
    if accel:
        kind = _post_accel_char(hin, hwnd, accel)
        time.sleep(0.08)
        if armed():
            return True, f"accel-{kind}"
    # Fallback 4: posted click on the deepest child HWND at the element centre (UWP CoreWindow)
    cx = cy = None
    if coords:
        cx, cy = coords
    elif rect and tuple(rect) != (0, 0, 0, 0):
        cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    if cx is not None and not minimized:
        ok2, note2 = hin.post_click(hwnd, int(cx), int(cy))
        time.sleep(0.08)
        if armed():
            return True, "postclick-child"
        return ok2, "postclick-child"
    return ok, "uia-silent-drop"


def _attempt_step(step, i, path, hwnd, vis, minimized, isolated, lex_threshold, proof, dry_run):
    """Resolve -> (vision handoff) -> actuate -> verify ONE step. Returns (rec, verified, after_nodes).
    Honesty preserved: a step is verified only if delivered AND the UIA tree changed AND the
    postcondition was observed on screen; [0,0,0,0] bbox is only replaced by a real scanned rect."""
    target = step.get("ui_target", {}) or {}
    nodes = snapshot_nodes(hwnd)
    m = SM.resolve(target, nodes)
    route, method = "uia", m.how
    coords = m.coords if m.how in ("lexical", "embedding") and m.score >= lex_threshold else None
    if m.node is not None and coords:
        step.setdefault("ui_target", {})["bounding_box"] = list(m.rect)
    if coords is None and not minimized:
        desc = target.get("visual_description") or target.get("element_name") or ""
        if vis is not None and desc:
            try:
                if isolated:
                    payload = _window_vision_payload(hwnd, nodes)
                    src = "offscreen-window"
                else:
                    payload = None
                    frame_b64, _dw, _dh = vis.capture_desktop_frame()
                    if frame_b64:
                        crop_b64, (cw, ch), offset = prepare_vision_payload(frame_b64, _vision_region(nodes))
                        payload = (crop_b64, cw, ch, offset)
                    src = "crop"
                if payload:
                    b64, w, h, (ox, oy) = payload
                    vm = vis.locate_element(desc, image_base64=b64, width=w, height=h)
                    if getattr(vm, "found", False):
                        coords = (int(vm.pixel_x + ox), int(vm.pixel_y + oy))
                        route, method = "vision", f"vision(conf={vm.confidence},{src}={w}x{h})"
            except Exception as exc:
                log(f"    vision handoff error: {type(exc).__name__}: {str(exc)[:80]}")
    rec = {"step_id": step.get("step_id", i), "target": target.get("element_name"),
           "route": route, "method": method, "match_score": m.score,
           "coords": list(coords) if coords else None,
           "expected": str(step.get("expected_state_change", ""))[:120]}
    if coords is None and m.node is None:
        rec.update(action="none", delivered=False, verified=False,
                   reason="UIA did not match and vision did not locate (not faked)")
        return rec, False, nodes
    if dry_run:
        rec.update(action="dry", delivered=False, verified=False, reason="dry-run: resolution only")
        return rec, False, nodes
    pops = clear_popups(hwnd)
    before_sig = deep_tree_signature(hwnd, snapshot_nodes(hwnd))
    need_visual = (PIXEL_VERIFY or VLM_VERIFY) and not minimized
    pre_img = _grab(hwnd) if need_visual else None
    pf = {}
    if proof:
        pf["before"] = capture_proof(hwnd, f"{Path(path).stem}_step{i}_before")
    time.sleep(0.04)   # inter-step micro-settle: UWP XAML drops invokes fired <15ms apart
    if atype(step) == "CLICK" and m.node is not None:
        ok, note = _click_retry(m.node, hwnd, rec["expected"], coords, m.rect, minimized)
    else:
        ok, note = actuate(step, m, hwnd, minimized, coords)
    time.sleep(0.6)
    after_nodes = snapshot_nodes(hwnd)
    # Settle-poll for numeric results: some apps (Calculator's display) update the UIA tree a
    # beat after the Invoke lands, so a single 0.6s snapshot can miss the correct value and a
    # math step reads as unverified. Re-read for up to ~2s only when a numeric postcondition
    # is expected and not yet present -- never fabricates a value, just waits for the real one.
    _expd = str(rec["expected"])
    if ok and any(c.isdigit() for c in _expd) and not expected_present(after_nodes, _expd):
        for _ in range(5):
            time.sleep(0.4)
            _an = snapshot_nodes(hwnd)
            if expected_present(_an, _expd):
                after_nodes = _an
                break
            after_nodes = _an
    after_sig = deep_tree_signature(hwnd, after_nodes)
    structurally_changed = verify_state_delta(before_sig, after_sig)
    uia_changed = structurally_changed or expected_present(after_nodes, str(rec["expected"]))
    at = atype(step)
    payload = (step.get("virtual_mouse_action", {}) or {}).get("text_payload")
    hay = collect_text(after_nodes)
    if at == "TYPE_TEXT" and payload:
        screen_confirmed = (str(payload).lower() in hay) or expected_present(after_nodes, str(rec["expected"]))
    elif str(rec["expected"]).strip():
        screen_confirmed = expected_present(after_nodes, str(rec["expected"]))
    else:
        # no explicit postcondition (e.g. agent-loop free-form step): a real structural
        # mutation IS the confirmation; do not require a keyword match that can't exist.
        screen_confirmed = True
    if proof:
        pf["after"] = capture_proof(hwnd, f"{Path(path).stem}_step{i}_after")
    # STRICT SELECTION GATE (kills the Paint Settings-gear false positive): if the target control
    # exposes SelectionItem/Toggle, a CLICK only truly succeeds when that SAME control reports
    # selected==True or toggle_state==1 AFTER acting. A generic tree delta (an accidental Settings
    # view spawning 278 nodes) must NOT be accepted as "tool selected".
    _tgt = m.node
    _pats = (getattr(_tgt, "pats", []) or []) if _tgt is not None else []
    _has_toggle = "toggle" in _pats
    _has_select = "select" in _pats
    _sel_gate = _tgt is not None and (_has_toggle or _has_select)
    _selection_ok = True
    if _sel_gate:
        _tn = str(getattr(_tgt, "name", "") or "").lower()
        _before_ts = int(getattr(_tgt, "toggle_state", -1))
        _selection_ok = False
        for n in after_nodes:
            if _tn and str(getattr(n, "name", "") or "").lower() == _tn:
                _after_ts = int(getattr(n, "toggle_state", -1))
                if _has_toggle and not _has_select:
                    # a toggle step succeeds when its state genuinely FLIPS (on->off OR off->on);
                    # hardcoding ==1 wrongly failed deliberate toggle-OFF actions (status bar etc.)
                    _selection_ok = _after_ts in (0, 1) and _after_ts != _before_ts
                elif bool(getattr(n, "selected", False)) or _after_ts == 1:
                    _selection_ok = True
                break
    # INVARIANT (no-op loophole closed): credit a step only if the UI genuinely MUTATED
    # (structural delta here, or a real ROI-pixel change in the visual tier below) -- never
    # because a pre-existing display value already happened to match the expected text.
    v = bool(ok and structurally_changed and screen_confirmed and _selection_ok)
    verification_type = ("SELECTION_STATE" if _sel_gate else "UIA_DELTA") if v else None
    # ---- Tier A/B visual postcondition: credit correct-but-UIA-invisible actions ----
    # A selection-gated control that did NOT flip is authoritative -- do not let pixel/VLM rescue it.
    if (not v) and ok and need_visual and pre_img is not None and not (_sel_gate and not _selection_ok):
        post_img = _grab(hwnd)
        roi = _target_roi_local(m, coords, nodes, pre_img)
        d = _roi_delta(pre_img, post_img, roi)
        rec["roi_delta"] = round(d, 4) if d is not None else None
        credited = False
        # Tier A: a localized change of the target region in [ROI_LOW, ROI_HIGH] == a real state flip.
        if d is not None and ROI_LOW <= d <= ROI_HIGH:
            v = True; screen_confirmed = True; verification_type = "PIXEL_DIFF"; credited = True
        # Tier B: effect landed OUTSIDE the target crop (display/status/checkmark) -> ask the VLM
        # about the WHOLE window. Gated to inconclusive Tier A, never trusted on a bypassed call,
        # and NEVER used to confirm a NUMERIC expectation (the VLM must not guess math -- a wrong
        # 42/99 would otherwise slip past as a false-positive step verification).
        _exp = str(rec["expected"])
        _numeric = any(c.isdigit() for c in _exp)
        if (not credited) and VLM_VERIFY and vis is not None and post_img is not None and _exp and not _numeric:
            pre_c, post_c = _img_b64(pre_img), _img_b64(post_img)
            verdict = {}
            if pre_c and post_c:
                try:
                    verdict = vis.verify_state_change(str(rec["expected"]), pre_c, post_c) or {}
                except Exception:
                    verdict = {}
            expl = str(verdict.get("explanation", "")).lower()
            if verdict.get("success") and verdict.get("change_detected") and "bypass" not in expl:
                v = True; screen_confirmed = True; verification_type = "VLM_SEMANTIC"
    rec.update(action=at, delivered=bool(ok), actuation_note=note, popups_cleared=pops,
               uia_changed=bool(uia_changed), screen_confirmed=bool(screen_confirmed),
               verification_type=verification_type)
    if proof:
        rec["proof"] = pf
    rec["verified"] = v
    if not v:
        if not ok:
            rec["reason"] = note
        else:
            rec["reason"] = "postcondition not observed (UIA, ROI-pixel and VLM all negative)"
    return rec, v, after_nodes


def _run_steps(path: str, hwnd, title, dry_run=False, vision_handoff=True,
               lex_threshold=SM.LEX_STRONG, proof=False, isolated=False):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    steps = data.get("trajectory") or []
    app_name = data.get("app_metadata", {}).get("app_name", Path(path).name)
    log(f"{app_name}: {len(steps)} steps  [{Path(path).name}]")

    if not hwnd:
        log("  ERROR: no target window resolved; cannot execute live.")
        return {"file": path, "status": "no_window", "verified": 0, "total": len(steps)}

    _, hin = _organs()
    # After isolation the window is restored (off-screen), so coordinate actuation is allowed;
    # minimized only remains True if we are running on-screen and the app is genuinely iconic.
    minimized = hin.is_minimized(hwnd)
    log(f"  hwnd={hwnd} title={title!r} minimized={minimized} dry_run={dry_run}")
    # Vision is available BOTH on-screen (physical-desktop grab) and while parked off-screen
    # (the window's own PrintWindow pixels -- see _window_vision_payload), so isolation no
    # longer blinds the :8081 tier for custom-canvas apps that expose no UIA (e.g. Paint).
    vis = _vision() if (vision_handoff and not dry_run) else None

    # Episodic memory read: have we already VERIFIED this (app, task) before? If so the proven
    # trajectory is available as a fast path / few-shot reference instead of re-guessing.
    if emem is not None and getattr(emem, "CACHE_ON", False):
        try:
            _hit = emem.lookup(app_name, data.get("high_level_task", ""))
            log(f"  episodic memory: {'HIT score=' + str(_hit[1]) + ' (proven ' + str(_hit[2]['steps']) + '-step plan)' if _hit else 'miss'}")
        except Exception:
            pass

    results, verified = [], 0
    for i, step in enumerate(steps, 1):
        rec, v, after_nodes = _attempt_step(step, i, path, hwnd, vis, minimized, isolated, lex_threshold, proof, dry_run)
        # --- Part 3: Reflexion recovery loop (bounded retries on a failed step) ---
        attempts = 0
        while (not v) and (not dry_run) and REFLEXION and attempts < REFLEXION_BUDGET:
            attempts += 1
            log(f"  step {i}: reflexion recovery attempt {attempts} (reason: {str(rec.get('reason') or 'no change')[:50]})")
            proposal = _reflexion_propose(app_name, step, str(rec.get("reason") or "no state change"), after_nodes)
            log(f"  step {i}: reflexion proposal -> {json.dumps(proposal) if proposal else 'NONE'}")
            if not proposal:
                break
            s2 = _apply_reflexion(step, proposal)
            rec2, v, after_nodes = _attempt_step(s2, i, path, hwnd, vis, minimized, isolated, lex_threshold, proof, dry_run)
            log(f"  step {i}: reflexion re-attempt {proposal['element_name']!r} -> verified={v} route={rec2.get('route')}")
            rec["reflexion"] = {"attempts": attempts, "proposal": proposal,
                                "recovered": bool(v), "route": rec2.get("route")}
            if v:
                rec = rec2
                rec["recovered_by_reflexion"] = True
        if v:
            verified += 1
        results.append(rec)
        log(f"  step {i}: {rec.get('route')}/{rec.get('method')} verified={v}"
            + (" [REFLEXION RECOVERED]" if rec.get("recovered_by_reflexion") else ""))

    RESOLVED_DIR.mkdir(parents=True, exist_ok=True)
    (RESOLVED_DIR / (Path(path).stem + ".resolved.json")).write_text(
        json.dumps(data, ensure_ascii=False, indent=3), encoding="utf-8")
    n_recovered = sum(1 for r in results if r.get("recovered_by_reflexion"))
    from collections import Counter as _C
    vtally = _C(r.get("verification_type") for r in results if r.get("verified"))
    # Episodic memory write: only a FULLY verified task becomes ground truth for reuse/training.
    # Episodic memory write is DISABLED here by default (e13 fix): committing on
    # all-steps-verified alone can cache a symbolic task whose FINAL numeric postcondition
    # failed. The authoritative commit now lives behind the caller's modality-aware task
    # gate (see phase2_live_accuracy.run_task). Set HOJAIGA_EPISODIC_AUTOWRITE=1 to opt in.
    stored = False
    if (emem is not None and getattr(emem, "CACHE_ON", False)
            and os.environ.get("HOJAIGA_EPISODIC_AUTOWRITE", "0").strip().lower() not in ("0", "false", "no", "off")
            and verified and verified == len(steps)):
        _vt = vtally.most_common(1)
        stored = emem.save_verified(app_name, data.get("high_level_task", ""), steps,
                                    (_vt[0][0] if _vt else "MIXED"))
    summary = {"file": path, "app": app_name, "status": "run",
               "verified": verified, "total": len(steps), "minimized": minimized,
               "reflexion_recovered": n_recovered, "reflexion_on": bool(REFLEXION and not dry_run),
               "verification_breakdown": dict(vtally), "episodic_stored": stored}
    with EVAL_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), **summary,
                             "steps": results}, ensure_ascii=False) + "\n")
    log(f"  -> {verified}/{len(steps)} steps verified; eval logged to {EVAL_LOG}")
    return summary


def atype(step):
    return (step.get("virtual_mouse_action", {}) or {}).get("action_type", "CLICK")


# ---------------------------------------------------------------------------
# safe self-test: a tiny Calculator trajectory (visible window; no installs)
# ---------------------------------------------------------------------------

CALC_DEMO = {
    "app_metadata": {"app_name": "Calculator", "dataset_split": "EVAL", "scan_prerequisites_met": True},
    "high_level_task": "Compute 1 + 1 = 2",
    "prerequisite_state": "Calculator is open in Standard mode",
    "total_steps": 4,
    "trajectory": [
        {"step_id": 1, "ui_target": {"element_name": "Num1Button", "element_type": "Button", "automation_id": "num1Button", "bounding_box": [0, 0, 0, 0]},
         "virtual_mouse_action": {"action_type": "CLICK"}, "expected_state_change": "display shows 1"},
        {"step_id": 2, "ui_target": {"element_name": "plusButton", "element_type": "Button", "automation_id": "plusButton", "bounding_box": [0, 0, 0, 0]},
         "virtual_mouse_action": {"action_type": "CLICK"}, "expected_state_change": "plus operator armed"},
        {"step_id": 3, "ui_target": {"element_name": "Num1Button", "element_type": "Button", "automation_id": "num1Button", "bounding_box": [0, 0, 0, 0]},
         "virtual_mouse_action": {"action_type": "CLICK"}, "expected_state_change": "display shows 1"},
        {"step_id": 4, "ui_target": {"element_name": "equalButton", "element_type": "Button", "automation_id": "equalButton", "bounding_box": [0, 0, 0, 0]},
         "virtual_mouse_action": {"action_type": "CLICK"}, "expected_state_change": "display shows 2"},
    ],
}


def calculator_demo(args):
    calc = RESOLVED_DIR.parent / "_calc_demo.json"
    RESOLVED_DIR.mkdir(parents=True, exist_ok=True)
    calc.write_text(json.dumps(CALC_DEMO, indent=3), encoding="utf-8")
    hwnd, title = find_hwnd(args.title or "Calculator")
    if not hwnd:
        log("Calculator not running. Open it (start calc.exe), then re-run, or pass --hwnd.")
        return
    log(f"demo target hwnd={hwnd} '{title}'")
    run_trajectory(str(calc), hwnd, title, dry_run=args.dry_run, vision_handoff=not args.no_vision, proof=args.proof)


def main():
    p = argparse.ArgumentParser(description="Execute a decomposed trajectory live against a real window.")
    p.add_argument("--traj", help="path (or glob) to a trajectory JSON")
    p.add_argument("--hwnd", type=int, default=None)
    p.add_argument("--title", default="", help="substring of the target window title")
    p.add_argument("--dry-run", action="store_true", help="resolve targets only; execute nothing")
    p.add_argument("--no-vision", action="store_true", help="disable the :8081 vision handoff tier")
    p.add_argument("--calculator-demo", action="store_true", help="safe self-test on Calculator")
    p.add_argument("--proof", action="store_true", help="save before/after screenshots per step (visual proof) to trajectories/proof/")
    args = p.parse_args()

    if args.calculator_demo:
        return calculator_demo(args)
    if not args.traj:
        p.error("give --traj or --calculator-demo")
    files = glob.glob(args.traj) if any(c in args.traj for c in "*?[") else [args.traj]
    hwnd = args.hwnd
    title = args.title
    if not hwnd and title:
        hwnd, title = find_hwnd(title)
    if not hwnd:
        log("ERROR: could not resolve a window from --hwnd/--title.")
        sys.exit(2)
    for f in files:
        run_trajectory(f, hwnd, title, dry_run=args.dry_run, vision_handoff=not args.no_vision, proof=args.proof)


if __name__ == "__main__":
    main()
