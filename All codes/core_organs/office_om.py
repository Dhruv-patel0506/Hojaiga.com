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
import os
import re
import time
import ctypes
import ctypes.wintypes
from typing import Any, Dict, List, Optional, Tuple

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


PROGIDS = {"excel": "Excel.Application", "word": "Word.Application", "powerpoint": "PowerPoint.Application"}
_APP_KINDS = {"excel": "excel", "microsoft excel": "excel", "word": "word", "winword": "word", "microsoft word": "word", "powerpoint": "powerpoint", "powerpnt": "powerpoint",
              "microsoft powerpoint": "powerpoint"}


def kind_for_app(app_name: str) -> str:
    return _APP_KINDS.get((app_name or "").strip().lower(), "")


class Headless:
    """A NEW, invisible instance of an Office app reached through its object model (DispatchEx: never the person's running Excel / Word / PowerPoint). No window,
    no start screen, nothing on the screen. Live Oct-28: Excel and PowerPoint opened on their start screen with no document, so there was no object model to
    attach to and every step fell back to clicks; measured here: a new invisible instance writes, saves and quits in 1-3 s per app."""

    def __init__(self, kind: str):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        self.kind = kind
        self.visible = os.environ.get("HOJAIGA_OFFICE_VISIBLE", "0") == "1"
        self.shots: List[str] = []                         # the on-screen test: the same new instance, shown, so the person watches each step
        self.app = win32com.client.DispatchEx(PROGIDS[kind])
        with contextlib.suppress(Exception):
            if kind != "powerpoint":
                self.app.Visible = self.visible                                                        # PowerPoint refuses a hidden application; its documents are opened windowless
            self.app.DisplayAlerts = False if kind == "excel" else 0 if kind == "word" else 1

    def has_document(self) -> bool:
        with contextlib.suppress(Exception):
            return {"excel": lambda: self.app.Workbooks.Count, "word": lambda: self.app.Documents.Count, "powerpoint": lambda: self.app.Presentations.Count}[self.kind]() > 0
        return False

    def shot(self, tag: str = "end") -> str:
        """On-screen runs only: the app's OWN window as the person saw it, saved under HOJAIGA_SHOT_DIR (data/proof_runs) -- the proof that the app itself did the
        steps. Only that window's rectangle is captured (a full-screen grab on Oct-28 also caught the person's browser)."""
        if not self.visible:
            return ""
        with contextlib.suppress(Exception):
            from PIL import ImageGrab
            folder = os.environ.get("HOJAIGA_SHOT_DIR", os.path.join("D:" + os.sep, "new_automation", "data", "proof_runs"))
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"{time.strftime('%Y%m%d_%H%M%S')}_{self.kind}_{tag}.png")
            hwnd = 0
            for get in (lambda: self.app.Hwnd, lambda: self.app.HWND, lambda: self.app.ActiveWindow.Hwnd):
                with contextlib.suppress(Exception):
                    v = get()
                    hwnd = int(v() if callable(v) else v)                                             # PowerPoint's HWND comes through late binding as a method
                    if hwnd:
                        break
            if not hwnd:                                                                              # PowerPoint: its HWND is not reachable late-bound; its window carries the document's name
                with contextlib.suppress(Exception):
                    import win32gui
                    name = os.path.splitext(str(_pres(self.app).Name))[0]
                    found: List[int] = []
                    win32gui.EnumWindows(lambda h, _: found.append(h) if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "PPTFrameClass"
                                         and win32gui.GetWindowText(h).startswith(name) else None, None)
                    hwnd = found[0] if found else 0
            if not hwnd:
                return ""                                                                             # no window of ours to show: no picture rather than the whole screen
            from core_organs import headless_input as HI                                               # the window's OWN pixels (PrintWindow): a screen grab of its rectangle
            img = HI.capture_window_robust(hwnd)[0]                                                   # caught the person's browser lying over it (Oct-28)
            if img is None:
                return ""
            img.save(path)
            self.shots.append(path)
            return path
        return ""

    def close(self) -> None:
        """Every document closed WITHOUT saving (saving is the plan's own step), then the instance quits. An on-screen run leaves its last screen first."""
        self.shot("end")
        with contextlib.suppress(Exception):
            if self.kind == "excel":
                for wb in list(self.app.Workbooks):
                    wb.Close(False)
            elif self.kind == "word":
                for d in list(self.app.Documents):
                    d.Close(0)
            else:
                for p in list(self.app.Presentations):
                    p.Close()
        with contextlib.suppress(Exception):
            self.app.Quit()
        self.app = None


