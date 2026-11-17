import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/manual_rag.py"
s = io.open(P, "r", encoding="utf-8").read()
old = s[s.index("    def flush() -> None:\n        body = "):s.index("    for line in text.splitlines():\n        m = re.match(r\"^(#{1,6})")]
new = '''    def flush() -> None:
        # LINES are kept (a numbered procedure is a list of lines: '1. Click ... 2. Choose ...'); only the white space inside a line is collapsed
        lines = [" ".join(l.split()) for l in buf if l.strip()]
        buf.clear()
        if not lines:
            return
        path = " > ".join(h for _l, h in stack) or "(untitled)"
        if sum(len(l.split()) for l in lines) <= max_words:
            out.append((path, "\\n".join(lines)))
            return
        cur: List[str] = []
        n = 0
        for ln in lines:
            pieces = [ln] if len(ln.split()) <= max_words else re.split(r"(?<=[.!?])\\s+", ln)
            for pc in pieces:
                cur.append(pc)
                n += len(pc.split())
                if n >= target_words:
                    out.append((path, "\\n".join(cur)))
                    cur, n = [], 0
        if cur:
            out.append((path, "\\n".join(cur)))

'''
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("chunk_markdown keeps lines")
