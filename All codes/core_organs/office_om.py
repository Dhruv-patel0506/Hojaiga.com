"""
office_om -- read (and, for a grid, write) what a Microsoft Office window holds, through ITS OWN object model, reached through THAT window.

Why: the accessibility tree does not list a slide's shapes, a document body is one control, and a spreadsheet's cells are not controls at all, so a check made on the tree (or on OCR of a small picture) misses text that is plainly
there. The object model lists everything, for exactly the window we own - never 'whichever Word / Excel / PowerPoint is running'.

    text_of(hwnd)            all text the window's document holds (Word: body; PowerPoint: every shape of every slide; Excel: every used cell)  -> str ('' when no object model answers)
    grid_write(hwnd, cells)  {"A1": "x", ...} -> keyboard-free commit through the sheet's own Range.Value, read back; returns {address: ok}
    app_kind(hwnd)           'word' | 'excel' | 'powerpoint' | ''

Nothing here knows a task; callers decide what to look for.
"""
from __future__ import annotations

import contextlib
import ctypes
from typing import Any, Dict, List, Optional

CLASSES = {"word": ("_WwG",), "excel": ("EXCEL7",), "powerpoint": ("mdiClass", "paneClassDC", "screenClass")}


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


def _children(hwnd: int) -> List[int]:
    import win32gui
    out: List[int] = []
    win32gui.EnumChildWindows(hwnd, lambda h, _l: out.append(h) or True, None)
    return out


def app_kind(hwnd: int) -> str:
    import win32gui
    classes = {win32gui.GetClassName(h) for h in _children(hwnd)}
    for kind, names in CLASSES.items():
        if classes & set(names):
            return kind
    return ""


def _application(hwnd: int) -> Any:
    """The Office Application object of the instance that owns this window (AccessibleObjectFromWindow on a document pane, OBJID_NATIVEOM)."""
    import pythoncom
    import win32com.client
    import win32gui
    pythoncom.CoInitialize()
    kids = [(h, win32gui.GetClassName(h)) for h in _children(hwnd)]
    iid = _GUID(0x00020400, 0, 0, (ctypes.c_ubyte * 8)(0xC0, 0, 0, 0, 0, 0, 0, 0x46))             # IID_IDispatch
    for kind, names in CLASSES.items():
        for h, cls in kids:
            if cls in names:
                ptr = ctypes.c_void_p()
                try:
                    ctypes.oledll.oleacc.AccessibleObjectFromWindow(h, -16, ctypes.byref(iid), ctypes.byref(ptr))
                    disp = pythoncom.ObjectFromAddress(ptr.value, pythoncom.IID_IDispatch)
                    obj = win32com.client.Dispatch(disp)
                    return obj.Application if hasattr(obj, "Application") else obj
                except Exception:
                    continue
    return None


def text_of(hwnd: int, limit: int = 20000) -> str:
    parts: List[str] = []
    with contextlib.suppress(Exception):
        kind = app_kind(hwnd)
        app = _application(hwnd)
        if app is None:
            return ""
        if kind == "word":
            parts.append(str(app.ActiveDocument.Content.Text or ""))
        elif kind == "powerpoint":
            pres = app.ActivePresentation
            for sl in pres.Slides:
                for shp in sl.Shapes:
                    with contextlib.suppress(Exception):
                        if shp.HasTextFrame and shp.TextFrame.HasText:
                            parts.append(str(shp.TextFrame.TextRange.Text))
                    with contextlib.suppress(Exception):
                        if shp.HasTable:
                            for r in range(1, shp.Table.Rows.Count + 1):
                                for c in range(1, shp.Table.Columns.Count + 1):
                                    parts.append(str(shp.Table.Cell(r, c).Shape.TextFrame.TextRange.Text))
        elif kind == "excel":
            ur = app.ActiveSheet.UsedRange
            for row in ur.Value or ():
                parts += [str(v) for v in (row if isinstance(row, tuple) else (row,)) if v not in (None, "")]
    return " ".join(p.strip() for p in parts if p.strip())[:limit]


def grid_write(hwnd: int, cells: Dict[str, str]) -> Dict[str, bool]:
    """Write cells through the active sheet's Range.Value (a commit, as Enter would do) and read each back."""
    out: Dict[str, bool] = {}
    with contextlib.suppress(Exception):
        app = _application(hwnd)
        sh = app.ActiveSheet if app is not None else None
        if sh is None:
            return out
        for addr, text in cells.items():
            with contextlib.suppress(Exception):
                sh.Range(addr).Value = text
            out[addr] = str(getattr(sh.Range(addr), "Value", "") or "") == str(text)
    return out


def grid_type(hwnd: int, cells: Dict[str, str]) -> Dict[str, bool]:
    """The keyboard route into a spreadsheet, for any grid that has a Name Box: go to the cell (the Name Box takes the address, Enter), post the characters to the grid pane, commit with Enter (the cell must really be
    in edit mode - a value set through UI Automation on an un-activated cell does not stick). Each cell is read back through the object model when there is one (else the caller checks the picture). Returns {address: read-back ok}."""
    import time
    import uiautomation as auto
    import win32gui
    from core_organs import headless_input as hin
    out: Dict[str, bool] = {}
    grid = next((h for h in _children(hwnd) if win32gui.GetClassName(h) == "EXCEL7"), 0)
    root = auto.ControlFromHandle(hwnd)
    namebox = None
    for c, _d in auto.WalkControl(root, maxDepth=12):
        if (c.Name or "") == "Name Box" and c.ControlTypeName == "EditControl":
            namebox = c
            break
    if namebox is None or not grid:
        return out
    sheet = None
    with contextlib.suppress(Exception):
        app = _application(hwnd)
        sheet = app.ActiveSheet if app is not None else None
    for addr, text in cells.items():
        with contextlib.suppress(Exception):
            namebox.GetValuePattern().SetValue(addr)
            time.sleep(0.15)
            hin.post_key_combo(hwnd, "enter")
            time.sleep(0.25)
            u = ctypes.windll.user32
            for ch in str(text):
                u.PostMessageW(grid, 0x0102, ord(ch), 0)                         # WM_CHAR to the grid pane starts the in-cell editor
                time.sleep(0.004)
            time.sleep(0.15)
            hin.post_key_combo(grid, "enter")                                    # commit
            time.sleep(0.3)
        ok = False
        if sheet is not None:
            with contextlib.suppress(Exception):
                ok = str(sheet.Range(addr).Value or "") == str(text)
        out[addr] = ok
    return out
