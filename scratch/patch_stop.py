import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new, 1)


rep(r'''_SKIP_TARGETS = {"it", "this", "that", "them", "the", "a", "an", "your", "here", "now", "then"}''',
    r'''_SKIP_TARGETS = {"it", "this", "that", "them", "the", "a", "an", "your", "here", "now", "then"}
# a capitalised word that merely STARTS a sentence ('On your computer ...', 'If you ...', 'To undo ...') is not an interface term
_STOP_TARGETS = _SKIP_TARGETS | {"on", "to", "if", "you", "do", "be", "when", "in", "at", "by", "for", "these", "those", "there", "we", "they", "and", "or", "but", "as", "from", "with", "after", "before",
                                 "once", "note", "tip", "tips", "warning", "learn", "see", "use", "go", "get", "make", "keep", "applies", "important", "example", "for example", "windows", "macos", "mac", "android", "ios",
                                 "sign", "start", "ai", "all", "any", "each", "some", "more", "next", "back", "done", "yes", "no", "ok", "can", "will", "should", "may", "also", "just", "so", "than"}''')
rep(r'''                m2 = re.search(r"\b(?:the\s+)?([A-Z][\w&/+-]*(?:\s+[A-Z][\w&/+-]*){0,3})", tail)
                if m2:
                    target = m2.group(1)''',
    r'''                for m2 in re.finditer(r"\b(?:the\s+)?([A-Z][\w&/+-]*(?:\s+[A-Z][\w&/+-]*){0,3})", tail):
                    if fold(m2.group(1)) not in _STOP_TARGETS and fold(m2.group(1).split()[0]) not in _STOP_TARGETS:
                        target = m2.group(1)
                        break''')
rep(r'''    if fold(target) in _SKIP_TARGETS or (chord''', r'''    if fold(target) in _STOP_TARGETS or (chord''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
