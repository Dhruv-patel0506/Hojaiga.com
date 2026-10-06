"""
capability_probe.py — per-window/control capability probe for the actuation ladder (input wall, #5).

Some surfaces simply do not take posted input: Chromium/CEF render widgets, XAML islands
(WinUI/UWP), and DirectX/GL swapchains all swallow WM_LBUTTONDOWN or address invisible
-32000 rects, and Steam is exactly such a wall (CEF inside Qt inside Win32). The product law
here is honesty: prefer the NATIVE TREE (UIA patterns / classic WM_COMMAND), use posted mouse
only where the surface plausibly takes it, use pixel geometry as the LAST resort, and when
nothing actuates, record the WALL with the full tiers trail — never fake a success.

The probe is STRUCTURAL, not a per-app table: it reads window-class markers that frameworks
themselves plant (Chrome_RenderWidgetHostHWND, Microsoft.UI.Content.DesktopChildSiteBridge,
Windows.UI.Core.CoreWindow, an HMENU on the frame, counts of classic Win32 controls) and turns
that into an informed ordering of the SAME effector ladder EffectorLadder already runs. No
app name ever enters the decision.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as _wt
from typing import Any, Dict, List, Tuple

_u32 = ctypes.windll.user32

# Framework self-identification markers (class substrings the toolkits put on their own
# windows). Matching a FRAMEWORK is not matching an APP: every Chromium/CEF app carries
# Chrome_RenderWidgetHostHWND whether it is Steam, Slack or a VS Code panel.
_CHROMIUM_MARKS = ("chrome_renderwidgethosthwnd", "chrome_widgetwin", "intermediate d3d window")
_XAML_MARKS = ("microsoft.ui.content.desktopchildsitebridge", "windows.ui.core.corewindow",
               "microsoft.ui.input", "desktopwindowcontentbridge", "winuidesktopwin32windowclass",
               "inputsite", "xaml_windowsuicomponents_windowsuicompositionswpholder")
_D3D_MARKS = ("d3d", "opengl", "vulkan", "nvrpi", "cuda")
_WIN32_CONTROL_MARKS = ("button", "edit", "static", "toolbarwindow32", "sysmainmenu", "combobox",
                        "listview", "treeview", "msctls_", "richedit", "scal_0", "#32770")


def _child_classes(hwnd: int, cap: int = 60) -> List[str]:
    out: List[str] = []

    @ctypes.WINFUNCTYPE(_wt.BOOL, _wt.HWND, _wt.LPARAM)
    def _cb(h, _l):
        b = ctypes.create_unicode_buffer(128)
        _u32.GetClassNameW(h, b, 128)
        if b.value:
            out.append(b.value)
        return len(out) < cap
    try:
        _u32.EnumChildWindows(hwnd, _cb, 0)
    except Exception:  # noqa: BLE001
        pass
    return out


def _lower(root_cls: str, kids: List[str]) -> str:
    return " ".join([root_cls] + kids).lower()


def surface_profile(hwnd: int) -> Dict[str, Any]:
    """Structural read of what kind of surface this window presents (framework markers only)."""
    b = ctypes.create_unicode_buffer(128)
    _u32.GetClassNameW(hwnd, b, 128)
    root = b.value
    kids = _child_classes(hwnd)
    blob = _lower(root, kids)
    flags = {
        "chromium_cef": any(m in blob for m in _CHROMIUM_MARKS),
        "xaml_island": any(m in blob for m in _XAML_MARKS),
        "d3d_opaque": any(m in blob for m in _D3D_MARKS),
        "classic_menu": bool(_u32.GetMenu(hwnd)),
        "win32_controls": sum(1 for k in kids if any(m in k.lower() for m in _WIN32_CONTROL_MARKS)),
    }
    if flags["chromium_cef"]:
        surface = "chromium/cef"
    elif flags["xaml_island"]:
        surface = "xaml/winui"
    elif flags["d3d_opaque"] and flags["win32_controls"] == 0:
        surface = "directx/opaque"
    elif flags["win32_controls"] >= 3 or flags["classic_menu"]:
        surface = "classic-win32"
    elif kids:
        surface = "mixed/unknown"
    else:
        surface = "unknown"
    posted_mouse = ("unlikely" if surface in ("chromium/cef", "xaml/winui", "directx/opaque")
                    else "likely" if surface == "classic-win32" else "unknown")
    return {"hwnd": int(hwnd), "root_class": root, "surface": surface, "flags": flags,
            "evidence_classes": kids[:6], "posted_mouse_expectation": posted_mouse}


def native_tree_available(hwnd: int, timeout_ms: int = 4000) -> Tuple[bool, int, List[str]]:
    """Does the NATIVE tree reach operable controls on this surface? One bounded UIA snapshot;
    returns (usable, nodes_seen, patterns_seen). Cheap evidence, not a guess."""
    try:
        from core_organs import fast_uia
        snap = fast_uia.snapshot(hwnd, timeout_ms=timeout_ms) or []
        pats = sorted({p for n in snap for p in (n.pats or [])})[:8]
        operable = sum(1 for n in snap if n.pats and n.enabled)
        return (operable >= 1 and len(snap) >= 5), len(snap), pats
    except Exception:  # noqa: BLE001
        return False, 0, []


def probe(hwnd: int) -> Dict[str, Any]:
    """Full per-window probe: surface + native-tree reach + where posted input stands.
    wall_risk is a HONEST head-forecast, never a per-app verdict."""
    p = surface_profile(hwnd)
    nat, nodes, pats = native_tree_available(hwnd)
    out = dict(p)
    out.update({"native_tree": {"reachable": nat, "nodes": nodes, "patterns": pats},
                "wall_risk": ("" if (nat or p["surface"] == "classic-win32") else
                              f"high: surface '{p['surface']}' rejects posted mouse and the native "
                              "tree reached no operable control - pixels alone would be acting blind")})
    return out


# Effector families as EffectorLadder names them. Native = the app's OWN tree/pipes.
NATIVE_TIERS = ("snapshot_invoke", "uia", "wm_command", "menu_command")
GEOMETRY_TIERS = ("postmessage", "layout_click")


def order_routes(order: List[str], profile: Dict[str, Any], verb: str) -> Tuple[List[str], List[str]]:
    """Probe-informed reordering of the EXISTING ladder - tiers are never invented or dropped,
    only put in a plausibility order: native tree first, posted geometry middle, and if the
    surface rejects posted input, geometry goes last. Returns (new_order, rationale)."""
    rationale: List[str] = []
    surface = profile.get("surface", "unknown")
    nat_ok = bool(profile.get("native_tree", {}).get("reachable"))
    order = list(order)
    if surface in ("chromium/cef", "xaml/winui", "directx/opaque") and any(e in GEOMETRY_TIERS for e in order):
        geo = [e for e in order if e in GEOMETRY_TIERS]
        rest = [e for e in order if e not in GEOMETRY_TIERS]
        order = rest + geo
        rationale.append(f"surface '{surface}' rejects posted mouse: geometry tiers sent to the end {geo}")
    if not nat_ok and surface != "classic-win32" and any(e in NATIVE_TIERS for e in order):
        rationale.append("native tree reached no operable control this run - trying it is still "
                         "preferred over geometry, but the wall note says what to expect")
    elif nat_ok:
        rationale.append(f"native tree live ({profile['native_tree']['nodes']} nodes, "
                         f"patterns {profile['native_tree']['patterns'][:4]})")
    return order, rationale


def wall_note(profile: Dict[str, Any], order: List[str], trail: List[str]) -> str:
    """The honest end-of-ladder sentence: what was tried, what the surface is, and that NOTHING
    was claimed. Produced only when the whole ladder ran dry - the caller must not translate it
    into success."""
    tiers = ", ".join(order)
    misses = " | ".join(t[:90] for t in trail[:6])
    return (f"WALL: no tier could actuate this control. surface={profile.get('surface')} "
            f"flags={profile.get('flags')} native_tree={profile.get('native_tree', {}).get('reachable')} "
            f"tiers_used=[{tiers}]. misses: {misses}. NOT done - not faked.")
