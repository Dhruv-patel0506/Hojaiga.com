"""
professor.interaction -- WHAT KIND OF WINDOW IS THIS, and how deep can its interface be read? (toolkit-agnostic interaction)

An application can be built on Win32, WinForms, WPF, WinUI / UWP XAML, Office's own shell, Qt, Chromium / Electron, OpenGL canvases, Java, a terminal ... Each exposes a different surface to
automation. The Professor does not special-case applications; it recognises the TOOLKIT FAMILY from the window (class, process, the accessibility framework id, the classes of its children),
starts from that family's best-known route order, and then lets measured outcomes (professor.ml.OutcomeModel) re-order the routes per toolkit and per control.

  classify(hwnd)   -> ToolkitProfile  {family, evidence, a11y expectation, route prior, adapters worth trying}
  deep_scan(hwnd)  -> DeepScan        the accessibility tree read to its full depth, after waiting for it to settle (Chromium / Electron build theirs on demand), plus the native menu
                                      tree; reports how rich it is ('rich' / 'sparse' / 'blind') and what it can NOT see (closed drop-downs and menus are invisible to a tree; they come from native
                                      menus, the guide and the vision model).
Routes are named as the executor names them: value | command | shortcut | control | click | adapter. The priors below are starting points, not facts about any application.
"""

from __future__ import annotations

import collections
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

# family -> (route prior, expected accessibility, adapters worth trying, note)
FAMILIES: Dict[str, Tuple[List[str], str, List[str], str]] = {
    "win32": (["command", "shortcut", "control", "click"], "rich", [], "classic controls: WM_COMMAND / BM_CLICK and UI Automation both work"),
    "win32-dialog": (["control", "shortcut", "click"], "rich", [], "a #32770 dialog: buttons answer BM_CLICK"),
    "winforms": (["control", "shortcut", "click"], "rich", [], "UIA patterns and posted clicks both work; tool strips have no HWND of their own"),
    "wpf": (["control", "shortcut", "value", "click"], "rich", [], "UIA is native here; posted mouse messages are often ignored"),
    "winui": (["control", "shortcut", "value"], "rich", [], "XAML: Invoke / Toggle / Select work; posted mouse input is usually ignored (measured on Paint)"),
    "uwp-xaml": (["control", "shortcut", "value"], "rich", [], "UWP in ApplicationFrameHost: park the FRAME, act through UIA"),
    "office": (["shortcut", "control", "command"], "rich", ["com"], "the ribbon is a UIA tree; menus open only on demand; a COM automation object exists"),
    "qt": (["control", "shortcut", "click"], "sparse", [], "Qt exposes UIA only with accessibility active; many custom widgets are invisible"),
    "chromium-browser": (["adapter", "control", "shortcut"], "sparse", ["cdp"], "UIA tree appears after the first query (and always with --force-renderer-accessibility); the DevTools protocol sees the page itself"),
    "electron": (["adapter", "control", "shortcut"], "sparse", ["cdp"], "a Chromium shell: same as the browser; many have a DevTools port when launched with --remote-debugging-port"),
    "gl-canvas": (["adapter", "shortcut", "click"], "blind", ["bridge"], "draws its own UI: no tree, and posted pointer / key messages are often ignored; an embedded scripting host (if any) is the reliable route"),
    "java": (["control", "shortcut", "click"], "sparse", [], "AWT / Swing needs the Java Access Bridge for a tree"),
    "swt": (["control", "shortcut", "click"], "sparse", [], "SWT widgets are native; the tree is usually fine"),
    "terminal": (["shortcut", "adapter"], "sparse", [], "a text surface: input is keystrokes, output is the text buffer"),
    "unknown": (["control", "shortcut", "click"], "unknown", [], "no rule matched: the learnt route order takes over after a few actions"),
}
CHROMIUM_BROWSERS = ("chrome", "msedge", "brave", "opera", "vivaldi", "chromium")
OFFICE_CLASSES = {"opusapp": "Word", "pptframeclass": "PowerPoint", "xlmain": "Excel", "rctrl_renwnd32": "Outlook", "onenote": "OneNote"}


