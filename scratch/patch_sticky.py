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
    # state
    (r'''        self.placeholder = "Hojaiga test" ''', r'''        self._sticky = None                                          # a held foreground while a flyout menu opened by an earlier step is still to be used by the next one
        self.placeholder = "Hojaiga test" '''),
    # helpers
    (r'''    def _open_path(self, v: Verb) -> bool:''', r'''    def _is_opener(self, v: Optional[Verb]) -> bool:
        """A verb whose activation opens a flyout (menu bar item, drop-down, split button): the foreground must stay with the application until the next step has used the flyout."""
        return bool(v is not None and (v.role in ("menu_item", "dropdown") or "menu" in (v.leads_to or "") or "submenu" in (v.leads_to or "")) and not v.command_id)

    def _hold_open(self) -> None:
        if self._sticky is None and self.fx.allowed:
            import contextlib
            self._sticky = contextlib.ExitStack()
            self._sticky.enter_context(self.fx.holding())

    def _hold_release(self) -> None:
        if self._sticky is not None:
            st, self._sticky = self._sticky, None
            try:
                st.close()
            except Exception:
                pass

    def _open_path(self, v: Verb) -> bool:'''),
    # in the run loop: release the previous sticky hold before a step that is not inside the flyout; take one after an opener step
    (r'''            routes = self.routes_for(v, st.text) if v else []
            if st.prefer:''', r'''            if self._sticky is not None and not (v is not None and v.path):
                self._hold_release()                                               # the flyout opened earlier is not what this step uses
            if v is not None and self._is_opener(v) and not v.path and not rep.dry_run:
                self._hold_open()                                                  # opening a menu: keep the foreground until the next step used it (a flyout closes when its window loses activation)
            routes = self.routes_for(v, st.text) if v else []
            if st.prefer:'''),
    (r'''    def _run(self, rep: ExecReport, dry_run: bool, approve: Optional[Callable[[Step], bool]], settle_s: float) -> ExecReport:
        from .probe import snapshot, delta''', r'''    def _run(self, rep: ExecReport, dry_run: bool, approve: Optional[Callable[[Step], bool]], settle_s: float) -> ExecReport:
        try:
            return self._run_inner(rep, dry_run, approve, settle_s)
        finally:
            self._hold_release()

    def _run_inner(self, rep: ExecReport, dry_run: bool, approve: Optional[Callable[[Step], bool]], settle_s: float) -> ExecReport:
        from .probe import snapshot, delta'''),
    # an item inside a flyout that was opened by a held step: after delivering it, release
    (r'''            result.ms = int((time.time() - t0) * 1000)
            rep.results.append(result)
            if result.status != "done":''', r'''            result.ms = int((time.time() - t0) * 1000)
            rep.results.append(result)
            if self._sticky is not None and v is not None and v.path:
                self._hold_release()                                               # the flyout item was used: foreground goes back to the user
            if result.status != "done":'''),
])
print("ok")
