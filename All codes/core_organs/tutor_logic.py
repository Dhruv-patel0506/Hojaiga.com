"""
tutor_logic -- the pure (no torch, no GUI, no screen) logic behind run_autonomous_app_tutor.py, so it can be replayed offline from a saved trace and unit-tested.

    build_action_queue(controls, win_size)      every named, non-frame control discovered in Stage 2 -> the Stage 3 queue. No count cap; the only things left out are window chrome, exact
                                                duplicates (same role + name + position) and nameless controls, and queue_audit() reports each of them so nothing disappears silently.
    container_context(control, all_controls)    the smallest enclosing control and the nearest siblings: what surrounds this control
    explain_control(...)                        one functional sentence from the VLM (control crop + its container), cached; a context-derived sentence ONLY when the model is
                                                unavailable / over budget / answers badly, and the result says which (source = vlm | context_fallback)
    live_rect(win) / resolve_point(...)         re-read the window rectangle and re-derive the click point from the control's window-relative (normalised) centre
    act_on_control(win, control, action, ...)   re-fetch the rectangle AFTER focusing and BEFORE every move / click / type, refuse when the window is gone or the point left it
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:
    from . import chrome_filter as _chrome
except ImportError:
    import chrome_filter as _chrome                                           # type: ignore

Rect = Tuple[int, int, int, int]                                              # left, top, width, height

_ROLE_GROUP = {"edit": 0, "searchbox": 0, "combobox": 0, "button": 1, "splitbutton": 1, "menuitem": 1, "checkbox": 1, "radiobutton": 1,
               "tabitem": 2, "treeitem": 2, "hyperlink": 2, "listitem": 3}
NOISE_NAMES = re.compile(r"^(button|list item|text|image|pane|group|custom)$", re.I)       # scanner placeholders: a role word is not a name


def _role(c: Dict[str, Any]) -> str:
    return re.sub(r"Control$", "", str(c.get("role") or c.get("type") or "")).strip().lower()


def _name(c: Dict[str, Any]) -> str:
    return str(c.get("name") or "").strip()


# ---- geometry: normalise at scan time, re-derive at act time -------------------------------------------------------------------
def normalise_controls(raw: Sequence[Dict[str, Any]], rect: Rect) -> List[Dict[str, Any]]:
    """Attach window-relative geometry: norm = {cx, cy, w, h} as fractions of the window rectangle in force when the control was read. bbox stays absolute (left, top, right, bottom)."""
    L, T, W, H = rect
    W, H = max(W, 1), max(H, 1)
    out = []
    for c in raw:
        b = c.get("bbox")
        if not b or len(b) != 4:
            continue
        cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        d = dict(c)
        d["norm"] = {"cx": (cx - L) / W, "cy": (cy - T) / H, "w": (b[2] - b[0]) / W, "h": (b[3] - b[1]) / H}
        d["rect0"] = [L, T, W, H]
        out.append(d)
    return out


def live_rect(win: Any) -> Optional[Rect]:
    """The window's rectangle RIGHT NOW as (left, top, width, height); None when it is gone, minimised or empty."""
    try:
        if hasattr(win, "is_minimized") and win.is_minimized():
            return None
        r = win.rectangle()
        L, T, R, B = int(r.left), int(r.top), int(r.right), int(r.bottom)
    except Exception:
        return None
    w, h = R - L, B - T
    if w < 50 or h < 50 or L <= -30000 or T <= -30000:                        # Windows parks minimised windows at -32000
        return None
    return (L, T, w, h)


def resolve_point(control: Dict[str, Any], rect: Rect) -> Optional[Tuple[int, int]]:
    """Absolute screen point of the control's centre inside the CURRENT rectangle, from its window-relative centre (falls back to the stored absolute centre when no norm exists)."""
    L, T, W, H = rect
    n = control.get("norm")
    if n:
        x, y = L + n["cx"] * W, T + n["cy"] * H
    else:
        b = control.get("bbox")
        if not b:
            return None
        x, y = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    if not (L <= x <= L + W and T <= y <= T + H):
        return None                                                           # the point left the window: refuse rather than click whatever is there
    return int(round(x)), int(round(y))


