import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:80]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


EX = "D:/new_automation/All codes/core_organs/professor/executor.py"
patch(EX, [
    ('''        self.skills, self.guide_index, self.archetype, self.app_version = skills, guide_index, archetype, app_version
''', '''        self.skills, self.guide_index, self.archetype, self.app_version = skills, guide_index, archetype, app_version
        self.deny: Optional["re.Pattern"] = None                  # an application-level policy: verbs matching this are NEVER performed without a human yes (Save As in a throw-away document, Send in a messenger)
'''),
    ('''        hum = safety.needs_human(v.label, " ".join(v.path)) and not (self.owned and cls == "commit")
''', '''        hum = safety.needs_human(v.label, " ".join(v.path)) and not (self.owned and cls == "commit")
        if self.deny is not None and self.deny.search(v.label + " " + " ".join(v.path)):
            hum, cls = True, ("sensitive" if cls == "safe" else cls)
'''),
])

AR = "D:/new_automation/All codes/core_organs/professor/apprun.py"
patch(AR, [
    ('''NAV_FORBID_RX = re.compile(''', '''DENY_RX = re.compile(r"\\b(save|save as|save all|export|print|publish|share|send|email|upload|sign in|log ?in|sign out|log ?out|uninstall|delete|erase|format|restore defaults|reset)\\b", re.I)
NAV_FORBID_RX = re.compile('''),
    ('''        self.fx = Effector(self.hwnd, allow_input=True, owned=True)
''', '''        self.fx = Effector(self.hwnd, allow_input=True, owned=True)
'''),
    ('''        try:
            self.history.register_app(self.spec.key, self.spec.name, "", ds.profile.family, self.spec.tier, self._guide_docs(), len(cat.verbs), self.spec.notes)
        except Exception:
            pass
''', '''        self.ex.deny = NAV_FORBID_RX if self.spec.mode == "navigate" else DENY_RX
        # the deep tree: open every opener once (owned window), read its items, close it - a guide speaks in menu paths the tree alone cannot show
        try:
            from . import menus as MN
            mrep = MN.expand_menus(self.fx, self.hwnd, cat, self.ex._all_nodes, budget_s=45.0, history=self.history, toolkit=ds.profile.family, restore_popups=self._popups0)
            self.report["phases"]["menus"] = mrep
            self.say(f"menus: {mrep['opened']}/{mrep['openers']} openers opened, {mrep['items']} items read ({mrep['seconds']}s)" + (f"; problems {mrep['failed'][:3]}" if mrep["failed"] else ""))
            cat.save()
            self.report["phases"]["catalog_after_menus"] = cat.summary()
        except Exception as exc:
            self.report["phases"]["menus"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}", "trace": traceback.format_exc()[-600:]}
            self.say("menu expansion failed: " + self.report["phases"]["menus"]["error"])
        try:
            self.history.register_app(self.spec.key, self.spec.name, "", ds.profile.family, self.spec.tier, self._guide_docs(), len(cat.verbs), self.spec.notes)
        except Exception:
            pass
'''),
])
print("ok")
