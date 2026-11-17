import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, (path[-34:], old[:90])
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


B = "D:/new_automation/All codes/core_organs/professor/ml/"
patch(B + "candidates.py", [
    ("        self.updates = 0\n        self.preq_p: List[float] = []", "        self.updates = 0\n        self.sources: set = set()                              # which applications / layouts it has learnt from (generalisation needs diversity)\n        self.preq_p: List[float] = []"),
    ("    def observe_scan(self, cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray], truth: Sequence[Any], train: bool = True, epochs: int = 2) -> Dict[str, Any]:",
     "    def observe_scan(self, cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray], truth: Sequence[Any], train: bool = True, epochs: int = 2, source: str = \"\") -> Dict[str, Any]:"),
    ("        feats = features_for(cands, size, ink)\n        y = match_labels(cands, truth)\n        if self.seen >= 40:", "        feats = features_for(cands, size, ink)\n        y = match_labels(cands, truth)\n        if source:\n            self.sources.add(source)\n        if self.seen >= 40:"),
    ('''        return {"seen": self.seen, "positives": self.pos, "updates": self.updates, "prequential_auc": None if math.isnan(auc) else round(auc, 4), "parameters": self.net.n_params()}''',
     '''        return {"seen": self.seen, "positives": self.pos, "updates": self.updates, "prequential_auc": None if math.isnan(auc) else round(auc, 4), "parameters": self.net.n_params(),
                "sources": len(self.sources), "ready_to_filter": self.ready()}

    def ready(self) -> bool:
        """May the model act on a window that has NO tree? Only after it has learnt from enough different applications AND predicted new scans well BEFORE learning from them
        (measured: trained on one layout it is at chance on a very different one, so an under-travelled model must not drop anything)."""
        auc = roc_auc(self.preq_p, self.preq_y) if len(self.preq_y) > 100 else float("nan")
        return self.seen >= 400 and len(self.sources) >= 4 and not math.isnan(auc) and auc >= 0.85'''),
    ('''        if self.seen < 400 or not cands:
            return list(cands), 0''', '''        if not cands or not self.ready():
            return list(cands), 0'''),
    ('''            json.dump({"seen": self.seen, "pos": self.pos, "updates": self.updates}, fh)''', '''            json.dump({"seen": self.seen, "pos": self.pos, "updates": self.updates, "sources": sorted(self.sources), "preq_p": self.preq_p[-2000:], "preq_y": self.preq_y[-2000:]}, fh)'''),
    ('''                self.seen, self.pos, self.updates = int(m.get("seen", 0)), int(m.get("pos", 0)), int(m.get("updates", 0))''', '''                self.seen, self.pos, self.updates = int(m.get("seen", 0)), int(m.get("pos", 0)), int(m.get("updates", 0))
                self.sources = set(m.get("sources", []))
                self.preq_p, self.preq_y = list(m.get("preq_p", [])), list(m.get("preq_y", []))'''),
])
patch(B + "learner.py", [
    ("    def observe_scan(self, cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray], truth: Sequence[Any]) -> Dict[str, Any]:",
     "    def observe_scan(self, cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray], truth: Sequence[Any], source: str = \"\") -> Dict[str, Any]:"),
    ("            return self.candidates.observe_scan(cands, size, ink, truth)", "            return self.candidates.observe_scan(cands, size, ink, truth, source=source)"),
])
patch("D:/new_automation/All codes/core_organs/professor/sweeper.py", [
    ("info_ml = lrn.observe_scan(cs.candidates, img.size, ink_ml, [e.bbox for e in uia_els if e.label])", "info_ml = lrn.observe_scan(cs.candidates, img.size, ink_ml, [e.bbox for e in uia_els if e.label], source=sm.app_key or sm.process)"),
])
print("candidate-model gate patched")
