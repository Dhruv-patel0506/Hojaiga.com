import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''    t = re.sub(r"\s+([.,;:!?)])", r"\1", t)
    return re.sub(r"[ \t]+", " ", t).strip()''', r'''    t = re.sub(r"\*\*\s+([.,;:!?)])", r"**\1", t)                 # tighten punctuation only where it directly follows an emphasis ('Type .LOG' keeps its space)
    return re.sub(r"[ \t]+", " ", t).strip()''')
rep(r'''".&%$#@/\_-+*=<>[]{}()"''', r'''".&%$#@/_-+*=<>[]{}()"''')
rep(r'''def _spaced_bold(raw: str) -> str:''', r'''_CANON_ON_MENU = re.compile(r"(?i)\b(?:on|in|from|under)\s+the\s+\**([^*,.;>]+?)\**\s+(?:menu|tab|toolbar|ribbon|drop-?down)\s*,?\s*(?:then\s+)?(?:select|choose|click(?: on)?|pick)\s+\**([^*,.;>]+?)\**(?=$|[\s,.;])")
_CANON_FROM_MENU = re.compile(r"(?i)\b(select|choose|click(?: on)?|pick)\s+\**([^*,.;>]+?)\**\s+(?:from|in|on)\s+the\s+\**([^*,.;>]+?)\**\s+(?:menu|tab|toolbar|ribbon|drop-?down)\b")


def _canon_menu_phrases(line: str) -> str:
    """'On the File menu, select Save As' / 'Select Page Setup from the File menu'  ->  'select File > Save As' (one menu PATH, so no later splitting can tear it apart)."""
    t = _CANON_ON_MENU.sub(lambda m: f"select {m.group(1).strip()} > {m.group(2).strip()}", line)
    return _CANON_FROM_MENU.sub(lambda m: f"{m.group(1).lower()} {m.group(3).strip()} > {m.group(2).strip()}", t)


def _spaced_bold(raw: str) -> str:''')
rep(r'''    for ln in lines:
        ln = _spaced_bold(ln)''', r'''    for ln in lines:
        ln = _canon_menu_phrases(_spaced_bold(ln).replace("**", ""))''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
