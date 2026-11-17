import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:70]
    s = s.replace(old, new, 1)


rep('''(r"drag", "drag"), (r"toggle", "toggle"),
]''', '''(r"drag", "drag"), (r"toggle", "toggle"),
    (r"adjust|set|change|modify", "set"),
]''')
rep('''        else:
            m = _THE_X.search(txt) or _X_KIND.search(txt)
            if m:
                target = m.group(1)''', '''        else:
            m = _THE_X.search(txt) or _X_KIND.search(txt)
            if m:
                target = m.group(1)
            else:                                                  # 'Adjust the Cropping Ratio in the Inspector': the first Capitalised phrase after the verb
                am = _ACTION_RX.search(txt)
                tail = txt[am.end():] if am else txt
                m2 = re.search(r"\\b(?:the\\s+)?([A-Z][\\w&/+-]*(?:\\s+[A-Z][\\w&/+-]*){0,3})", tail)
                if m2:
                    target = m2.group(1)''')
rep('''    for ln in lines:
        for piece in re.split(r"(?<=[.!?])\\s+(?=(?:Then|Next|Finally|After that)\\b)", ln):
            st = parse_line(piece, len(out) + 1, cite)
            if st is not None:
                out.append(st)
    return out''', '''    for ln in lines:
        for sent in re.split(r"(?<=[.!?])\\s+(?=(?:Then|Next|Finally|After that)\\b)", ln):
            for piece in re.split(r",?\\s+(?:and\\s+)?then\\s+|;\\s+|\\s+and\\s+(?=(?:click|press|choose|select|open|tick|check|uncheck|type|enter|drag|switch)\\b)", sent, flags=re.I):
                st = parse_line(piece, len(out) + 1, cite)
                if st is not None:
                    out.append(st)
    return out''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("guide_steps patched")