_PASSWORD = re.compile(r"password|passcode|\bpin\b|secret|cvv|card number", re.I)


def act_on_control(win: Any, control: Dict[str, Any], action: str = "move", text: str = "", *, archetype: str = "",
                   rect_fn: Callable[[Any], Optional[Rect]] = live_rect, mouse: Any = None, keyboard: Any = None, settle: Callable[[], None] = lambda: None) -> Dict[str, Any]:
    """Re-fetch the window rectangle, re-normalise the control centre, then move / click / type. Order: read rect -> focus -> read rect AGAIN (focus can restore or move the window) -> act.
    Returns {ok, reason, rect, point, drift_px}; never raises. A click on a trap control (rag.archetypes.is_trap) and typing into a credential field are refused."""
    res: Dict[str, Any] = {"ok": False, "reason": "", "rect": None, "point": None, "drift_px": None, "action": action}
    try:
        name = _name(control)
        if action == "click" and archetype:
            try:
                from core_organs.rag import archetypes as _A                  # type: ignore
                if _A.is_trap(archetype, name):
                    res["reason"] = "trap_control_refused"
                    return res
            except Exception:
                pass
        if action == "type" and _PASSWORD.search(name):
            res["reason"] = "credential_field_refused"
            return res
        if rect_fn(win) is None:
            res["reason"] = "window_not_visible"
            return res
        try:
            win.set_focus()
            settle()
        except Exception:
            pass
        rect = rect_fn(win)                                                   # after focus: restore / snap / DPI changes land here
        if rect is None:
            res["reason"] = "window_not_visible_after_focus"
            return res
        pt = resolve_point(control, rect)
        res["rect"] = list(rect)
        if pt is None:
            res["reason"] = "point_outside_window"
            return res
        res["point"] = list(pt)
        b = control.get("bbox")
        if b:
            res["drift_px"] = round(((pt[0] - (b[0] + b[2]) / 2.0) ** 2 + (pt[1] - (b[1] + b[3]) / 2.0) ** 2) ** 0.5, 1)
        if mouse is not None:
            if action in ("move", "click", "type"):
                mouse.move(coords=pt)
            if action == "click" or action == "type":
                mouse.click(coords=pt)
        if action == "type" and keyboard is not None and text:
            keyboard.send_keys(text, with_spaces=True)
        res["ok"] = True
        res["reason"] = "done" if mouse is not None else "resolved_dry_run"
        return res
    except Exception as e:
        res["reason"] = f"error:{type(e).__name__}"
        return res


