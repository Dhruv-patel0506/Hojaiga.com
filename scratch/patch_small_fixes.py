import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, (path[-34:], old[:90])
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


B = "D:/new_automation/All codes/core_organs/professor/knowledge/"
patch(B + "guide_finder.py", [
    ("    if len(n.split()) == 1 and vend:\n        ctx = \" \" + vend[0]", "    if len(n.split()) == 1 and vend and vend[0].lower() not in n.lower():\n        ctx = \" \" + vend[0]"),
])
patch(B + "manual_rag.py", [
    ("    t = _html.unescape(\"\".join(p.parts))\n", "    t = _html.unescape(\"\".join(p.parts)).replace(\"\\u00b6\", \"\").replace(\"\\u2020\", \"\")                # pilcrow / dagger anchors that doc generators append to headings\n"),
])
print("small fixes applied")
