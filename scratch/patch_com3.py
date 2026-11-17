p = r"D:\new_automation\All codes\core_organs\atlas\comlib.py"
s = open(p, encoding="utf-8").read()
a = s.index("        def sim(f: str) -> int:")
b = s.index("        out += [os.path.join(d, f) for f in sorted(files")
new = '''        def lcs(x: str, y: str) -> int:
            prev = [0] * (len(y) + 1)
            for ch in x:
                cur = [0]
                for j, cy in enumerate(y):
                    cur.append(prev[j] + 1 if ch == cy else max(prev[j + 1], cur[j]))
                prev = cur
            return prev[-1]

        def sim(f: str) -> float:
            b = re.sub(r"[^a-z]", "", os.path.splitext(f)[0].lower())
            b = b[2:] if b.startswith("ms") and len(b) > 3 else b             # MSPPT -> ppt: the vendor prefix says nothing about the program
            return lcs(b, stem) / max(1, len(b)) if b else 0.0
'''
s = s[:a] + new + s[b:]
s = s.replace("out += [os.path.join(d, f) for f in sorted(files, key=lambda f: -sim(f))[:6]]", "out += [os.path.join(d, f) for f in sorted(files, key=lambda f: -sim(f))[:6] if sim(f) >= 0.6]")
open(p, "w", encoding="utf-8").write(s)
print("ok")
