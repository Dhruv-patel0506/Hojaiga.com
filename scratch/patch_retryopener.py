import ast, io
P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''            tried: List[str] = []
            result: Optional[StepResult] = None
            self._last_trace = None'''
new = '''            if v is not None and routes and (self._is_opener(v) or "menu" in (v.leads_to or "")) and not rep.dry_run:
                routes = routes + [routes[0]]                                          # a flyout left open by the previous step swallows the first click (light dismiss): the first route gets a second chance
            tried: List[str] = []
            result: Optional[StepResult] = None
            self._last_trace = None'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
