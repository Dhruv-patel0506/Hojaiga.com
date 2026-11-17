import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/reveal.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:70]
    s = s.replace(old, new, 1)


rep(r'''|\b(choose|select|pick) (a |an )?(file|folder|picture|image)\b|\bfrom (file|computer|device|disk)\b")''',
    r'''|\b(choose|select|pick|insert|add|attach|upload) (a |an |the )?(file|folder|pictures?|images?|photos?|videos?|audio|documents?)\b|\bfrom (file|computer|device|disk)\b")''')
rep('''        return False, "lists the person's own files / history - not opened", looks''', '''        return False, "lists the person's own files / history - not opened", True''')
rep('''        return False, "leaves the application (web, account, update, help) - not opened", looks''', '''        return False, "leaves the application (web, account, update, help) - not opened", True''')
rep('''        return False, "a help link usually opens a browser - not opened", looks''', '''        return False, "a help link usually opens a browser - not opened", True''')
rep('''        return False, "opens a file picker / saves / prints: it would touch the person's files - not opened", looks''', '''        return False, "opens a file picker / saves / prints: it would touch the person's files - not opened", True''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)

t = io.open("D:/new_automation/scratch/pr59_60.txt", "r", encoding="utf-8").read()
t = t.replace('        view = NS(name="View", ident=None)\n', '')
t = t.replace("    real_expand, real_collapse = MN._expand, MN.collapse\n", "    real_expand, real_collapse, real_await = MN._expand, MN.collapse, MN._await_items\n")
t = t.replace("        MN._expand, MN.collapse = real_expand, real_collapse\n", "        MN._expand, MN.collapse, MN._await_items = real_expand, real_collapse, real_await\n")
t = t.replace('''[c.label for c in cands] == ["Page setup", "Insert picture..."] and any(s["path"].endswith("Open") for s in skipped)''',
              '''[c.label for c in cands] == ["Page setup"] and any(s["path"].endswith("Open") for s in skipped) and any("Insert picture" in s["path"] for s in skipped)''')
T = "D:/new_automation/All codes/core_organs/si_tests_apprun.py"
f = io.open(T, "r", encoding="utf-8").read()
assert "run_pr59" not in f
f = f.replace('\nTESTS = [("PR49"', "\n" + t + '\nTESTS = [("PR49"', 1)
f = f.replace('("PR58", run_pr58)]', '("PR58", run_pr58), ("PR59", run_pr59), ("PR60", run_pr60)]', 1)
ast.parse(f)
io.open(T, "w", encoding="utf-8", newline="\n").write(f)
print("ok")
