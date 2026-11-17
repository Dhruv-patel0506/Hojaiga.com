import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


# winget: the package NAME must equal the application name (case-insensitive, whitespace-normalised): 'Notepad--' and 'Notepad++' are other programs
rep('''    norm = lambda t: re.sub(r"[^a-z0-9+#]+", " ", t.lower()).strip()''', '''    norm = lambda t: re.sub(r"\\s+", " ", t.strip().lower())''')
# ranking: a hit that never names the application is never a source, whatever its URL looks like
rep('''        if any(q in host for q in _QA_HOSTS):
            score -= 2
            why.append("Q&A site")''', '''        named = any(p in (title + " " + host + " " + path).lower() for p in prod) if prod else True
        if not named:
            score = min(score, 1.5)                                  # a 'user guide' of something else (YouTube TV help for a Notepad query) must not qualify
            why.append("never names the application")
        if any(q in host for q in _QA_HOSTS):
            score -= 2
            why.append("Q&A site")''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("winget exact names; ranking requires the application's name")
