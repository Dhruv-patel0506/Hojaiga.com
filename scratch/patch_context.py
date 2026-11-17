import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


# ------------------------------------------------------------------------------- context-aware grounding: 'Select > Rectangle' means the Rectangle NEXT TO Select, not the Rectangle shape
patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
    (r'''def resolve_label(catalog: Any, text: str) -> Tuple[Any, float]:
    """(verb, confidence): exact label = 1.0, else the share of content words the label explains (enabled / safe / shallow verbs win ties)."""
    q = fold(text)
    exact = [v for v in catalog.verbs if fold(v.label) == q]
    if exact:
        exact.sort(key=lambda v: (not v.enabled, v.safety != "safe", len(v.path)))
        return exact[0], 1.0''', r'''def near_of(v: Any) -> Tuple[str, ...]:
    """The names a LATER step is most likely to be near: the verb itself and every group / menu it sits under."""
    if v is None:
        return ()
    return tuple(x for x in {fold(v.label)} | {fold(p) for p in v.path} if x)


def resolve_label(catalog: Any, text: str, near: Sequence[str] = ()) -> Tuple[Any, float]:
    """(verb, confidence): exact label = 1.0, else the share of content words the label explains (enabled / safe / shallow verbs win ties). `near`: names of the previous step's control and its
    groups - among equally good matches the one that sits in the SAME group wins ('Select', then 'Rectangle' = the selection shape, not the Rectangle in the Shapes gallery)."""
    q = fold(text)
    nearset = set(near)
    exact = [v for v in catalog.verbs if fold(v.label) == q]
    if exact:
        exact.sort(key=lambda v: (not v.enabled, v.safety != "safe", not (nearset and any(fold(p) in nearset for p in v.path)), len(v.path)))
        return exact[0], 1.0'''),
    (r'''        key = (round(sc, 3), 1.0 if v.enabled else 0.0, 1.0 if v.safety == "safe" else 0.0, -float(len(v.path)))''', r'''        key = (round(sc, 3), 1.0 if v.enabled else 0.0, 1.0 if v.safety == "safe" else 0.0, 1.0 if (nearset and any(fold(p) in nearset for p in v.path)) else 0.0, -float(len(v.path)))'''),
    (r'''def ground_step(st: GuideStep, catalog: Any) -> Grounded:''', r'''def ground_step(st: GuideStep, catalog: Any, near: Sequence[str] = ()) -> Grounded:'''),
    (r'''    if st.target:
        v, c = resolve_label(catalog, st.target)
        if v is not None and c >= 0.66:
            return Grounded(st, v, c, "label")
        for alt in st.alts:                                                   # 'Pixels, Inches, or Centimeters': the first option that exists will do
            v2, c2 = resolve_label(catalog, alt)''', r'''    if st.target:
        v, c = resolve_label(catalog, st.target, near)
        if v is not None and c >= 0.66:
            return Grounded(st, v, c, "label")
        for alt in st.alts:                                                   # 'Pixels, Inches, or Centimeters': the first option that exists will do
            v2, c2 = resolve_label(catalog, alt, near)'''),
    (r'''def ground(steps: Sequence[GuideStep], catalog: Any) -> List[Grounded]:
    return [ground_step(s, catalog) for s in steps]''', r'''def ground(steps: Sequence[GuideStep], catalog: Any) -> List[Grounded]:
    out: List[Grounded] = []
    near: Tuple[str, ...] = ()
    for s in steps:
        g = ground_step(s, catalog, near)
        out.append(g)
        if g.verb is not None:
            near = near_of(g.verb)
    return out'''),
])

