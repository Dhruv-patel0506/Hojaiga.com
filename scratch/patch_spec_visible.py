import ast
import io

R = "D:/new_automation/All codes/core_organs/professor/"


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:100]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch(R + "apprun.py", [
    ('''SPECS: Dict[str, AppSpec] = load_specs()
TIERS: Dict[int, List[str]] = {}
for _s in SPECS.values():
    TIERS.setdefault(_s.tier, []).append(_s.key)
''', '''SPECS: Dict[str, AppSpec] = load_specs()
TIERS: Dict[int, List[str]] = {}
for _s in SPECS.values():
    TIERS.setdefault(_s.tier, []).append(_s.key)


def spec_for(name: str, mode: str = "full") -> AppSpec:
    """ANY application, by key or by name. A listed one keeps its plan (tier, scenario, focus); anything else gets a spec made from what the name is: the guide corpus catalog maps a process / product name
    to its guide key, otherwise the name itself is the key - the launcher then resolves it from the machine (Start menu, packages, install folders) and the guide finder looks for its guide."""
    n = (name or "").strip()
    if n in SPECS:
        return SPECS[n]
    low = n.lower()
    for s in SPECS.values():
        if low in (s.name.lower(), s.key.lower()):
            return s
    key, display, tier = re.sub(r"[^a-z0-9]+", "", low) or "app", n, 0
    try:
        from .knowledge import guide_corpus as GCP
        for a in GCP.load_catalog():
            procs = [p.lower().rsplit(".", 1)[0] for p in a.get("processes", [])]
            if low in (a["key"].lower(), a["name"].lower()) or low in procs:
                key, display, tier = a["key"], a["name"], int(a.get("tier", 0) or 0)
                break
    except Exception:
        pass
    if key in SPECS:
        return SPECS[key]
    return AppSpec(key=key, name=display, tier=tier, mode=mode, vision_verify=True, notes="made from the name (not in the test plan)")


class _Visible:
    """Stands in for BackgroundSession when the window is deliberately left on screen (a demonstration with the virtual cursor shown)."""
    mode = "visible"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def lay_out(self, settle_s: float = 1.2) -> bool:
        return False
'''),
    ('''phases: Sequence[str] = ("guide",), echo: bool = True,
                 out_dir: Optional[str] = None):''', '''phases: Sequence[str] = ("guide",), echo: bool = True,
                 out_dir: Optional[str] = None, visible: bool = False):'''),
    ('''        self.vision = vision
        self.overlay_visible = overlay_visible''', '''        self.vision = vision
        self.visible = visible                                                 # leave the window on screen (so the virtual cursor can be watched) instead of parking it
        self.overlay_visible = overlay_visible'''),
    ('''        self.bg = bw.BackgroundSession(self.hwnd)
        self.bg.__enter__()''', '''        if self.visible:
            import ctypes
            u = ctypes.windll.user32
            u.ShowWindow(self.hwnd, 9)                                          # SW_RESTORE
            u.SetWindowPos(self.hwnd, 0, 80, 60, 1180, 780, 0x0010 | 0x0040)      # SWP_NOACTIVATE | SWP_SHOWWINDOW
            self.bg = _Visible()
        else:
            self.bg = bw.BackgroundSession(self.hwnd)
        self.bg.__enter__()'''),
    ('''        self.report["path"] = path
        self.ui.summary(''', '''        self.report["path"] = path
        try:                                                                   # the guide's procedures, analysed against what the run saw, with this run's result on each
            from . import workflows as WF
            WF.build(self.spec.key, ix=self.index, catalog=self.cat, guide_key=self.gkey)
            doc = WF.record_run(self.spec.key, self.report)
            for ext in ("json", "md"):
                shutil.copy(WF.path_of(self.spec.key, ext), os.path.join(self.run_dir, f"workflows.{ext}"))
            self.report["workflows"] = {"file": WF.path_of(self.spec.key, "md"), "count": len(doc["workflows"]) if doc else 0, "by_status": (doc or {}).get("summary", {}).get("by_status", {})}
        except Exception as exc:
            self.report["workflows_error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
        self.ui.summary('''),
    ("import re\nimport time\nimport traceback\n", "import re\nimport shutil\nimport time\nimport traceback\n"),
])

patch(R + "checkpoints.py", [
    ('''    specs_all = [AR.SPECS[k] for k in AR.SPECS]
    want = [AR.SPECS[k] for k in apps] if apps else [sp for sp in specs_all if sp.tier == tier]''', '''    specs_all = [AR.SPECS[k] for k in AR.SPECS]
    want = [AR.spec_for(k) for k in apps] if apps else [sp for sp in specs_all if sp.tier == tier]
    specs_all += [sp for sp in want if sp.key not in AR.SPECS]                      # an application named on the command line joins the checklist'''),
    ('''    keys = [k.strip() for k in a.apps.split(",") if k.strip()]
    bad = [k for k in keys if k not in AR.SPECS]
    if bad:
        print("unknown application key(s):", bad, "- known:", sorted(AR.SPECS))
        return 2
''', '''    keys = [k.strip() for k in a.apps.split(",") if k.strip()]                  # any application: a listed key, or any name the machine can resolve (e.g. --apps "visual studio code,calculator")
'''),
    ('''    ap.add_argument("--apps", default="", help="comma list of application keys (default: every application of --tier)")''', '''    ap.add_argument("--apps", default="", help="comma list of applications - a key of the plan or ANY application name (default: every application of --tier)")'''),
])
print("ok")
