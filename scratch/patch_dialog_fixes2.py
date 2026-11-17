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
    ('_HEAVY_CHILD_CLASSES = ("DUIViewWndClassName", "ComboBoxEx32", "SHELLDLL_DefView", "DirectUIHWND")', '_HEAVY_CHILD_CLASSES = ("DUIViewWndClassName", "ComboBoxEx32", "SHELLDLL_DefView")          # the shell\'s file-browsing controls (a task dialog / message box has DirectUIHWND only)'),
    ('''    def look(self) -> List[DialogInfo]:
        infos = []
        for w in self.windows()[:5]:
            conceal(w)''', '''    def look(self, skip: Sequence[int] = ()) -> List[DialogInfo]:
        infos = []
        for w in [x for x in self.windows() if x not in skip][:5]:
            conceal(w)'''),
    ('''                if not btn:
                    self._press(info.hwnd, VK_RETURN)
                    res["steps"].append("pressed Enter")
                closed = self._closed(info.hwnd, 5.0)
                if not closed:
                    follow = self.settle(max_s=4.0, intent="accept")                     # 'file exists - replace?' and the like''', '''                if not btn:
                    self._press(info.hwnd, VK_RETURN)
                    res["steps"].append("pressed Enter")
                closed = self._closed(info.hwnd, 5.0)
                if not closed:
                    follow = self.settle(max_s=4.0, intent="accept", skip=(info.hwnd,))     # 'file exists - replace?' and the like (never the dialog being driven)'''),
    ('''                ok, how = self._set_name(info, path)
                res["steps"].append(f"file name field: {how}")
                btn = self._click(info, *[b for b in CONFIRM_FILE_BUTTONS])''', '''                ok, how = self._set_name(info, path)
                res["steps"].append(f"file name field: {how}")
                if not ok:                                                              # nothing was put into the field: confirming would act on whatever the dialog proposed (maybe the person's folder)
                    res["steps"].append("not confirmed: the file name could not be set")
                    self._press(info.hwnd, VK_ESCAPE)
                    res["ok"] = self._closed(info.hwnd, 3.0) and False
                    res["seconds"] = round(time.time() - t0, 1)
                    self.handled.append(res)
                    self._log(info, res)
                    return res
                btn = self._click(info, *[b for b in CONFIRM_FILE_BUTTONS])'''),
    ('''    def settle(self, max_s: float = 6.0, intent: str = "", kinds: Sequence[str] = ("file_open", "file_save", "folder", "print", "message")) -> List[Dict[str, Any]]:''',
     '''    def settle(self, max_s: float = 6.0, intent: str = "", kinds: Sequence[str] = ("file_open", "file_save", "folder", "print", "message"), skip: Sequence[int] = ()) -> List[Dict[str, Any]]:'''),
    ('''            infos = [i for i in self.look() if i.kind in kinds]''', '''            infos = [i for i in self.look(skip) if i.kind in kinds]'''),
])
patch(R + "executor.py", [
    ('''        t_start = time.time()
        rep.dry_run = dry_run or not self.fx.allowed
        rep.results = []
        rep.stopped = ""''', '''        t_start = time.time()
        rep.dry_run = dry_run or not self.fx.allowed
        rep.results = []
        rep.stopped = ""
        self._file_followups = 0                                                  # what a file dialog of an EARLIER plan satisfied does not carry over'''),
])
print("ok")
