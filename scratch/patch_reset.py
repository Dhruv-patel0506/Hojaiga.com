import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()
old = s[s.index("    def reset_ui(self) -> None:"):s.index("    @staticmethod\n    def _judge")]
new = r'''    def reset_ui(self) -> None:
        """Back to a clean state between procedures: expanded drop-downs collapsed, stray popups / dialogs closed, menus dismissed."""
        from . import menus as MN
        try:
            self.ex._hold_release()
        except Exception:
            pass
        try:
            for n in self.ex._all_nodes():
                if getattr(n, "expand_state", -1) == 1 and n.name and not n.offscreen:
                    MN.collapse(n, deadline_s=1.0)
        except Exception:
            pass
        try:
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

'''
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
