p = r"D:\new_automation\All codes\core_organs\atlas\teach.py"
s = open(p, encoding="utf-8").read()
a = s.index("    scored: List[Tuple[float, Dict[str, Any]]] = []\n    for e, (nm, ids, ctx, extra) in zip(entries, cache):")
b = s.index("    scored.sort(key=lambda x: -x[0])\n    return scored")
new = '''    scored: List[Tuple[float, Dict[str, Any]]] = []
    content = [t for t in qt if t not in LIGHT]
    orig = {t for t in qt if w.get(t, 1.0) >= 1.0}
    for e, (nm, ids, ctx, extra) in zip(entries, cache):
        n_name = max(1, len(nm))
        exact = syn = 0.0                                   # evidence from the user's own words vs from synonyms (a synonym family can only add ONE hit's worth)
        m_name = set()
        best_syn = 0.0
        for t in qt:
            wt = w.get(t, 1.0) * (0.25 if t in LIGHT and content else 1.0)    # "add" / "insert" / "make" say little; the thing being added says everything
            idf = math.log(1 + N / (1 + df.get(t, 0)))
            if t in nm:
                v, m_name = 3.0 * wt * idf, m_name | {t}
            elif t in ids:
                v = 2.0 * wt * idf
            elif t in extra:
                v = 0.8 * wt * idf
            elif t in ctx:
                v = 0.5 * wt * idf
            else:
                continue
            if t in orig:
                exact += v
            else:
                best_syn = max(best_syn, v)
        s = exact + best_syn
        if s <= 0:
            continue
        hit = [t for t in content if t in nm or t in ids or t in extra or t in ctx]
        if content and not hit:
            continue                                                              # only a light verb matched: not an answer
        s *= 0.5 + 0.5 * len(m_name) / n_name                                     # a name that IS the thing beats a long name that merely contains it
        s *= 0.5 + 0.5 * len(hit) / max(1, len(content))                          # ... and every content word of the question should be accounted for
        if exact <= 0 and content:
            s *= 0.45                                                             # matched only through synonyms of the user's words
        if e["kind"].startswith("field"):
            s *= 0.55                                                             # a dialog field is rarely THE answer, but explains a route
        if e["surface_kind"] == "backstage":
            s *= 0.9
        s *= 1.0 / (1.0 + 0.12 * e["depth"])
        if not e["enabled"]:
            s *= 0.85
        scored.append((s, e))
'''
s = s[:a] + new + s[b:]
open(p, "w", encoding="utf-8").write(s)
print("ok")
