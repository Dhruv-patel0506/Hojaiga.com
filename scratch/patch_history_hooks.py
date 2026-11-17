import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


B = "D:/new_automation/All codes/core_organs/professor/"

patch(B + "probe.py", [
    ("""    def __init__(self, hwnd: int, effector: Effector, catalog: Optional[Catalog] = None, app_key: str = "", budget_s: float = 90.0, max_probes: int = 15, owned: bool = False):
        self.hwnd, self.fx, self.catalog, self.app_key = hwnd, effector, catalog, app_key""",
     """    def __init__(self, hwnd: int, effector: Effector, catalog: Optional[Catalog] = None, app_key: str = "", budget_s: float = 90.0, max_probes: int = 15, owned: bool = False,
                 history: Any = None):
        self.hwnd, self.fx, self.catalog, self.app_key = hwnd, effector, catalog, app_key
        self.history = history                                   # professor.history.History or None: every probe leaves a state-transition row"""),
    ("""        if d.new_windows:
            closed = self.fx.close_popups(s0.windows)
            return f"closed {closed} window(s)", self._settle(s1)""",
     """        if d.new_windows:
            closed = self.fx.close_popups(s0.windows)
            self._log_recovery(h.verb, "close", "Escape then WM_CLOSE", closed > 0)
            return f"closed {closed} window(s)", self._settle(s1)"""),
    ("""            self.graph.record(rule)
            rep.rules.append(rule)""", """            self.graph.record(rule)
            self._log_probe(h, rule, s0, s1)
            rep.rules.append(rule)"""),
    ("""    # ---- the loop
    def run(self""", """    # ---- the state-transition log
    def _log_probe(self, h: Hypothesis, rule: Rule, s0: Snapshot, s1: Snapshot, source: str = "probe") -> None:
        if self.history is None:
            return
        try:
            from .history import primitive_of
            self.history.log(self.app_key, source, primitive_of(rule.how), h.verb, rule.how, s0.sig, f"{len(s0.names)} controls, {len(s0.texts)} texts", s1.sig, rule.note, rule.effect,
                             rule.effect != "no_effect" and not rule.how.startswith("not delivered"), rule.restored, h.aid, {"unwind": rule.unwind, "restore_why": rule.restore_why, "benign": rule.benign})
        except Exception:
            pass

    def _log_recovery(self, trigger: str, primitive: str, route: str, ok: bool) -> None:
        if self.history is None:
            return
        try:
            self.history.log(self.app_key, "recovery", primitive, trigger, route, effect="dialog_closed" if ok else "dialog_stuck", ok=ok)
        except Exception:
            pass

    # ---- the loop
    def run(self"""),
])

patch(B + "executor.py", [
    ("""vision_check: Optional[Callable[[Step, Any, Any], Optional[bool]]] = None, skills: Any = None, guide_index: Any = None, archetype: str = "", app_version: str = ""):
        self.hwnd, self.fx, self.catalog, self.sm, self.brain, self.owned = hwnd, effector, catalog, sm, brain, owned
        self.vision_check = vision_check""", """vision_check: Optional[Callable[[Step, Any, Any], Optional[bool]]] = None, skills: Any = None, guide_index: Any = None, archetype: str = "", app_version: str = "",
                 history: Any = None):
        self.hwnd, self.fx, self.catalog, self.sm, self.brain, self.owned = hwnd, effector, catalog, sm, brain, owned
        self.vision_check = vision_check
        self.history = history                                   # professor.history.History or None: every route tried leaves a state-transition row"""),
    ("""                s1 = self._settle(s0, settle_s)
                d = delta(s0, s1)
                if d.effect() == "no_effect":
                    continue
                vis = self.vision_check""", """                s1 = self._settle(s0, settle_s)
                d = delta(s0, s1)
                self._log_attempt(st, v, r, how, s0, s1, d)
                if d.effect() == "no_effect":
                    continue
                vis = self.vision_check"""),
    ("""    # ---- learning
    def _learn(""", """    def _log_attempt(self, st: Step, v: Any, r: Route, how: str, s0: Any, s1: Any, d: Any) -> None:
        if self.history is None:
            return
        try:
            src = "skill" if st.source.startswith("skill") else ("guide" if st.source == "guide" else "exec")
            self.history.log(self.app_key, src, r.kind if r.kind in ("command", "key") else {"shortcut": "key", "control": "invoke", "value": "set_value", "click": "click"}.get(r.kind, "click"),
                             st.verb or "", r.label(), s0.sig, f"{len(s0.names)} controls", s1.sig, d.summary(), d.effect(), d.effect() != "no_effect", None, v.aid if v else "", {"how": how, "cite": st.cite})
        except Exception:
            pass

    # ---- learning
    def _learn("""),
])
print("history hooks patched")
