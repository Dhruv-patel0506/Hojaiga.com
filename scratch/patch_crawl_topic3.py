import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''                    topic = (lambda pg, w=words: relevant(pg, w)) if words else None'''
new = '''                    portal = urllib.parse.urlsplit(c["url"]).path in ("", "/")                      # a site ROOT cannot be scoped by path: there, only pages that name the application are kept
                    topic = (lambda pg, w=words: relevant(pg, w)) if (words and portal) else None'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("topic filter only for portal roots")
