import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


R = "D:/new_automation/All codes/core_organs/professor/"
patch(R + "knowledge/guide_steps.py", [
    # fields
    (r'''    alts: List[str] = field(default_factory=list)   # 'Choose Pixels, Inches, or Centimeters': the other options a person may take instead (any one satisfies the step)
''', r'''    alts: List[str] = field(default_factory=list)   # 'Choose Pixels, Inches, or Centimeters': the other options a person may take instead (any one satisfies the step)
    group: str = ""                       # 'Choose a color from the color palette': the group the manual points into (any item of it satisfies the step)
    optional: bool = False                # 'if needed' / 'optionally': a step a person may skip
'''),
    # parse: an action with no named control, but a described group / optionality
    (r'''    if not (target or path or chord or typed):
        if _ACTION_RX.search(txt):                                         # an action with no named control ('Choose a color from the palette'): kept as an UNDERSPECIFIED step - dropping it would let a half-run procedure look finished
            return GuideStep(n, raw.strip(), act, "", [], "", "", cite)
        return None''', r'''    optional = bool(re.search(r"(?i)\b(if needed|if necessary|if you want|optionally|\(optional\)|as needed|if desired)\b", txt))
    if not (target or path or chord or typed):
        if _ACTION_RX.search(txt):                                         # an action with no named control ('Choose a color from the palette'): kept - dropping it would let a half-run procedure look finished
            gm = re.search(r"(?i)\b(?:a|an|any|one|the)\s+[\w -]{1,30}?\s+(?:from|in|on|of|within)\s+(?:the\s+)?([\w -]{3,40}?)(?:[.,;]|\s+(?:to|if|and|then)\b|$)", txt)
            return GuideStep(n, raw.strip(), act, "", [], "", "", cite, [], _clean_term(gm.group(1)) if gm else "", optional)
        return None'''),
    (r'''    return GuideStep(n, raw.strip(), act, target, path, typed, chord, cite, [_clean_term(a) for a in alts_found if _clean_term(a)])''',
     r'''    return GuideStep(n, raw.strip(), act, target, path, typed, chord, cite, [_clean_term(a) for a in alts_found if _clean_term(a)], "", optional)'''),
    # grounding: 'optional' and 'any item of the group'
    (r'''    if st.chord and re.search(r"(?i)(?:^|\+)(?:win|windows|cmd|meta|super)(?:\+|$)", st.chord):
        return Grounded(st, None, 0.0, "human", f"policy: {st.chord} is an operating-system shortcut, not one of the application's")''',
     r'''    if st.optional and not (st.target or st.path or st.chord or st.text):
        return Grounded(st, None, 1.0, "optional", "the manual says this step is optional ('if needed'): skipped")
    if st.chord and re.search(r"(?i)(?:^|\+)(?:win|windows|cmd|meta|super)(?:\+|$)", st.chord):
        return Grounded(st, None, 0.0, "human", f"policy: {st.chord} is an operating-system shortcut, not one of the application's")'''),
    (r'''    if st.action == "drag" or (not st.path and fold(st.target) in GESTURE_TARGETS):''', r'''    if st.group and not (st.target or st.path):
        v, grp = pick_from_group(catalog, st.group)
        if v is not None:
            return Grounded(st, v, 0.6, "group", f"the manual says 'one from the {st.group}': any item of '{grp}' will do - '{v.label}' was taken")
    if st.action == "drag" or (not st.path and fold(st.target) in GESTURE_TARGETS):'''),
    (r'''GROUNDED_HOW = ("path", "label", "chord", "typed", "key")''', r'''GROUNDED_HOW = ("path", "label", "chord", "typed", "key", "group", "optional")'''),
    (r'''def near_of(v: Any)''', r'''def pick_from_group(catalog: Any, phrase: str) -> Tuple[Any, str]:
    """'a color from the color palette': the group of the live interface whose name is closest to the phrase ('Colours' ~ 'color palette'), and the first plain, enabled item inside it."""
    import difflib
    q = {_stem(w) for w in fold(phrase).split() if len(w) > 2} - {"the", "list", "menu", "gallery", "options", "option", "section"}
    if not q:
        return None, ""
    groups: Dict[str, List[Any]] = {}
    for v in catalog.verbs:
        for p in v.path:
            groups.setdefault(p, []).append(v)
    best, best_s = "", 0.0
    for g in groups:
        gw = {_stem(w) for w in fold(g).split() if len(w) > 2}
        if not gw:
            continue
        sc = max((max(difflib.SequenceMatcher(None, a, b).ratio() for b in gw) for a in q), default=0.0)       # 'color' ~ 'colour'
        if sc > best_s:
            best, best_s = g, sc
    if best_s < 0.8:
        return None, ""
    items = [v for v in groups[best] if v.enabled and v.safety == "safe" and v.role in ("button", "list_item", "radio", "checkbox", "menu_item", "tab", "tree_item") and v.label and v.path and v.path[-1] == best]
    return (items[0], best) if items else (None, "")


def near_of(v: Any)'''),
])

patch(R + "executor.py", [
    (r'''            elif g.how == "human":''', r'''            elif g.how == "optional":
                s = Step(0, st.raw, None, "", [], "skip", safety="safe", routes=["optional: skipped"], expected="nothing - the manual calls it optional", source="guide", cite=gp["cite"], note=g.note)
            elif g.how == "human":'''),
    (r'''            if g.how in ("path", "label", "chord") and g.verb is not None:''', r'''            if g.how in ("path", "label", "chord", "group") and g.verb is not None:'''),
    (r'''            if st.kind == "unknown":
                rep.results.append(StepResult(st.index, label, "unknown", summary=st.note))''', r'''            if st.kind == "skip":
                rep.results.append(StepResult(st.index, label, "done", route="skipped", effect="optional", summary=st.note, ms=0))
                continue
            if st.kind == "unknown":
                rep.results.append(StepResult(st.index, label, "unknown", summary=st.note))'''),
])
print("ok")