def _ka(target: Any) -> Tuple[str, Any]:
    """(kind, Application) for a window handle we own or a Headless session."""
    if isinstance(target, Headless):
        return target.kind, target.app
    return app_kind(target), _application(target)


def _pres(app: Any) -> Any:
    """The presentation being worked on: the active one, or (windowless, which has no 'active') the newest."""
    try:
        return app.ActivePresentation
    except Exception:
        return app.Presentations(app.Presentations.Count)


def text_of(hwnd: int, limit: int = 20000) -> str:
    parts: List[str] = []
    with contextlib.suppress(Exception):
        kind, app = _ka(hwnd)
        if app is None:
            return ""
        if kind == "word":
            parts.append(str(app.ActiveDocument.Content.Text or ""))
        elif kind == "powerpoint":
            pres = _pres(app)
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


# ------------------------------------------------------------------------------------------------ steps through the object model
# Live Oct-27: Word ignored every posted character (four 'type' attempts, nothing arrived) and PowerPoint went round its Save As page without ever
# reaching a file name. The object model of the window we own does these directly, without focus or a mouse, and every step is read back.
OM_STEPS = {"word": {"open_file", "new_document", "type", "format", "save_as", "read", "insert_table", "insert_picture"},
            "excel": {"open_file", "new_document", "type", "format", "save_as", "read", "insert_table"},
            "powerpoint": {"open_file", "new_document", "add_slide", "type", "format", "save_as", "read", "insert_table", "insert_picture"}}
_CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")
_FORMATS = {".docx": 16, ".doc": 0, ".pdf": 17, ".txt": 2, ".rtf": 6, ".xlsx": 51, ".xls": 56, ".csv": 6, ".pptx": 24, ".ppt": 1}


def _cell_of(target: str) -> str:
    m = _CELL.match(re.sub(r"(?i)\bcell\b", "", target or "").strip())
    return (m.group(1) + m.group(2)).upper() if m else ""


FRAMES = {"word": "OpusApp", "excel": "XLMAIN", "powerpoint": "PPTFrameClass"}


def frame_kind(hwnd: int) -> str:
    """'word' | 'excel' | 'powerpoint' from the top window's own class, also when no document is open yet (the start screen)."""
    with contextlib.suppress(Exception):
        import win32gui
        cls = win32gui.GetClassName(hwnd)
        return next((k for k, c in FRAMES.items() if c == cls), "")
    return ""


def open_blank(hwnd: int, wait_s: float = 8.0) -> bool:
    """Leave the Office start screen for a blank document (live Oct-27: PowerPoint sat on its start screen, so there was no document for the object
    model and the loop typed the title into 'Search for a file'): the start screen's own 'Blank ...' item is invoked through UI Automation (no focus,
    no mouse), then the document pane must appear."""
    import time
    if app_kind(hwnd):
        return True
    with contextlib.suppress(Exception):
        import uiautomation as auto
        root = auto.ControlFromHandle(hwnd)
        for c, _d in auto.WalkControl(root, maxDepth=14):
            if (c.Name or "").strip().lower().startswith("blank") and c.ControlTypeName in ("ListItemControl", "ButtonControl", "HyperlinkControl"):
                with contextlib.suppress(Exception):
                    c.GetInvokePattern().Invoke()
                    break
                with contextlib.suppress(Exception):
                    c.GetSelectionItemPattern().Select()
                    break
    end = time.time() + wait_s
    while time.time() < end:
        if app_kind(hwnd):
            return True
        time.sleep(0.4)
    return False


def can_do(kind: str, step: Dict[str, str]) -> bool:
    do = step.get("do", "")
    if do not in OM_STEPS.get(kind, ()):
        return False
    if do == "read" and re.match(r"(?i)https?://", step.get("text", "")):
        return False                                                                     # a web page is read by the web route, not by the document
    if kind == "excel" and do == "type":
        return bool(_cell_of(step.get("target", "")))                                    # a grid takes a value only at an address
    return True


def _value(text: str) -> Any:
    if re.fullmatch(r"-?\d+", text.strip()):
        return int(text)
    with contextlib.suppress(ValueError):
        return float(text)
    return text


def _same(a: Any, b: str) -> bool:
    if a is None:
        return b == ""
    if isinstance(a, float) and a.is_integer():
        a = int(a)
    return str(a).strip() == str(b).strip()