@dataclass
class ToolkitProfile:
    family: str = "unknown"
    evidence: List[str] = field(default_factory=list)
    window_class: str = ""
    process: str = ""
    framework_id: str = ""
    route_prior: List[str] = field(default_factory=list)
    expected_a11y: str = "unknown"
    adapters: List[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _framework_id(hwnd: int) -> str:
    try:
        from core_organs import fast_uia
        iua, _core, _ua = fast_uia._client()
        return str(iua.ElementFromHandle(hwnd).CurrentFrameworkId or "")
    except Exception:
        return ""


def classify_from(window_class: str, process: str, framework_id: str = "", child_classes: Optional[List[str]] = None) -> ToolkitProfile:
    """The rules, separated from the system calls so they can be tested on plain strings."""
    cls, proc, fw = (window_class or ""), (process or "").lower().replace(".exe", ""), (framework_id or "")
    low = cls.lower()
    kids = collections.Counter((c or "").lower() for c in (child_classes or []))
    ev: List[str] = []
    fam = "unknown"
    if low.startswith("chrome_widgetwin") or low.startswith("chrome_renderwidgethosthwnd") or fw.lower() == "chrome":
        fam = "chromium-browser" if any(proc.startswith(b) for b in CHROMIUM_BROWSERS) else "electron"
        ev.append(f"window class {cls}")
    elif low in OFFICE_CLASSES:
        fam = "office"
        ev.append(f"Office shell class {cls} ({OFFICE_CLASSES[low]})")
    elif low.startswith("windowsforms10") or fw.lower() in ("winform", "windowsforms"):
        fam = "winforms"
        ev.append(f"class {cls} / framework {fw or '-'}")
    elif low.startswith("hwndwrapper[") or fw.upper() == "WPF":
        fam = "wpf"
        ev.append(f"class {cls} / framework {fw or '-'}")
    elif low in ("applicationframewindow", "windows.ui.core.corewindow"):
        fam = "uwp-xaml"
        ev.append(f"UWP frame class {cls}")
    elif low.startswith("winuidesktopwin32windowclass") or (fw.upper() == "XAML"):
        fam = "winui"
        ev.append(f"XAML framework ({cls})")
    elif low.startswith(("qt5", "qt6", "qt4")) or fw.lower() == "qt" or any(k.startswith(("qt5", "qt6")) for k in kids):
        fam = "qt"
        ev.append(f"Qt class {cls}")
    elif low in ("ghost_windowclass",) or low.startswith(("glfw", "sdl_app", "unitywndclass", "ogl")):
        fam = "gl-canvas"
        ev.append(f"GL / game-engine window class {cls}")
    elif low == "sunawtframe" or low.startswith("sunawt"):
        fam = "java"
        ev.append(f"Java AWT class {cls}")
    elif low.startswith("swt_window"):
        fam = "swt"
        ev.append(f"SWT class {cls}")
    elif low in ("consolewindowclass", "cascadia_hosting_window_class", "virtualconsoleclass"):
        fam = "terminal"
        ev.append(f"terminal host {cls}")
    elif low == "#32770":
        fam = "win32-dialog"
        ev.append("standard dialog class #32770")
    elif fw.lower() == "win32" or low:
        fam = "win32"
        ev.append(f"class {cls} / framework {fw or '-'}")
    if fam in ("win32", "unknown") and (fw.upper() == "XAML" or any(k.startswith(("microsoft.ui.xaml", "windows.ui.xaml", "microsoft.ui.content", "xaml")) for k in kids)):
        fam = "winui"                                             # a classic top-level window HOSTING a XAML island: the children's own class names say so
        ev.append("XAML controls inside")
    prior, a11y, adapters, note = FAMILIES.get(fam, FAMILIES["unknown"])
    return ToolkitProfile(fam, ev, cls, proc, fw, list(prior), a11y, list(adapters), note)


def classify(hwnd: int) -> ToolkitProfile:
    from . import capture as CAP
    try:
        info = CAP.window_info(hwnd)
        cls, proc = info.cls, info.process
    except Exception:
        cls, proc = "", ""
    kids: List[str] = []
    try:
        from core_organs import fast_uia
        nodes = fast_uia.snapshot(hwnd, max_nodes=300, timeout_ms=3000, cheap=True) or []
        kids = [n.cls for n in nodes[:300] if n.cls]
    except Exception:
        pass
    return classify_from(cls, proc, _framework_id(hwnd), kids)


@dataclass
class DeepScan:
    profile: ToolkitProfile
    nodes: int = 0
    interactive: int = 0
    named: int = 0
    depth: int = 0
    native_menu_items: int = 0
    state: str = "blind"                 # rich (>= 25 interactive named controls) | sparse (5-24) | blind
    waited_s: float = 0.0
    settled: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["profile"] = self.profile.to_dict()
        return d


def deep_scan(hwnd: int, budget_s: float = 20.0, wake: bool = True) -> DeepScan:
    """Read the whole accessibility tree (every depth, hidden-from-control-view elements included), waiting until it stops growing - Chromium / Electron / WinUI build theirs lazily after the first
    query - and add the window's native menu tree. Read-only: nothing is clicked, expanded or typed."""
    from core_organs import fast_uia
    t0 = time.time()
    prof = classify(hwnd)
    first = fast_uia.snapshot(hwnd, timeout_ms=int(min(8000, budget_s * 400))) or []      # this first query is what makes a Chromium app build its tree
    settled_n = fast_uia.wait_ready(hwnd, timeout_s=max(2.0, min(budget_s, 12.0)), min_nodes=3)
    nodes = fast_uia.snapshot(hwnd, timeout_ms=int(min(10000, budget_s * 500))) or []
    notes: List[str] = []
    if wake and prof.family in ("chromium-browser", "electron") and len(nodes) < 60:
        end = t0 + budget_s
        while time.time() < end and len(nodes) < 60:
            time.sleep(1.2)
            more = fast_uia.snapshot(hwnd, timeout_ms=6000) or []
            if len(more) > len(nodes):
                nodes = more
            else:
                break
        notes.append(f"Chromium-family window: tree grew from {len(first)} to {len(nodes)} nodes while waiting")
    inter = [n for n in nodes if n.name and (n.pats or n.role in ("button", "menuitem", "tabitem", "checkbox", "radiobutton", "edit", "combobox", "listitem", "treeitem", "hyperlink", "splitbutton"))]
    menu_n = 0
    try:
        from . import native_menu
        menu_n = len(native_menu.harvest(hwnd))
    except Exception:
        pass
    state = "rich" if len(inter) >= 25 else ("sparse" if len(inter) >= 5 else "blind")
    if state == "blind":
        notes.append("no usable accessibility tree: names and positions must come from OCR / the vision model / native menus / the guide")
    if state == "sparse":
        notes.append("sparse tree: the vision scan fills in what the tree does not name")
    notes.append("a tree cannot see closed drop-downs and menus: those come from native menus, the guide, or opening them (owned windows only)")
    depth = max((n.depth for n in nodes), default=0)
    return DeepScan(prof, len(nodes), len(inter), sum(1 for n in nodes if n.name), depth, menu_n, state, round(time.time() - t0, 2), settled_n >= 3, notes)
