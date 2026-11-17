import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


# --- parse: a bold term after 'the' is a FIELD name, not text to type
patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
    (r'''        if tm.group(2) and re.search(r"(?:\bin|\binto|\bto|\bon|\bfrom)\s+(?:the\s+)?$", raw[:tm.start(2)].rstrip("* ").rstrip() + " ", re.I):
            typed = ""''', r'''        if tm.group(2) and re.search(r"(?:(?:\bin|\binto|\bto|\bon|\bfrom)\s+(?:the\s+)?|\bthe\s+)$", raw[:tm.start(2)].rstrip("* ").rstrip() + " ", re.I):
            typed = ""                                                    # 'enter the **Width**' / 'in the **Name** box': a bold term after 'the' names the FIELD'''),
])

# --- apprun: launch-goal skip, reveal hidden UI
patch("D:/new_automation/All codes/core_organs/professor/apprun.py", [
    (r'''NAV_FORBID_RX = re.compile(''', r'''LAUNCH_GOAL_RX = re.compile(r"^\s*(?:\d+[.)]\s*)?(?:how (?:do i|to) )?(?:open|start|launch|run|update|install|download|get|find)\b.*\b(?:paint|notepad|word|powerpoint|chrome|app|application|start menu|taskbar|microsoft store|windows)\b|\bfrom the (?:start menu|taskbar)\b|\bstart menu\b", re.I)
REVEAL_RX = re.compile(r"^(?:show|expand|unhide|pin|open)\s+(?:the\s+)?(?:toolbar|tool bar|ribbon|tools|command bar|side ?bar|panel|properties|options bar)\b", re.I)
NAV_FORBID_RX = re.compile('''),
    (r'''            if len(steps) < len(p["steps"]) and all(s.chord or s.action in ("press", "type") for s in steps):
                skip(p, "describes starting the application (Start menu), not using it")
                continue''', r'''            if len(steps) < len(p["steps"]) and all(s.chord or s.action in ("press", "type") for s in steps):
                skip(p, "describes starting the application (Start menu), not using it")
                continue
            if LAUNCH_GOAL_RX.search(p["goal"]) and not any(s.path for s in steps):
                skip(p, "describes launching / updating the application, not using it")
                continue'''),
    (r'''    # ----------------------------------------------------------------------------------------------- tasks
    def build_tasks(self)''', r'''    # ----------------------------------------------------------------------------------------------- hidden UI
    def reveal_ui(self) -> List[str]:
        """A toolbar / ribbon / side panel that is collapsed hides the very controls a guide talks about ('click Select'). Show it - and remember how to put it back (the application keeps
        such a preference in the user's own settings, so the run leaves it as it found it)."""
        done: List[str] = []
        for n in self.ex._all_nodes():
            if n.role == "button" and n.name and REVEAL_RX.match(n.name.strip()) and not n.offscreen and n.enabled and not safety_blocked(n.name):
                ok, how = self.fx.node(n)
                if ok:
                    done.append(n.name)
                    self._revealed.append(n.name)
                    time.sleep(0.8)
        if done:
            try:
                self.sm, _i, _f = self.sess.look(self.hwnd, mode="quick", force=True)
                self.ex.refresh_catalog()
            except Exception:
                pass
        return done

    def unreveal_ui(self) -> List[str]:
        undone: List[str] = []
        for name in self._revealed:
            opposite = re.sub(r"^(show|expand|unhide|pin|open)\b", lambda m: {"show": "hide", "expand": "collapse", "unhide": "hide", "pin": "unpin", "open": "close"}[m.group(1).lower()], name, flags=re.I)
            for n in self.ex._all_nodes():
                if n.role == "button" and n.name and fold(n.name) == fold(opposite) and not n.offscreen and n.enabled:
                    ok, how = self.fx.node(n)
                    if ok:
                        undone.append(n.name)
                    break
        self._revealed = []
        return undone

    # ----------------------------------------------------------------------------------------------- tasks
    def build_tasks(self)'''),
    (r'''        self.ledger: List[Dict[str, Any]] = []
''', r'''        self.ledger: List[Dict[str, Any]] = []
        self._revealed: List[str] = []
'''),
    (r'''from . import config as CFG
''', r'''from . import config as CFG
from .schema import fold
from . import safety


def safety_blocked(label: str) -> bool:
    return safety.classify(label) in ("unsafe", "sensitive")
'''),
    # perceive: reveal a collapsed toolbar before the menus are read
    (r'''        self.ex.deny = NAV_FORBID_RX if self.spec.mode == "navigate" else DENY_RX''', r'''        self.ex.deny = NAV_FORBID_RX if self.spec.mode == "navigate" else DENY_RX
        try:
            shown = self.reveal_ui()
            if shown:
                self.report["phases"]["revealed"] = shown
                self.say(f"revealed hidden UI: {shown}; catalog now {len(self.cat.verbs)} verbs")
        except Exception as exc:
            self.say("reveal failed: " + type(exc).__name__)'''),
    (r'''        if self.hwnd:
            try:
                self.report["phases"]["close"] = SC.close_owned(self.hwnd)''', r'''        try:
            if self._revealed and self.ex is not None:
                self.report["phases"]["unrevealed"] = self.unreveal_ui()
        except Exception:
            pass
        if self.hwnd:
            try:
                self.report["phases"]["close"] = SC.close_owned(self.hwnd)'''),
])
print("ok")
