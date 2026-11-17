import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, old[:80]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/executor.py", [(
    "        rep.steps = steps or rule_steps\n        return rep",
    '''        if not steps:
            # the words alone matched a control only weakly: that is a COINCIDENCE of one shared word ('remove every marker' vs 'Add Marker'), not a plan - never forced onto the nearest control
            steps = []
            for st in rule_steps:
                if st.kind == "verb" and st.conf < 0.66:
                    steps.append(Step(st.index, st.goal, None, "", [], "unknown", safety="unknown", need_human=True,
                                      note=f"the closest control, '{st.verb}', explains only {st.conf:.0%} of the words of '{st.goal}' - not used (no guide, skill or model could ground this step)"))
                else:
                    steps.append(st)
        rep.steps = steps
        return rep'''), ])

patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
    ('''def parse_steps(text: str, cite: str = "") -> List[GuideStep]:''', '''def _imperative_clause(sentence: str) -> str:
    """'To place a marker in the view, click **Add Marker**.' -> 'click **Add Marker**.'  (manuals state the purpose first, then the action; 'You can simply ...' likewise)."""
    s = sentence.strip().lstrip("* ").strip()
    m = re.match(r"(?i)^(?:to|in order to|if you want to|when you want to)\\b[^,]{0,140},\\s*(.*)$", s)
    if m:
        s = m.group(1).strip()
    for _ in range(3):
        s2 = re.sub(r"(?i)^(?:you\\s+(?:can|may|should|need to|have to|must|will)|simply|just|now|first|finally|next|then|also|please|and)\\b[,:]?\\s*", "", s).strip()
        if s2 == s:
            break
        s = s2
    return s


def parse_steps(text: str, cite: str = "") -> List[GuideStep]:'''),
    ('''        lines = [s for s in sents if _ACTION_RX.match(s.lstrip("* ").strip()) is not None or re.match(r"(?:then|next|finally),?\\s+\\w+", s, re.I)]''',
     '''        lines = []
        for s in sents:
            c = _imperative_clause(s)
            if _ACTION_RX.match(c.lstrip("* ").strip()) is not None:
                lines.append(c)'''), ])
print("patched forced-match + purpose clause")