def _same_cell(got: Any, want: str) -> bool:
    """A cell holds what was written, allowing the grid's own reading of it: '41,913,860' is stored as the number 41913860 (live Oct-28), '5%' as 0.05."""
    if _same(got, want):
        return True
    w = re.sub(r"[,\s ]", "", str(want))
    with contextlib.suppress(ValueError, TypeError):
        g = float(got)
        if w.endswith("%"):
            return abs(g - float(w[:-1]) / 100.0) < 1e-9
        return abs(g - float(w)) < 1e-9 * max(1.0, abs(g))
    return False


def _apply_format(font: Any, fmt: str) -> List[str]:
    done = []
    f = (fmt or "").lower()
    for word, attr in (("bold", "Bold"), ("italic", "Italic"), ("underline", "Underline")):
        if word in f:
            setattr(font, attr, True)
            done.append(word)
    m = re.search(r"(\d{1,3})\s*(?:pt|point)", f) or (re.search(r"(\d{1,3})", f) if "size" in f else None)
    if m:
        font.Size = int(m.group(1))
        done.append(f"size {m.group(1)}")
    n = re.search(r"\bfont\s+['\"]?([A-Za-z][\w\- ]*?[\w)])['\"]?\s*(?:,|;|\bsize\b|\d|$)", fmt or "")   # 'font Cascadia Code Light, 36 pt' (case kept: it is a name)
    if n:
        font.Name = n.group(1).strip()
        done.append(f"font {font.Name}")
    return done


def _formatted(font: Any, done: List[str]) -> bool:
    ok = all(getattr(font, w.capitalize()) in (True, -1, 1) for w in done if w in ("bold", "italic"))
    for w in done:                                                                                   # read back: the app keeps the name / size only if it has them
        if w.startswith("font "):
            ok = ok and str(font.Name).lower() == w[5:].lower()
        if w.startswith("size "):
            ok = ok and abs(float(font.Size or 0) - float(w[5:])) < 0.6
    return bool(done) and ok


# ---- data between apps (operations after microsoft/UFO's app adapters: sheet as a table, insert a table at a cell, insert a table / picture into a
# document; reached through OUR window's object model, never 'whichever instance is running')
def _rows(value: Any) -> List[List[Any]]:
    if value is None:
        return []
    if not isinstance(value, tuple):
        return [[value]]
    if value and not isinstance(value[0], tuple):
        return [list(value)]
    return [list(r) for r in value]


def read(hwnd: int, target: str = "") -> Dict[str, Any]:
    """What the window's document holds, for the next app: {'kind': 'table', 'rows': [[...]]} for a sheet (a range like 'A1:C5', else the used range) or a
    document's first table; {'kind': 'text', 'text': ...} otherwise."""
    kind, app = _ka(hwnd)
    if app is None:
        return {}
    with contextlib.suppress(Exception):
        if kind == "excel":
            m = re.search(r"\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?", target or "")
            rng = app.ActiveSheet.Range(m.group(0)) if m else app.ActiveSheet.UsedRange
            return {"kind": "table", "rows": [[("" if v is None else (int(v) if isinstance(v, float) and v.is_integer() else v)) for v in r] for r in _rows(rng.Value)]}
        if kind == "word":
            doc = app.ActiveDocument
            if "table" in (target or "").lower() and doc.Tables.Count:
                t = doc.Tables(1)
                return {"kind": "table", "rows": [[str(t.Cell(r, c).Range.Text).rstrip("\r\x07") for c in range(1, t.Columns.Count + 1)] for r in range(1, t.Rows.Count + 1)]}
            return {"kind": "text", "text": str(doc.Content.Text or "").strip()}
        if kind == "powerpoint":
            return {"kind": "text", "text": text_of(hwnd)}
    return {}


