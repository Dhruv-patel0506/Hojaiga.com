import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/probe.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''    ordinals: Dict[str, int] = {}
    for n in nodes:
        if n.offscreen or not n.name or n.rect[2] <= n.rect[0]:
            continue
        k = _key(n, ordinals)'''
new = '''    ordinals: Dict[str, int] = {}
    frame_ids: Set[int] = set()                                   # the window's OWN frame (title bar, caption buttons, system menu) says where the window is, not what the application is doing
    for n in nodes:
        if n.ctype == "TitleBarControl" or (n.parent in frame_ids):
            frame_ids.add(n.idx)
            continue
        if n.offscreen or not n.name or n.rect[2] <= n.rect[0]:
            continue
        if n.role in ("button", "menuitem") and fold(n.name) in safety.CHROME and n.parent >= 0 and nodes[n.parent].ctype in ("WindowControl", "TitleBarControl"):
            continue
        k = _key(n, ordinals)'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("window frame excluded from snapshots")
