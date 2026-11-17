import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''    def run_task(self, t: Dict[str, Any]) -> TaskResult:''', r'''    def evidence(self, tag: str) -> str:
        """What the screen looked like when something failed: a picture of the window with its pop-ups, and the windows / controls the tree showed. Kept beside the report."""
        try:
            from . import capture as CAP
            from core_organs import headless_input as hin
            d = os.path.join(OUT_DIR, "evidence", f"{self.spec.key}_{self.stamp}")
            os.makedirs(d, exist_ok=True)
            base = os.path.join(d, re.sub(r"[^A-Za-z0-9_.-]+", "_", tag)[:60])
            pops = hin.popup_windows(self.hwnd)[:6]
            fr = CAP.grab_composite(self.hwnd, pops)
            if fr is not None:
                fr.image.save(base + ".png")
            wins = [(w, hin._class_name(w), hin.safe_window_text(w, 100)) for w in hin.process_windows(self.hwnd, include_hidden=False)]
            nodes = self.ex._all_nodes()
            with open(base + ".json", "w", encoding="utf-8") as fh:
                json.dump({"windows": wins, "popups": pops, "nodes": [(n.ctype[:-7], n.name[:40], n.expand_state, n.rect) for n in nodes if n.name and not n.offscreen][:80]}, fh, ensure_ascii=False, default=str)
            return base + ".png"
        except Exception:
            return ""

    def run_task(self, t: Dict[str, Any]) -> TaskResult:''')
rep(r'''            tr.attempts.append(at)
            self.say(f"  attempt {n}: {at.status} ({at.done}/{at.steps} steps){' - ' + at.why[:150] if at.why else ''}")''', r'''            tr.attempts.append(at)
            self.say(f"  attempt {n}: {at.status} ({at.done}/{at.steps} steps){' - ' + at.why[:150] if at.why else ''}")
            if at.status not in ("ok", "blocked"):
                at.results.append({"evidence": self.evidence(f"{len(self.tasks) + 1:02d}_{t['goal']}_a{n}")})''')
rep(r'''        self.prep = _Prep(spec.prep)
        self.hwnd = 0''', r'''        self.prep = _Prep(spec.prep)
        self.stamp = time.strftime("%Y%m%d_%H%M%S")
        self.hwnd = 0''')
rep(r'''        path = os.path.join(OUT_DIR, f"{self.spec.key}_{time.strftime('%Y%m%d_%H%M%S')}.json")''', r'''        path = os.path.join(OUT_DIR, f"{self.spec.key}_{self.stamp}.json")''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
