"""
professor.dialogs -- WINDOWS POPUPS, FILE DIALOGS AND THE CLIPBOARD, for any application, without touching the person's own files.

A real application opens dialogs: 'Open', 'Save as', 'Import passwords', 'Select folder', 'Do you want to save changes?', 'Replace file?', permission prompts, print dialogs. A guide says 'choose the file you want'
and 'type a name and click Save'. Doing that on the person's own files would be wrong; refusing it leaves half of every manual unrun. So the run owns a SANDBOX:

  Sandbox        a throw-away folder  data/professor/sandbox/<app>/<stamp>/{inbox,outbox}.  Whatever a dialog asks to OPEN is a fixture the Professor generates there, of the type the dialog
                 asks for (read from the dialog's own file-type filter: *.csv -> a CSV, *.png -> a picture, *.docx -> a Word file ...); whatever it asks to SAVE goes to outbox with the name the
                 application proposed.  Nothing outside the sandbox is ever chosen, opened or written.
  DialogDriver   finds the dialogs of the application (by ownership, not by name), reads them through UI Automation, tells what kind each is from its CONTENT (a 'File name' field and Open / Save buttons,
                 a few buttons and a question, a form full of fields ...) and drives it: sets the file name field, presses Open / Save / Select Folder, answers a message box by wording-category
                 policy (never 'save my work', never 'allow camera', 'don't save' / 'cancel' / 'ok' as the situation says), cancels a print dialog. Every dialog window is also moved off every monitor
                 the moment it appears (the popup guard of a parked window does that for most toolkits; this closes the gap for the others - a Chromium file chooser showed on the person's screen).
  ClipboardGuard what the application copies / what a 'paste' step needs goes through the clipboard, which belongs to the PERSON. The guard saves what was there (text, picture, files, html, rtf),
                 puts a fixture there only when a step needs one, and puts the person's content back at the end - unless the person has copied something else meanwhile (then it is left alone).
                 A clipboard that holds something that cannot be put back is never overwritten.
Nothing here names an application. Which dialog it is comes from what the dialog contains.
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import re
import struct
import threading
import time
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import config as CFG
from .schema import fold

SANDBOX_ROOT = os.path.join(CFG.DATA_DIR, "sandbox")
FIXTURE_NOTE = "Hojaiga sandbox fixture - generated for testing. It contains no personal data."

_u = ctypes.windll.user32 if os.name == "nt" else None
_g = ctypes.windll.gdi32 if os.name == "nt" else None
SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
WM_KEYDOWN, WM_KEYUP, VK_RETURN, VK_ESCAPE = 0x0100, 0x0101, 0x0D, 0x1B
PARK_X = int(os.environ.get("HOJAIGA_PARK_X", "-24000"))
PARK_Y = int(os.environ.get("HOJAIGA_PARK_Y", "-24000"))

# ---- wording categories (never application names)
FILE_FIELD_RX = re.compile(r"(?i)\b(file ?name|filename|name of the file|file)\b\s*:?$|^name:?$|\bfile name\b")
FILTER_FIELD_RX = re.compile(r"(?i)(files? of type|save as type|file type|format|type):?")
CONFIRM_FILE_BUTTONS = ("open", "save", "select folder", "select", "choose", "upload", "import", "export", "insert", "attach", "ok", "yes")
FILE_TITLE_RX = re.compile(r"(?i)\b(open|save|save as|import|export|browse|select|choose|upload|insert|attach|place|locate|find file|add file|pick)\b")
FOLDER_RX = re.compile(r"(?i)\b(select|choose|browse for|pick)( a| the)? (folder|directory)\b|\bselect folder\b|\bfolder:\s*$")
PRINT_RX = re.compile(r"(?i)\bprint\b")
FRAMEWORK_HOST_RX = re.compile(r"(?i)(popupwindowsitebridge|xaml_windowedpopup|corewindow|#32768|tooltip|msctfime|ime\b|nvopenglwindow|dwm)")
MESSAGE_BUTTONS = ("ok", "yes", "no", "cancel", "close", "retry", "ignore", "abort", "save", "don't save", "dont save", "discard", "allow", "block", "continue", "later", "not now", "got it", "dismiss",
                   "try again", "replace", "skip", "stop", "keep", "exit", "don t save", "don t allow")
SAVE_PROMPT_RX = re.compile(r"(?i)\b(save (changes|your|the|this)|unsaved|do you want to save|want to save|changes (you|will)|discard|before (closing|exiting|you close))\b")
OVERWRITE_RX = re.compile(r"(?i)\b(replace|overwrite|already exists|confirm save as|same name)\b")
PERMISSION_RX = re.compile(r"(?i)\b(allow|permission|access to your|camera|microphone|location|notifications?|clipboard|want to (use|access|see)|wants to)\b")
CREDENTIAL_PROMPT_RX = re.compile(r"(?i)\b(sign in|log in|password|credential|account|authenticate|verify it'?s you|enter your pin)\b")
DESTRUCTIVE_PROMPT_RX = re.compile(r"(?i)\b(delete|remove|erase|uninstall|reset|restart|shut ?down|update now|install|reboot|format|wipe|factory|permanently)\b")
NEGATIVE_FIRST = ("don't save", "dont save", "don t save", "discard", "no", "cancel", "close without saving", "not now", "later", "block", "don't allow", "dont allow", "deny", "no thanks", "skip", "close")
AFFIRMATIVE_FIRST = ("ok", "yes", "continue", "accept", "got it", "allow", "save", "replace", "retry", "try again", "close", "dismiss")
HINT_EXT: List[Tuple[str, str]] = [(r"password|credential", "csv"), (r"csv|spreadsheet|excel|table|comma", "csv"), (r"bookmark|html|web ?page", "html"), (r"image|picture|photo|background|logo|sticker|icon|png|jpe?g|bitmap|graphic", "png"),
                                   (r"word|document|\bdoc\b", "docx"), (r"powerpoint|presentation|slide", "pptx"), (r"pdf", "pdf"), (r"audio|sound|music|song|wave", "wav"), (r"json", "json"),
                                   (r"markdown|\bmd\b", "md"), (r"xml", "xml"), (r"video|movie|clip|gif", "gif")]
EXT_PRIORITY = ["txt", "csv", "png", "docx", "xlsx", "pptx", "pdf", "json", "html", "md", "xml", "wav", "gif", "jpg", "jpeg", "bmp", "log", "rtf", "obj", "stl", "ply"]


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s or "app")[:40] or "app"


# ===================================================================================================================== the sandbox
class Sandbox:
    """The only place a dialog is ever allowed to read from or write to."""

    def __init__(self, app_key: str = "app", stamp: str = "", root: str = ""):
        self.root = root or os.path.join(SANDBOX_ROOT, _safe(app_key), stamp or time.strftime("%Y%m%d_%H%M%S"))
        self.inbox = os.path.join(self.root, "inbox")
        self.outbox = os.path.join(self.root, "outbox")
        os.makedirs(self.inbox, exist_ok=True)
        os.makedirs(self.outbox, exist_ok=True)
        self.made: List[str] = []

    def inside(self, path: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(path), os.path.abspath(self.root)]) == os.path.abspath(self.root)
        except Exception:
            return False

    def saved(self) -> List[str]:
        """Every file in the sandbox that the application WROTE (the fixtures the run generated are not counted)."""
        made = {os.path.abspath(p) for p in self.made}
        out = []
        for dp, _dn, fn in os.walk(self.root):
            out += [os.path.join(dp, f) for f in fn if os.path.abspath(os.path.join(dp, f)) not in made]
        return out

    def pick_ext(self, hint: str = "", exts: Sequence[str] = ()) -> str:
        clean = [e.lower().lstrip(".*") for e in exts if e and e.strip(".*")]
        if clean:
            for p in EXT_PRIORITY:
                if p in clean:
                    return p
            return clean[0]
        low = (hint or "").lower()
        for rx, ext in HINT_EXT:
            if re.search(rx, low):
                return ext
        return "txt"

    def fixture(self, hint: str = "", exts: Sequence[str] = (), name: str = "") -> str:
        """A file of the type the dialog asked for, generated now, inside the inbox."""
        ext = self.pick_ext(hint, exts)
        base = _safe(name) if name else "hojaiga-fixture"                         # the name the application proposed when it proposed one, else a plain one
        path = os.path.join(self.inbox, f"{base}.{ext}")
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(self.inbox, f"{base}_{n}.{ext}")
        write_fixture(path, ext, hint)
        self.made.append(path)
        return path

    def save_target(self, proposed: str = "", exts: Sequence[str] = ()) -> str:
        """Where a 'Save as' goes: the sandbox's outbox, the name the application proposed (made unique), the extension its file-type filter asks for."""
        name = os.path.basename((proposed or "").strip().strip('"')) or "hojaiga-output"
        stem, ext0 = os.path.splitext(name)
        ext = (ext0.lstrip(".") or self.pick_ext("", exts)).lower()
        stem = _safe(stem) or "hojaiga-output"
        path = os.path.join(self.outbox, f"{stem}.{ext}")
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(self.outbox, f"{stem}_{n}.{ext}")
        return path

    def summary(self) -> Dict[str, Any]:
        return {"root": self.root, "fixtures_made": [os.path.basename(p) for p in self.made], "files_saved": [os.path.relpath(p, self.root) for p in self.saved()]}


