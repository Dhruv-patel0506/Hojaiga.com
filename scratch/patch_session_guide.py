import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, old[:80]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


BASE = "D:/new_automation/All codes/core_organs/professor/"

patch(BASE + "session.py", [
    ("interactive: bool = True, use_catalog: bool = True, watch_state: bool = True, spotlight: bool = False):",
     "interactive: bool = True, use_catalog: bool = True, watch_state: bool = True, spotlight: bool = False, find_guide: bool = True, guide_web: Optional[bool] = None):"),
    ("        self.use_catalog, self.watch_state, self.spotlight = use_catalog, watch_state, spotlight\n",
     "        self.use_catalog, self.watch_state, self.spotlight = use_catalog, watch_state, spotlight\n"
     "        self.find_guide, self.guide_web = find_guide, guide_web                 # guide_web None = follow HOJAIGA_GUIDE_WEB (off unless you turned it on)\n"
     "        self._guide_threads: Dict[str, threading.Thread] = {}\n"
     "        self.guide_reports: Dict[str, Dict[str, Any]] = {}\n"),
    ("""            cat, arch = frame_for(sm, hwnd or sm.hwnd, self.brain, harvest=True)
            self.frames[sm.app_key] = (cat, arch)
            return cat, arch""", """            cat, arch = frame_for(sm, hwnd or sm.hwnd, self.brain, harvest=True)
            self.frames[sm.app_key] = (cat, arch)
            self._ensure_guide(sm, hwnd or sm.hwnd)
            return cat, arch"""),
    ("""    def element_under_cursor(self, sm: ScreenModel) -> Optional[UIElement]:""", """    def _ensure_guide(self, sm: ScreenModel, hwnd: int) -> None:
        \"\"\"Find + index the application's user guide in the BACKGROUND (install folder; the web only if you enabled it). The lesson never waits for it: whatever is indexed by the time a
        question is planned is used, with citations.\"\"\"
        key = sm.app_key
        if not self.find_guide or not hwnd or not key or key == "unknown" or key in self._guide_threads:
            return

        def work() -> None:
            try:
                from .knowledge import guide_finder as GF
                ident = GF.identity_of(hwnd, app_key=key)
                self.guide_reports[key] = GF.discover(ident, web=self.guide_web, budget_s=90.0)
            except Exception as exc:
                self.guide_reports[key] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}

        th = threading.Thread(target=work, name=f"professor-guide-{key}", daemon=True)
        self._guide_threads[key] = th
        th.start()

    def element_under_cursor(self, sm: ScreenModel) -> Optional[UIElement]:"""),
])

patch(BASE + "teacher.py", [
    ("""        if routes:
            parts += ["KNOWN ROUTES (measured from this application):", routes_text(routes)]
        try:
            from .knowledge import manual_rag""", """        try:
            from . import skills as SK
            if os.path.isfile(SK.SKILL_DB):
                wf = SK.library().prompt_lines(question, sm.app_key)
                if wf:
                    parts += ["VERIFIED WORKFLOWS (these exact sequences worked on this application before):", wf]
        except Exception:
            pass
        if routes:
            parts += ["KNOWN ROUTES (measured from this application):", routes_text(routes)]
        try:
            from .knowledge import manual_rag"""),
    ("import re\nimport time\n", "import os\nimport re\nimport time\n"),
])
print("session + teacher guide integration patched")
