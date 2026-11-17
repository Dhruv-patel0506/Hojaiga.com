import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()
old = s[s.index("                try:\n                    r = pg.call(\"Runtime.evaluate\", {\"expression\": \"Array.from(document.querySelectorAll('a'))"):s.index("                self.b.close_tab(tg[\"id\"])\n            urls = [u for u in urls")]
new = '''                try:                                                     # the page is a web component: its links are in the accessibility tree (names are the URLs), not in the light DOM
                    urls = sorted({v["label"].split("#")[0].rstrip("/") + "/" for v in pg.verbs(limit=500) if v["ax_role"] == "link" and v["label"].startswith("chrome://")})
                except CdpError:
                    urls = []
'''
s = s.replace(old, new, 1)
s = s.replace('''            urls = [u for u in urls if not DANGEROUS_PAGES.search(u) and u.count("/") <= 3][:70]''', '''            urls = [u for u in urls if not DANGEROUS_PAGES.search(u) and not re.search(r"internals|-debug|^chrome://(?:web-app|webui|test|invalidations|process|ukm|usb|bluetooth|nacl|oobe|omnibox|proximity|quota|predictors|prefs|local-state|metrics|histograms|field-trial|management)", u)
                                                            and u.count("/") <= 3][:60]''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