def write_fixture(path: str, ext: str, hint: str = "") -> None:
    """A small, valid file of the requested type. Each is real (it opens in the application that reads the type) and says what it is."""
    e = ext.lower()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    low = (hint or "").lower()
    if e in ("txt", "log", "ini", "cfg", "text", ""):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(FIXTURE_NOTE + "\nLine two of the fixture.\nLine three.\n")
    elif e in ("md", "markdown"):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# Hojaiga fixture\n\n" + FIXTURE_NOTE + "\n\n- item one\n- item two\n")
    elif e == "csv":
        with open(path, "w", encoding="utf-8", newline="") as fh:
            if re.search(r"password|credential", low):
                fh.write("name,url,username,password,note\nexample,https://example.com/,test-user,not-a-real-password,fixture\n")
            else:
                fh.write("id,name,value\n1,alpha,10\n2,beta,20\n3,gamma,30\n")
    elif e == "json":
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"fixture": True, "note": FIXTURE_NOTE, "items": [1, 2, 3]}, fh, indent=1)
    elif e in ("html", "htm"):
        with open(path, "w", encoding="utf-8") as fh:
            if re.search(r"bookmark", low):
                fh.write('<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n<TITLE>Bookmarks</TITLE>\n<H1>Bookmarks</H1>\n<DL><p>\n'
                         '    <DT><A HREF="https://example.com/">Example (fixture)</A>\n</DL><p>\n')
            else:
                fh.write("<!doctype html><meta charset=utf-8><title>Hojaiga fixture</title><h1>Hojaiga fixture</h1><p>" + FIXTURE_NOTE + "</p>")
    elif e == "xml":
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('<?xml version="1.0" encoding="utf-8"?>\n<fixture note="' + FIXTURE_NOTE + '"><item>1</item></fixture>\n')
    elif e in ("png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "webp", "ico"):
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (320, 200), (240, 240, 240))
        d = ImageDraw.Draw(im)
        for i in range(0, 320, 16):
            d.rectangle((i, 0, i + 8, 200), fill=(40 + i // 2, 120, 200 - i // 3))
        d.text((12, 90), "Hojaiga fixture", fill=(0, 0, 0))
        im.save(path, {"jpg": "JPEG", "jpeg": "JPEG", "tif": "TIFF", "tiff": "TIFF", "ico": "ICO"}.get(e, e.upper()))
    elif e == "pdf":
        try:
            from reportlab.pdfgen import canvas
            c = canvas.Canvas(path)
            c.drawString(72, 760, "Hojaiga fixture")
            c.drawString(72, 740, FIXTURE_NOTE)
            c.save()
        except Exception:
            with open(path, "wb") as fh:
                fh.write(b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
    elif e == "obj":                                                              # a unit cube: the smallest 3D file every modelling tool can import
        corners = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
        faces = ["f 1 3 4 2", "f 5 6 8 7", "f 1 2 6 5", "f 3 7 8 4", "f 1 5 7 3", "f 2 4 8 6"]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(["# " + FIXTURE_NOTE, "o hojaiga_fixture_cube"] + [f"v {x} {y} {z}" for x, y, z in corners] + faces) + "\n")
    elif e == "stl":
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("solid hojaiga_fixture\n  facet normal 0 0 1\n    outer loop\n      vertex 0 0 0\n      vertex 1 0 0\n      vertex 0 1 0\n    endloop\n  endfacet\nendsolid hojaiga_fixture\n")
    elif e == "ply":
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(["ply", "format ascii 1.0", "comment " + FIXTURE_NOTE, "element vertex 3", "property float x", "property float y", "property float z", "element face 1",
                                 "property list uchar int vertex_indices", "end_header", "0 0 0", "1 0 0", "0 1 0", "3 0 1 2"]) + "\n")
    elif e in ("docx", "dotx"):
        from docx import Document
        doc = Document()
        doc.add_heading("Hojaiga fixture", 1)
        doc.add_paragraph(FIXTURE_NOTE)
        doc.save(path)
    elif e in ("xlsx", "xlsm"):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["id", "name", "value"])
        ws.append([1, "alpha", 10])
        ws.append([2, "beta", 20])
        wb.save(path)
    elif e in ("pptx", "potx"):
        from pptx import Presentation
        pr = Presentation()
        sl = pr.slides.add_slide(pr.slide_layouts[1])
        sl.shapes.title.text = "Hojaiga fixture"
        sl.placeholders[1].text = FIXTURE_NOTE
        pr.save(path)
    elif e in ("wav", "wave"):
        import math
        import wave
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 8000))) for i in range(4000)))
    elif e == "zip":
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("fixture.txt", FIXTURE_NOTE)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(FIXTURE_NOTE + "\n")


