import ast, io
P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''            ok, _how = self.b.new_tab("chrome://chrome-urls/")
            time.sleep(0.6)
            tg = next((x for x in self.b.targets() if "chrome-urls" in x.get("url", "")), None)
'''
new = '''            ok, _how = self.b.new_tab("chrome://chrome-urls/")
            tg = self._await_target("chrome-urls")
'''
assert old in s
s = s.replace(old, new, 1)
old2 = '''                ok, _h = self.b.new_tab(u)
                if not ok:
                    continue
                time.sleep(0.5)
                tg = next((x for x in self.b.targets() if x.get("url", "").rstrip("/") == u.rstrip("/")), None) or None
                if tg is None:
                    continue
                titles[u] = (tg.get("title") or "").strip()
                self.b.close_tab(tg["id"])'''
new2 = '''                ok, _h = self.b.new_tab(u)
                if not ok:
                    continue
                tg = self._await_target(u.rstrip("/"), need_title=True, seconds=3.0)
                if tg is None:
                    continue
                titles[u] = (tg.get("title") or "").strip()
                self.b.close_tab(tg["id"])'''
assert old2 in s
s = s.replace(old2, new2, 1)
old3 = '''    def _load_cache(self) -> Dict[str, Any]:'''
new3 = '''    def _await_target(self, url_part: str, need_title: bool = False, seconds: float = 5.0) -> Optional[Dict[str, Any]]:
        """The tab whose URL contains `url_part` (a new tab lists as about:blank for a moment before its navigation commits)."""
        end = time.time() + seconds
        last = None
        while time.time() < end:
            for x in self.b.targets():
                if url_part in x.get("url", ""):
                    last = x
                    if not need_title or (x.get("title") and x.get("title") != x.get("url")):
                        return x
            time.sleep(0.25)
        return last

    def _load_cache(self) -> Dict[str, Any]:'''
s = s.replace(old3, new3, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
