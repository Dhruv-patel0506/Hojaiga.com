import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/probe.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep('''def _key(n: Any, ox: int, oy: int) -> str:
    cell = f"{(n.rect[0] - ox) // 24},{(n.rect[1] - oy) // 24}"
    role = n.role
    if n.aid:
        return f"aid:{n.aid}"
    if role in TEXTY:
        return f"{role}|@{cell}"
    return f"{role}|{fold(n.name)}|@{cell}"
''', '''def _key(n: Any, seen: Dict[str, int]) -> str:
    """A control's IDENTITY across snapshots: its automation id, else role + name + which one of that name it is (the n-th). Geometry is NOT part of it: a toolbar that shifts by a pixel
    when the window is (de)activated or re-laid-out must not look like 'the controls changed' (measured: it made a perfectly restored application look un-restored)."""
    role = n.role
    if n.aid:
        return f"aid:{n.aid}"
    base = f"{role}|#" if role in TEXTY else f"{role}|{fold(n.name)}|#"
    seen[base] = seen.get(base, 0) + 1
    return f"{base}{seen[base]}"
''')
rep('''    for n in nodes:
        if n.offscreen or not n.name or n.rect[2] <= n.rect[0]:
            continue
        k = _key(n, ox, oy)''', '''    ordinals: Dict[str, int] = {}
    for n in nodes:
        if n.offscreen or not n.name or n.rect[2] <= n.rect[0]:
            continue
        k = _key(n, ordinals)''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("snapshot keys are identities now")

S = "D:/new_automation/All codes/core_organs/si_tests_professor.py"
t = io.open(S, "r", encoding="utf-8").read()
old = '''        while ov.cursor is not None and ov.cursor.flying() and time.time() - t0 < planned + 3.0:
            time.sleep(0.05)
        took = time.time() - t0'''
new = '''        ov.wait_idle(planned + 3.0)                                  # the glide command is queued; the overlay reports idle once the pointer has arrived
        took = time.time() - t0'''
assert old in t
t = t.replace(old, new, 1)
ast.parse(t)
io.open(S, "w", encoding="utf-8", newline="\n").write(t)
print("PL13 waits for the glide")
