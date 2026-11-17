import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, (path[-34:], old[:90])
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


B = "D:/new_automation/All codes/core_organs/professor/"

# ---------------------------------------------------------------- pointing: Fitts parameters can be learnt (ml.motor)
patch(B + "pointing.py", [
    ('''def fitts_seconds(distance: float, width: float, a: float = 0.10, b: float = 0.12) -> float:
    """Fitts's law: movement time MT = a + b * log2(D / W + 1). Far targets take longer, SMALL targets take longer (a hand slows to land on them). Clamped to a believable range."""
    w = max(4.0, float(width))''', '''FITTS_A, FITTS_B = 0.10, 0.12                        # the textbook prior; ml.motor.MotorModel refines it from measured movements (set_fitts)


def set_fitts(a: float, b: float) -> None:
    global FITTS_A, FITTS_B
    FITTS_A, FITTS_B = float(a), float(b)


def fitts_seconds(distance: float, width: float, a: Optional[float] = None, b: Optional[float] = None) -> float:
    """Fitts's law: movement time MT = a + b * log2(D / W + 1). Far targets take longer, SMALL targets take longer (a hand slows to land on them). Clamped to a believable range."""
    a = FITTS_A if a is None else a
    b = FITTS_B if b is None else b
    w = max(4.0, float(width))'''),
])

# ---------------------------------------------------------------- executor: learner-ordered routes, features in every logged attempt, training while it runs
patch(B + "executor.py", [
    ('''                 history: Any = None):
        self.hwnd, self.fx, self.catalog, self.sm, self.brain, self.owned = hwnd, effector, catalog, sm, brain, owned''', '''                 history: Any = None, learner: Any = None, toolkit: str = ""):
        self.hwnd, self.fx, self.catalog, self.sm, self.brain, self.owned = hwnd, effector, catalog, sm, brain, owned
        self.learner = learner                                   # professor.ml.Learner: re-orders routes by learnt P(ok) and trains while this runs
        self.toolkit = toolkit                                   # the application's toolkit family (professor.interaction): a feature of every logged action'''),
    ('''        if dry_run or not self.fx.allowed:
            return self._run(rep, dry_run, approve, settle_s)
        with self.fx.focus_watch():
            self._run(rep, dry_run, approve, settle_s)
        self._learn(rep, learn)
        return rep''', '''        if dry_run or not self.fx.allowed:
            return self._run(rep, dry_run, approve, settle_s)
        import contextlib
        with (self.learner.training() if self.learner is not None else contextlib.nullcontext()), self.fx.focus_watch():
            self._run(rep, dry_run, approve, settle_s)
        self._learn(rep, learn)
        return rep'''),
    ('''            routes = self.routes_for(v, st.text) if v else []
            if st.prefer:                                                                        # the route that worked last time goes first
                routes.sort(key=lambda r: 0 if r.label() == st.prefer else 1)''', '''            routes = self.routes_for(v, st.text) if v else []
            if st.prefer:                                                                        # the route that worked last time goes first
                routes.sort(key=lambda r: 0 if r.label() == st.prefer else 1)
            elif self.learner is not None and v is not None and len(routes) > 1:                 # otherwise the LEARNT order (it can only re-order routes that exist and are allowed)
                try:
                    ctx = {"app": self.app_key, "toolkit": self.toolkit, "role": v.role, "safety": st.safety, "source": st.source, "archetype": self.archetype, "label": v.label,
                           "has_shortcut": bool(v.shortcut), "n_controls": len(self.catalog.verbs)}
                    order = [k for k, _s in self.learner.rank_routes(ctx, [r.kind for r in routes])]
                    routes.sort(key=lambda r: order.index(r.kind) if r.kind in order else 99)
                except Exception:
                    pass'''),
    ('''            src = "skill" if st.source.startswith("skill") else ("guide" if st.source == "guide" else "exec")''', '''            src = "skill" if st.source.startswith("skill") else ("guide" if st.source == "guide" else "exec")
            role = v.role if v else ""'''),
    ('''                             st.verb or "", r.label(), s0.sig, f"{len(s0.names)} controls", s1.sig, d.summary(), d.effect(), d.effect() != "no_effect", None, v.aid if v else "", {"how": how, "cite": st.cite})''',
     '''                             st.verb or "", r.label(), s0.sig, f"{len(s0.names)} controls", s1.sig, d.summary(), d.effect(), d.effect() != "no_effect", None, v.aid if v else "",
                             {"how": how, "cite": st.cite, "shortcut": bool(v and v.shortcut)}, toolkit=self.toolkit, archetype=self.archetype, role=role, safety=st.safety)'''),
])

