import ast, io
P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''                try:                                                     # the page is a web component: its links are in the accessibility tree (names are the URLs), not in the light DOM
                    urls = sorted({v["label"].split("#")[0].rstrip("/") + "/" for v in pg.verbs(limit=500) if v["ax_role"] == "link" and v["label"].startswith("chrome://")})
                except CdpError:
                    urls = []
'''
new = '''                for _try in range(4):                                   # the page is a web component: its links are in the accessibility tree (names are the URLs), which a browser builds lazily
                    try:
                        urls = sorted({v["label"].split("#")[0].rstrip("/") + "/" for v in pg.verbs(limit=500) if v["ax_role"] == "link" and v["label"].startswith("chrome://")})
                    except CdpError:
                        urls = []
                    if len(urls) >= 10:
                        break
                    time.sleep(1.0)
'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
