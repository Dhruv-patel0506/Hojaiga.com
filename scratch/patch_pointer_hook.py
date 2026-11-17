import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, (path[-34:], old[:90])
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


B = "D:/new_automation/All codes/core_organs/professor/"
patch(B + "virtual_mouse.py", [
    ('''        if self.history is not None:
            try:
                self.history.log_pointer(self.app_key, trace["x0"], trace["y0"], trace["x1"], trace["y1"], trace["planned_s"], trace["actual_s"], 2, self.visible, transition_id)
            except Exception:
                pass''', '''        if self.history is not None:
            try:
                trace["pointer_id"] = self.history.log_pointer(self.app_key, trace["x0"], trace["y0"], trace["x1"], trace["y1"], trace["planned_s"], trace["actual_s"], 2, self.visible, transition_id)
            except Exception:
                pass'''),
])
patch(B + "history.py", [
    ('''    # ---------------------------------------------------------------------------------------------------------- queries''', '''    def link_pointer(self, pointer_id: int, transition_id: int) -> None:
        """Attach a virtual-mouse trace to the action it was made for."""
        with self._lock:
            self.db.execute("UPDATE pointer_traces SET transition_id=? WHERE id=?", (transition_id, pointer_id))
            self.db.commit()

    # ---------------------------------------------------------------------------------------------------------- queries'''),
])
patch(B + "executor.py", [
    ('''                 history: Any = None, learner: Any = None, toolkit: str = ""):''', '''                 history: Any = None, learner: Any = None, toolkit: str = "", pointer: Any = None):'''),
    ('''        self.toolkit = toolkit                                   # the application's toolkit family (professor.interaction): a feature of every logged action''', '''        self.toolkit = toolkit                                   # the application's toolkit family (professor.interaction): a feature of every logged action
        self.pointer = pointer                                   # professor.virtual_mouse.VirtualMouse: glides to each control before the action is delivered (overlay + database trace)
        self._last_trace: Optional[Dict[str, Any]] = None'''),
    ('''            tried: List[str] = []
            result: Optional[StepResult] = None
            for r in routes:
                s0 = snapshot(self.hwnd)''', '''            tried: List[str] = []
            result: Optional[StepResult] = None
            self._last_trace = None
            if self.pointer is not None and v is not None:                                       # the virtual mouse goes to the control first (it never moves the real one)
                try:
                    node = self._live_node(v)
                    if node is not None and node.rect[2] > node.rect[0]:
                        from .schema import Box
                        self._last_trace = self.pointer.move_to(Box(*node.rect), v.label, "click", v.shortcut, st.index + 1)
                except Exception:
                    self._last_trace = None
            for r in routes:
                s0 = snapshot(self.hwnd)'''),
    ('''            self.history.log(self.app_key, src, r.kind if r.kind in ("command", "key") else {"shortcut": "key", "control": "invoke", "value": "set_value", "click": "click"}.get(r.kind, "click"),''', '''            tid = self.history.log(self.app_key, src, r.kind if r.kind in ("command", "key") else {"shortcut": "key", "control": "invoke", "value": "set_value", "click": "click"}.get(r.kind, "click"),'''),
    ('''                             {"how": how, "cite": st.cite, "shortcut": bool(v and v.shortcut)}, toolkit=self.toolkit, archetype=self.archetype, role=role, safety=st.safety)''', '''                             {"how": how, "cite": st.cite, "shortcut": bool(v and v.shortcut)}, toolkit=self.toolkit, archetype=self.archetype, role=role, safety=st.safety)
            if self._last_trace and self._last_trace.get("pointer_id"):
                self.history.link_pointer(self._last_trace["pointer_id"], tid)'''),
])
print("pointer hooks patched")
