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
    (r'''        rep.unknown = [x.note or x.step.raw for x in g if x.how == "none"]
        return rep''', r'''        rep.unknown = [x.note or x.step.raw for x in g if x.how not in GROUNDED_HOW]
        return rep'''),
    (r'''from .harvest import Catalog, Verb''', r'''from .harvest import Catalog, Verb
from .knowledge.guide_steps import GROUNDED_HOW'''),
    (r'''    def _is_opener(self, v: Optional[Verb]) -> bool:''', r'''    def placeholder_for(self, v: Verb) -> str:
        """What goes into a field when the manual says only 'enter a value': a number where the field is numeric (its range, when the application states one, or a size-like name), else a neutral string."""
        m = re.search(r"range (-?\d+)\.\.(-?\d+)", v.desc or "")
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            return str(min(max(100, lo), hi))
        if re.search(r"\b(width|height|size|number|count|percent|zoom|quantity|opacity|angle|degrees|pixels|amount|margin|spacing|radius|rows|columns|value)\b", fold(v.label)):
            return "100"
        return self.placeholder

    def _is_opener(self, v: Optional[Verb]) -> bool:'''),
    (r'''                    txt, placeholder = self.placeholder, True            # the manual says WHAT to enter only in general terms ('a descriptive name'): a neutral test string stands in, and the step says so''', r'''                    txt, placeholder = self.placeholder_for(g.verb), True            # the manual says WHAT to enter only in general terms ('a descriptive name'): a neutral test value stands in, and the step says so'''),
    (r'''                txt = self.placeholder                                    # the manual says only 'enter a name': a neutral placeholder stands in''', r'''                txt = self.placeholder_for(g.verb)                        # the manual says only 'enter a name': a neutral placeholder stands in'''),
    (r'''" - the manual gives no literal value: a neutral placeholder is entered" if txt == self.placeholder else "")''', r'''" - the manual gives no literal value: a neutral placeholder is entered" if txt == self.placeholder_for(g.verb) else "")'''),
])
patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
    (r'''"unknown": [x.note or x.step.raw for x in g if x.how == "none"], "passage_score"''', r'''"unknown": [x.note or x.step.raw for x in g if x.how not in GROUNDED_HOW], "passage_score"'''),
])
patch("D:/new_automation/All codes/core_organs/professor/apprun.py", [
    (r'''            if cover < 0.5 and g[0].how == "none":''', r'''            if cover < 0.5 and g[0].how not in GS.GROUNDED_HOW:'''),
])
patch("D:/new_automation/All codes/core_organs/professor/harvest.py", [
    (r'''        b.add(_RANGE_SUFFIX.sub("", n.name), path[-2:], source="uia", shortcut=chord or tchord or (chords_in(n.name) or [""])[0], desc=desc or n.help, enabled=n.enabled, checked=bool(n.selected) or n.toggle_state == 1,''', r'''        rng = re.search(r"Minimum\s*(-?\d+)\s+Maximum\s*(-?\d+)", n.name or "", re.I)
        b.add(_RANGE_SUFFIX.sub("", n.name), path[-2:], source="uia", shortcut=chord or tchord or (chords_in(n.name) or [""])[0], desc=(f"range {rng.group(1)}..{rng.group(2)}" if rng else (desc or n.help)), enabled=n.enabled, checked=bool(n.selected) or n.toggle_state == 1,'''),
])
print("ok")
