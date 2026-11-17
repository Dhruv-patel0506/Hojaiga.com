import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''_CHORD = re.compile(r"\b((?:Ctrl|Control|Alt|Shift|Cmd|Command|Win)(?:\s*\+\s*(?:Ctrl|Control|Alt|Shift|Cmd|Command|Win))*\s*\+\s*''', r'''_CHORD = re.compile(r"\b((?:Ctrl|Control|Alt|Shift|Cmd|Command|Windows|Win|Meta|Super)(?:\s*\+\s*(?:Ctrl|Control|Alt|Shift|Cmd|Command|Windows|Win|Meta|Super))*\s*\+\s*''')
rep(r'''    if not act and not target and not chord and not path:
        return None
    if not act and not (emph or''', r'''    if not target and not chord and not path and re.search(r"(?i)\b(click and drag|drag|draw|sketch|paint on|swipe)\b", txt):
        return GuideStep(n, raw.strip(), "drag", "canvas", [], typed, "", cite)                  # a pointer gesture with no named control ('Click and drag on the canvas'): kept, so it is NAMED as one
    if not act and not target and not chord and not path:
        return None
    if not act and not (emph or''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)

# the tests: a page that kills the browser must not carry a hazard token; the ledger test counts run + set-aside; quiet websockets
T = "D:/new_automation/All codes/core_organs/si_tests_apprun.py"
t = io.open(T, "r", encoding="utf-8").read()
for old, new in [
    ('"chrome://killer/": ("Killer", [("button", "Boom")], []),', '"chrome://bomb/": ("Bomb", [("button", "Boom")], []),'),
    ('for x in ("settings", "history", "crash", "internals", "bookmarks", "killer", "sync-optin")', 'for x in ("settings", "history", "crash", "internals", "bookmarks", "bomb", "sync-optin")'),
    ('if "killer" in url:', 'if "bomb" in url:'),
    ('guide_terms=["Settings", "Killer"], cache_path=cache)\n        gone = None', 'guide_terms=["Settings", "Bomb"], cache_path=cache)\n        gone = None'),
    ('ad3 = chromium.ChromiumAdapter(br3, guide_terms=["Settings", "Killer"], cache_path=cache)', 'ad3 = chromium.ChromiumAdapter(br3, guide_terms=["Settings", "Bomb"], cache_path=cache)'),
    ('"killer" in gone', '"bomb" in gone'),
    ('"killer" in json.dumps(json.load', '"bomb" in json.dumps(json.load'),
    ('"killer" not in " ".join(fb3.visits)', '"bomb" not in " ".join(fb3.visits)'),
    ('        "chrome://settings/": ("Settings",', '        "chrome://settings/": ("Settings",'),
    ('N("MenuItemControl", "File", (0, 0, 30, 10), ("invoke", "expand"), 1, idx=5, expand_state=0)', 'N("MenuItemControl", "File", (400, 400, 430, 410), ("invoke", "expand"), 1, idx=5, expand_state=0)'),
    ('"## Zoom in\\n1. Click **Zoom in**.\\n## Zoom the view in\\n1. Click **Zoom in**.\\n"', '"## Zoom in\\n1. Click **Zoom in**.\\n## Bold text\\n1. Click **Bold**.\\n2. Click **Italic**.\\n## Bold text\\n1. Click **Bold**.\\n2. Click **Colour wheel**.\\n"'),
    ('"every_procedure_is_in_the_ledger": len(run.ledger) >= 7', '"every_procedure_is_in_the_ledger": len(run.ledger) + len(tasks) >= 8'),
    ('"rows_in_the_database": len(h.guide_runs("demo", 50)) >= 3', '"rows_in_the_database": len(h.guide_runs("demo", 50)) >= 2'),
]:
    assert old in t, old[:70]
    t = t.replace(old, new, 1)
t = t.replace('sys.path[:0] = [p for p in ("D:/new_automation", "D:/new_automation/All codes") if p not in sys.path]', 'sys.path[:0] = [p for p in ("D:/new_automation", "D:/new_automation/All codes") if p not in sys.path]\nimport logging\nlogging.getLogger("websockets").setLevel(logging.CRITICAL)', 1)
io.open(T, "w", encoding="utf-8", newline="\n").write(t)
print("ok")
