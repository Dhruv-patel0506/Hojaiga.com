p = r"D:\new_automation\All codes\core_organs\hojaiga_run.py"
s = open(p, encoding="utf-8").read()
a = s.index("    parts = re.split(")
b = s.index("    out = [p.strip(")
new = '    parts = re.split(r"\\s*(?:;|\\n|\\bthen\\b|\\band then\\b|\\bafter that\\b|\\bnext\\b,?|\\bfinally\\b,?|\\balso\\b,?)\\s*", text or "", flags=re.I)\n'
s = s[:a] + new + s[b:]
open(p, "w", encoding="utf-8").write(s)
import ast
ast.parse(s)
print("fixed; control chars left:", sum(1 for c in s if c in "\x08"))
