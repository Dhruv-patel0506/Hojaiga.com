"""
fast_uia.py — read a whole UI Automation subtree in ONE cross-process call.

The per-node way (control.Name, control.BoundingRectangle, control.GetChildren() ...) costs several
COM round trips per element; a ribbon app has thousands of elements, so scanning takes tens of
seconds. UIA's CacheRequest asks the target process for a subtree *with the properties we need* in a
single call, after which every read is local memory. Measured on this host (Paint, parked):
0.94 s per-node vs 0.11 s cached for 232 nodes (x8.5); the gap grows with tree size.

    nodes = snapshot(hwnd)             # list[Node], depth-first, parent index kept
    nodes = snapshot_element(raw_el)   # same, rooted at a raw IUIAutomationElement (e.g. a popup)
    node.ctrl                          # lazily wraps the live element as a uiautomation Control, for
                                       # the few actions (Expand/Select/Invoke) that need a live handle

Everything degrades: any failure returns None and callers fall back to the slow per-node walk.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.fast_uia")

CONTROL_TYPES = {
    50000: "ButtonControl", 50001: "CalendarControl", 50002: "CheckBoxControl", 50003: "ComboBoxControl",
    50004: "EditControl", 50005: "HyperlinkControl", 50006: "ImageControl", 50007: "ListItemControl",
    50008: "ListControl", 50009: "MenuControl", 50010: "MenuBarControl", 50011: "MenuItemControl",
    50012: "ProgressBarControl", 50013: "RadioButtonControl", 50014: "ScrollBarControl", 50015: "SliderControl",
    50016: "SpinnerControl", 50017: "StatusBarControl", 50018: "TabControl", 50019: "TabItemControl",
    50020: "TextControl", 50021: "ToolBarControl", 50022: "ToolTipControl", 50023: "TreeControl",
    50024: "TreeItemControl", 50025: "CustomControl", 50026: "GroupControl", 50027: "ThumbControl",
    50028: "DataGridControl", 50029: "DataItemControl", 50030: "DocumentControl", 50031: "SplitButtonControl",
    50032: "WindowControl", 50033: "PaneControl", 50034: "HeaderControl", 50035: "HeaderItemControl",
    50036: "TableControl", 50037: "TitleBarControl", 50038: "SeparatorControl", 50039: "SemanticZoomControl",
    50040: "AppBarControl",
}

# property ids (UIA_*PropertyId)
P_RECT, P_CTYPE, P_NAME, P_ACCEL, P_AID, P_CLASS, P_HELP = 30001, 30003, 30005, 30006, 30011, 30012, 30013
P_ENABLED, P_OFFSCREEN = 30010, 30022
P_PAT = {"invoke": 30031, "toggle": 30041, "expand": 30028, "select": 30036, "value": 30043, "scroll": 30034,
         "text": 30040}
P_EXPAND_STATE = 30070          # ExpandCollapseExpandCollapseState
P_SELECTED = 30079              # SelectionItemIsSelected
P_ACCESSKEY = 30007
P_TOGGLE_STATE = 30086          # ToggleToggleState: 0 off, 1 on, 2 indeterminate

_cache_request = None
_DEFAULT_TIMEOUT_MS = int(__import__("os").environ.get("HOJAIGA_UIA_TIMEOUT_MS", "12000"))


def _set_timeout(ms: int) -> None:
    """Cap how long ONE UIA transaction may take (IUIAutomation6, Windows 10+). Without it a single
    slow provider (a print-preview control inside a Win32 dialog took 65 s) stalls the whole scan."""
    try:
        iua, core, _ = _client()
        iua6 = iua.QueryInterface(core.IUIAutomation6)
        iua6.TransactionTimeout = int(ms)
        iua6.ConnectionTimeout = min(int(ms), 4000)
    except Exception:
        pass


def _client():
    from uiautomation import uiautomation as ua
    cl = ua._AutomationClient.instance()
    return cl.IUIAutomation, cl.UIAutomationCore, ua


def _request():
    global _cache_request
    if _cache_request is None:
        iua, core, _ = _client()
        cr = iua.CreateCacheRequest()
        for pid in (P_RECT, P_CTYPE, P_NAME, P_ACCEL, P_AID, P_CLASS, P_HELP, P_ENABLED, P_OFFSCREEN, P_ACCESSKEY,
                    P_EXPAND_STATE, P_SELECTED, P_TOGGLE_STATE, *P_PAT.values()):
            try:
                cr.AddProperty(pid)
            except Exception:
                continue
        cr.TreeScope = core.TreeScope_Subtree
        cr.TreeFilter = iua.RawViewCondition          # the full tree (control view hides panes/groups/custom)
        _cache_request = cr
    return _cache_request


class Node:
    __slots__ = ("idx", "parent", "depth", "ctype", "name", "aid", "cls", "rect", "enabled", "offscreen",
                 "help", "accel", "pats", "expand_state", "selected", "toggle_state", "el", "_ctrl", "children")

    def __init__(self):
        self.children: List[int] = []
        self._ctrl = None

    @property
    def role(self) -> str:
        return self.ctype.replace("Control", "").lower()

    @property
    def ctrl(self):
        """The live uiautomation Control for this node (created on first use, then cached)."""
        if self._ctrl is None:
            _, _, ua = _client()
            self._ctrl = ua.Control.CreateControlFromElement(self.el)
        return self._ctrl


def _read(el, idx: int, parent: int, depth: int) -> Node:
    n = Node()
    n.idx, n.parent, n.depth, n.el = idx, parent, depth, el
    try:
        n.ctype = CONTROL_TYPES.get(int(el.CachedControlType), "CustomControl")
    except Exception:
        n.ctype = "CustomControl"
    n.name = (el.CachedName or "").strip()
    n.aid = (el.CachedAutomationId or "").strip()
    n.cls = el.CachedClassName or ""
    try:
        r = el.CachedBoundingRectangle
        n.rect = (int(r.left), int(r.top), int(r.right), int(r.bottom))
    except Exception:
        n.rect = (0, 0, 0, 0)
    try:
        n.enabled = bool(el.CachedIsEnabled)
        n.offscreen = bool(el.CachedIsOffscreen)
    except Exception:
        n.enabled, n.offscreen = True, False
    try:
        n.help = el.CachedHelpText or ""
        n.accel = el.CachedAcceleratorKey or ""
    except Exception:
        n.help = n.accel = ""
    pats = []
    for label, pid in P_PAT.items():
        try:
            if el.GetCachedPropertyValue(pid):
                pats.append(label)
        except Exception:
            continue
    n.pats = pats
    try:
        n.expand_state = int(el.GetCachedPropertyValue(P_EXPAND_STATE)) if "expand" in pats else -1
    except Exception:
        n.expand_state = -1
    try:
        n.selected = bool(el.GetCachedPropertyValue(P_SELECTED)) if "select" in pats else None
    except Exception:
        n.selected = None
    try:
        n.toggle_state = int(el.GetCachedPropertyValue(P_TOGGLE_STATE)) if "toggle" in pats else -1
    except Exception:
        n.toggle_state = -1
    return n


def _flatten(cached_root, max_nodes: int) -> List[Node]:
    nodes: List[Node] = []
    stack: List[Tuple[Any, int, int]] = [(cached_root, -1, 0)]
    while stack and len(nodes) < max_nodes:
        el, parent, depth = stack.pop()
        node = _read(el, len(nodes), parent, depth)
        nodes.append(node)
        if parent >= 0:
            nodes[parent].children.append(node.idx)
        try:
            arr = el.GetCachedChildren()
            ln = arr.Length
        except Exception:
            continue
        for i in range(ln - 1, -1, -1):                 # reversed so the DFS visits children in order
            try:
                stack.append((arr.GetElement(i), node.idx, depth + 1))
            except Exception:
                continue
    return nodes


def snapshot(hwnd: int, max_nodes: int = 20000, timeout_ms: Optional[int] = None) -> Optional[List[Node]]:
    """Whole-window subtree in one call, bounded by `timeout_ms` (default 12 s; pass ~3000 for
    dialogs and popups). None on any failure or timeout (caller falls back / reports skipped)."""
    try:
        iua, _, _ = _client()
        _set_timeout(timeout_ms or _DEFAULT_TIMEOUT_MS)
        try:
            root = iua.ElementFromHandleBuildCache(hwnd, _request())
            return _flatten(root, max_nodes)
        finally:
            _set_timeout(_DEFAULT_TIMEOUT_MS)
    except Exception as exc:
        logger.debug("[fast_uia] snapshot(%s) failed: %s", hwnd, exc)
        return None


def snapshot_element(raw_el, max_nodes: int = 5000, timeout_ms: Optional[int] = None) -> Optional[List[Node]]:
    """Subtree under a raw IUIAutomationElement (e.g. `control.Element`), one bounded call."""
    try:
        _set_timeout(timeout_ms or _DEFAULT_TIMEOUT_MS)
        try:
            cached = raw_el.BuildUpdatedCache(_request())
            return _flatten(cached, max_nodes)
        finally:
            _set_timeout(_DEFAULT_TIMEOUT_MS)
    except Exception as exc:
        logger.debug("[fast_uia] snapshot_element failed: %s", exc)
        return None


def descendants_of(nodes: List[Node], idx: int) -> List[Node]:
    out, stack = [], list(nodes[idx].children)
    while stack:
        i = stack.pop()
        out.append(nodes[i])
        stack.extend(nodes[i].children)
    return out


def wait_ready(hwnd: int, timeout_s: float = 15.0, min_nodes: int = 3) -> int:
    """Block (bounded) until the window's UI tree has STOPPED GROWING; returns the settled node count. Apps
    populate for a second or two after being restored/parked (UWP/WinUI/Office); mapping or acting before that
    maps an empty UI (6 controls instead of 70)."""
    import time as _t
    last, steady, end = -1, 0, _t.time() + timeout_s
    while _t.time() < end and steady < 2:
        snap = snapshot(hwnd, timeout_ms=6000)
        cnt = len(snap) if snap else 0
        steady = steady + 1 if (cnt == last and cnt >= min_nodes) else 0
        last = cnt
        _t.sleep(0.3)
    return max(last, 0)
