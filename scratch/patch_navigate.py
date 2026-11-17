import ast
import io

D = "D:/new_automation/All codes/core_organs/professor/dialogs.py"
s = io.open(D, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:100]
    s = s.replace(old, new, 1)


rep('''    def drive(self, info: DialogInfo, intent: str = "") -> Dict[str, Any]:''', '''    def _address_of(self, hwnd: int) -> str:
        for _h, _p, c, t, _i in _w32_children(hwnd, 200):
            if c == "ToolbarWindow32" and t.lower().startswith("address:"):
                return t[8:].strip()
        return ""

    def _navigate(self, info: DialogInfo, folder: str) -> bool:
        """A file dialog saves / opens relative to the folder it shows: like a person, type the FOLDER and confirm (the dialog goes there and stays open), and check its address bar says so."""
        ok, _how = self._set_name(info, folder)
        if not ok or not self._click(info, "open", "save", "select", "choose"):
            return False
        want = os.path.normcase(os.path.abspath(folder)).rstrip("\\\\")
        end = time.time() + 3.5
        while time.time() < end:
            time.sleep(0.25)
            addr = os.path.normcase(self._address_of(info.hwnd)).rstrip("\\\\")
            if addr and (addr == want or addr.endswith(os.path.basename(want))):
                return True
        return False

    def drive(self, info: DialogInfo, intent: str = "") -> Dict[str, Any]:''')
rep('''                res["path"] = path
                ok, how = self._set_name(info, path)
                res["steps"].append(f"file name field: {how}")''', '''                res["path"] = path
                typed = path
                if info.win32 and info.kind in ("file_open", "file_save"):
                    folder = os.path.dirname(path)
                    if self._navigate(info, folder):
                        typed = os.path.basename(path)                              # the dialog is in the sandbox folder now: only the file name is typed
                        res["steps"].append("navigated the dialog to the sandbox folder")
                    else:
                        res["steps"].append("could not confirm the dialog moved to the sandbox folder: the full path is typed instead")
                ok, how = self._set_name(info, typed)
                res["steps"].append(f"file name field: {how}")''')
ast.parse(s)
io.open(D, "w", encoding="utf-8", newline="\n").write(s)

p = "D:/new_automation/scratch/debug_savedlg2.py"
t = io.open(p, "r", encoding="utf-8").read()
i0 = t.index("        i = infos[0]")
i1 = t.index("        fx.close_popups(list(base))")
t = t[:i0] + '''        i = infos[0]
        res = drv.drive(i)
        print("drive:", res)
        time.sleep(3.0)
        for w in drv.windows():
            j = DG.inspect(w)
            print("STILL OPEN:", w, j.brief() if j else None, j.texts[:3] if j else "")
        print("outbox now:", os.listdir(sb.outbox), "inbox:", os.listdir(sb.inbox))
''' + t[i1:]
io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("ok")
