"""
professor.perception_ladder -- WHEN THE ACCESSIBILITY TREE IS BLIND: retry it properly, then fall back on vision, and SAY which one was used.

An application can show 0 nodes for reasons that have nothing to do with it being unreadable:
  1 the window the launcher returned is gone (a splash / launcher window replaced by the real main window) - the tree of a dead handle is empty
  2 a Chromium / WebView2 / Electron surface builds its accessibility tree only after an assistive client asks for it (WM_GETOBJECT on its render windows)
  3 a lazily laid-out toolkit realises its controls only when a pixel of it is on screen (atlas.scanner.ensure_tree nudges a parked window for that)
Only when all of that has been tried is the application treated as BLIND: names and positions then come from the vision pipeline (OCR + the icon detector + the vision model) and the
report says so ('perception.used = vision'), so nobody mistakes a vision catalog for a tree catalog.

  tree_ladder(hwnd, bg, ...)  -> (hwnd, nodes, report)      report = {used: tree | tree-retry | vision-needed, attempts: [...], hwnd_changed}
Nothing here is specific to an application: the rungs are about window lifetimes, toolkits and accessibility clients in general.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from typing import Any, Dict, List, Tuple

WM_GETOBJECT = 0x003D
OBJID_CLIENT = -4
UIA_ROOT_OBJECT_ID = -25
SMTO_ABORTIFHUNG = 0x0002
_u = ctypes.windll.user32


def _alive(h: int) -> bool:
    return bool(h) and bool(_u.IsWindow(h))


def _pid(h: int) -> int:
    pid = wt.DWORD()
    _u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return int(pid.value)


def _children(h: int) -> List[int]:
    out: List[int] = []
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(c, _lp):
        out.append(int(c))
        return True
    try:
        _u.EnumChildWindows(h, PROC(cb), 0)
    except Exception:
        pass
    return out


def _class(h: int) -> str:
    buf = ctypes.create_unicode_buffer(128)
    _u.GetClassNameW(h, buf, 128)
    return buf.value


def refind_window(old: int, title_hint: str = "", pid_hint: int = 0) -> int:
    """The application's CURRENT main window when the launcher's handle died or holds nothing: a top-level window of the same process (else one with the expected title), the largest one."""
    from core_organs import universal_scan as us
    pid = pid_hint or (_pid(old) if _alive(old) else 0)
    best, area = 0, 0
    for h, (wpid, cls, title) in us._top_windows().items():
        if h == old:
            continue
        if not ((pid and wpid == pid) or (title_hint and title and title.strip().lower() == title_hint.strip().lower())):
            continue
        r = wt.RECT()
        _u.GetWindowRect(h, ctypes.byref(r))
        a = max(0, r.right - r.left) * max(0, r.bottom - r.top)
        if a > area and title:
            best, area = h, a
    return best


def wake_accessibility(h: int) -> int:
    """Ask the window and its render children for their accessibility root the way a screen reader does (WM_GETOBJECT, client + UIA root). Chromium-family surfaces switch their tree on
    when asked. Returns how many windows were asked. Read-only: no input, no focus change."""
    asked = 0
    res = ctypes.c_size_t()
    for w in [h] + _children(h)[:60]:
        cls = _class(w)
        if w != h and not any(k in cls for k in ("Chrome_RenderWidgetHostHWND", "Chrome_WidgetWin", "Intermediate D3D Window", "WebView", "CefBrowserWindow", "Windows.UI")):
            continue
        for obj in (OBJID_CLIENT, UIA_ROOT_OBJECT_ID):
            try:
                _u.SendMessageTimeoutW(w, WM_GETOBJECT, 0, obj, SMTO_ABORTIFHUNG, 500, ctypes.byref(res))
            except Exception:
                pass
        asked += 1
    return asked


def tree_ladder(hwnd: int, bg: Any = None, title_hint: str = "", min_nodes: int = 8, max_s: float = 24.0) -> Tuple[int, List[Any], Dict[str, Any]]:
    """Rung by rung until the tree is usable (>= min_nodes nodes that are not just the frame) or the time is up. Returns (hwnd to use, nodes, report)."""
    from core_organs import fast_uia
    from core_organs.atlas import scanner as SC
    t0 = time.time()
    rep: Dict[str, Any] = {"used": "", "attempts": [], "hwnd_changed": False, "first_hwnd": hwnd}

    def usable(nodes: List[Any]) -> bool:
        return len(nodes) >= min_nodes and not SC.frame_only(nodes)

    nodes, waited, frame_only = SC.ensure_tree(hwnd, bg, max_s=6.0) if _alive(hwnd) else ([], 0.0, True)
    rep["attempts"].append({"how": "accessibility tree", "nodes": len(nodes), "frame_only": frame_only, "s": round(time.time() - t0, 1)})
    if usable(nodes):
        rep["used"] = "tree"
        return hwnd, nodes, rep
    # rung 1: the window may have been replaced
    if not _alive(hwnd) or not nodes:
        nh = refind_window(hwnd, title_hint)
        if nh and nh != hwnd:
            hwnd = nh
            rep["hwnd_changed"] = True
            nodes = fast_uia.snapshot(hwnd, timeout_ms=7000) or []
            rep["attempts"].append({"how": "re-found the application's current main window", "hwnd": nh, "nodes": len(nodes), "s": round(time.time() - t0, 1)})
            if usable(nodes):
                rep["used"] = "tree-retry"
                return hwnd, nodes, rep
    # rung 2: ask for the accessibility tree like an assistive client, then give it time (backing off)
    for i, wait in enumerate((1.5, 3.0, 5.0)):
        if time.time() - t0 > max_s:
            break
        asked = wake_accessibility(hwnd) if _alive(hwnd) else 0
        if bg is not None and getattr(bg, "mode", "") == "parked":
            try:
                bg.lay_out(settle_s=0.5)
            except Exception:
                pass
        time.sleep(wait)
        nodes = (fast_uia.snapshot(hwnd, timeout_ms=7000) or []) if _alive(hwnd) else []
        rep["attempts"].append({"how": f"asked {asked} window(s) for their accessibility root, waited {wait}s", "nodes": len(nodes), "s": round(time.time() - t0, 1)})
        if usable(nodes):
            rep["used"] = "tree-retry"
            return hwnd, nodes, rep
    rep["used"] = "vision-needed"
    return hwnd, nodes, rep
