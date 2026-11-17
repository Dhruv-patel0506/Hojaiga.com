import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep('''                if misses >= give_up_after and not pages:
                    skipped.append((start_url, f"abandoned: the first {misses} pages never named the application"))
                    break''', '''                if misses >= give_up_after + 2 * len(pages):
                    skipped.append((start_url, f"abandoned: {misses} pages never named the application (a portal for many products?)"))
                    break''')
rep('''        if depth < max_depth and on_topic and ("html" in ct or ct == ""):''', '''        if depth < max_depth and (on_topic or depth == 0) and ("html" in ct or ct == ""):                 # a portal's own start page is always read for its links''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("portal give-up rule")
