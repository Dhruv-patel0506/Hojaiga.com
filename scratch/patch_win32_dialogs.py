import ast
import io

R = "D:/new_automation/All codes/core_organs/professor/"


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:100]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch(R + "dialogs.py", [
    # ---- DialogInfo carries the win32 handles
    ('''    filter_exts: List[str] = field(default_factory=list)
    default_name: str = ""
''', '''    filter_exts: List[str] = field(default_factory=list)
    default_name: str = ""
    win32: bool = False                       # read through window messages, not UI Automation (a file dialog's tree is huge and slow)
    edit_hwnd: int = 0
    buttons_w32: Dict[str, int] = field(default_factory=dict)
'''),
    # ---- win32 reading, before inspect()
    ('''def inspect(hwnd: int) -> Optional[DialogInfo]:
    from core_organs import fast_uia, headless_input as hin
    nodes = fast_uia.snapshot(hwnd, timeout_ms=3000) or []''', '''WM_GETTEXT, WM_SETTEXT, BM_CLICK, SMTO_ABORTIFHUNG = 0x000D, 0x000C, 0x00F5, 0x0002
_HEAVY_CHILD_CLASSES = ("DUIViewWndClassName", "ComboBoxEx32", "SHELLDLL_DefView", "DirectUIHWND")
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
    edits = [k for k in kids if k[2] == "Edit" and inside(k[0], "ComboBoxEx32")] or [k for k in kids if k[2] == "Edit" and k[4] in (0x480, 0x47C)]
    if edits:
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
            break
    ok_label = fold(next((b for b in info.buttons if info.buttons_w32.get(fold(b)) == info.buttons_w32.get("__ok__")), ""))
    title = fold(info.title)
    if "folder" in ok_label or FOLDER_RX.search(info.title + " " + " ".join(info.texts)):
        info.kind = "folder"
    elif "save" in ok_label or re.search(r"\\b(save|export)\\b", title):
        info.kind = "file_save"
    else:
        info.kind = "file_open"
    return info


def inspect(hwnd: int) -> Optional[DialogInfo]:
    from core_organs import fast_uia, headless_input as hin
    if is_heavy_dialog(hwnd):
        return inspect_win32(hwnd)
    nodes = fast_uia.snapshot(hwnd, timeout_ms=3000) or []'''),
    # ---- acting on win32 dialogs
    ('''    def _click(self, info: DialogInfo, *names: str) -> str:
        want = [fold(n) for n in names]''', '''    def _click(self, info: DialogInfo, *names: str) -> str:
        want = [fold(n) for n in names]
        if info.win32:
            for wname in want + ["__ok__"] * (1 if any(w in ("open", "save", "select folder", "select", "choose", "upload", "import", "export", "insert", "attach", "ok") for w in want) else 0):
                h = info.buttons_w32.get(wname)
                if h and _u.PostMessageW(h, BM_CLICK, 0, 0):
                    return next((b for b in info.buttons if info.buttons_w32.get(fold(b)) == h), wname)
            if "cancel" in want and info.buttons_w32.get("__cancel__") and _u.PostMessageW(info.buttons_w32["__cancel__"], BM_CLICK, 0, 0):
                return "Cancel"
            return ""'''),
    ('''    def _set_name(self, info: DialogInfo, text: str) -> Tuple[bool, str]:
        n = info.file_edit
        if n is None:
            return False, "no file-name field found"''', '''    def _set_name(self, info: DialogInfo, text: str) -> Tuple[bool, str]:
        n = info.file_edit
        if n is None:
            return False, "no file-name field found"
        if info.win32:
            res = ctypes.c_size_t(0)
            ok = _u.SendMessageTimeoutW(info.edit_hwnd, WM_SETTEXT, 0, text, SMTO_ABORTIFHUNG, 1000, ctypes.byref(res))
            got = _w32_text(info.edit_hwnd)
            return bool(ok and os.path.basename(text).lower() in got.lower()), "WM_SETTEXT into the file-name field" + ("" if ok else " (refused)")'''),
])

# ---- keep file dialogs out of every UI Automation walk
patch(R + "probe.py", [
    ('''            for w in hin.popup_windows(hwnd)[:6]:
                g = fast_uia.snapshot(w, timeout_ms=2500) or []''', '''            from .dialogs import light_popups
            for w in light_popups(hwnd):                           # a file dialog's tree (folders, OneDrive) is huge: it is read through window messages by professor.dialogs, never walked here
                g = fast_uia.snapshot(w, timeout_ms=2500) or []'''),
])
patch(R + "executor.py", [
    ('''            for w in hin.popup_windows(self.hwnd)[:6]:
                nodes += fast_uia.snapshot(w, timeout_ms=3000) or []''', '''            from .dialogs import light_popups
            for w in light_popups(self.hwnd):
                nodes += fast_uia.snapshot(w, timeout_ms=3000) or []'''),
])
patch(R + "apprun.py", [
    ('''        nodes: List[Any] = []
        boxes = []
        for p in pops:''', '''        from .dialogs import is_heavy_dialog
        nodes: List[Any] = []
        boxes = []
        for p in [q for q in pops if not is_heavy_dialog(q)] or list(pops)[:1]:'''),
])
print("ok")
