import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
''', r'''import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .. import config as CFG
''')
rep(r'''class ChromiumAdapter:
    name = "cdp"
''', r'''# internal pages that crash, kill, hang or restart the browser, leak memory or open debugging tools: never visited
DANGEROUS_PAGES = re.compile(r"crash|kill|hang|quit|restart|dino|gpuclean|gpucrash|gpuhang|memory-exhaust|inducebrowser|badcast|browserrelaunch|ppapiflash|net-export|tracing|inspect|devtools|webrtc-internals|"
                             r"sandbox|safe-browsing|signin-internals|sync-internals|policy|chrome-signin|enterprise|reset-password|download-internals|discards|syncfs|serviceworker", re.I)
CACHE_PATH = os.path.join(CFG.DATA_DIR, "adapters", "chromium_pages.json")


class ChromiumAdapter:
    name = "cdp"
''')
# goto verbs + title discovery
rep(r'''    # ------------------------------------------------------------------------------------------------------------------ acting
    def owns(self, v: Verb) -> bool:''', r'''    def _load_cache(self) -> Dict[str, Any]:
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as fh:
                c = json.load(fh)
            return c if c.get("browser") == self._ver else {}
        except Exception:
            return {}

    def _save_cache(self, c: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
            c["browser"] = self._ver
            with open(CACHE_PATH, "w", encoding="utf-8") as fh:
                json.dump(c, fh, indent=1, ensure_ascii=False)
        except Exception:
            pass

    def harvest_destinations(self, cat: Catalog, budget_s: float = 120.0) -> Dict[str, Any]:
        """The browser's own pages as DESTINATIONS: the application lists its internal pages (chrome://chrome-urls); each page's title is what a guide calls it ('Settings', 'History', 'Downloads').
        Every title becomes a verb that navigates there, under the browser's menu ('More > Settings') and under 'Browser'. Read once per browser version, then cached."""
        t0 = time.time()
        self._ver = self.b.version().get("Browser", "")
        cache = self._load_cache()
        titles: Dict[str, str] = cache.get("titles", {})
        urls: List[str] = []
        if not titles or time.time() - cache.get("when", 0) > 14 * 86400:
            ok, _how = self.b.new_tab("chrome://chrome-urls/")
            time.sleep(0.6)
            tg = next((x for x in self.b.targets() if "chrome-urls" in x.get("url", "")), None)
            if tg is not None:
                pg = self.b.pages.get(tg["id"]) or CdpPage(tg)
                self.b.pages[tg["id"]] = pg
                self._wait_loaded(pg)
                try:
                    r = pg.call("Runtime.evaluate", {"expression": "Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h.startsWith('chrome://'))", "returnByValue": True})
                    urls = sorted({u.split("#")[0] for u in (r.get("result", {}).get("value") or [])})
                except CdpError:
                    urls = []
                self.b.close_tab(tg["id"])
            urls = [u for u in urls if not DANGEROUS_PAGES.search(u) and u.count("/") <= 3][:70]
            for u in urls:
                if time.time() - t0 > budget_s:
                    break
                ok, _h = self.b.new_tab(u)
                if not ok:
                    continue
                time.sleep(0.5)
                tg = next((x for x in self.b.targets() if x.get("url", "").rstrip("/") == u.rstrip("/")), None) or None
                if tg is None:
                    continue
                titles[u] = (tg.get("title") or "").strip()
                self.b.close_tab(tg["id"])
            cache = {"titles": titles, "when": time.time()}
            self._save_cache(cache)
        have = {(tuple(v.path), fold(v.label)) for v in cat.verbs}
        added = 0
        for u, title in titles.items():
            parts = [p.strip() for p in re.split(r"\s+[-–—|]\s+", title) if p.strip()]
            labels = []
            for p in parts[:2]:
                p = re.sub(r"^chrome://", "", p)
                if 2 <= len(p) <= 40 and p.lower() not in ("google chrome", "chrome"):
                    labels.append(p)
            for lab in labels:
                for path in (["Browser"], ["More"]):
                    key = (tuple(path), fold(lab))
                    if key in have:
                        continue
                    have.add(key)
                    cat.verbs.append(Verb(verb_id(path, lab), lab, list(path), "", f"opens {u}", True, False, "", 0, f"cdp-browser:goto:{u}", "menu_item", ["cdp"], "measured", "safe"))
                    added += 1
        # the profile picker is the browser's own 'Profile' bubble content ('Who's using Chrome?')
        for lab, u in (("Profile", "chrome://profile-picker/"),):
            for path in (["Browser"], ["More"]):
                if (tuple(path), fold(lab)) not in have:
                    cat.verbs.append(Verb(verb_id(path, lab), lab, list(path), "", f"opens {u}", True, False, "", 0, f"cdp-browser:goto:{u}", "menu_item", ["cdp"], "measured", "safe"))
                    added += 1
        cat.sources["cdp"] = cat.sources.get("cdp", 0) + added
        cat.verbs.sort(key=lambda v: (v.path, v.label.lower()))
        return {"destinations": len(titles), "verbs": added, "seconds": round(time.time() - t0, 1)}

    # ------------------------------------------------------------------------------------------------------------------ acting
    def owns(self, v: Verb) -> bool:''')
rep(r'''        kind = (v.aid or "").split(":", 1)[-1]
        ts = self.b.targets()''', r'''        kind = (v.aid or "").split(":", 1)[-1]
        if kind.startswith("goto:"):
            url = kind[5:]
            pg = self.current()
            if pg is None:
                return False, "no page"
            ok, how = pg.navigate(url)
            self._wait_loaded(pg)
            return ok, how
        ts = self.b.targets()''')
rep(r'''        self.current_id = ""
        self.harvested_pages: Dict[str, int] = {}''', r'''        self.current_id = ""
        self._ver = ""
        self.harvested_pages: Dict[str, int] = {}''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)

P2 = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s2 = io.open(P2, "r", encoding="utf-8").read()
old = '''                    self.report["phases"]["cdp"] = self.adapter.harvest(self.cat)
'''
new = '''                    self.report["phases"]["cdp"] = self.adapter.harvest(self.cat)
                    self.report["phases"]["cdp"]["destinations"] = self.adapter.harvest_destinations(self.cat)
'''
assert old in s2
s2 = s2.replace(old, new, 1)
ast.parse(s2)
io.open(P2, "w", encoding="utf-8", newline="\n").write(s2)
print("ok")
