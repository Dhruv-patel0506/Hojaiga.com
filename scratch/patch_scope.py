import ast
import io
import json

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep('''deadline: Optional[float] = None, sleep: Callable[[float], None] = time.sleep, keep: Optional[Callable[[Page], bool]] = None, give_up_after: int = 10) -> Tuple[List[Page], List[Tuple[str, str]]]:''',
    '''deadline: Optional[float] = None, sleep: Callable[[float], None] = time.sleep, keep: Optional[Callable[[Page], bool]] = None, give_up_after: int = 10,
          scope: str = "") -> Tuple[List[Page], List[Tuple[str, str]]]:''')
rep('''    prefix = u0.path if u0.path.endswith("/") else (u0.path.rsplit("/", 1)[0] + "/" if "/" in u0.path else "/")
    queue''', '''    prefix = u0.path if u0.path.endswith("/") else (u0.path.rsplit("/", 1)[0] + "/" if "/" in u0.path else "/")
    if scope and u0.path.startswith(scope):                                   # a portal keeps its articles beside, not under, the product's landing page (support.microsoft.com/office/...)
        prefix = scope
    queue''')
rep('''                ent.update({k: sd[k] for k in ("depth", "pages") if k in sd})''', '''                ent.update({k: sd[k] for k in ("depth", "pages", "scope") if k in sd})''')
rep('''max_depth=int(c.get("depth", max_depth)), delay_s=delay_s, allow_local=allow_local_net,
                                      deadline=deadline, keep=topic)''', '''max_depth=int(c.get("depth", max_depth)), delay_s=delay_s, allow_local=allow_local_net,
                                      deadline=deadline, keep=topic, scope=c.get("scope", ""))''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)

C = "D:/new_automation/All codes/core_organs/professor/data/app_catalog.json"
cat = json.load(io.open(C, "r", encoding="utf-8"))
for a in cat["apps"]:
    if a["key"] in ("winword", "powerpnt"):
        for sd in a["seeds"]:
            if isinstance(sd, dict) and sd.get("depth", 0) >= 1:
                sd["scope"] = "/en-us/"
io.open(C, "w", encoding="utf-8", newline="\n").write(json.dumps(cat, indent=2, ensure_ascii=False))
print("scope patched")
