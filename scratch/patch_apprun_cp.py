import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


# ---- ctor: where the run's files go
rep('''max_attempts: int = 3, vision: bool = True, overlay_visible: bool = False, settle_s: float = 2.5, phases: Sequence[str] = ("guide",), echo: bool = True):''',
    '''max_attempts: int = 3, vision: bool = True, overlay_visible: bool = False, settle_s: float = 2.5, phases: Sequence[str] = ("guide",), echo: bool = True,
                 out_dir: Optional[str] = None):''')
rep('''        self.run_dir = os.path.join(OUT_DIR, f"{spec.key}_{self.stamp}")                       # created when the first picture / report is written''',
    '''        self.run_dir = out_dir or os.path.join(OUT_DIR, f"{spec.key}_{self.stamp}")             # created when the first picture / report is written
        self._cp_n = 0''')

# ---- the checkpoint picture
rep('''    def shoot_scan(self, tag: str, sm: Any, img: Any) -> None:''', '''    def checkpoint(self, tag: str) -> str:
        """A plain picture of the application (its window plus open pop-ups, as it really looks) at a named point of the run, kept in checkpoints/ with the others. Never raises."""
        try:
            from . import capture as CAP
            from core_organs import headless_input as hin
            if not self.hwnd:
                return ""
            fr = CAP.grab_composite(self.hwnd, hin.popup_windows(self.hwnd)[:6])
            if fr is None:
                return ""
            self._cp_n += 1
            os.makedirs(os.path.join(self.run_dir, "checkpoints"), exist_ok=True)
            name = f"cp_{self._cp_n:02d}_{re.sub(r'[^A-Za-z0-9_.-]+', '_', tag)[:50]}.png"
            fr.image.convert("RGB").save(os.path.join(self.run_dir, "checkpoints", name))
            self.report.setdefault("checkpoints", []).append({"n": self._cp_n, "tag": tag, "file": "checkpoints/" + name, "at_s": round(time.time() - self._t_run, 1)})
            return name
        except Exception:
            return ""

    def shoot_scan(self, tag: str, sm: Any, img: Any) -> None:''')
rep('''        self._surf = 0
        self._no_reveal = False''', '''        self._surf = 0
        self._no_reveal = False
        self._t_run = time.time()''')

# ---- hooks: after launch, after the scan, after every procedure, at the end
rep('''        self.report["phases"]["perceive_s"] = round(time.time() - t0, 1)''', '''        self.report["phases"]["perceive_s"] = round(time.time() - t0, 1)
        self.checkpoint("after_scan_home")''')
rep('''                for i, t in enumerate(tasks, 1):
                    self.ui.task_start(i, len(tasks), t["goal"], len(t["steps"]), t["grounded"])
                    self.tasks.append(self.run_task(t))''', '''                for i, t in enumerate(tasks, 1):
                    self.ui.task_start(i, len(tasks), t["goal"], len(t["steps"]), t["grounded"])
                    self.tasks.append(self.run_task(t))
                    self.checkpoint(f"task{i:02d}_{self.tasks[-1].final}_{t['goal']}")''')
rep('''        self.report["seconds"] = round(time.time() - t0, 1)
        return self.finish()

    def finish(self)''', '''        self.checkpoint("end_of_run")
        self.report["seconds"] = round(time.time() - t0, 1)
        return self.finish()

    def finish(self)''')
rep('''        self.ui.banner(f"{self.spec.key} · tier {self.spec.tier}"''', '''        self._t_run = t0
        self.ui.banner(f"{self.spec.key} · tier {self.spec.tier}"''')
rep('''        self.report["phases"]["park"] = getattr(self.bg, "mode", "?")''', '''        self.report["phases"]["park"] = getattr(self.bg, "mode", "?")
        self.checkpoint("launched")''')

ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
