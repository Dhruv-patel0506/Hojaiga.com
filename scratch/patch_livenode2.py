import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()
old = r'''        return next((n for n in nodes if v.aid and n.aid == v.aid and not n.offscreen), None) or next((n for n in nodes if fold(n.name) == fold(v.label) and not n.offscreen), None)
'''
new = r'''        ACTIVE = {"invoke", "toggle", "select", "expand", "value", "range", "scroll"}

        def best(cands):
            """A button and the text label inside it share a name: take the one that can be ACTED on (patterns), then the one whose control type matches the verb's role."""
            return min(cands, key=lambda n: (not (set(n.pats or []) & ACTIVE), n.role in ("text", "image", "pane", "group", "custom"), (n.role or "") not in (v.role or "", {"menu_item": "menuitem", "tab": "tabitem", "list_item": "listitem", "tree_item": "treeitem", "radio": "radiobutton", "field": "edit", "dropdown": "combobox"}.get(v.role, "")),
                                       n.idx)) if cands else None
        by_aid = [n for n in nodes if v.aid and n.aid == v.aid and not n.offscreen]
        if by_aid:
            return best(by_aid)
        return best([n for n in nodes if fold(n.name) == fold(v.label) and not n.offscreen])
'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
