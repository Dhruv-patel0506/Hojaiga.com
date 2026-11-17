import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''            if self._sticky is not None and not (v is not None and v.path):
                self._hold_release()                                               # the flyout opened earlier is not what this step uses
            live0 = None
            if v is not None and not v.path and not rep.dry_run:
                try:
                    live0 = self._live_node(v)
                except Exception:
                    live0 = None
            if v is not None and not v.path and not rep.dry_run and (self._is_opener(v) or (live0 is not None and "expand" in (live0.pats or []))):
                self._hold_open()''', r'''            live0 = None
            if v is not None and not rep.dry_run:
                try:
                    live0 = self._live_node(v)
                except Exception:
                    live0 = None
            if v is not None and not rep.dry_run and (self._is_opener(v) or (live0 is not None and "expand" in (live0.pats or []))):
                self._hold_open()                                                  # opening a flyout: keep the foreground for THIS step and the NEXT one (the item inside it)
                self._sticky_left = 2''')
rep(r'''            if self._sticky is not None and v is not None and v.path:
                self._hold_release()                                               # the flyout item was used: foreground goes back to the user''', r'''            if self._sticky is not None:
                self._sticky_left -= 1
                if self._sticky_left <= 0 or result.status != "done":
                    self._hold_release()                                           # the flyout item was used (or the step failed): the foreground goes back to the user''')
rep(r'''        self._sticky = None                                          # a held foreground''', r'''        self._sticky_left = 0
        self._sticky = None                                          # a held foreground''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