def paths_in(text: str) -> List[str]:
    """Existing files / folders a person wrote in a request ('insert D:\\pics\\cat.png into the slide', "open 'C:\\Users\\me\\Report.docx'"): the only own files a dialog may choose."""
    out: List[str] = []
    for m in re.finditer(r"""["']?([A-Za-z]:[\\/][^"'<>|?*\r\n]+?)(?=["']|\s+(?:in|into|to|from|and|then|as|on)\b|[,;]|$)""", text or ""):
        p = m.group(1).strip().rstrip(".")
        if os.path.exists(p) and os.path.abspath(p) not in out:
            out.append(os.path.abspath(p))
    return out


def combo_items(h: int, limit: int = 40) -> List[str]:
    """The entries of a Win32 combo box (CB_GETCOUNT / CB_GETLBTEXT; the system marshals the text across processes)."""
    out: List[str] = []
    if _u is None:
        return out
    try:
        n = int(_u.SendMessageW(h, 0x0146, 0, 0))                          # CB_GETCOUNT
        for i in range(max(0, min(n, limit))):
            ln = int(_u.SendMessageW(h, 0x0149, i, 0))                     # CB_GETLBTEXTLEN
            if ln <= 0 or ln > 2000:
                continue
            buf = ctypes.create_unicode_buffer(ln + 2)
            _u.SendMessageW(h, 0x0148, i, buf)                              # CB_GETLBTEXT
            if buf.value:
                out.append(buf.value)
    except Exception:
        pass
    return out


FIXTURE_EXTS = {"txt", "log", "ini", "cfg", "text", "md", "markdown", "html", "htm", "png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "webp", "ico", "docx", "dotx", "xlsx", "xlsm",
                "pptx", "potx", "wav", "wave", "zip", "csv", "pdf", "json", "xml", "rtf", "obj", "stl", "ply"}


def parse_filter(text: str) -> List[str]:
    """'Microsoft Excel Comma Separated Values File (*.csv)' / 'Images (*.png;*.jpg)' / 'All files (*.*)' -> ['csv'] / ['png','jpg'] / []."""
    out: List[str] = []
    for m in re.finditer(r"\*\.([A-Za-z0-9]{1,6})\b", text or ""):
        if m.group(1) not in out:
            out.append(m.group(1).lower())
    return out


