import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/menus.py", [
    (r'''    return n.role in ("menuitem", "button", "splitbutton", "combobox", "tabitem") and (has_expand or n.role == "menuitem")''',
     r'''    return n.role in ("menuitem", "button", "splitbutton", "combobox", "tabitem", "radiobutton", "listitem", "checkbox", "treeitem") and (has_expand or n.role == "menuitem")'''),
    (r'''ITEM_ROLES = {"menuitem", "button", "listitem", "checkbox", "radiobutton", "hyperlink", "splitbutton", "combobox", "edit", "tabitem", "treeitem", "slider"}''',
     r'''ITEM_ROLES = {"menuitem", "button", "listitem", "checkbox", "radiobutton", "hyperlink", "splitbutton", "combobox", "edit", "tabitem", "treeitem", "slider", "spinner"}'''),
])
patch("D:/new_automation/All codes/core_organs/professor/harvest.py", [
    (r'''"hyperlink", "edit", "spinner", "slider"}
_RANGE_SUFFIX''', r'''"hyperlink", "edit", "slider"}
_RANGE_SUFFIX'''),
])
patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
    (r'''    if not st.path and st.action in ("press", "click", "select", "type") and fold(st.target) in PLAIN_KEYS and not st.text:''', r'''    if st.action == "drag" or (not st.path and fold(st.target) in GESTURE_TARGETS):
        return Grounded(st, None, 0.0, "gesture", f"'{st.raw[:60]}' needs a pointer gesture on the canvas (drag / draw): a toolkit that ignores posted pointer input cannot be driven headlessly")
    if not st.path and st.action in ("press", "click", "select", "type") and fold(st.target) in PLAIN_KEYS and not st.text:'''),
    (r'''_SKIP_TARGETS = {"it", "this",''', r'''GESTURE_TARGETS = {"canvas", "draw", "drawing area", "mouse", "pointer", "cursor", "image area", "drawing", "the canvas", "workspace"}
_SKIP_TARGETS = {"it", "this",'''),
])
patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''            elif g.how == "key":''', r'''            elif g.how == "gesture":
                s = Step(0, st.raw, None, "", [], "unknown", safety="unknown", need_human=True, note=g.note, source="guide", cite=gp["cite"], target=st.target)
            elif g.how == "key":'''),
])
print("ok")
