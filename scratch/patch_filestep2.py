import ast
import io

D = "D:/new_automation/All codes/core_organs/professor/dialogs.py"
s = io.open(D, "r", encoding="utf-8").read()
old = '''    t = _MENU_PATH_RX.sub(" ", (raw or "").replace("**", ""))
    return bool(FILE_STEP_RX.search(t))'''
new = '''    t = _MENU_PATH_RX.sub(" ", (raw or "").replace("**", ""))
    if re.search(r"(?i)\\b\\w+\\s+(menu|tab|ribbon|toolbar)\\b|\\bfrom the\\b[^.]{0,24}\\b(menu|ribbon|toolbar|tab)\\b", t):          # 'from the File menu', 'on the Home tab': the application's own commands
        return False
    return bool(FILE_STEP_RX.search(t))'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(D, "w", encoding="utf-8", newline="\n").write(s)

T = "D:/new_automation/All codes/core_organs/si_tests_apprun.py"
f = io.open(T, "r", encoding="utf-8").read()
old2 = '''    return _verdict(checks, f"statuses={ {g: w['status'] for g, w in ws.items()} } requires={ {g: w['requires'] for g, w in ws.items()} } found={[w['goal'] for w in found]}")'''
new2 = '''    return _verdict(checks, f"statuses={ {g: w['status'] for g, w in ws.items()} } requires={ {g: w['requires'] for g, w in ws.items()} } found={[w['goal'] for w in found]} task={task['goal']!r}/{len(task['steps'])}/{task['source']!r}")'''
assert old2 in f
f = f.replace(old2, new2, 1)
ast.parse(f)
io.open(T, "w", encoding="utf-8", newline="\n").write(f)
print("ok")
