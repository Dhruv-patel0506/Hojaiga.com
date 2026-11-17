import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''        for u, title in titles.items():
            parts = [p.strip() for p in re.split(r"\s+[-–—|]\s+", title) if p.strip()]
            labels = []
            for p in parts[:2]:
                p = re.sub(r"^chrome://", "", p)
                if 2 <= len(p) <= 40 and p.lower() not in ("google chrome", "chrome"):
                    labels.append(p)''', r'''        full = {fold(t) for t in titles.values()}
        for u, title in titles.items():
            parts = [p.strip() for p in re.split(r"\s+[-–—|]\s+", title) if p.strip()]
            labels = []
            # 'Settings - Management' is the MANAGEMENT page: its specific tail names it; the head ('Settings') only when no page is itself called that
            cand = [parts[-1]] if len(parts) > 1 else parts[:1]
            if len(parts) > 1 and fold(parts[0]) not in full:
                cand.append(parts[0])
            for p in cand:
                p = re.sub(r"^chrome://", "", p)
                if 2 <= len(p) <= 40 and p.lower() not in ("google chrome", "chrome"):
                    labels.append(p)''')
rep(r'''        vs = here()                                                           # a navigation entry ('Appearance') exists on every settings page: act on the page we are ON when it is there
        if not vs and not cur.startswith(url.rstrip("/")):
            ok, how = pg.navigate(url)
            if not ok:
                return False, how
            self._wait_loaded(pg)
            vs = here()''', r'''        vs = here()                                                           # a navigation entry ('Appearance') exists on every settings page: act on the page we are ON when it is there
        if not vs and not cur.startswith(url.rstrip("/")):
            ok, how = pg.navigate(url)
            if not ok:
                return False, how
            self._wait_loaded(pg)
            for _ in range(5):                                                # the page's accessibility tree is built lazily after the load
                vs = here()
                if vs:
                    break
                time.sleep(0.8)''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