def insert_table(hwnd: int, rows: List[List[Any]], target: str = "") -> Tuple[bool, str]:
    """A table from the blackboard into the document: Excel at a cell (A1 by default), Word as a table at the end, PowerPoint as a table on the last slide. Read back."""
    kind, app = _ka(hwnd)
    if app is None or not rows:
        return False, "no object model answered" if app is None else "the table is empty"
    n_r, n_c = len(rows), max(len(r) for r in rows)
    try:
        if kind == "excel":
            sh = app.ActiveSheet
            start = _cell_of(target) or "A1"
            top = sh.Range(start)
            grid = tuple(tuple((_value(str(v)) if isinstance(v, str) else v) for v in list(r) + [""] * (n_c - len(r))) for r in rows)
            sh.Range(sh.Cells(top.Row, top.Column), sh.Cells(top.Row + n_r - 1, top.Column + n_c - 1)).Value = grid    # one write, not one per cell
            got = _rows(sh.Range(sh.Cells(top.Row, top.Column), sh.Cells(top.Row + n_r - 1, top.Column + n_c - 1)).Value)
            ok = all(_same_cell(got[i][j], str(rows[i][j])) for i in range(n_r) for j in range(len(rows[i])))
            return ok, f"{n_r}x{n_c} table at {start}"
        if kind == "word":
            doc = app.ActiveDocument
            doc.Content.InsertParagraphAfter()
            # the rows go in as tab-separated text and Word turns them into ONE table (live Oct-28: 87x13 cell-by-cell took 75 s on screen)
            clean = lambda v: re.sub(r"[\t\r\n\x07]+", " ", str(v)).strip()
            rng = doc.Paragraphs(doc.Paragraphs.Count).Range
            rng.Text = "\r".join("\t".join(clean(v) for v in list(r) + [""] * (n_c - len(r))) for r in rows)
            t = rng.ConvertToTable(Separator=1, NumRows=n_r, NumColumns=n_c)                         # 1 = wdSeparateByTabs
            with contextlib.suppress(Exception):
                t.Borders.Enable = True
            return doc.Tables.Count >= 1 and str(rows[0][0]) in str(t.Cell(1, 1).Range.Text), f"{n_r}x{n_c} table in the document"
        if kind == "powerpoint":
            pres = _pres(app)
            if pres.Slides.Count == 0:
                pres.Slides.AddSlide(1, pres.SlideMaster.CustomLayouts(2))
            sl = pres.Slides(pres.Slides.Count)
            tbl = sl.Shapes.AddTable(n_r, n_c, 40, 120, 640, 30 * n_r).Table
            for i, r in enumerate(rows):
                for j, v in enumerate(r):
                    tbl.Cell(i + 1, j + 1).Shape.TextFrame.TextRange.Text = str(v)
            return str(rows[0][0]) in text_of(hwnd), f"{n_r}x{n_c} table on slide {pres.Slides.Count}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"
    return False, f"no table route for {kind or 'this window'}"


def insert_picture(hwnd: int, path: str) -> Tuple[bool, str]:
    """A picture file (another app's output) into the document: Word inline at the end, PowerPoint on the last slide. Read back by the shape count."""
    import os
    kind, app = _ka(hwnd)
    if app is None:
        return False, "no object model answered"
    if not os.path.isfile(path):
        return False, f"the picture {path} does not exist"
    try:
        if kind == "word":
            doc = app.ActiveDocument
            n = doc.InlineShapes.Count
            doc.Content.InsertParagraphAfter()
            doc.InlineShapes.AddPicture(path, False, True, doc.Paragraphs(doc.Paragraphs.Count).Range)
            return doc.InlineShapes.Count == n + 1, f"{doc.InlineShapes.Count} picture(s) in the document"
        if kind == "powerpoint":
            pres = _pres(app)
            if pres.Slides.Count == 0:
                pres.Slides.AddSlide(1, pres.SlideMaster.CustomLayouts(2))
            sl = pres.Slides(pres.Slides.Count)
            n = sl.Shapes.Count
            sl.Shapes.AddPicture(path, False, True, 120, 120)
            return sl.Shapes.Count == n + 1, f"picture on slide {pres.Slides.Count}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"
    return False, f"no picture route for {kind or 'this window'}"


