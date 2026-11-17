import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()
old = s[s.index("        pg = self.current()\n        if pg is None:\n            return False, \"no page\"\n        _t, cur = pg.title_url()"):s.index("        tgt = next((x for x in vs if x[\"ordinal\"] == ordinal), vs[0])")]
new = '''        pg = self.current()
        if pg is None:
            return False, "no page"
        _t, cur = pg.title_url()

        def here() -> List[Dict[str, Any]]:
            return [x for x in pg.verbs() if fold(x["label"]) == fold(v.label) and x["role"] == role]
        vs = here()                                                           # a navigation entry ('Appearance') exists on every settings page: act on the page we are ON when it is there
        if not vs and not cur.startswith(url.rstrip("/")):
            ok, how = pg.navigate(url)
            if not ok:
                return False, how
            self._wait_loaded(pg)
            vs = here()
        if not vs:
            return False, f"'{v.label}' is not on the current page ({cur[:50]}) nor on {url}"
'''
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
