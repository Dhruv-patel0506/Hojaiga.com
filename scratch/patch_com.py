p = r"D:\new_automation\All codes\core_organs\atlas\comlib.py"
s = open(p, encoding="utf-8").read()
old = '''    return {"classes": cls[:80], "n_classes": len(cls), "typelibs": libs, "seconds": round(time.time() - t0, 2)}'''
new = '''    if not libs:                                    # the registry names no type library for the class (an Office click-to-run install keeps the main automation class
        for p in sibling_typelibs(exe):             # without one): the exe itself or an .olb/.tlb beside it holds it
            if time.time() - t0 > budget_s + 6:
                break
            r = enumerate_typelib(p, budget_s=max(2.0, budget_s - (time.time() - t0)))
            if r.get("ok") and r.get("types", 0) >= 40:
                libs[p] = r
                break
    return {"classes": cls[:80], "n_classes": len(cls), "typelibs": libs, "seconds": round(time.time() - t0, 2)}


def sibling_typelibs(exe: str) -> List[str]:
    """Candidate type libraries for a program: the exe (embedded resource), then *.olb / *.tlb beside it whose name shares letters with the exe's name (most similar first)."""
    out: List[str] = []
    if exe and os.path.isfile(exe):
        out.append(exe)
        d = os.path.dirname(exe)
        stem = re.sub(r"[^a-z]", "", os.path.splitext(os.path.basename(exe))[0].lower())
        try:
            files = [f for f in os.listdir(d) if f.lower().endswith((".olb", ".tlb"))]
        except OSError:
            files = []

        def sim(f: str) -> int:
            b = re.sub(r"[^a-z]", "", os.path.splitext(f)[0].lower())
            return len(set(b) & set(stem)) + (5 if b.startswith("ms") and b[2:4] == stem[:2] else 0) + (6 if b in stem or stem in b else 0)
        out += [os.path.join(d, f) for f in sorted(files, key=lambda f: -sim(f))[:6]]
    return out'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
