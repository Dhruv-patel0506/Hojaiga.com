import ast, io
P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
L = io.open(P, "r", encoding="utf-8").read().split("\n")
for i, ln in enumerate(L):
    if ln.lstrip().startswith("return bool(_ADULT_RX.search(re.sub") and "_STORES" in ln:
        L[i] = '    return bool(_ADULT_RX.search(re.sub(r"[^a-z0-9]+", " ", host) + " " + (title or ""))) or any(a in host for a in _AGGREGATORS) or not_a_user_guide(url)'
        print("patched line", i + 1)
        break
else:
    raise SystemExit("not found")
s = "\n".join(L)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