# ===================================================================================================================== concealing
def conceal(hwnd: int) -> bool:
    """Give a window an empty region and move it off every monitor (nothing of it is drawn on any screen; UI Automation and posted messages still reach it)."""
    if _u is None or not hwnd:
        return False
    try:
        from core_organs import background_window as bw
        if not bw._on_real_screen(bw._rect(hwnd)):
            return False
        rgn = _g.CreateRectRgn(0, 0, 0, 0)
        if rgn and not _u.SetWindowRgn(hwnd, rgn, False):
            _g.DeleteObject(rgn)
        _u.SetWindowPos(hwnd, 0, PARK_X, PARK_Y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        return True
    except Exception:
        return False


class DialogWatch(threading.Thread):
    """Every ~80 ms: any window of the application's process that is not the frame and was not there at the start is concealed. Covers toolkits whose dialogs the parked-window guard does not
    recognise (a Chromium file chooser opened on the person's screen)."""

    def __init__(self, hwnd: int, baseline: Sequence[int] = ()):
        super().__init__(daemon=True, name=f"dialog-watch-{hwnd}")
        self.hwnd, self.baseline = hwnd, set(baseline)
        self._halt = threading.Event()
        self.concealed: List[int] = []

    def run(self) -> None:
        from core_organs import headless_input as hin
        while not self._halt.wait(0.08):
            try:
                for w in hin.popup_windows(self.hwnd):
                    if w in self.baseline or w in self.concealed:
                        continue
                    if FRAMEWORK_HOST_RX.search(hin._class_name(w) or ""):
                        continue                                                  # flyouts / tooltips: the popup guard owns those
                    if conceal(w):
                        self.concealed.append(w)
            except Exception:
                pass

    def halt(self) -> None:
        self._halt.set()


# ===================================================================================================================== reading a dialog
@dataclass
class DialogInfo:
    hwnd: int
    title: str = ""
    cls: str = ""
    nodes: List[Any] = field(default_factory=list)
    buttons: List[str] = field(default_factory=list)
    texts: List[str] = field(default_factory=list)
    n_fields: int = 0
    kind: str = "other"                       # file_open | file_save | folder | print | message | other
    file_edit: Any = None
    filter_text: str = ""
    filter_exts: List[str] = field(default_factory=list)
    filter_all: List[str] = field(default_factory=list)
    default_name: str = ""
    win32: bool = False                       # read through window messages, not UI Automation (a file dialog's tree is huge and slow)
    edit_hwnd: int = 0
    buttons_w32: Dict[str, int] = field(default_factory=dict)

    def brief(self) -> str:
        return f"{self.kind}: '{self.title[:50]}' buttons={self.buttons[:6]} fields={self.n_fields}"


def _value_of(n: Any) -> str:
    try:
        from .probe import _editable_value
        v = _editable_value(n)
        if v is not None:
            return v
    except Exception:
        pass
    try:
        from .effectors import pattern_of
        for pn in ("Value", "LegacyIAccessible"):
            p = pattern_of(n.ctrl, pn)
            v = getattr(p, "Value", None) if p is not None else None
            if v:
                return str(v)
    except Exception:
        pass
    return ""


WM_GETTEXT, WM_SETTEXT, BM_CLICK, SMTO_ABORTIFHUNG = 0x000D, 0x000C, 0x00F5, 0x0002
_HEAVY_CHILD_CLASSES = ("DUIViewWndClassName", "ComboBoxEx32", "SHELLDLL_DefView")          # the shell's file-browsing controls (a task dialog / message box has DirectUIHWND only)
_heavy_cache: Dict[int, bool] = {}


def _w32_text(h: int, timeout_ms: int = 250) -> str:
    buf = ctypes.create_unicode_buffer(1024)
    res = ctypes.c_size_t(0)
    ok = _u.SendMessageTimeoutW(h, WM_GETTEXT, 1024, buf, SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(res))
    return buf.value if ok else ""


def _w32_children(hwnd: int, limit: int = 300) -> List[Tuple[int, int, str, str, int]]:
    """(hwnd, parent, class, text, control id) of the dialog's real child windows. A DirectUI file list is windowless, so this stays small however many files the folder holds."""
    out: List[Tuple[int, int, str, str, int]] = []
    cls = ctypes.create_unicode_buffer(128)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(h, _l):
        if len(out) >= limit:
            return False
        try:
            _u.GetClassNameW(h, cls, 128)
            out.append((int(h), int(_u.GetParent(h) or 0), cls.value, _w32_text(h), int(_u.GetDlgCtrlID(h))))
        except Exception:
            pass
        return True
    try:
        _u.EnumChildWindows(hwnd, cb, 0)
    except Exception:
        pass
    return out


def is_heavy_dialog(hwnd: int) -> bool:
    """A common file dialog (Open / Save as / Select folder / Import ...): a top-level dialog whose children are the shell's file-browsing controls. Cached per window."""
    if hwnd in _heavy_cache:
        return _heavy_cache[hwnd]
    res = False
    try:
        from core_organs import headless_input as hin
        if (hin._class_name(hwnd) or "") == "#32770":
            res = any(c[2] in _HEAVY_CHILD_CLASSES for c in _w32_children(hwnd, 60))
    except Exception:
        res = False
    if len(_heavy_cache) > 400:
        _heavy_cache.clear()
    _heavy_cache[hwnd] = res
    return res


def light_popups(hwnd: int, cap: int = 6) -> List[int]:
    """The pop-up windows of an application that are cheap to read through UI Automation (menus, flyouts, small dialogs) - file dialogs are left out."""
    from core_organs import headless_input as hin
    return [w for w in hin.popup_windows(hwnd)[:cap + 4] if not is_heavy_dialog(w)][:cap]


def inspect_win32(hwnd: int) -> Optional[DialogInfo]:
    from core_organs import headless_input as hin
    kids = _w32_children(hwnd)
    if not kids:
        return None
    info = DialogInfo(hwnd, (hin.safe_window_text(hwnd, 200) or "").strip(), hin._class_name(hwnd) or "", [], win32=True)
    parent_of = {k[0]: k[1] for k in kids}
    cls_of = {k[0]: k[2] for k in kids}

    def inside(h: int, klass: str) -> bool:
        cur, n = parent_of.get(h, 0), 0
        while cur and cur != hwnd and n < 8:
            if cls_of.get(cur) == klass:
                return True
            cur, n = parent_of.get(cur, 0), n + 1
        return False
    def edit_score(k: Tuple[int, int, str, str, int]) -> int:
        """Which Edit is the FILE NAME field: the Vista dialog's id 1001, the classic ids, an edit inside a combo box; never the search box or the address bar."""
        sc = 0
        if k[4] == 1001 or k[4] in (0x480, 0x47C):
            sc += 3
        if inside(k[0], "ComboBoxEx32"):
            sc += 2
        if inside(k[0], "ComboBox"):
            sc += 1
        if any(inside(k[0], bad) for bad in ("UniversalSearchBand", "SearchEditBoxWrapperClass", "Address Band Root", "ToolbarWindow32", "Breadcrumb Parent")):
            sc -= 10
        return sc
    edits = sorted((k for k in kids if k[2] == "Edit"), key=lambda k: -edit_score(k))
    if edits and edit_score(edits[0]) >= 1:
        info.edit_hwnd = edits[0][0]
        info.file_edit = edits[0][0]
        info.default_name = edits[0][3].strip()
    for h, _p, c, t, i in kids:
        if c == "Button" and t:
            label = t.replace("&", "").strip()
            info.buttons.append(label)
            info.buttons_w32[fold(label)] = h
            if i == 1:
                info.buttons_w32["__ok__"] = h
            if i == 2:
                info.buttons_w32["__cancel__"] = h
        elif c == "Static" and t.strip():
            info.texts.append(t.replace("&", "").strip())
    for h, _p, c, t, i in kids:
        if c == "ComboBox" and not inside(h, "ComboBoxEx32") and (i == 0x470 or re.search(r"\*\.", t or "")):
            info.filter_text = t
            info.filter_exts = parse_filter(t)
            entries = combo_items(h)                                       # a dialog often SHOWS only a friendly name ('All Pictures'); its list says which types it takes
            info.filter_all = entries
            if any("*.*" in e for e in entries + [t or ""]):
                info.filter_exts.append("*")                                   # 'All files (*.*)': any type is taken
            for e in entries:
                for x in parse_filter(e):
                    if x not in info.filter_exts:
                        info.filter_exts.append(x)
            break
    ok_label = fold(next((b for b in info.buttons if info.buttons_w32.get(fold(b)) == info.buttons_w32.get("__ok__")), ""))
    title = fold(info.title)
    if "folder" in ok_label or FOLDER_RX.search(info.title + " " + " ".join(info.texts)):
        info.kind = "folder"
    elif "save" in ok_label or re.search(r"\b(save|export)\b", title):
        info.kind = "file_save"
    else:
        info.kind = "file_open"
    return info


def inspect(hwnd: int) -> Optional[DialogInfo]:
    from core_organs import fast_uia, headless_input as hin
    if is_heavy_dialog(hwnd):
        return inspect_win32(hwnd)
    nodes = fast_uia.snapshot(hwnd, timeout_ms=3000) or []
    if not nodes:
        return None
    info = DialogInfo(hwnd, (hin.safe_window_text(hwnd, 200) or "").strip(), hin._class_name(hwnd) or "", nodes)
    info.buttons = [n.name for n in nodes if n.role in ("button", "splitbutton") and n.name and not n.offscreen]
    info.texts = [n.name for n in nodes if n.role == "text" and n.name and not n.offscreen]
    info.n_fields = sum(1 for n in nodes if n.role in ("edit", "combobox", "checkbox", "radiobutton", "spinner", "slider", "list", "tree", "datagrid", "table") and not n.offscreen)
    # the file-name field: an Edit (with a value pattern) that is, or sits inside, a control called 'File name'
    for n in nodes:
        if n.role in ("edit", "combobox") and n.name and FILE_FIELD_RX.search(n.name.strip()) and not n.offscreen:
            edit = n if (n.role == "edit" and "value" in (n.pats or [])) else next((c for c in nodes if c.parent == n.idx and c.role == "edit"), n)
            info.file_edit = edit
            info.default_name = (_value_of(edit) or "").strip()
            break
    for n in nodes:
        if n.role in ("combobox", "edit") and n.name and FILTER_FIELD_RX.search(n.name) and n is not info.file_edit and not n.offscreen:
            txt = _value_of(n) or next((v for v in (_value_of(c) for c in nodes if c.parent == n.idx and c.role in ("edit", "text", "listitem")) if v), "") or " ".join(c.name for c in nodes if c.parent == n.idx and c.name)
            if not txt:
                sel = next((c for c in nodes if c.parent == n.idx and c.selected), None)
                txt = sel.name if sel is not None else ""
            info.filter_text = txt
            info.filter_exts = parse_filter(txt)
            break
    bt = {fold(b) for b in info.buttons}
    title = fold(info.title)
    alltext = fold(" ".join([info.title] + info.texts))
    if info.file_edit is not None or (FILE_TITLE_RX.search(info.title or "") and {"cancel"} & bt and ({"open", "save", "select folder", "select", "choose", "upload"} & bt)):
        if FOLDER_RX.search(info.title + " " + " ".join(info.texts)) or "select folder" in bt:
            info.kind = "folder"
        elif "save" in bt or re.search(r"\b(save|export)\b", title):
            info.kind = "file_save"
        else:
            info.kind = "file_open"
    elif PRINT_RX.search(info.title or "") and ({"print"} & bt or {"cancel"} & bt) and info.n_fields >= 2:
        info.kind = "print"
    elif info.buttons and info.n_fields <= 1 and len(info.buttons) <= 6 and any(fold(b) in MESSAGE_BUTTONS or fold(b).rstrip(".") in MESSAGE_BUTTONS for b in info.buttons):
        info.kind = "message"
    else:
        info.kind = "other"
    return info


# ===================================================================================================================== the driver
def choose_button(info: DialogInfo, in_sandbox: bool = True, intent: str = "") -> Tuple[str, str]:
    """Which button of a message box, and why. Policy by WORDING CATEGORY of the question: a person's work is never saved, permissions are never granted, accounts are never signed in, destructive
    questions are declined, plain information is acknowledged. `intent` ('accept' / 'decline') settles only an otherwise neutral question."""
    text = " ".join([info.title] + info.texts)
    labels = {fold(b).rstrip("."): b for b in info.buttons}

    def pick(*names: str) -> str:
        for nme in names:
            k = fold(nme)                                                          # 'Don't save' is 'don t save' once folded: both sides are folded
            if k in labels:
                return labels[k]
        return ""
    if SAVE_PROMPT_RX.search(text) and not OVERWRITE_RX.search(text):
        b = pick("don't save", "dont save", "don t save", "discard", "no", "close without saving", "don’t save")
        return (b, "unsaved-changes question: the person's work is never saved by a test") if b else (pick("cancel", "close"), "unsaved-changes question with no 'don't save': cancelled")
    if OVERWRITE_RX.search(text):
        if in_sandbox:
            b = pick("yes", "replace", "ok", "overwrite")
            if b:
                return b, "replace question about a file inside the sandbox"
        return pick("no", "cancel", "skip", "keep"), "replace question: a file outside the sandbox is never replaced"
    if CREDENTIAL_PROMPT_RX.search(text):
        return pick("cancel", "close", "not now", "no", "later", "dismiss"), "sign-in / credential question: left to the person"
    if PERMISSION_RX.search(text) and re.search(r"(?i)\b(allow|block|permission|camera|microphone|location|notifications?|access)\b", text):
        return pick("block", "don't allow", "dont allow", "deny", "no", "cancel", "not now", "close"), "permission question: never granted by a test"
    if DESTRUCTIVE_PROMPT_RX.search(text):
        return pick("cancel", "no", "not now", "later", "close", "dismiss"), "destructive / system question: declined"
    if "?" not in text:
        return pick("ok", "close", "got it", "dismiss", "continue", "yes"), "information: acknowledged"
    if intent == "decline":
        return pick(*NEGATIVE_FIRST), "neutral question: declined"
    return pick(*AFFIRMATIVE_FIRST) or pick(*NEGATIVE_FIRST), "neutral question: accepted"


class DialogDriver:
    def __init__(self, fx: Any, hwnd: int, sandbox: Sandbox, baseline: Sequence[int] = (), history: Any = None, toolkit: str = "", log: Optional[Callable[[str], None]] = None):
        self.fx, self.hwnd, self.sandbox = fx, hwnd, sandbox
        self.baseline = set(baseline)
        self.history, self.toolkit = history, toolkit
        self.log = log or (lambda s: None)
        self.handled: List[Dict[str, Any]] = []
        self.last_file_dialog_at = 0.0
        self.needs_prime = False                                                    # a Save dialog was cancelled because it showed a folder outside the sandbox
        self.user_files: List[str] = []                                             # files / folders the PERSON named in the request (the only own files a dialog may choose)
        self.watch: Optional[DialogWatch] = None

    # ---- lifecycle
    def start_watch(self) -> None:
        if self.watch is None:
            self.watch = DialogWatch(self.hwnd, self.baseline)
            self.watch.start()

    def stop_watch(self) -> None:
        if self.watch is not None:
            self.watch.halt()
            self.watch = None

    # ---- finding
    def windows(self) -> List[int]:
        from core_organs import headless_input as hin
        out: List[int] = []
        try:
            for w in hin.popup_windows(self.hwnd):
                if w in self.baseline or FRAMEWORK_HOST_RX.search(hin._class_name(w) or ""):
                    continue
                out.append(w)
        except Exception:
            pass
        return out

    def pending(self) -> bool:
        return bool(self.windows())

    def look(self, skip: Sequence[int] = ()) -> List[DialogInfo]:
        infos = []
        for w in [x for x in self.windows() if x not in skip][:5]:
            conceal(w)
            i = inspect(w)
            if i is not None:
                infos.append(i)
        return infos

    # ---- acting
    def _click(self, info: DialogInfo, *names: str) -> str:
        want = [fold(n) for n in names]
        if info.win32:
            for wname in want + ["__ok__"] * (1 if any(w in ("open", "save", "select folder", "select", "choose", "upload", "import", "export", "insert", "attach", "ok") for w in want) else 0):
                h = info.buttons_w32.get(wname)
                if h and _u.PostMessageW(h, BM_CLICK, 0, 0):
                    return next((b for b in info.buttons if info.buttons_w32.get(fold(b)) == h), wname)
            if "cancel" in want and info.buttons_w32.get("__cancel__") and _u.PostMessageW(info.buttons_w32["__cancel__"], BM_CLICK, 0, 0):
                return "Cancel"
            return ""
        for wname in want:
            for n in info.nodes:
                if n.role in ("button", "splitbutton") and n.enabled and not n.offscreen and fold(n.name).rstrip(".") == wname:
                    ok, how = self.fx.node(n)
                    if ok:
                        return n.name
        return ""

    def _closed(self, hwnd: int, max_s: float = 6.0) -> bool:
        from core_organs import headless_input as hin
        end = time.time() + max_s
        while time.time() < end:
            if not hin.is_alive(hwnd) or hwnd not in self.windows():
                return True
            time.sleep(0.2)
        return False

    def _press(self, hwnd: int, vk: int) -> None:
        _u.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
        _u.PostMessageW(hwnd, WM_KEYUP, vk, 0)

    def _type_w32(self, edit: int, text: str) -> Tuple[bool, str]:
        """Put text into a dialog's edit field the way a person does: select what is there, then send the characters one by one. (WM_SETTEXT changes only what is DRAWN: the dialog confirms its own
        remembered name - measured - whereas typed characters raise the change notifications the dialog listens to.)"""
        res = ctypes.c_size_t(0)
        _u.SendMessageTimeoutW(edit, 0x00B1, 0, -1, SMTO_ABORTIFHUNG, 500, ctypes.byref(res))             # EM_SETSEL(0, -1)
        for i, ch in enumerate(text):
            _u.PostMessageW(edit, 0x0102, ord(ch), 0)                                                    # WM_CHAR
            if i % 24 == 23:
                time.sleep(0.02)
        time.sleep(0.6)
        got = _w32_text(edit)
        if got.lower() == text.lower():
            return True, "typed into the file-name field"
        ok = _u.SendMessageTimeoutW(edit, WM_SETTEXT, 0, text, SMTO_ABORTIFHUNG, 1000, ctypes.byref(res))      # fall back to setting the text
        time.sleep(0.7)
        got = _w32_text(edit)
        return bool(ok and os.path.basename(text).lower() in got.lower()), "WM_SETTEXT into the file-name field (typing did not take)"

    def _set_name(self, info: DialogInfo, text: str) -> Tuple[bool, str]:
        n = info.file_edit
        if n is None:
            return False, "no file-name field found"
        if info.win32:
            return self._type_w32(info.edit_hwnd, text)
        ok, how = self.fx.set_value(n, text)
        got = _value_of(n)
        if ok and got and os.path.basename(text).lower() in got.lower():
            return True, how
        ok2, how2 = self.fx.insert_text(text)
        return ok2, f"{how}; then {how2}"

    def _address_of(self, hwnd: int) -> str:
        for _h, _p, c, t, _i in _w32_children(hwnd, 200):
            if c == "ToolbarWindow32" and t.lower().startswith("address:"):
                return t[8:].strip()
        return ""

    def _user_choice(self, info: DialogInfo) -> str:
        """A file / folder the PERSON named in the request (self.user_files), of a type this dialog takes - the only way one of the person's own files is ever chosen."""
        for f in getattr(self, "user_files", []) or []:
            if info.kind == "folder" and os.path.isdir(f):
                return f
            if info.kind == "file_open" and os.path.isfile(f):
                ext = os.path.splitext(f)[1].lower().lstrip(".")
                if not info.filter_exts or "*" in info.filter_exts or ext in info.filter_exts:
                    return f
        return ""

    def _navigate(self, info: DialogInfo, folder: str) -> bool:
        """A file dialog saves / opens relative to the folder it shows: like a person, type the FOLDER and confirm (the dialog goes there and stays open), and check its address bar says so."""
        ok, _how = self._set_name(info, folder)
        if not ok or not self._click(info, "open", "save", "select", "choose"):
            return False
        want = os.path.normcase(os.path.abspath(folder)).rstrip("\\")
        end = time.time() + 3.5
        while time.time() < end:
            time.sleep(0.25)
            addr = os.path.normcase(self._address_of(info.hwnd)).rstrip("\\")
            if addr and (addr == want or addr.endswith(os.path.basename(want))):
                return True
        return False

    def drive(self, info: DialogInfo, intent: str = "") -> Dict[str, Any]:
        t0 = time.time()
        res: Dict[str, Any] = {"kind": info.kind, "title": info.title[:60], "ok": False, "steps": [], "path": ""}
        try:
            if info.kind in ("file_open", "file_save", "folder"):
                self.last_file_dialog_at = time.time()
                hint = " ".join([info.title, info.default_name, info.filter_text] + info.texts[:3])
                mine = self._user_choice(info)
                if info.kind in ("file_open", "folder") and mine:
                    path = mine
                    res["steps"].append(f"the file / folder the person named in the request: {mine}")
                elif info.kind == "file_open" and info.filter_exts and "*" not in info.filter_exts and not (set(info.filter_exts) & FIXTURE_EXTS):
                    self._click(info, "cancel")
                    why = (f"the dialog takes only {', '.join('.' + e for e in info.filter_exts[:6])} files; no such file can be generated in the sandbox and none was named in the "
                           f"request - cancelled (name the file in the request to use your own)")
                    res["steps"].append(why)
                    res["ok"] = False
                    res["needs_file"] = info.filter_exts[:6]
                    res["closed"] = self._closed(info.hwnd, 3.0)
                    res["seconds"] = round(time.time() - t0, 1)
                    self.handled.append(res)
                    self._log(info, res)
                    return res
                elif info.kind == "file_open":
                    usable = [e for e in info.filter_exts if e in FIXTURE_EXTS] or info.filter_exts
                    path = self.sandbox.fixture(hint, usable, name=os.path.splitext(info.default_name)[0] if info.default_name else "")
                    res["steps"].append(f"made a {os.path.splitext(path)[1]} fixture in the sandbox inbox (the dialog takes {', '.join(info.filter_exts[:5]) or 'any type'})")
                elif info.kind == "file_save":
                    path = self.sandbox.save_target(info.default_name, info.filter_exts)
                    res["steps"].append("save target = sandbox outbox")
                else:
                    path = self.sandbox.inbox
                    res["steps"].append("folder = sandbox inbox")
                res["path"] = path
                typed = path
                if info.win32 and info.kind in ("file_save", "folder"):
                    # A Vista-style Save dialog saves into the folder it SHOWS (a full path typed into its name field loses its folder part - measured). So where it is shown is checked first: only a
                    # dialog that is already inside the sandbox may confirm; anything else is cancelled, never saved blind. (Windows reopens a dialog where the last one was completed; completing one
                    # Open of a sandbox fixture - Executor.prime_dialog_folder - makes that the sandbox.)
                    where = self._address_of(info.hwnd)
                    classic = any(c[2] == "ComboBoxEx32" for c in _w32_children(info.hwnd, 80))
                    res["dialog_folder"] = where
                    if not classic and not (where and self.sandbox.inside(where)):
                        self._click(info, "cancel")
                        res["steps"].append(f"the dialog is showing '{where or 'an unknown folder'}', outside the sandbox: cancelled - a file is never saved where it cannot be verified")
                        res["needs_prime"] = True
                        res["ok"] = self._closed(info.hwnd, 3.0) and False
                        res["seconds"] = round(time.time() - t0, 1)
                        self.needs_prime = True
                        self.handled.append(res)
                        self._log(info, res)
                        return res
                    if not classic and info.kind == "file_save":
                        stem, ext = os.path.splitext(os.path.basename(path))             # it will land in the folder the dialog SHOWS (inside the sandbox): that is where it is looked for
                        path, n_ = os.path.join(where, os.path.basename(path)), 1
                        while os.path.exists(path):
                            n_ += 1
                            path = os.path.join(where, f"{stem}_{n_}{ext}")
                        res["path"] = path
                    typed = os.path.basename(path) if not classic else path             # inside the sandbox: only the name is typed
                ok, how = self._set_name(info, typed)
                res["steps"].append(f"file name field: {how}")
                if not ok:                                                              # nothing was put into the field: confirming would act on whatever the dialog proposed (maybe the person's folder)
                    res["steps"].append("not confirmed: the file name could not be set")
                    self._press(info.hwnd, VK_ESCAPE)
                    res["ok"] = self._closed(info.hwnd, 3.0) and False
                    res["seconds"] = round(time.time() - t0, 1)
                    self.handled.append(res)
                    self._log(info, res)
                    return res
                btn = self._click(info, *[b for b in CONFIRM_FILE_BUTTONS])
                res["steps"].append(f"pressed '{btn}'" if btn else "no confirm button found")
                if not btn:
                    self._press(info.hwnd, VK_RETURN)
                    res["steps"].append("pressed Enter")
                closed = self._closed(info.hwnd, 5.0)
                if not closed:
                    follow = self.settle(max_s=4.0, intent="accept", skip=(info.hwnd,))     # 'file exists - replace?' and the like (never the dialog being driven)
                    res["steps"].append(f"follow-up dialogs handled: {len(follow)}: " + " / ".join("; ".join(f.get("steps", []))[:200] for f in follow))
                    closed = self._closed(info.hwnd, 3.0)
                res["ok"] = closed and (info.kind != "file_save" or self._exists_soon(path))
                if info.kind == "file_save":
                    res["saved"] = os.path.exists(path)
            elif info.kind == "print":
                btn = self._click(info, "cancel", "close")
                if not btn:
                    self._press(info.hwnd, VK_ESCAPE)
                res["steps"].append("print dialog cancelled: nothing is ever printed" + (f" ('{btn}')" if btn else ""))
                res["ok"] = self._closed(info.hwnd, 4.0)
            elif info.kind == "message":
                btn, why = choose_button(info, True, intent)
                res["steps"].append(f"message box '{(' '.join(info.texts))[:160]}' -> {why}")
                res["texts"] = info.texts[:3]
                clicked = self._click(info, btn) if btn else ""
                if not clicked:
                    self._press(info.hwnd, VK_ESCAPE)
                res["steps"].append(f"pressed '{clicked}'" if clicked else "pressed Escape")
                res["ok"] = self._closed(info.hwnd, 4.0)
            else:
                res["steps"].append("an application form: left to the guide's steps")
                res["left"] = True
        except Exception as exc:
            res["steps"].append(f"error {type(exc).__name__}: {str(exc)[:100]}")
        res["seconds"] = round(time.time() - t0, 1)
        if not res.get("left"):
            self.handled.append(res)
            self._log(info, res)
            self.log(f"dialog handled: {res['kind']} '{res['title']}' -> {'ok' if res['ok'] else 'NOT closed'}")
        return res

    def _exists_soon(self, path: str, max_s: float = 3.0) -> bool:
        end = time.time() + max_s
        while time.time() < end:
            if os.path.exists(path):
                return True
            time.sleep(0.2)
        return False

    def settle(self, max_s: float = 6.0, intent: str = "", kinds: Sequence[str] = ("file_open", "file_save", "folder", "print", "message"), skip: Sequence[int] = ()) -> List[Dict[str, Any]]:
        """Handle every dialog of the application that is open now (and any that its answer brings up) until none is left or the time is up. Application forms ('other') stay open."""
        out: List[Dict[str, Any]] = []
        end = time.time() + max_s
        quiet_since = time.time()
        seen: Dict[int, int] = {}
        while time.time() < end:
            infos = [i for i in self.look(skip) if i.kind in kinds]
            if not infos:
                if time.time() - quiet_since > 0.7:
                    break
                time.sleep(0.2)
                continue
            quiet_since = time.time()
            for i in infos:
                seen[i.hwnd] = seen.get(i.hwnd, 0) + 1
                if seen[i.hwnd] > 3:                                                  # it will not go away: stop pushing, the report says so
                    continue
                out.append(self.drive(i, intent))
        return out

    def recent_file_dialog(self, within_s: float = 25.0) -> bool:
        return bool(self.last_file_dialog_at and time.time() - self.last_file_dialog_at < within_s)

    def _log(self, info: DialogInfo, res: Dict[str, Any]) -> None:
        if self.history is None:
            return
        try:
            self.history.log("dialogs", "dialog", "dialog", f"{info.kind}:{info.title[:30]}", "dialog-driver", "", f"{len(info.buttons)} buttons", "", "; ".join(res["steps"])[:120],
                             "dialog_closed" if res["ok"] else "dialog_stuck", bool(res["ok"]), None, "", {"path": res.get("path", ""), "kind": info.kind}, toolkit=self.toolkit, role="dialog", safety="safe")
        except Exception:
            pass


# step wording that belongs to a file dialog: what a guide says once the dialog is open
FILE_STEP_RX = re.compile(r"(?i)(\b(file name|filename|folder|directory|browse|save in|save as type|file type|files of type|where to save|where you want to save)\b|\b(?:choose|select|pick|browse to|specify)\s+(?:a|the|your)\s+(?:save |file |folder |install )?location\b|"
                          r"\b(choose|select|pick)\s+(?:a|the)\s+(?:file\s+)?format\b|"
                          r"\b(choose|select|pick|find|locate|navigate to|go to|open|double-?click)\b[^.>()]{0,40}\b(files?(?!\s+(?:menu|tab|button))|images?|pictures?|photos?|documents?|folders?|csv|spreadsheet|pdf)\b|"
                          r"\b(click|press|select|choose)\b[^.>]{0,12}\b(open|save|select folder|upload|insert|import|export)\b|"
                          r"\b(type|enter|name)\b[^.>]{0,30}\b(file|document|image) name\b|\bname (your|the) (file|document|image)\b)")


_MENU_PATH_RX = re.compile(r"(?:[\w&./+-]+(?:\s[\w&./+-]+){0,2}\s*>\s*)+[\w&./+-]+(?:\s[\w&./+-]+)?")


def is_file_step_text(raw: str) -> bool:
    """Does a guide step belong to a file dialog? A menu path ('Select File > Page setup') and the File MENU are not file choosing, whatever words they share with it."""
    t = _MENU_PATH_RX.sub(" ", (raw or "").replace("**", ""))
    if re.search(r"(?i)\b\w+\s+(menu|tab|ribbon|toolbar)\b|\bfrom the\b[^.]{0,24}\b(menu|ribbon|toolbar|tab)\b", t):          # 'from the File menu', 'on the Home tab': the application's own commands
        return False
    return bool(FILE_STEP_RX.search(t))


# ===================================================================================================================== the clipboard
CF_TEXT, CF_BITMAP, CF_DIB, CF_UNICODETEXT, CF_HDROP, CF_DIBV5, CF_OEMTEXT = 1, 2, 8, 13, 15, 17, 7
_SYNTHESIZED = {CF_BITMAP, 9, 14, 16, CF_TEXT, CF_OEMTEXT}                          # formats Windows derives from DIB / UNICODETEXT: restoring the source restores them
_RESTORABLE_NAMES = ("HTML Format", "Rich Text Format", "PNG")
_IGNORABLE_PREFIXES = ("chromium", "chrome", "application/x-", "cf_", "windows.clipboard", "microsoft office", "x-")        # the source-tracking tokens browsers and Office add: losing them changes nothing the person sees
_IGNORABLE_NAMES = ("CanIncludeInClipboardHistory", "CanUploadToCloudClipboard", "ExcludeClipboardContentFromMonitorProcessing", "ClipboardHistoryItemId", "Preferred DropEffect", "DataObject",
                    "OwnerLink", "ObjectLink", "Link Source", "Link Source Descriptor", "Embed Source", "Object Descriptor", "Shell IDList Array", "FileNameW", "FileName", "FileGroupDescriptorW",
                    "Ole Private Data", "application/x-moz-nativeimage", "Chromium Web Custom MIME Data Format", "Chromium internal source URL", "chromium/x-source-url", "Csv", "Biff12", "Biff8", "Biff5")


class ClipboardBusy(Exception):
    pass


class ClipboardGuard:
    """The clipboard is the person's. The guard saves it before the run's first clipboard write, restores it afterwards, and never overwrites something it cannot restore."""

    def __init__(self) -> None:
        self.saved: Optional[List[Tuple[Any, Any]]] = None
        self.unrestorable: List[str] = []
        self.sig_after: Optional[str] = None
        self.touched = False
        self.notes: List[str] = []

    # ---- low level
    @staticmethod
    def _open(retries: int = 15) -> Any:
        import win32clipboard as wc
        for _ in range(retries):
            try:
                wc.OpenClipboard()
                return wc
            except Exception:
                time.sleep(0.05)
        raise ClipboardBusy("the clipboard is held by another program")

    def _formats(self, wc: Any) -> List[int]:
        out, f = [], 0
        while True:
            f = wc.EnumClipboardFormats(f)
            if not f:
                break
            out.append(f)
        return out

    def signature(self) -> str:
        import hashlib
        wc = self._open()
        try:
            h = hashlib.sha1()
            for f in self._formats(wc):
                if f in _SYNTHESIZED:
                    continue
                try:
                    d = wc.GetClipboardData(f)
                    h.update(repr(f).encode() + (d if isinstance(d, (bytes, bytearray)) else repr(d).encode("utf-8", "replace")))
                except Exception:
                    h.update(repr(f).encode())
            return h.hexdigest()[:16]
        finally:
            wc.CloseClipboard()

    def begin(self) -> bool:
        """Save what the person has on the clipboard (once). False when it holds something that cannot be put back."""
        if self.saved is not None:
            return not self.unrestorable
        wc = self._open()
        try:
            saved: List[Tuple[Any, Any]] = []
            for f in self._formats(wc):
                if f in _SYNTHESIZED:
                    continue
                try:
                    name = wc.GetClipboardFormatName(f) if f >= 0xC000 else ""
                except Exception:
                    name = ""
                if f in (CF_UNICODETEXT, CF_DIB, CF_DIBV5, CF_HDROP) or name in _RESTORABLE_NAMES:
                    try:
                        saved.append((f, wc.GetClipboardData(f)))
                    except Exception:
                        self.unrestorable.append(name or str(f))
                elif name in _IGNORABLE_NAMES or name.lower().startswith(_IGNORABLE_PREFIXES):
                    continue
                else:
                    self.unrestorable.append(name or f"format {f}")
            self.saved = saved
        finally:
            wc.CloseClipboard()
        return not self.unrestorable

    def _set(self, items: Sequence[Tuple[Any, Any]]) -> None:
        wc = self._open()
        try:
            wc.EmptyClipboard()
            for f, d in items:
                if f == CF_HDROP and not isinstance(d, (bytes, bytearray)):
                    d = self._dropfiles(list(d))
                wc.SetClipboardData(f, d)
        finally:
            wc.CloseClipboard()

    @staticmethod
    def _dropfiles(paths: Sequence[str]) -> bytes:
        body = ("\0".join(paths) + "\0\0").encode("utf-16-le")
        return struct.pack("<IiiII", 20, 0, 0, 0, 1) + body

    # ---- what a step may do
    def touch(self) -> None:
        """A step has just written to the clipboard (the application's own Copy / Cut, or a fixture): remember what is there, so that at the end only OUR content is replaced."""
        try:
            self.sig_after = self.signature()
            self.touched = True
        except Exception:
            pass

    def put_text(self, text: str) -> None:
        if not self.begin():
            raise ClipboardBusy("the clipboard holds " + ", ".join(self.unrestorable[:3]) + ": it cannot be put back, so it is not overwritten")
        self._set([(CF_UNICODETEXT, text)])
        self.touch()

    def put_image(self, path: str) -> None:
        if not self.begin():
            raise ClipboardBusy("the clipboard holds " + ", ".join(self.unrestorable[:3]) + ": it cannot be put back, so it is not overwritten")
        from PIL import Image
        im = Image.open(path).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "BMP")
        self._set([(CF_DIB, buf.getvalue()[14:])])                             # a DIB is a BMP without its 14-byte file header
        self.touch()

    def put_files(self, paths: Sequence[str]) -> None:
        if not self.begin():
            raise ClipboardBusy("the clipboard holds " + ", ".join(self.unrestorable[:3]) + ": it cannot be put back, so it is not overwritten")
        self._set([(CF_HDROP, self._dropfiles([os.path.abspath(p) for p in paths]))])
        self.touch()

    def has_run_content(self) -> bool:
        """Does the clipboard still hold what a step of this run put there?"""
        try:
            return self.touched and self.signature() == self.sig_after
        except Exception:
            return False

    def end(self) -> str:
        """Give the person's clipboard back. If the person copied something meanwhile, it stays."""
        if self.saved is None or not self.touched:
            return "the clipboard was never touched"
        try:
            if self.signature() != self.sig_after:
                self.notes.append("the person copied something else during the run: left alone")
                return self.notes[-1]
            if self.unrestorable:
                return "not restored (it held " + ", ".join(self.unrestorable[:3]) + ")"
            if self.saved:
                self._set(self.saved)
            else:
                wc = self._open()
                try:
                    wc.EmptyClipboard()
                finally:
                    wc.CloseClipboard()
            self.notes.append("the person's clipboard was put back")
            return self.notes[-1]
        except Exception as exc:
            return f"restore failed: {type(exc).__name__}"
        finally:
            self.saved, self.touched, self.sig_after, self.unrestorable = None, False, None, []


COPY_RX = re.compile(r"(?i)^(copy|cut|copy as .*|copy to clipboard)\b|\bcopy\b.*\bclipboard\b|\bctrl\+(c|x|insert)\b")
PASTE_RX = re.compile(r"(?i)^(paste|paste special|paste as .*|paste from clipboard)\b|\bctrl\+v\b|\bshift\+insert\b")
IMAGE_CONTEXT_RX = re.compile(r"(?i)\b(image|picture|photo|canvas|drawing|shape|layer|sticker|graphic|icon|bitmap)\b")
