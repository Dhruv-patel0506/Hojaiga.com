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
    (r'''    if not target and not chord and not path and re.search(r"(?i)\b(click and drag|drag|draw|sketch|paint on|swipe)\b", txt):
        return GuideStep(n, raw.strip(), "drag", "canvas", [], typed, "", cite)                  # a pointer gesture with no named control ('Click and drag on the canvas'): kept, so it is NAMED as one''',
     r'''    if not emph and not path and not chord and re.search(r"(?i)\b(click and drag|drag|draw(?:ing)?|sketch|paint on|swipe|release the mouse)\b", txt):
        return GuideStep(n, raw.strip(), "drag", "canvas", [], typed, "", cite)                  # a pointer gesture with no named control ('Draw on the canvas'): kept, so it is NAMED as one'''),
    (r'''    if not (target or path or chord or typed):
        return None
    return GuideStep(n, raw.strip(), act, target, path, typed, chord, cite, [_clean_term(a) for a in alts_found if _clean_term(a)])''',
     r'''    if not (target or path or chord or typed):
        if _ACTION_RX.search(txt):                                         # an action with no named control ('Choose a color from the palette'): kept as an UNDERSPECIFIED step - dropping it would let a half-run procedure look finished
            return GuideStep(n, raw.strip(), act, "", [], "", "", cite)
        return None
    return GuideStep(n, raw.strip(), act, target, path, typed, chord, cite, [_clean_term(a) for a in alts_found if _clean_term(a)])'''),
])
patch(R + "apprun.py", [
    (r'''            if "pointer gesture" in (last.summary or "") or (last.summary or "").startswith("policy:"):
                return "blocked", last.summary''', r'''            if "pointer gesture" in (last.summary or "") or (last.summary or "").startswith("policy:"):
                return "blocked", last.summary
            if "names no control" in (last.summary or ""):
                return "blocked", "underspecified: " + (last.summary or "")'''),
])
print("ok")
