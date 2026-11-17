p = r"D:\new_automation\All codes\core_organs\atlas\comlib.py"
s = open(p, encoding="utf-8").read()
old = '''        for p in sibling_typelibs(exe):             # without one): the exe itself or an .olb/.tlb beside it holds it
            if time.time() - t0 > budget_s + 6:
                break
            r = enumerate_typelib(p, budget_s=max(2.0, budget_s - (time.time() - t0)))
            if r.get("ok") and r.get("types", 0) >= 40:
                libs[p] = r
                break'''
new = '''        best, best_n = None, 0
        for p in sibling_typelibs(exe):             # without one): the exe itself or an .olb/.tlb beside it holds it
            if time.time() - t0 > budget_s + 10:
                break
            r = enumerate_typelib(p, budget_s=max(2.0, budget_s - (time.time() - t0)))
            if not r.get("ok") or r.get("types", 0) < 40:
                continue
            if any(c.lower() == "application" for c in r.get("coclasses", [])):
                best = (p, r)                       # the library that defines the program's Application object IS its object model
                break
            if r.get("members", 0) > best_n:
                best, best_n = (p, r), r.get("members", 0)
        if best:
            libs[best[0]] = best[1]'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
