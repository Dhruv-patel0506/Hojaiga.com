"""
professor.native_menu -- classic Win32 menus read straight from the window, without opening them.

A window with a real menu bar (HMENU: Notepad++, Paint.NET-style tools, most older and cross-platform-toolkit programs, Python/Tk apps) holds the ENTIRE menu tree in
memory: every item's text, accelerator, enabled / checked state and sub-menu, even the ones nobody has opened. `GetMenu` + `GetMenuItemInfoW` read them passively
(no click, no focus, nothing drawn) in milliseconds. This is the cheapest source of exact names for the menu bar's items and what each opens.
Applications that draw their own menus (Office ribbon, Blender, Electron, WinUI) have no HMENU: `harvest` returns [] and the other tiers carry the scan.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from .schema import UIElement, fold

_u = ctypes.WinDLL("user32", use_last_error=True)
_H = ctypes.c_void_p


class MENUITEMINFOW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("fMask", wt.UINT), ("fType", wt.UINT), ("fState", wt.UINT), ("wID", wt.UINT), ("hSubMenu", _H), ("hbmpChecked", _H),
                ("hbmpUnchecked", _H), ("dwItemData", ctypes.c_size_t), ("dwTypeData", wt.LPWSTR), ("cch", wt.UINT), ("hbmpItem", _H)]


_u.GetMenu.argtypes = [_H]
_u.GetMenu.restype = _H
_u.GetMenuItemCount.argtypes = [_H]
_u.GetMenuItemInfoW.argtypes = [_H, wt.UINT, wt.BOOL, ctypes.POINTER(MENUITEMINFOW)]
MIIM_STATE, MIIM_ID, MIIM_SUBMENU, MIIM_STRING, MIIM_FTYPE = 0x1, 0x2, 0x4, 0x40, 0x100
MFT_SEPARATOR = 0x800
MFS_GRAYED, MFS_DISABLED, MFS_CHECKED = 0x3, 0x2, 0x8


@dataclass
class MenuItem:
    path: List[str]
    label: str
    shortcut: str = ""
    enabled: bool = True
    checked: bool = False
    has_submenu: bool = False
    command_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    @property
    def text_path(self) -> str:
        return " > ".join(self.path + [self.label])


def _read(hmenu: int, depth: int, path: List[str], out: List[MenuItem], limit: int) -> None:
    if depth > 6 or len(out) >= limit:
        return
    count = _u.GetMenuItemCount(_H(hmenu))
    for i in range(max(0, count)):
        buf = ctypes.create_unicode_buffer(256)
        mi = MENUITEMINFOW()
        mi.cbSize = ctypes.sizeof(MENUITEMINFOW)
        mi.fMask = MIIM_STATE | MIIM_ID | MIIM_SUBMENU | MIIM_STRING | MIIM_FTYPE
        mi.dwTypeData = ctypes.cast(buf, wt.LPWSTR)
        mi.cch = 255
        if not _u.GetMenuItemInfoW(_H(hmenu), i, True, ctypes.byref(mi)):
            continue
        if mi.fType & MFT_SEPARATOR:
            continue
        raw = buf.value.replace("&", "")
        if not raw.strip():                                           # owner-drawn entry (the program paints it itself): no text is stored in the menu, nothing to read
            if mi.hSubMenu:
                _read(int(mi.hSubMenu), depth + 1, path + ["(unnamed)"], out, limit)
            continue
        label, _, accel = raw.partition("\t")
        item = MenuItem(list(path), label.strip(), accel.strip(), not (mi.fState & MFS_GRAYED), bool(mi.fState & MFS_CHECKED), bool(mi.hSubMenu), int(mi.wID))
        out.append(item)
        if mi.hSubMenu:
            _read(int(mi.hSubMenu), depth + 1, path + [item.label], out, limit)


def harvest(hwnd: int, limit: int = 2000) -> List[MenuItem]:
    """Every item of the window's menu bar tree, in order. [] when the window has no classic menu."""
    try:
        h = _u.GetMenu(_H(hwnd))
    except Exception:
        return []
    if not h:
        return []
    out: List[MenuItem] = []
    try:
        _read(int(h), 0, [], out, limit)
    except Exception:
        pass
    return out


def apply_menus(elements: Sequence[UIElement], items: Sequence[MenuItem]) -> int:
    """Attach what each visible top-level menu opens (its items and their shortcuts) to the menu-bar element carrying the same name. Returns how many matched."""
    tops = {fold(i.label): i for i in items if not i.path and i.has_submenu}
    n = 0
    for e in elements:
        if not e.label or e.role not in ("menu_item", "text", "button", "tab", "unknown"):
            continue
        top = tops.get(fold(e.label))
        if top is None:
            continue
        kids = [i for i in items if i.path == [top.label]]
        if not kids:
            continue
        names = [k.label + (f" ({k.shortcut})" if k.shortcut else "") for k in kids[:14]]
        e.leads_to = f"opens a menu with {len(kids)} items: " + ", ".join(names)
        e.knowledge = {"items": [k.to_dict() for k in kids], "source": "win32-menu", "trust": "measured"}
        e.role = "menu_item"
        if "native_menu" not in e.sources:
            e.sources.append("native_menu")
        n += 1
    return n


def shortcut_index(items: Sequence[MenuItem]) -> Dict[str, MenuItem]:
    """folded label -> item for every NON-top-level command: lets the teacher answer 'what is the shortcut for Save As' for items that are not on screen."""
    return {fold(i.label): i for i in items if i.path and not i.has_submenu and i.shortcut}
