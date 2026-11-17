import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''    cite: str = ""

    def phrase(self) -> str:''', r'''    cite: str = ""
    alts: List[str] = field(default_factory=list)   # 'Choose Pixels, Inches, or Centimeters': the other options a person may take instead (any one satisfies the step)

    def phrase(self) -> str:''')
rep(r'''        if terms:
            target = terms[0] if act in ("type",) else terms[-1] if len(terms) > 1 and act not in ("type",) else terms[0]''', r'''        if terms:
            target = terms[0] if act in ("type",) else terms[-1] if len(terms) > 1 and act not in ("type",) else terms[0]
            if act in ("select", "click", "set") and len(terms) >= 2 and re.search(r"\b(?:or|either)\b", txt) and not re.search(r"\band\b\s+(?:then\s+)?(?:click|select|choose)", txt):
                target, alts_found = terms[0], terms[1:]''')
rep(r'''    target = ""
    if path:
        target = path[-1]
    else:''', r'''    target = ""
    alts_found: List[str] = []
    if path:
        target = path[-1]
    else:''')
rep(r'''    return GuideStep(n, raw.strip(), act, target, path, typed, chord, cite)''', r'''    return GuideStep(n, raw.strip(), act, target, path, typed, chord, cite, [_clean_term(a) for a in alts_found if _clean_term(a)])''')
rep(r'''    if st.target:
        v, c = resolve_label(catalog, st.target)
        if v is not None and c >= 0.66:
            return Grounded(st, v, c, "label")''', r'''    if st.target:
        v, c = resolve_label(catalog, st.target)
        if v is not None and c >= 0.66:
            return Grounded(st, v, c, "label")
        for alt in st.alts:                                                   # 'Pixels, Inches, or Centimeters': the first option that exists will do
            v2, c2 = resolve_label(catalog, alt)
            if v2 is not None and c2 >= 0.66:
                return Grounded(st, v2, c2, "label", f"the manual offers alternatives; '{alt}' exists here")''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
