p = r"D:\new_automation\All codes\core_organs\web_executor.py"
s = open(p, encoding="utf-8").read()
a = "    if exact_click and now[\"text\"] != home.get(\"text\", now[\"text\"]):"
assert a in s
new = '''    before = set((home.get("text") or "").splitlines())
    added = [l for l in body.splitlines() if l.strip() and l not in before]
    shown_new = [l for l in added if words and all(w in l for w in words)]
    if shown_new:                                                                                      # text that was NOT on the page before now names the goal
        return True, f"new text on the page names the goal: '{shown_new[0][:70]}'", False
'''
s = s.replace(a, new + a, 1)
open(p, "w", encoding="utf-8").write(s)
import ast; ast.parse(s); print("ok")
