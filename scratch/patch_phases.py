import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''                 max_attempts: int = 3, vision: bool = True, overlay_visible: bool = False, settle_s: float = 2.5):''',
    r'''                 max_attempts: int = 3, vision: bool = True, overlay_visible: bool = False, settle_s: float = 2.5, phases: Sequence[str] = ("guide",)):''')
rep(r'''        self.settle_s = settle_s
        self.prep = _Prep(spec.prep)''', r'''        self.settle_s = settle_s
        self.phases = tuple(phases)
        self.prep = _Prep(spec.prep)''')
rep(r'''from typing import Any, Callable, Dict, List, Optional, Tuple''', r'''from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple''')

rep(r'''    def run(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            if not self.start():
                self.report["result"] = "launch_failed"
                return self.finish()
            self.perceive()
            tasks = self.build_tasks()
            self.report["phases"]["guide"] = {"docs": self._guide_docs(), "runnable_procedures": len(tasks)}
            self.say(f"guide: {self._guide_docs()} documents, {len(tasks)} runnable procedures")
            for i, t in enumerate(tasks, 1):
                self.say(f"task {i}/{len(tasks)}: {t['goal'][:70]!r} ({len(t['steps'])} steps, {t['grounded']:.0%} grounded) [{t['cite'][:60]}]")
                self.tasks.append(self.run_task(t))
        except Exception as exc:''', r'''    # ----------------------------------------------------------------------------------------------- scenario 3 / probing on the owned window
    def phase_probe(self, budget_s: float = 90.0, max_probes: int = 25) -> Dict[str, Any]:
        """Hypothesis-driven probing of the application's own controls (safe verbs only, every one unwound and verified): each probe is a row in the history database -> training data."""
        from .probe import ProbeEngine
        pe = ProbeEngine(self.hwnd, self.fx, self.cat, self.spec.key, budget_s=budget_s, max_probes=max_probes, owned=True, history=self.history, learner=self.learner,
                         toolkit=self.profile.family if self.profile else "", archetype=self.arch.get("id", ""))
        self.reset_ui()
        with self.fx.focus_watch():
            rep = pe.run()
        by: Dict[str, int] = {}
        for r in rep.rules:
            by[r.effect] = by.get(r.effect, 0) + 1
        out = {"probes": len(rep.rules), "by_effect": by, "skipped": len(rep.skipped), "stopped": rep.stopped, "seconds": rep.seconds, "tainted": pe.tainted}
        self.say(f"probe: {out}")
        self.reset_ui()
        return out

    def phase_explore(self, actions: int = 4, budget_s: float = 150.0) -> Dict[str, Any]:
        """Idle permutation learning: for pairs of safe actions run A-then-B and B-then-A, record whether the ORDER matters, put the application back exactly (owned window only)."""
        from .explore import Explorer
        ex = Explorer(self.hwnd, self.fx, self.cat, self.spec.key, self.history, owned=True, idle_required_s=0.0, max_actions=actions, budget_s=budget_s, learner=self.learner,
                      toolkit=self.profile.family if self.profile else "")
        self.reset_ui()
        with self.fx.focus_watch():
            rep = ex.run(require_idle=False)
        out = rep.summary()
        out["all_restored"] = all(p.restored for p in rep.pairs)
        self.say(f"explore: {len(rep.pairs)} pairs, order matters {len(out['order_matters'])}, commute {len(out['commute'])}, restored={out['all_restored']}, stopped={rep.stopped!r}")
        self.reset_ui()
        return out

    def run(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            if not self.start():
                self.report["result"] = "launch_failed"
                return self.finish()
            self.perceive()
            if "guide" in self.phases:
                tasks = self.build_tasks()
                self.report["phases"]["guide"] = {"docs": self._guide_docs(), "runnable_procedures": len(tasks)}
                self.say(f"guide: {self._guide_docs()} documents, {len(tasks)} runnable procedures")
                for i, t in enumerate(tasks, 1):
                    self.say(f"task {i}/{len(tasks)}: {t['goal'][:70]!r} ({len(t['steps'])} steps, {t['grounded']:.0%} grounded) [{t['cite'][:60]}]")
                    self.tasks.append(self.run_task(t))
            if "probe" in self.phases:
                self.report["phases"]["probe"] = self.phase_probe()
            if "explore" in self.phases:
                self.report["phases"]["explore"] = self.phase_explore()
        except Exception as exc:''')
rep(r'''    ap.add_argument("--no-vision", action="store_true")
    a = ap.parse_args()
    if a.tasks:
        SPECS[a.app].max_tasks = a.tasks
    r = run_app(a.app, max_attempts=a.attempts, vision=not a.no_vision)''', r'''    ap.add_argument("--no-vision", action="store_true")
    ap.add_argument("--phases", default="guide", help="comma list of: guide, probe, explore")
    a = ap.parse_args()
    if a.tasks:
        SPECS[a.app].max_tasks = a.tasks
    r = run_app(a.app, max_attempts=a.attempts, vision=not a.no_vision, phases=tuple(x.strip() for x in a.phases.split(",") if x.strip()))''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