# ---------------------------------------------------------------- probe: same features, training while it runs
patch(B + "probe.py", [
    ('''                 history: Any = None):
        self.hwnd, self.fx, self.catalog, self.app_key = hwnd, effector, catalog, app_key''', '''                 history: Any = None, learner: Any = None, toolkit: str = "", archetype: str = ""):
        self.hwnd, self.fx, self.catalog, self.app_key = hwnd, effector, catalog, app_key
        self.learner, self.toolkit, self.archetype = learner, toolkit, archetype'''),
    ('''        with self.fx.focus_watch():
            return self._run(hyps, t_start)''', '''        import contextlib
        with (self.learner.training() if self.learner is not None else contextlib.nullcontext()), self.fx.focus_watch():
            return self._run(hyps, t_start)'''),
    ('''rule.effect != "no_effect" and not rule.how.startswith("not delivered"), rule.restored, h.aid, {"unwind": rule.unwind, "restore_why": rule.restore_why, "benign": rule.benign})''',
     '''rule.effect != "no_effect" and not rule.how.startswith("not delivered"), rule.restored, h.aid, {"unwind": rule.unwind, "restore_why": rule.restore_why, "benign": rule.benign},
                             toolkit=self.toolkit, archetype=self.archetype, role=h.role, safety=safety.classify(h.verb))'''),
])

# ---------------------------------------------------------------- sweeper: tree-labelled scans train the candidate model; the model can drop near-certain noise where there is no tree
patch(B + "sweeper.py", [
    ('''    yolo: bool = field(default_factory=lambda: os.environ.get("HOJAIGA_PROF_YOLO_DEFAULT", "0") == "1")''', '''    ml_observe: bool = field(default_factory=lambda: os.environ.get("HOJAIGA_PROF_ML_OBSERVE", "0") == "1")   # a scan of a window WITH a tree labels the candidates -> trains professor.ml.CandidateModel
    ml_filter: bool = field(default_factory=lambda: os.environ.get("HOJAIGA_PROF_ML_FILTER", "0") == "1")     # where there is no tree: drop the candidates the model is nearly sure are noise
    yolo: bool = field(default_factory=lambda: os.environ.get("HOJAIGA_PROF_YOLO_DEFAULT", "0") == "1")'''),
    ('''    sm.timings["candidates"] = round(time.time() - ts, 2)
    sm.timings.update({f"cv.{k}": v for k, v in cs.timings.items() if k != "total"})
''', '''    if opt.ml_observe or opt.ml_filter:
        try:
            from .ml import get_learner
            lrn = get_learner()
            ink_ml = CV.ink_mask(np.asarray(img.convert("L")), scale)
            if opt.ml_observe and len([e for e in uia_els if e.label]) >= 12:
                info_ml = lrn.observe_scan(cs.candidates, img.size, ink_ml, [e.bbox for e in uia_els if e.label])
                sm.tiers_used.append(f"ml:learned {info_ml.get('examples', 0)}")
            elif opt.ml_filter and len(uia_els) < 15:
                kept, dropped = lrn.candidate_filter(cs.candidates, img.size, ink_ml)
                if dropped:
                    cs.candidates = kept
                    sm.tiers_used.append(f"ml:-{dropped}")
        except Exception as exc:
            sm.tiers_skipped.append(f"ml:{type(exc).__name__}")
    sm.timings["candidates"] = round(time.time() - ts, 2)
    sm.timings.update({f"cv.{k}": v for k, v in cs.timings.items() if k != "total"})
'''),
])
print("ml hooks patched")
