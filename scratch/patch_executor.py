import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new, count=1):
    global s
    assert old in s, old[:60]
    s = s.replace(old, new, count)


# Step gets a confidence
rep("""    expected: str = ""
    note: str = ""


@dataclass
class StepResult:""", """    expected: str = ""
    note: str = ""
    conf: float = 0.0               # how well the wording matches the verb's label (1.0 = exact); the model is only asked when this is low


@dataclass
class StepResult:""")

# scored resolve
rep('''    def resolve(self, text: str) -> Optional[Verb]:
        """The catalog verb a phrase means: exact label first, then the best word overlap. Enabled verbs win ties."""
        q = fold(text)
        exact = [v for v in self.catalog.verbs if fold(v.label) == q]
        pool = exact or self.catalog.best(text, 3)
        if not pool:
            return None
        pool.sort(key=lambda v: (not v.enabled, v.safety != "safe", len(v.path)))
        return pool[0]
''', '''    def resolve_scored(self, text: str) -> Tuple[Optional[Verb], float]:
        """(verb, confidence) for a phrase: exact label = 1.0, else the share of the (content) words that the label explains. Enabled, plainly safe, shallow verbs win ties."""
        q = fold(text)
        exact = [v for v in self.catalog.verbs if fold(v.label) == q]
        if exact:
            exact.sort(key=lambda v: (not v.enabled, v.safety != "safe", len(v.path)))
            return exact[0], 1.0
        qw = {w for w in q.split() if len(w) > 2}
        best: Optional[Verb] = None
        best_key: Tuple[float, ...] = (0.0,)
        for v in self.catalog.verbs:
            lw = {w for w in fold(v.label).split() if len(w) > 2}
            inter = qw & lw
            if not inter:
                continue
            sc = len(inter) / max(len(qw), len(lw))
            key = (round(sc, 3), 1.0 if v.enabled else 0.0, 1.0 if v.safety == "safe" else 0.0, -float(len(v.path)))
            if key > best_key:
                best, best_key = v, key
        return best, (best_key[0] if best is not None else 0.0)

    def resolve(self, text: str) -> Optional[Verb]:
        """The catalog verb a phrase means (see resolve_scored)."""
        return self.resolve_scored(text)[0]
''')

# ground: use scored resolve and record confidence
rep('''        v = self.resolve(verb_label or goal)
        if v is None:
            return Step(index, goal, None, "", [], "unknown", note="no verb in the catalog matches this step -- not invented", safety="unknown", need_human=True)''',
    '''        if verb_label is not None and fold(verb_label) in ("none", "(none)"):
            return Step(index, goal, None, "", [], "unknown", note="none of the application's commands does this (it may sit in a menu that was never opened) -- not invented", safety="unknown", need_human=True)
        v, conf = self.resolve_scored(verb_label or goal)
        if v is None:
            return Step(index, goal, None, "", [], "unknown", note="no verb in the catalog matches this step -- not invented", safety="unknown", need_human=True)''')
rep('''        return Step(index, goal, v.label, v.id, v.path, "verb", safety=cls, need_human=hum, routes=[r.label() for r in self.routes_for(v)], expected=exp)''',
    '''        return Step(index, goal, v.label, v.id, v.path, "verb", safety=cls, need_human=hum, routes=[r.label() for r in self.routes_for(v)], expected=exp, conf=conf)''')

# plan: rules first; the model only arbitrates when a clause is not confidently grounded; "(none)" is an allowed answer
rep('''        rep = ExecReport(goal=goal)
        clauses = [c for c in SPLIT_RX.split(goal) if c.strip()]
        steps: List[Step] = []
        if self.brain is not None and not TYPE_RX.match(goal.strip()):''', '''        rep = ExecReport(goal=goal)
        clauses = [c for c in SPLIT_RX.split(goal) if c.strip()]
        steps: List[Step] = []
        rule_steps = [self._ground(c, None, i) for i, c in enumerate(clauses[:max_steps])]
        sure = bool(rule_steps) and all(st.kind == "text" or (st.kind == "verb" and st.conf >= 0.66) for st in rule_steps)
        if self.brain is not None and not sure and not TYPE_RX.match(goal.strip()):''')
rep('''                        schema = {"type": "object", "properties": {"steps": {"type": "array", "maxItems": max_steps, "items": {"type": "object", "properties": {
                            "verb": {"type": "string", "enum": cands}, "why": {"type": "string"}}, "required": ["verb", "why"]}}}, "required": ["steps"]}
                        r = self.brain.generate("You plan GUI work as a short ordered list of the application's OWN commands. Use ONLY the verbs offered. Fewest steps. One sentence 'why' each.",''',
    '''                        schema = {"type": "object", "properties": {"steps": {"type": "array", "maxItems": max_steps, "items": {"type": "object", "properties": {
                            "verb": {"type": "string", "enum": cands + ["(none)"]}, "why": {"type": "string"}}, "required": ["verb", "why"]}}}, "required": ["steps"]}
                        r = self.brain.generate("You plan GUI work as a short ordered list of the application's OWN commands. Use ONLY the verbs offered, and ONLY steps the goal needs - never pad. "
                                                "If a step needs a command that is not offered, answer \\"(none)\\" for it. Fewest steps. One sentence 'why' each.",''')
rep('''        if not steps:
            for i, c in enumerate(clauses[:max_steps]):
                steps.append(self._ground(c, None, i))
        rep.steps = steps''', '''        if not steps:
            steps = rule_steps
        rep.steps = steps''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("executor patched")
