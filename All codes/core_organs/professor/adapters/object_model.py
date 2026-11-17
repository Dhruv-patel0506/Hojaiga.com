"""
professor.adapters.object_model -- THE SAME COMMAND, ANOTHER WAY IN: an application's own automation object model as a fallback route.

When the interface route cannot reach a control (it sits in a drop-down that will not open on a parked window, a gallery that renders lazily, a ribbon group folded away), the
SAME command can often still be performed through the application's object model - the route a macro would take. Measured: 11 of 12 failed guide procedures on Word / PowerPoint /
Paint (2026-10-10) failed only because the control could not be reached on screen.

  OfficeModel     an Office application (recognised by its COM ProgID, professor.vendor_commands): CommandBars.ExecuteMso(<id>) for every catalogued 'mso:' command, Selection.TypeText for
                  text into the document, GetEnabledMso / GetPressedMso to know a command's state. Bound to the OWNED window (AccessibleObjectFromWindow(OBJID_NATIVEOM) on its document
                  pane), never to another instance; else, only when this process is the application's only one, the running object.
Every call runs in a worker thread with a wall-clock bound: a command that opens a modal dialog keeps its COM call open until the dialog closes - the executor goes on driving the dialog
through UI Automation meanwhile.
Input still goes only to a window the run launched (the executor asks the effector first). Nothing here names an application: the family comes from the COM registration.
"""

from __future__ import annotations

import ctypes
import re
import ctypes.wintypes as wt
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

OBJID_NATIVEOM = -16


def _children(h: int) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    u = ctypes.windll.user32
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(c, _lp):
        buf = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(c, buf, 64)
        out.append((int(c), buf.value))
        return True
    u.EnumChildWindows(h, PROC(cb), 0)
    return out


def _native_om(hwnd: int) -> Any:
    """The application object behind an OWNED top-level window: the first child window whose accessible native object model answers (Office document panes do)."""
    import pythoncom
    import win32com.client as wc
    oleacc = ctypes.oledll.oleacc
    for ch, _cls in _children(hwnd)[:400]:
        ptr = ctypes.c_void_p()
        from comtypes import GUID
        guid = GUID(str(pythoncom.IID_IDispatch))
        try:
            oleacc.AccessibleObjectFromWindow(ch, OBJID_NATIVEOM, ctypes.byref(guid), ctypes.byref(ptr))
        except OSError:
            continue
        if not ptr.value:
            continue
        try:
            disp = pythoncom.ObjectFromAddress(ptr.value, pythoncom.IID_IDispatch)
            obj = wc.Dispatch(disp)
            app = getattr(obj, "Application", None)
            if app is not None:
                return app
        except Exception:
            continue
    return None


def _attr(o: Any, name: str) -> Any:
    try:
        return getattr(o, name)
    except Exception:
        return None


def _shape_type(s: Any) -> int:
    t = _attr(s, "Type")
    return int(t) if isinstance(t, int) else -1


def _shapes_of(app: Any) -> List[Any]:
    """The objects of the active document (floating shapes, then in-line pictures) or of the slide in view, in the order they were added."""
    out: List[Any] = []
    doc = _attr(app, "ActiveDocument")
    if doc is not None:
        for coll in (_attr(doc, "Shapes"), _attr(doc, "InlineShapes")):
            n = int(_attr(coll, "Count") or 0) if coll is not None else 0
            out += [coll.Item(i) for i in range(1, n + 1)]
        return out
    win = _attr(app, "ActiveWindow")
    slide = _attr(_attr(win, "View"), "Slide") if win is not None else None
    coll = _attr(slide, "Shapes") if slide is not None else None
    n = int(_attr(coll, "Count") or 0) if coll is not None else 0
    return [coll.Item(i) for i in range(1, n + 1)]


def _selection(app: Any) -> Any:
    sel = _attr(app, "Selection")
    if sel is not None:
        return sel
    win = _attr(app, "ActiveWindow")
    return _attr(win, "Selection") if win is not None else None