# ---- Stage 2 -> Stage 3 queue -------------------------------------------------------------------------------------------------
def _key(c: Dict[str, Any]) -> Tuple[str, str, int, int]:
    b = c.get("bbox") or [0, 0, 0, 0]
    return (_role(c), _name(c).lower(), int((b[0] + b[2]) // 2 // 4), int((b[1] + b[3]) // 2 // 4))


def queue_audit(controls: Sequence[Dict[str, Any]], win_size: Optional[Tuple[int, int]] = None, rect: Optional[Rect] = None) -> Dict[str, Any]:
    """Partition every discovered control into queued / dropped-with-reason. queued + sum(dropped) == len(controls) always."""
    queued: List[Dict[str, Any]] = []
    dropped = {"nameless": 0, "placeholder_name": 0, "window_chrome": 0, "duplicate": 0, "no_geometry": 0}
    seen = set()
    for c in controls:
        nm, b = _name(c), c.get("bbox")
        if not nm:
            dropped["nameless"] += 1
            continue
        if NOISE_NAMES.match(nm):
            dropped["placeholder_name"] += 1
            continue
        if not b or len(b) != 4:
            dropped["no_geometry"] += 1
            continue
        if rect:
            box = [b[0] - rect[0], b[1] - rect[1], b[2] - b[0], b[3] - b[1]]
        else:
            box = None
        if _chrome.is_window_chrome(nm, str(c.get("type", "")), box, win_size if box else None):
            dropped["window_chrome"] += 1
            continue
        k = _key(c)
        if k in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(k)
        queued.append(c)
    queued.sort(key=lambda c: (_ROLE_GROUP.get(_role(c), 4), (c["bbox"][1] // 24), c["bbox"][0]))     # inputs, then commands, then navigation, then the rest; reading order inside a group
    return {"queued": queued, "dropped": dropped, "total": len(controls), "balanced": len(queued) + sum(dropped.values()) == len(controls)}


def build_action_queue(controls: Sequence[Dict[str, Any]], win_size: Optional[Tuple[int, int]] = None, rect: Optional[Rect] = None) -> List[Dict[str, Any]]:
    return queue_audit(controls, win_size, rect)["queued"]


# ---- Stage 3 explanations ------------------------------------------------------------------------------------------------------
def _area(b: Sequence[float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def container_context(control: Dict[str, Any], all_controls: Sequence[Dict[str, Any]], k: int = 6) -> Dict[str, Any]:
    """The smallest strictly-larger control whose box contains this one (its container) and up to k nearest siblings inside it."""
    b = control.get("bbox")
    if not b:
        return {"container": "", "container_role": "", "siblings": []}
    cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    best, best_area = None, float("inf")
    for o in all_controls:
        ob = o.get("bbox")
        if o is control or not ob or len(ob) != 4:
            continue
        if ob[0] <= b[0] + 2 and ob[1] <= b[1] + 2 and ob[2] >= b[2] - 2 and ob[3] >= b[3] - 2 and _area(ob) > _area(b) * 1.2 and _name(o):
            a = _area(ob)
            if a < best_area:
                best, best_area = o, a
    pool = [o for o in all_controls if o is not control and _name(o) and o.get("bbox") and len(o["bbox"]) == 4
            and (best is None or (best["bbox"][0] <= (o["bbox"][0] + o["bbox"][2]) / 2 <= best["bbox"][2] and best["bbox"][1] <= (o["bbox"][1] + o["bbox"][3]) / 2 <= best["bbox"][3]))]
    pool.sort(key=lambda o: ((o["bbox"][0] + o["bbox"][2]) / 2 - cx) ** 2 + ((o["bbox"][1] + o["bbox"][3]) / 2 - cy) ** 2)
    sib = []
    for o in pool:
        n = _name(o)
        if n.lower() != _name(control).lower() and n not in sib:
            sib.append(n)
        if len(sib) >= k:
            break
    return {"container": _name(best) if best else "", "container_role": _role(best) if best else "", "siblings": sib}


def build_explain_prompt(control: Dict[str, Any], ctx: Dict[str, Any], app_title: str = "") -> str:
    where = f"inside the '{ctx['container']}' {ctx['container_role'] or 'area'}" if ctx.get("container") else "in the application window"
    near = f" Nearby controls: {', '.join(repr(s) for s in ctx.get('siblings', [])[:6])}." if ctx.get("siblings") else ""
    return (f"The image is the {_role(control) or 'control'} labelled '{_name(control)}' in the application '{app_title}', {where}.{near} "
            f"In ONE short sentence, say what this control does for the user, judging by how it looks and what surrounds it. "
            f"Do not start with 'This is' or 'Here is', do not repeat the label alone, and do not use a list.")


_TEMPLATE_ECHO = re.compile(r"^\s*(here is the\b|this is the\b.*\bcontrol\b|use '.*' to switch views)", re.I)


def clean_sentence(raw: str, max_words: int = 32) -> Optional[str]:
    """Keep the first sentence of a model answer; None when it is empty, an echo of the old static template, a prompt echo or too short to mean anything."""
    s = (raw or "").strip()
    s = re.sub(r"^(assistant|answer|response)\s*[:\n]+", "", s, flags=re.I).strip()
    s = s.strip("`\"' \n")
    if not s or "\n\n" in s:
        s = s.split("\n\n")[-1].strip() if s else s
    m = re.match(r"(.+?[.!?])(\s|$)", s.replace("\n", " "))
    s = (m.group(1) if m else s.replace("\n", " ")).strip()
    words = s.split()
    if len(words) < 4 or _TEMPLATE_ECHO.match(s) or "ONE short sentence" in s:
        return None
    if len(words) > max_words:
        s = " ".join(words[:max_words]).rstrip(",;:") + "."
    return s if s.endswith((".", "!", "?")) else s + "."


def context_sentence(control: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Model-free sentence derived only from this control's role, label and surroundings. Used ONLY as the labelled fallback."""
    role, nm = _role(control), _name(control)
    where = f"in the {ctx['container']} {ctx['container_role'] or 'area'}" if ctx.get("container") else "in the main window"
    near = f", next to {' and '.join(repr(s) for s in ctx['siblings'][:2])}" if ctx.get("siblings") else ""
    if role in ("edit", "searchbox", "combobox"):
        return f"Type or choose a value for '{nm}' {where}{near}."
    if role in ("tabitem", "treeitem", "hyperlink", "listitem"):
        return f"Select '{nm}' {where} to move to that part of the app{near}."
    if role in ("checkbox", "radiobutton"):
        return f"Toggle '{nm}' {where} to turn that option on or off{near}."
    return f"Press '{nm}' {where} to run that command{near}."


def explain_control(control: Dict[str, Any], all_controls: Sequence[Dict[str, Any]], *, image: Any = None, rect: Optional[Rect] = None, app_title: str = "",
                    vlm_fn: Optional[Callable[[Any, str], str]] = None, cache: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, str]:
    """{text, source}. source = 'vlm' when the model produced an acceptable sentence, else 'context_fallback'. vlm_fn(crop_image, prompt) -> raw text and may raise."""
    ctx = container_context(control, all_controls)
    ck = hashlib.sha1(f"{app_title}|{_role(control)}|{_name(control)}|{ctx['container']}|{'/'.join(ctx['siblings'][:3])}".encode("utf-8", "ignore")).hexdigest()
    if cache is not None and ck in cache:
        return dict(cache[ck], cached=True)
    out: Dict[str, str] = {}
    if vlm_fn is not None:
        try:
            crop = crop_control(image, control, rect) if image is not None else None
            text = clean_sentence(vlm_fn(crop, build_explain_prompt(control, ctx, app_title)))
            if text:
                out = {"text": text, "source": "vlm"}
        except Exception:
            pass
    if not out:
        out = {"text": context_sentence(control, ctx), "source": "context_fallback"}
    if cache is not None:
        cache[ck] = out
    return out


def crop_control(image: Any, control: Dict[str, Any], rect: Optional[Rect], pad: int = 24) -> Any:
    """The control plus padding from the window screenshot (scaled when the screenshot and the window rectangle differ in size)."""
    b = control.get("bbox")
    if image is None or not b or not rect:
        return image
    L, T, W, H = rect
    sx, sy = image.width / max(W, 1), image.height / max(H, 1)
    x0, y0 = max(0, int((b[0] - L - pad) * sx)), max(0, int((b[1] - T - pad) * sy))
    x1, y1 = min(image.width, int((b[2] - L + pad) * sx)), min(image.height, int((b[3] - T + pad) * sy))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return image
    return image.crop((x0, y0, x1, y1))


# ---- saved traces (offline replay) --------------------------------------------------------------------------------------------
def controls_from_trace(trace: Dict[str, Any]) -> Dict[str, Any]:
    """A saved scan (`*_scan_result.json`: elements[{name, type, coords:{box:[l,t,r,b]}}]) -> {controls, rect, title}. Malformed elements are skipped, never fatal."""
    controls: List[Dict[str, Any]] = []
    for e in (trace.get("elements") or []) if isinstance(trace, dict) else []:
        try:
            box = (e.get("coords") or {}).get("box")
            if not box or len(box) != 4:
                continue
            controls.append({"role": re.sub(r"Control$", "", str(e.get("type") or "Element")), "name": str(e.get("name") or "").strip(), "bbox": [int(v) for v in box]})
        except Exception:
            continue
    if controls:
        L, T = min(c["bbox"][0] for c in controls), min(c["bbox"][1] for c in controls)
        R, B = max(c["bbox"][2] for c in controls), max(c["bbox"][3] for c in controls)
        rect: Rect = (L, T, max(R - L, 1), max(B - T, 1))
    else:
        rect = (0, 0, 1, 1)
    return {"controls": normalise_controls(controls, rect), "rect": rect, "title": str(trace.get("title") or "") if isinstance(trace, dict) else ""}
