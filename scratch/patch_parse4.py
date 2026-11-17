import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


# a bold term right after 'in the' / 'into the' names the FIELD, not the text to type
rep(r'''    if tm:
        typed = (tm.group(1) or tm.group(2) or "").strip()''', r'''    if tm:
        typed = (tm.group(1) or tm.group(2) or "").strip()
        if tm.group(2) and re.search(r"(?:\bin|\binto|\bto|\bon|\bfrom)\s+(?:the\s+)?$", raw[:tm.start(2)].rstrip("* ").rstrip() + " ", re.I):
            typed = ""''')

# 'enter X in the **Header** and **Footer** text boxes' -> one step per field
rep(r'''                st = parse_line(piece, len(out) + 1, cite)
                if st is not None:
                    out.append(st)''', r'''                st = parse_line(piece, len(out) + 1, cite)
                if st is not None:
                    fm = re.search(r"(?i)\b(?:in|into)\s+the\s+\**([^*,.;]+?)\**\s+and\s+\**([^*,.;]+?)\**\s+(?:text\s+)?(?:boxes|fields|areas|inputs)\b", piece)
                    if fm and st.action in ("type", "set"):
                        for fld in (fm.group(1), fm.group(2)):
                            cl = GuideStep(len(out) + 1, st.raw, st.action, _clean_term(fld), [], st.text, st.chord, st.cite)
                            out.append(cl)
                        continue
                    out.append(st)''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