class OfficeModel:
    name = "office-object-model"

    def __init__(self, hwnd: int, progid: str):
        self.hwnd, self.progid = hwnd, progid
        self.multi_document = False
        self.calls: List[Dict[str, Any]] = []

    @staticmethod
    def for_window(hwnd: int, exe: str) -> Optional["OfficeModel"]:
        from ..vendor_commands import progid_for_exe
        pid = progid_for_exe(exe) if exe else ""
        if not pid:
            return None
        m = OfficeModel(hwnd, pid)
        ok, _ = m._call(lambda app: bool(app.CommandBars), 8.0)
        if ok:
            ok2, multi = m._call(lambda app: any(_attr(app, c) is not None for c in ("Documents", "Presentations", "Workbooks")), 6.0)
            m.multi_document = bool(ok2 and multi is True)                     # a 'New' opens ANOTHER top-level document window (it would show on the person's screen)
        return m if ok else None

    def _app(self) -> Any:
        app = _native_om(self.hwnd)
        if app is not None:
            return app
        import win32com.client as wc
        from ..vendor_commands import _pids
        exe = {"word": "WINWORD.EXE", "powerpoint": "POWERPNT.EXE", "excel": "EXCEL.EXE"}.get(self.progid.split(".")[0].lower(), "")
        pids = _pids(exe) if exe else None
        if pids is not None and len(pids) == 1:                               # one process only = the run's own instance: the running object is safe to use
            return wc.GetActiveObject(self.progid)
        return None

    def _call(self, fn: Callable[[Any], Any], wall_s: float) -> Tuple[bool, Any]:
        box: Dict[str, Any] = {}

        def work() -> None:
            import pythoncom
            pythoncom.CoInitialize()
            try:
                app = self._app()
                if app is None:
                    box["err"] = "the owned window exposes no object model"
                    return
                box["res"] = fn(app)
            except Exception as exc:
                box["err"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            finally:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(wall_s)
        if t.is_alive():
            return True, "still running (a modal dialog it opened is waiting)"           # a dialog-opening command: its call returns when the dialog is closed
        if "err" in box:
            return False, box["err"]
        return True, box.get("res")

    def _new_popups(self, before: List[int]) -> List[int]:
        from core_organs import headless_input as hin
        return [w for w in hin.popup_windows(self.hwnd) if w not in before]

    def _nudge_activation(self, before: List[int], wait_s: float = 3.0) -> bool:
        """A dialog the command opened is CREATED only when the application believes it is active (measured 2026-10-10 on a parked Word: ExecuteMso('MarginsCustomMargins') kept its call
        open and no window appeared for 6 s; one posted WM_ACTIVATEAPP(TRUE) and 'Page Setup' was there). The message is POSTED to the owned window only: the real foreground, the
        keyboard focus and the person's windows are untouched (the parked-window guard conceals the dialog the moment it appears)."""
        u = ctypes.windll.user32
        u.PostMessageW(self.hwnd, 0x001C, 1, 0)                                # WM_ACTIVATEAPP, wParam TRUE
        end = time.time() + wait_s
        while time.time() < end:
            time.sleep(0.2)
            if self._new_popups(before):
                return True
        return False

    def execute(self, mso_id: str) -> Tuple[bool, str]:
        from core_organs import headless_input as hin
        try:
            before = list(hin.popup_windows(self.hwnd))
        except Exception:
            before = []
        ok, res = self._call(lambda app: (app.CommandBars.GetEnabledMso(mso_id), app.CommandBars.ExecuteMso(mso_id))[0], 4.0)
        if ok and isinstance(res, str) and res.startswith("still running") and not self._new_popups(before):
            shown = self._nudge_activation(before)
            res = res[:-1] + ("; shown after an activation message)" if shown else "; no dialog appeared even after an activation message)")
        self.calls.append({"execute": mso_id, "ok": ok, "res": str(res)[:80]})
        if ok and res is False:
            return False, f"ExecuteMso {mso_id}: the command is disabled in the current state"
        return ok, (f"object model: ExecuteMso {mso_id}" + (f" ({res})" if isinstance(res, str) else "")) if ok else f"object model failed: {res}"

    # ---- objects in the run's own document (the guide says 'select the WordArt', 'select a text placeholder')
    KIND_TESTS = (
        ("placeholder", lambda s: _shape_type(s) == 14),
        ("picture", lambda s: _shape_type(s) in (11, 13) or _attr(s, "Type") in (3, 4)),
        ("image", lambda s: _shape_type(s) in (11, 13) or _attr(s, "Type") in (3, 4)),
        ("photo", lambda s: _shape_type(s) in (11, 13)),
        ("chart", lambda s: bool(_attr(s, "HasChart"))),
        ("table", lambda s: bool(_attr(s, "HasTable"))),
        ("smartart", lambda s: bool(_attr(s, "HasSmartArt"))),
        ("text", lambda s: bool(_attr(s, "HasTextFrame")) and _shape_type(s) in (1, 14, 15, 17)),
        ("wordart", lambda s: _shape_type(s) in (15, 17) or bool(_attr(s, "HasTextFrame"))),
        ("shape", lambda s: _shape_type(s) in (1, 5, 15, 17, 14)),
    )

    def select_object(self, words: str) -> Tuple[bool, str]:
        """Select an object of the kind the guide names in the ACTIVE document / slide: the most recently added one that fits the words (a placeholder, a picture, a chart, a table, WordArt /
        a text box, a shape); with no kind word, the most recent object. (False, 'no ... object') when the document has none - the caller then creates one through the guide first."""
        w = (words or "").lower()

        def fn(app):
            if re.search(r"\b(slide|thumbnail)s?\b", w) and not re.search(r"\b(placeholder|shape|picture|image|chart|table|text ?box)\b", w):
                pres = _attr(app, "ActivePresentation")
                n = int(_attr(_attr(pres, "Slides"), "Count") or 0) if pres is not None else 0
                if not n:
                    return "none"
                pres.Slides(n).Select()                                          # 'select the slide your new slide should follow': the last one (the run's deck has only its own)
                return f"selected slide {n}"
            shapes = _shapes_of(app)
            if not shapes:
                return "none"
            tests = [t for k, t in self.KIND_TESTS if k in w]
            fit = [s for s in shapes if not tests or any(t(s) for t in tests)]
            if not fit:
                return "none"
            sh = fit[0] if "placeholder" in w else fit[-1]
            sh.Select()
            return f"selected '{_attr(sh, 'Name') or 'object'}'"
        ok, res = self._call(fn, 6.0)
        self.calls.append({"select": w[:30], "ok": ok, "res": str(res)[:80]})
        if ok and res == "none":
            return False, f"no {w or 'object'} in the run's document yet"
        return ok, (f"object model: {res}" if ok else f"object model failed: {res}")

    def key_equivalent(self, key: str) -> Tuple[bool, str]:
        """The document-editing keys a guide names, done through the model when a posted key does not reach the document: Delete / Backspace remove the selection; Ctrl+A selects all."""
        k = (key or "").lower().replace(" ", "")
        if k in ("delete", "del", "backspace"):
            def fn(app):
                sel = _selection(app)
                if sel is None:
                    raise RuntimeError("no selection in the active document")
                sel.Delete()
                return "Selection.Delete"
            ok, res = self._call(fn, 6.0)
        elif k == "ctrl+a":
            return self.execute("SelectAll")
        elif k in ("enter", "return"):
            def fn(app):
                sel = _selection(app)
                if sel is None:
                    raise RuntimeError("no selection in the active document")
                sel.TypeParagraph()                                               # the Enter key of a document: a new paragraph at the insertion point
                return "Selection.TypeParagraph"
            ok, res = self._call(fn, 6.0)
        else:
            return False, f"no object-model equivalent for the {key} key"
        self.calls.append({"key": k, "ok": ok, "res": str(res)[:80]})
        return ok, (f"object model: {res}" if ok else f"object model failed: {res}")

    def type_text(self, text: str) -> Tuple[bool, str]:
        def fn(app):
            sel = _attr(app, "Selection")
            if sel is not None and hasattr(sel, "TypeText"):
                sel.TypeText(text)
                return "Selection.TypeText"
            win = app.ActiveWindow
            s = win.Selection
            if _attr(s, "Type") == 3:                                            # text selected / an insertion point inside a text frame
                s.TextRange.InsertAfter(text)
                return "TextRange.InsertAfter"
            if _attr(s, "Type") == 2:                                            # a shape (a placeholder) selected: its text frame takes the text
                tr = s.ShapeRange(1).TextFrame.TextRange
                tr.InsertAfter(text)
                return "ShapeRange(1).TextFrame.TextRange.InsertAfter"
            raise RuntimeError("no text insertion point in the active document")
        ok, res = self._call(fn, 6.0)
        self.calls.append({"type": text[:30], "ok": ok, "res": str(res)[:80]})
        return ok, (f"object model: {res}" if ok else f"object model failed: {res}")
