import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''            if v is not None and not rep.dry_run and (self._is_opener(v) or (live0 is not None and "expand" in (live0.pats or []))):
                self._hold_open()''', r'''            if live0 is not None and not live0.enabled and not rep.dry_run:
                rep.results.append(StepResult(st.index, label, "disabled", summary=f"'{label}' is disabled in the application's current state: the guide assumes something done before it (a selection, an open document, a signed-in account)",
                                              ms=int((time.time() - t0) * 1000)))
                rep.stopped = f"step {st.index + 1} ('{label}'): disabled - a precondition the guide implies is not met"
                break
            if v is not None and not rep.dry_run and (self._is_opener(v) or (live0 is not None and "expand" in (live0.pats or []))):
                self._hold_open()'''),
    (r'''    status: str                     # done | no_effect | refused | needs_human | skipped | unknown | dry_run | failed''', r'''    status: str                     # done | no_effect | refused | needs_human | skipped | unknown | dry_run | failed | disabled'''),
])
patch("D:/new_automation/All codes/core_organs/professor/apprun.py", [
    (r'''        if st == "needs_human":
            return "blocked", last.summary''', r'''        if st == "needs_human":
            return "blocked", last.summary
        if st == "disabled":
            return "blocked", last.summary'''),
])
print("ok")
