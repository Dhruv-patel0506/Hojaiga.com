import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''    max_tasks: int = 30''', r'''    max_tasks: int = 30
    guide_key: str = ""            # the guide this run reads when it differs from `key` (two runs of Chrome: 'chrome' = profiles, 'chrome_tabs' = tabs, one guide)
    focus_rx: str = ""             # procedures whose goal / citation match come first (and the run is capped to them when there are enough)''')
rep(r'''    AppSpec("chrome", "chrome", 1, launcher="chrome_profile", prep="chrome_temp_profile", vision_verify=True, notes="owned Chrome with a throw-away profile directory (never the user's profile)"),''',
    r'''    AppSpec("chrome", "chrome", 1, launcher="chrome_profile", prep="chrome_temp_profile", vision_verify=True, focus_rx=r"profile|account|sync|customi[sz]e|theme|avatar|sign|homepage|startup|default browser|settings",
            notes="owned Chrome with a throw-away profile directory (never the user's profile); profile / settings procedures first"),
    AppSpec("chrome_tabs", "chrome", 2, guide_key="chrome", launcher="chrome_profile", prep="chrome_temp_profile", vision_verify=True, focus_rx=r"\btabs?\b|window|reload|back|forward|bookmark|history|search",
            notes="owned Chrome with a throw-away profile directory; tab / window / navigation procedures first"),''')
rep(r'''TIERS: Dict[int, List[str]] = {1: ["notepad", "mspaint", "chrome"], 2: ["winword", "powerpnt", "whatsapp", "systemsettings"], 3: ["discord", "code", "blender", "obs64"]}''',
    r'''TIERS: Dict[int, List[str]] = {1: ["notepad", "mspaint", "chrome"], 2: ["winword", "powerpnt", "whatsapp", "chrome_tabs", "systemsettings"], 3: ["discord", "code", "blender", "obs64"]}''')
rep(r'''        self.spec = spec
        self.history = history or HS.library()''', r'''        self.spec = spec
        self.gkey = spec.guide_key or spec.key
        self.adapter: Any = None
        self.history = history or HS.library()''')
# guide lookups use the guide key
rep(r'''        procs = GCARD.procedures(self.spec.key, self.index)''', r'''        procs = GCARD.procedures(self.gkey, self.index)''')
rep(r'''            return int(self.index.db.execute("SELECT COUNT(*) FROM docs WHERE app=?", (self.spec.key,)).fetchone()[0])''', r'''            return int(self.index.db.execute("SELECT COUNT(*) FROM docs WHERE app=?", (self.gkey,)).fetchone()[0])''')
# order by focus
rep(r'''        out.sort(key=lambda t: (-t["grounded"], len(t["steps"])))''', r'''        focus = re.compile(self.spec.focus_rx, re.I) if self.spec.focus_rx else None
        out.sort(key=lambda t: (0 if (focus and focus.search(t["goal"] + " " + t["cite"])) else 1, -t["grounded"], len(t["steps"])))''')
# adapter in perceive: after the executor exists
rep(r'''        self.ex.deny = NAV_FORBID_RX if self.spec.mode == "navigate" else DENY_RX''', r'''        self.ex.deny = NAV_FORBID_RX if self.spec.mode == "navigate" else DENY_RX
        port = int((self.report["phases"].get("launch") or {}).get("cdp_port") or 0)
        if port:
            try:
                from .adapters.cdp import CdpBrowser
                from .adapters.chromium import ChromiumAdapter
                br = CdpBrowser(port)
                if br.wait(20.0):
                    self.adapter = ChromiumAdapter(br, log=self.say)
                    self.report["phases"]["cdp"] = self.adapter.harvest(self.cat)
                    self.ex.adapter = self.adapter
                    self.say(f"cdp adapter: {self.report['phases']['cdp']}")
                    cat.save()
            except Exception as exc:
                self.report["phases"]["cdp"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
                self.say("cdp adapter failed: " + self.report["phases"]["cdp"]["error"])''')
# skip the UIA menu pass when the adapter reads the application instead
rep(r'''        try:
            from . import menus as MN
            mrep = MN.expand_menus(self.fx, self.hwnd, cat, self.ex._all_nodes, budget_s=45.0, history=self.history, toolkit=ds.profile.family, restore_popups=self._popups0)''', r'''        try:
            from . import menus as MN
            mrep = MN.expand_menus(self.fx, self.hwnd, cat, self.ex._all_nodes, budget_s=(8.0 if self.adapter else 45.0), history=self.history, toolkit=ds.profile.family, restore_popups=self._popups0)''')
# reset: one blank tab
rep(r'''        try:
            self.fx.close_popups(self._popups0)
        except Exception:
            pass
        try:
            for _ in range(2):
                self.fx.key("escape")
                time.sleep(0.15)
        except Exception:
            pass
        time.sleep(0.3)
''', r'''        try:
            self.fx.close_popups(self._popups0)
        except Exception:
            pass
        try:
            for _ in range(2):
                self.fx.key("escape")
                time.sleep(0.15)
        except Exception:
            pass
        if self.adapter is not None:
            try:
                ts = self.adapter.b.targets()
                for t in ts[:-1]:
                    self.adapter.b.close_tab(t["id"])
                self.adapter.current_id = ""
                pg = self.adapter.current()
                if pg is not None and not pg.title_url()[1].startswith("about:blank"):
                    pg.navigate("about:blank")
            except Exception:
                pass
        time.sleep(0.3)
''')
rep(r'''        try:
            if self._revealed and self.ex is not None:''', r'''        try:
            if self.adapter is not None:
                self.adapter.close()
        except Exception:
            pass
        try:
            if self._revealed and self.ex is not None:''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
