p = r"D:\new_automation\All codes\core_organs\atlas\teach.py"
s = open(p, encoding="utf-8").read()
s = s.replace('NOISE_MEMBERS = {', 'LIGHT = {"add", "insert", "creat", "make", "new", "chang", "set", "use", "open", "show", "turn", "appl", "edit", "get", "go", "do", "have", "need", "start", "want"}\nNOISE_MEMBERS = {', 1)
old = '''        s = 0.0
        hit_name = 0
        for t in qt:
            wt = w.get(t, 1.0)'''
new = '''        s = 0.0
        hit_name = 0
        n_name = max(1, len(nm))
        content = [t for t in qt if t not in LIGHT]
        for t in qt:
            wt = w.get(t, 1.0) * (0.25 if t in LIGHT and content else 1.0)           # "add" / "insert" / "make" say little; the thing being added says everything'''
assert old in s
s = s.replace(old, new, 1)
old = '''            if t in nm:
                s += 3.0 * wt * idf
                hit_name += 1 if wt >= 1.0 else 0'''
new = '''            if t in nm:
                s += 3.0 * wt * idf * (0.6 + 0.4 / n_name * min(n_name, 1 + len([x for x in qt if x in nm])))        # a short name that IS the thing beats a long name that contains it
                hit_name += 1 if wt >= 1.0 else 0'''
assert old in s
s = s.replace(old, new, 1)
old = '''        if s <= 0:
            continue
        if e["kind"].startswith("field"):'''
new = '''        if s <= 0:
            continue
        if content and not any(t in nm or t in ids or t in extra or t in ctx for t in content):
            continue                                                                  # only a light verb matched: not an answer
        if e["kind"].startswith("field"):'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
