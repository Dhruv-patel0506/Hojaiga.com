import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


i0 = s.index("    def build_tasks(self)")
i1 = s.index("    # ----------------------------------------------------------------------------------------------- doing")
new = r'''    def build_tasks(self) -> List[Dict[str, Any]]:
        """The guide's procedures that can be attempted here: the first step grounds in the live catalog (or at least half of the steps do). Every procedure the guide has is accounted for in
        `self.ledger` - attempted, or skipped WITH the reason."""
        from .knowledge import guide_card as GCARD, guide_steps as GS
        procs = GCARD.procedures(self.spec.key, self.index)
        name_words = {w for w in re.findall(r"[a-z0-9]+", (self.spec.name + " " + self.spec.key).lower()) if len(w) > 2}
        out: List[Dict[str, Any]] = []
        self.ledger = []

        def skip(p: Dict[str, Any], why: str, cover: float = 0.0) -> None:
            self.ledger.append({"goal": p["goal"], "cite": p["cite"], "source": p["source"], "steps": len(p["steps"]), "grounded": round(cover, 3), "disposition": "skipped", "reason": why})
            try:
                self.history.log_guide_run(self.spec.key, p["source"], p["cite"], p["goal"], len(p["steps"]), cover, False, False, "skipped: " + why, 0)
            except Exception:
                pass

        for p in procs:
            steps = [s for s in p["steps"] if not (s.action == "open" and s.target and {w for w in re.findall(r"[a-z0-9]+", s.target.lower())} <= name_words)]
            if not steps:
                skip(p, "only says to open the application")
                continue
            if self.spec.mode == "navigate" and (NAV_FORBID_RX.search(p["goal"]) or any(NAV_FORBID_RX.search(s.raw) for s in steps)):
                skip(p, "navigate mode: the procedure changes or sends something")
                continue
            g = GS.ground(steps, self.cat)
            ok = [x for x in g if x.how != "none"]
            cover = len(ok) / len(g)
            if not ok:
                skip(p, "no step names a control that exists in this application's interface (" + "; ".join((x.note or x.step.raw)[:60] for x in g[:2]) + ")", cover)
                continue
            if cover < 0.5 and g[0].how == "none":                       # a procedure whose FIRST step grounds can ground the rest just in time (dialog fields appear only after the dialog opens)
                skip(p, f"its first step ('{g[0].step.target or g[0].step.raw[:30]}') matches no control and only {cover:.0%} of the steps do", cover)
                continue
            out.append({"goal": p["goal"], "cite": p["cite"], "source": p["source"], "steps": steps, "grounded": round(cover, 3)})
        out.sort(key=lambda t: (-t["grounded"], len(t["steps"])))
        seen, uniq = set(), []
        for t in out:
            k = (t["goal"].lower(), t["steps"][0].target.lower())
            if k in seen:
                self.ledger.append({"goal": t["goal"], "cite": t["cite"], "source": t["source"], "steps": len(t["steps"]), "grounded": t["grounded"], "disposition": "skipped", "reason": "duplicate of a procedure already queued"})
                continue
            seen.add(k)
            uniq.append(t)
        for t in uniq[self.spec.max_tasks:]:
            self.ledger.append({"goal": t["goal"], "cite": t["cite"], "source": t["source"], "steps": len(t["steps"]), "grounded": t["grounded"], "disposition": "skipped", "reason": "beyond the per-run task cap"})
        return uniq[: self.spec.max_tasks]

'''
s = s[:i0] + new + s[i1:]
rep(r'''        self.tasks: List[TaskResult] = []
''', r'''        self.tasks: List[TaskResult] = []
        self.ledger: List[Dict[str, Any]] = []
''')
rep(r'''        self.report["tasks"] = [t.to_dict() for t in self.tasks]''', r'''        done = {(t.goal, t.cite): t for t in self.tasks}
        for row in self.ledger:
            t = done.get((row["goal"], row["cite"]))
            if t is not None and row["disposition"] != "skipped":
                row["disposition"] = t.final
        for t in self.tasks:
            if not any(r["goal"] == t.goal and r["cite"] == t.cite for r in self.ledger):
                self.ledger.append({"goal": t.goal, "cite": t.cite, "source": t.source, "steps": t.steps_in_guide, "grounded": t.grounded, "disposition": t.final, "reason": (t.attempts[-1].why if t.attempts else "")})
        self.report["ledger"] = self.ledger
        self.report["ledger_counts"] = {k: sum(1 for r in self.ledger if r["disposition"] == k) for k in sorted({r["disposition"] for r in self.ledger})}
        self.report["tasks"] = [t.to_dict() for t in self.tasks]''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
