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
    # the navigate-by-typing attempt is replaced by a VERIFICATION of where the dialog is
    ('''                typed = path
                if info.win32 and info.kind in ("file_open", "file_save"):
                    folder = os.path.dirname(path)
                    if self._navigate(info, folder):
                        typed = os.path.basename(path)                              # the dialog is in the sandbox folder now: only the file name is typed
                        res["steps"].append("navigated the dialog to the sandbox folder")
                    else:
                        res["steps"].append("could not confirm the dialog moved to the sandbox folder: the full path is typed instead")
                ok, how = self._set_name(info, typed)''', '''                typed = path
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
                ok, how = self._set_name(info, typed)'''),
    ('''        self.last_file_dialog_at = 0.0
        self.watch: Optional[DialogWatch] = None''', '''        self.last_file_dialog_at = 0.0
        self.needs_prime = False                                                    # a Save dialog was cancelled because it showed a folder outside the sandbox
        self.watch: Optional[DialogWatch] = None'''),
])
patch(R + "executor.py", [
    ('''            handled = self.dialogs.settle(max_s=10.0, intent="accept")
            if handled:
                self._file_followups = 3
                self.dialog_log += handled
                ok = all(h.get("ok") for h in handled)''', '''            handled = self.dialogs.settle(max_s=10.0, intent="accept")
            if handled:
                self._file_followups = 3
                self.dialog_log += handled
                ok = all(h.get("ok") for h in handled)
                if any(h.get("needs_prime") for h in handled):
                    return StepResult(st.index, label, "no_effect", route="dialog-driver", effect="dialog_outside_sandbox",
                                      summary="the save dialog showed a folder outside the sandbox and was cancelled: " + "; ".join(h["steps"][-1] for h in handled if h.get("needs_prime"))[:240], ms=int((time.time() - t0) * 1000))'''),
    ('''    def _auto_dialogs(self, rep: ExecReport) -> None:''', '''    def prime_dialog_folder(self) -> str:
        """Make the sandbox the folder file dialogs open in: complete one 'Open' of a sandbox fixture through the application's own Open command (Windows reopens a dialog where the last one was
        completed). Returns what was done, '' when the application has no Open command."""
        v = None
        for x in self.catalog.verbs:
            if fold(x.label) == "open" and x.enabled and x.safety in ("safe", "commit"):
                if v is None or (x.shortcut and not v.shortcut):
                    v = x
        if v is None:
            return ""
        step = self._step_for_verb(v, "open a sandbox file so file dialogs start in the sandbox", 1.0, "internal")
        rep = ExecReport(goal="prime file dialogs", steps=[step])
        step.index = 0
        self.run(rep, dry_run=False, approve=None, settle_s=2.5, learn=False)
        if self.dialogs is not None:
            self.dialogs.needs_prime = False
        return f"opened a sandbox fixture through '{v.label}' so file dialogs start in the sandbox ({'ok' if rep.ok else rep.stopped or 'no effect'})"

    def _auto_dialogs(self, rep: ExecReport) -> None:'''),
])
patch(R + "apprun.py", [
    ('''        self.settle_s = min(6.0, self.settle_s + 1.0) if status == "no_effect" else self.settle_s
        return "; ".join(done)''', '''        self.settle_s = min(6.0, self.settle_s + 1.0) if status == "no_effect" else self.settle_s
        if self.dialogs is not None and self.dialogs.needs_prime:                  # a Save dialog was cancelled because it showed a folder outside the sandbox
            try:
                note = self.ex.prime_dialog_folder()
                if note:
                    done.append(note)
            except Exception as exc:
                done.append(f"priming the file dialogs failed ({type(exc).__name__})")
        return "; ".join(done)'''),
])
print("ok")
