import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/probe.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''                s2 = s2 or snapshot(self.hwnd)
                why_not = diff_state(s0, s2)
                restored = not why_not
                if not restored:
                    time.sleep(0.5)
                    why_not = diff_state(s0, snapshot(self.hwnd))
                    restored = not why_not'''
new = '''                s2 = s2 or snapshot(self.hwnd)
                # WHO decides 'put back'? With a rich accessibility tree and a STRUCTURAL change, the tree does (controls, values, states, windows) and pixels only veto big drift: a toolbar
                # button keeps its focus highlight after an invoke (measured: 0.5 % of the cells) and that is not a changed application. A change that only showed up in pixels (visual_only), or an
                # application with almost no tree, is judged by pixels strictly - they are the only evidence there is.
                rich = len(s0.names) + len(s0.texts) >= 8
                tol = 0.02 if (rich and eff != "visual_only") else 0.003
                why_not = diff_state(s0, s2, tol)
                restored = not why_not
                if not restored:
                    time.sleep(0.5)
                    why_not = diff_state(s0, snapshot(self.hwnd), tol)
                    restored = not why_not'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("restoration tolerance depends on who the evidence is")
