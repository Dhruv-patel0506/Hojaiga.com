import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


# 1 normalise bold spacing ('from the**File**menu' -> 'from the **File** menu') at the top of parse_line
rep(r'''    emph = [e for e in _BOLD.findall(raw)]
    txt = raw.replace("**", "")''', r'''    raw = _spaced_bold(raw)
    emph = [e for e in _BOLD.findall(raw)]
    txt = raw.replace("**", "")''')

rep(r'''def parse_line(raw: str, n: int = 1, cite: str = "") -> Optional[GuideStep]:''', r'''def _spaced_bold(raw: str) -> str:
    """HTML manuals often lose the spaces around emphasis ('Select **Page Setup**from the**File**menu'): put them back, keeping punctuation tight."""
    t = re.sub(r"\s*\*\*([^*\n]{1,80}?)\*\*\s*", lambda m: " **" + m.group(1).strip() + "** ", raw)
    t = re.sub(r"\s+([.,;:!?)])", r"\1", t)
    return re.sub(r"[ \t]+", " ", t).strip()


_FROM_MENU = re.compile(r"(?i)\b(?:select|choose|click(?: on)?|pick|open)\s+\**([^*,.;]+?)\**\s+(?:from|in|on)\s+the\s+\**([^*,.;]+?)\**\s+(?:menu|tab|toolbar|ribbon|drop-?down|list)\b")
_ON_MENU_SELECT = re.compile(r"(?i)\b(?:on|in|from|under)\s+the\s+\**([^*,.;]+?)\**\s+(?:menu|tab|toolbar|ribbon|drop-?down)\s*,?\s*(?:select|choose|click(?: on)?|pick)\s+\**([^*,.;]+?)\**(?=$|[\s,.;])")


def parse_line(raw: str, n: int = 1, cite: str = "") -> Optional[GuideStep]:''')

# 2 'X from the Y menu' / 'On the Y menu, select X' are menu PATHS (Y > X)
rep(r'''    typed = ""
    tm = re.search(r"\b(?:type|enter|write|input)\b''', r'''    if not path:
        fm = _FROM_MENU.search(raw.replace("**", "")) or None
        om = _ON_MENU_SELECT.search(raw.replace("**", "")) or None
        if om:
            path = [_clean_term(om.group(1)), _clean_term(om.group(2))]
        elif fm:
            path = [_clean_term(fm.group(2)), _clean_term(fm.group(1))]
        path = [p for p in path if p and fold(p) not in _STOP_TARGETS] if path else []
        if len(path) < 2:
            path = []
    typed = ""
    tm = re.search(r"\b(?:type|enter|write|input)\b''')

# 3 steps: numbered lines and action-led bullets are steps; definition bullets ('- **Headers**: &f') are not; paragraphs of imperatives are used when there are no list steps
rep(r'''    lines = [m.group(1) for ln in (text or "").splitlines() for m in [_STEP_LINE.match(ln)] if m]
    if not lines:
        flat = re.sub(r"\s+", " ", (text or "").replace("\n", " "))''', r'''    lines = []
    para: List[str] = []
    for ln in (text or "").splitlines():
        m = _STEP_LINE.match(ln)
        if m:
            body = m.group(1)
            if re.match(r"\s*\d+[.)]", ln) or _ACTION_RX.match(_spaced_bold(body).replace("**", "").strip()):
                lines.append(body)
        else:
            para.append(ln)
    if not lines:
        flat = re.sub(r"\s+", " ", _spaced_bold(" ".join(para)).replace("\n", " "))''')
rep(r'''    out: List[GuideStep] = []
    for ln in lines:
        for sent in re.split(r"(?<=[.!?])\s+(?=(?:Then|Next|Finally|After that)\b)", ln):
            for piece in re.split(r",?\s+(?:and\s+)?then\s+|;\s+|\s+and\s+(?=(?:click|press|choose|select|open|tick|check|uncheck|type|enter|drag|switch)\b)", sent, flags=re.I):''',
    r'''    out: List[GuideStep] = []
    for ln in lines:
        ln = _spaced_bold(ln)
        for sent in re.split(r"(?<=[.!?])\s+(?=(?:Then|Next|Finally|After that)\b)", ln):
            for piece in re.split(r",?\s+(?:and\s+)?then\s+|;\s+|\s+and\s+(?=(?:click|press|choose|select|open|tick|check|uncheck|type|enter|drag|switch)\b)|,\s+(?:and\s+)?(?=(?:click|press|choose|select|open|tick|check|uncheck|type|enter|drag|switch)\b)", sent, flags=re.I):''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