def do_step(hwnd: int, step: Dict[str, str]) -> Tuple[bool, str]:
    """(ok, evidence) for one model step. ok only when the read-back shows the result."""
    import os
    import time
    kind, app = _ka(hwnd)
    if app is None:
        return False, "no object model answered for this window"
    do, text, target, fmt = step.get("do", ""), step.get("text", ""), step.get("target", ""), step.get("format", "")
    try:
        if do == "open_file":                                                                     # a file an earlier step saved (Excel -> PowerPoint reads cities.xlsx)
            path = text.strip().strip("\"'")
            if not os.path.isfile(path):
                return False, f"{path} does not exist"
            {"word": lambda: app.Documents.Open(path), "excel": lambda: app.Workbooks.Open(path), "powerpoint": lambda: app.Presentations.Open(path, False, False, not isinstance(hwnd, Headless) or hwnd.visible)}[kind]()
            name = {"word": lambda: app.ActiveDocument.FullName, "excel": lambda: app.ActiveWorkbook.FullName, "powerpoint": lambda: _pres(app).FullName}[kind]()
            return os.path.normcase(str(name)) == os.path.normcase(path), f"opened {name}"
        if do == "new_document":
            {"word": lambda: app.Documents.Add(), "excel": lambda: app.Workbooks.Add(), "powerpoint": lambda: app.Presentations.Add(not isinstance(hwnd, Headless) or hwnd.visible)}[kind]()
            return True, f"new {kind} document"
        doc = {"word": lambda: app.ActiveDocument, "excel": lambda: app.ActiveWorkbook, "powerpoint": lambda: _pres(app)}[kind]()
        if do == "type" and kind == "word":
            if (doc.Content.Text or "").strip():
                doc.Content.InsertParagraphAfter()
            doc.Content.InsertAfter(text)
            return (text in (doc.Content.Text or "")), f"the document holds the text ({len(doc.Content.Text or '')} chars)"
        if do == "type" and kind == "excel":
            addr = _cell_of(target)
            sh = app.ActiveSheet
            sh.Range(addr).Value = _value(text)
            got = sh.Range(addr).Value
            return _same(got, text), f"{addr} = {got!r}"
        if do == "add_slide":
            n = doc.Slides.Count
            doc.Slides.AddSlide(n + 1, doc.SlideMaster.CustomLayouts(1 if n == 0 else 2))
            return doc.Slides.Count == n + 1, f"{doc.Slides.Count} slide(s)"
        if do == "type" and kind == "powerpoint":
            if doc.Slides.Count == 0:
                doc.Slides.AddSlide(1, doc.SlideMaster.CustomLayouts(1))
            sl = doc.Slides(doc.Slides.Count)
            if sl.Shapes.HasTitle and ("title" in target.lower() or not (sl.Shapes.Title.TextFrame.TextRange.Text or "").strip()):
                sl.Shapes.Title.TextFrame.TextRange.Text = text
            else:
                sl.Shapes.AddTextbox(1, 60, 140, 600, 80).TextFrame.TextRange.Text = text
            return text in text_of(hwnd), f"slide {doc.Slides.Count} holds the text"
        if do == "format":
            if kind == "word":
                rng = doc.Content
                if not (text and rng.Find.Execute(text)):
                    return False, f"'{text}' is not in the document"
                done = _apply_format(rng.Font, fmt)
                return _formatted(rng.Font, done), f"'{text}' made {', '.join(done) or 'nothing'}"
            if kind == "excel":
                addr = _cell_of(target)
                rng = app.ActiveSheet.Range(addr) if addr else app.ActiveSheet.UsedRange.Find(text)
                if rng is None:
                    return False, f"no cell holds '{text}'"
                done = _apply_format(rng.Font, fmt)
                return _formatted(rng.Font, done), f"{rng.Address} made {', '.join(done) or 'nothing'}"
            for sl in doc.Slides:
                for shp in sl.Shapes:
                    with contextlib.suppress(Exception):
                        hit = shp.TextFrame.TextRange.Find(text) if text else None
                        if hit is not None:
                            done = _apply_format(hit.Font, fmt)
                            return _formatted(hit.Font, done), f"'{text}' made {', '.join(done) or 'nothing'}"
            return False, f"'{text}' is not on any slide"
        if do == "save_as":
            path = text.strip().strip("\"'")
            ext = os.path.splitext(path)[1].lower()
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            t0 = time.time()
            alerts = None
            with contextlib.suppress(Exception):
                alerts = app.DisplayAlerts
                app.DisplayAlerts = False if kind == "excel" else 0 if kind == "word" else 1      # the caller already refused an existing file; no prompt may block a headless window
            try:
                if kind == "word":
                    doc.SaveAs2(path, _FORMATS.get(ext, 16))
                elif kind == "excel":
                    doc.ExportAsFixedFormat(0, path) if ext == ".pdf" else doc.SaveAs(path, _FORMATS.get(ext, 51))
                else:
                    doc.SaveAs(path, 32 if ext == ".pdf" else _FORMATS.get(ext, 24))
            finally:
                if alerts is not None:
                    with contextlib.suppress(Exception):
                        app.DisplayAlerts = alerts
            ok = os.path.isfile(path) and os.path.getmtime(path) >= t0 - 2 and os.path.getsize(path) > 0
            return ok, f"saved {path} ({os.path.getsize(path) if os.path.isfile(path) else 0} bytes)"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"
    return False, f"'{do}' is not done through the object model for {kind or 'this window'}"
