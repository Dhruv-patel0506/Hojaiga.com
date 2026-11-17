import ast, io

# ---- guide_card.procedures
P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_card.py"
s = io.open(P, "r", encoding="utf-8").read()
add = '''

_GENERIC_HEADS = {"related topics", "see also", "next steps", "more information", "feedback", "was this information helpful", "need more help", "contents", "overview", "in this article", "summary"}


def procedures(app_key: str, ix: Any = None, min_steps: int = 1, max_steps: int = 14) -> List[Dict[str, Any]]:
    """Every procedure the indexed guide describes, as runnable material: [{goal, cite, source, steps: [GuideStep]}] - the card's `action_sequences` but with the parsed GuideStep objects (what the
    executor grounds and performs). Duplicates (the same heading with the same steps, e.g. a page reached by two URLs) appear once."""
    own = ix is None
    ix = ix or MR.ManualIndex()
    try:
        rows = ix.db.execute("SELECT c.cite, c.text, d.source FROM chunks c JOIN docs d ON d.id=c.doc WHERE d.app=? ORDER BY d.id, c.ord", (app_key,)).fetchall()
    finally:
        if own:
            ix.close()
    chord_rx = re.compile(r"(?:\*\*[A-Za-z0-9]+\*\*\s*\+\s*)+\*\*[A-Za-z0-9]+\*\*")
    out: List[Dict[str, Any]] = []
    seen = set()
    for cite, raw_text, source in rows:
        goal = cite.split(" > ")[-1].strip()
        if goal.lower() in _GENERIC_HEADS:
            continue
        text = chord_rx.sub(lambda m: m.group(0).replace("**", ""), raw_text)
        steps = GS.parse_steps(text, cite)
        if not (min_steps <= len(steps) <= max_steps):
            continue
        sig = (goal.lower(), tuple((s.action, s.target.lower(), s.chord.lower()) for s in steps))
        if sig in seen:
            continue
        seen.add(sig)
        out.append({"goal": goal, "cite": cite, "source": source, "steps": steps})
    return out
'''
s = s.rstrip("\n") + "\n" + add
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)

# ---- Executor.plan_from_procedure
P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()
anchor = "    def plan(self, goal: str, max_steps: int = 8, use_skills: bool = True, use_guide: bool = True) -> ExecReport:"
new = '''    def plan_from_procedure(self, goal: str, cite: str, steps: Sequence[Any], max_steps: int = 12) -> ExecReport:
        """A plan from ONE named procedure of the guide (parsed GuideStep list), grounded against the CURRENT catalog - no retrieval, no model: 'run what the manual says'."""
        from .knowledge import guide_steps as GS
        g = GS.ground(list(steps), self.catalog)
        rep = ExecReport(goal=goal)
        rep.steps, rep.by, rep.cite = self.steps_from_guide({"steps": g, "cite": cite}, max_steps), "guide", cite
        rep.unknown = [x.note or x.step.raw for x in g if x.how == "none"]
        return rep

'''
assert anchor in s
s = s.replace(anchor, new + anchor, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
