import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


# ---------------------------------------------------------------- probe.snapshot: extra state from an adapter
patch("D:/new_automation/All codes/core_organs/professor/probe.py", [
    (r'''def snapshot(hwnd: int, with_image: bool = True, nodes: Optional[list] = None, popups: bool = True) -> Snapshot:''', r'''def snapshot(hwnd: int, with_image: bool = True, nodes: Optional[list] = None, popups: bool = True, extra: Optional[Dict[str, str]] = None) -> Snapshot:'''),
    (r'''    names: Dict[str, str] = {}
    texts: Dict[str, str] = {}
    states: Dict[str, str] = {}
    cont: Dict[str, List[str]] = {}
    ordinals: Dict[str, int] = {}
    read_values = 0''', r'''    names: Dict[str, str] = {}
    texts: Dict[str, str] = dict(extra or {})                  # state a protocol adapter can see (tabs, current page) joins the tree's labels
    states: Dict[str, str] = {}
    cont: Dict[str, List[str]] = {}
    ordinals: Dict[str, int] = {}
    read_values = 0'''),
])

# ---------------------------------------------------------------- executor: the adapter route
patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''                 history: Any = None, learner: Any = None, toolkit: str = "", pointer: Any = None):''', r'''                 history: Any = None, learner: Any = None, toolkit: str = "", pointer: Any = None, adapter: Any = None):'''),
    (r'''        self.learner = learner                                   # professor.ml.Learner''', r'''        self.adapter = adapter                                   # professor.adapters.*: a protocol route (DevTools) for toolkits UI Automation cannot drive alone
        self.learner = learner                                   # professor.ml.Learner'''),
    # routes
    (r'''    def routes_for(self, v: Verb, text: str = "") -> List[Route]:
        out: List[Route] = []''', r'''    def _snap(self, **kw: Any) -> Any:
        from .probe import snapshot
        extra = None
        if self.adapter is not None:
            try:
                extra = self.adapter.state_texts()
            except Exception:
                extra = None
        return snapshot(self.hwnd, extra=extra, **kw)

    def routes_for(self, v: Verb, text: str = "") -> List[Route]:
        out: List[Route] = []
        if self.adapter is not None and self.adapter.owns(v):
            out.append(Route("adapter", f"{self.adapter.name}: {v.label}", 0, text))
            return out'''),
    (r'''        if r.kind == "expand":
            from . import menus as MN''', r'''        if r.kind == "adapter":
            if not self.fx.allowed:
                return False, "refused: " + self.fx.why_not()
            return self.adapter.act(v, str(r.arg or ""))
        if r.kind == "expand":
            from . import menus as MN'''),
])
print("ok")