# ------------------------------------------------------------------------------- executor: remember the previous verb for just-in-time grounding; group-aware opener choice
patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''        g = GS.ground_step(gs, self.catalog)
        if g.how in ("path", "label", "chord") and g.verb is not None:
            txt = gs.text if (gs.action == "type" and gs.text) else ""''', r'''        g = GS.ground_step(gs, self.catalog, GS.near_of(self._last_verb))
        if g.how in ("path", "label", "chord") and g.verb is not None:
            txt = gs.text if (gs.action == "type" and gs.text) else ""'''),
    (r'''        self._sticky_left = 0''', r'''        self._last_verb: Optional[Verb] = None                      # the verb the previous step performed: the next step's words are resolved NEAR it
        self._sticky_left = 0'''),
    (r'''            result.ms = int((time.time() - t0) * 1000)
            rep.results.append(result)''', r'''            result.ms = int((time.time() - t0) * 1000)
            rep.results.append(result)
            if v is not None and result.status == "done":
                self._last_verb = v'''),
    (r'''        chain = list(v.path) + [v.label]
        for i, name in enumerate(chain[:-1]):
            nodes = self._all_nodes()
            cand = [n for n in nodes if fold(n.name) == fold(name) and not n.offscreen and n.enabled and n.rect[2] > n.rect[0]]
            if not cand:
                continue
            ok, how = MN._expand(self.fx, cand[0])''', r'''        chain = list(v.path) + [v.label]
        for i, name in enumerate(chain[:-1]):
            nodes = self._all_nodes()
            cand = [n for n in nodes if fold(n.name) == fold(name) and not n.offscreen and n.enabled and n.rect[2] > n.rect[0]]
            if not cand:
                continue
            if i > 0 and len(cand) > 1:                                      # two openers may carry the same name ('More Options' of the Selection AND the Brushes group): take the one inside the group named before it
                grp = [n for n in nodes if fold(n.name) == fold(chain[i - 1]) and n.rect[2] > n.rect[0]]
                inside = [c for c in cand if any(g.rect[0] <= c.rect[0] and g.rect[1] <= c.rect[1] and c.rect[2] <= g.rect[2] and c.rect[3] <= g.rect[3] for g in grp)]
                cand = inside or cand
            cand = [c for c in cand if c.role in ("menuitem", "button", "splitbutton", "combobox", "tabitem", "listitem", "radiobutton") or "expand" in (c.pats or [])] or cand
            ok, how = MN._expand(self.fx, cand[0])'''),
])

# ------------------------------------------------------------------------------- menus: openers with the same name in different groups are all read; items keep the opener's group in their path
patch("D:/new_automation/All codes/core_organs/professor/menus.py", [
    (r'''        key = fold(n.name)
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out''', r'''        key = (fold(n.name), n.rect[0] // 40, n.rect[1] // 40)                 # the same name in two places ('More Options' under Selection and under Brushes) is two openers
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out'''),
    (r'''    seen: Set[str] = set()
    for n in nodes:
        if n.role == "tabitem":''', r'''    seen: Set[Any] = set()
    for n in nodes:
        if n.role == "tabitem":'''),
    (r'''    base_nodes = all_nodes()
    openers = find_openers([n for n in base_nodes if n.rect[2] > n.rect[0]])[:max_openers]''', r'''    base_nodes = all_nodes()
    openers = find_openers([n for n in base_nodes if n.rect[2] > n.rect[0]])[:max_openers]
    groups = [g for g in base_nodes if g.ctype == "GroupControl" and g.name and g.rect[2] > g.rect[0]]'''),
    (r'''            key = (tuple([op.name]), fold(label))
            if key in have:
                continue
            have.add(key)''', r'''            grp = next((g.name for g in groups if g.rect[0] <= op.rect[0] and g.rect[1] <= op.rect[1] and op.rect[2] <= g.rect[2] and op.rect[3] <= g.rect[3] and g.name != op.name), "")
            vpath = ([grp] if grp else []) + [op.name]                          # 'Selection > More Options > Rectangle': the group keeps two openers of the same name apart
            key = (tuple(vpath), fold(label))
            if key in have:
                continue
            have.add(key)'''),
    (r'''            cat.verbs.append(Verb(verb_id([op.name], label), re.sub(r"(\.\.\.|…)\s*$", "", label).strip(), [op.name], chord or tchord,''', r'''            cat.verbs.append(Verb(verb_id(vpath, label), re.sub(r"(\.\.\.|…)\s*$", "", label).strip(), list(vpath), chord or tchord,'''),
    (r'''["menu-expand"], "measured", safety.classify(label, op.name)))''', r'''["menu-expand"], "measured", safety.classify(label, " ".join(vpath))))'''),
])

# ------------------------------------------------------------------------------- harvest: spinners / sliders are fields, 'Width: Minimum1 Maximum99999' is just 'Width:'
patch("D:/new_automation/All codes/core_organs/professor/harvest.py", [
    (r'''_TREE_VERB_ROLES = {"button", "menuitem", "tabitem", "checkbox", "radiobutton", "splitbutton", "listitem", "treeitem", "combobox", "hyperlink", "edit"}''', r'''_TREE_VERB_ROLES = {"button", "menuitem", "tabitem", "checkbox", "radiobutton", "splitbutton", "listitem", "treeitem", "combobox", "hyperlink", "edit", "spinner", "slider"}
_RANGE_SUFFIX = re.compile(r"\s+Minimum\s*-?\d+\s+Maximum\s*-?\d+\s*$", re.I)'''),
    (r'''        b.add(n.name, path[-2:], source="uia", shortcut=chord or tchord or (chords_in(n.name) or [""])[0], desc=desc or n.help, enabled=n.enabled, checked=bool(n.selected) or n.toggle_state == 1,''', r'''        b.add(_RANGE_SUFFIX.sub("", n.name), path[-2:], source="uia", shortcut=chord or tchord or (chords_in(n.name) or [""])[0], desc=desc or n.help, enabled=n.enabled, checked=bool(n.selected) or n.toggle_state == 1,'''),
    (r'''                "edit": "field"}.get(n.role, n.role)''', r'''                "edit": "field", "spinner": "field", "slider": "field"}.get(n.role, n.role)'''),
])

# ------------------------------------------------------------------------------- effector: LegacyIAccessible default action as the last pattern
patch("D:/new_automation/All codes/core_organs/professor/effectors.py", [
    (r'''                    p = pattern_of(ctrl, pname)
                    if p is not None:
                        getattr(p, call)()
                        result["how"] = f"UIA {label}"
                        return''', r'''                    p = pattern_of(ctrl, pname)
                    if p is not None:
                        getattr(p, call)()
                        result["how"] = f"UIA {label}"
                        return
                try:                                                         # many XAML flyout items expose no standard pattern, only the legacy 'default action' (Press / Select)
                    lp = pattern_of(ctrl, "LegacyIAccessible")
                    if lp is not None and getattr(lp, "DefaultAction", ""):
                        lp.DoDefaultAction()
                        result["how"] = f"UIA LegacyIAccessible.DoDefaultAction ({lp.DefaultAction})"
                        return
                except Exception:
                    pass'''),
    (r'''        if how.startswith("UIA ") and "error" not in how and "no usable" not in how:
            return self._rec(f"node {name}", (True, how))''', r'''        if how.startswith("UIA ") and "error" not in how and "no usable" not in how:
            return self._rec(f"node {name}", (True, how))'''),
])
print("ok")
