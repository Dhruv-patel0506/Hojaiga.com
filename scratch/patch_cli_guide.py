import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, old[:80]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py", [(
    '''    if not ident.app_key:
        ident.app_key = re.sub(r"[^a-z0-9]+", "_", (os.path.splitext(ident.process)[0] or ident.product or "app").lower()).strip("_") or "app"
    return ident''', '''    if not ident.app_key:
        stem = os.path.splitext(ident.process)[0] or ident.title or ident.product or "app"
        try:                                                              # the SAME key a scan gives the application (one key per application everywhere)
            from core_organs.atlas import common as AC
            ident.app_key = AC.app_key_of(stem)
        except Exception:
            ident.app_key = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
        ident.app_key = ident.app_key or "app"
    return ident'''), ])

PROF = "D:/new_automation/All codes/core_organs/hojaiga_professor.py"
patch(PROF, [
    # catalog / probe / exec use the same application key as scans and guides
    ('''    info = window_info(hwnd)
    title = getattr(info, "title", "") or ""
    proc = getattr(info, "process", "") or ""
    key = a.name or (proc.replace(".exe", "").lower() or "app")''', '''    from core_organs.professor.knowledge import guide_finder as GF
    info = window_info(hwnd)
    title = getattr(info, "title", "") or ""
    proc = getattr(info, "process", "") or ""
    key = a.name or GF.identity_of(hwnd).app_key'''),
    ('''    fx = _effector(a, hwnd)
    cat = HV.harvest_tree(hwnd, a.name or "app")
    eng = P.ProbeEngine(hwnd, fx, cat, a.name or "app", budget_s=a.budget, max_probes=a.max)''', '''    from core_organs.professor.knowledge import guide_finder as GF
    key = a.name or GF.identity_of(hwnd).app_key
    fx = _effector(a, hwnd)
    cat = HV.harvest_tree(hwnd, key)
    eng = P.ProbeEngine(hwnd, fx, cat, key, budget_s=a.budget, max_probes=a.max)'''),
    ('''    from core_organs.professor import executor as X, harvest as HV
    from core_organs.professor.brain import brain
    hwnd = _target_hwnd(a)
    if not hwnd:
        print("no window found (use --hwnd or --title)")
        return 2
    fx = _effector(a, hwnd)
    cat = HV.harvest_tree(hwnd, a.name or "app")
    ex = X.Executor(hwnd, fx, cat, brain=brain())
    rep = ex.plan(a.goal)
    for s in rep.steps:
        print(f"  {s.index + 1}. {s.kind:7s} {(s.verb or s.goal)[:40]:40s} safety={s.safety:9s} human={s.need_human!s:5s} routes={s.routes}")
    rep = ex.run(rep, dry_run=not a.run)
    print(rep.line())''', '''    from core_organs.professor import executor as X, harvest as HV, skills as SK
    from core_organs.professor.brain import brain
    from core_organs.professor.knowledge import guide_finder as GF, manual_rag as MR
    hwnd = _target_hwnd(a)
    if not hwnd:
        print("no window found (use --hwnd or --title)")
        return 2
    ident = GF.identity_of(hwnd)
    key = a.name or ident.app_key
    fx = _effector(a, hwnd)
    cat = HV.harvest_tree(hwnd, key)
    lib = SK.library()
    ex = X.Executor(hwnd, fx, cat, brain=brain(), skills=lib, guide_index=MR.index(), app_version=ident.version)
    rep = ex.plan(a.goal)
    for s in rep.steps:
        print(f"  {s.index + 1}. {s.kind:7s} {(s.verb or s.goal)[:40]:40s} safety={s.safety:9s} human={s.need_human!s:5s} source={s.source} routes={s.routes}")
        if s.note:
            print(f"       note: {s.note[:150]}")
    if rep.unknown:
        print("  the guide mentions (no matching control visible):", rep.unknown[:4])
    rep = ex.run(rep, dry_run=not a.run, learn=not a.no_learn)
    print(rep.line())'''),
    # new commands
    ('''def cmd_status(a) -> int:''', '''def cmd_guide(a) -> int:
    """The application's USER GUIDE: find it (install folder; pages you name; the web only with --web / HOJAIGA_GUIDE_WEB=1), index it, show what is known."""
    from core_organs.professor.knowledge import guide_finder as GF, manual_rag as MR
    if a.action == "status":
        key = a.app or (GF.identity_of(_target_hwnd(a)).app_key if (a.hwnd or a.title) else "")
        if not key:
            ix = MR.index()
            print("indexed applications:", ix.apps() if ix else "none")
            return 0
        print(json.dumps(GF.status(key), indent=1, default=str))
        return 0
    hwnd = _target_hwnd(a) if (a.hwnd or a.title or not a.app) else 0
    ident = GF.identity_of(hwnd, app_key=a.app or "") if hwnd else GF.AppIdentity(app_key=a.app or "app", exe=a.exe or "", product=a.app or "")
    if a.exe:
        ident.exe = a.exe
    print(f"application: {ident.app_key}  product={ident.product!r} company={ident.company!r} version={ident.version!r}  exe={ident.exe}")
    if a.action == "find":
        cands, notes = GF.local_candidates(ident.exe)
        print(f"on this computer: {len(cands)} guide-looking file(s)")
        for c in cands[:12]:
            print(f"   {c['score']:4.1f}  {c['size'] // 1024:6d} KB  {c['path']}")
        for n in notes:
            print("   note:", n)
        if GF.web_enabled(True if a.web else None):
            q = f'"{(ident.names() or [ident.app_key])[0]}" user guide manual documentation'
            res = GF.rank_results(ident, GF.search_web(q, GF.default_fetch))
            print(f"web search ({q}): {len(res)} candidate(s) - nothing is downloaded by `find`")
            for r in res[:6]:
                print(f"   {r['score']:4.1f}  {r['url']}  {r['why']}")
        else:
            print("web search: off (pass --web or set HOJAIGA_GUIDE_WEB=1 to allow it)")
        return 0
    rep = GF.discover(ident, web=True if a.web else None, user_urls=a.url or [], force=a.force, budget_s=a.budget)
    print(json.dumps({k: rep[k] for k in ("tiers", "web", "coverage", "seconds") if k in rep}, indent=1, default=str)[:2500])
    for s in rep.get("skipped", [])[:8]:
        print("   skipped:", s)
    if rep.get("error"):
        print("error:", rep["error"])
    return 0


def cmd_skills(a) -> int:
    """The macro-action library: sequences that were verified on screen and are replayed without a guide lookup or a model call."""
    from core_organs.professor import skills as SK
    lib = SK.library()
    if a.action == "forget":
        print("forgotten" if lib.forget(a.id) else "no such skill")
        return 0
    if a.action == "show":
        s = lib.get(a.id)
        print(json.dumps(__import__("dataclasses").asdict(s), indent=1, default=str) if s else "no such skill")
        return 0
    print(json.dumps(lib.stats(a.app or ""), default=str))
    for s in lib.all(a.app or "", include_stale=True):
        print(f"  {s.id}  [{s.status:6s}] {s.app_key:18s} ok={s.verified} fail={s.failed} safety={s.safety:9s} {s.brief()[:90]}   goals={s.goals[:2]}")
    return 0


def cmd_status(a) -> int:'''),
    ('''    sub.add_parser("status").set_defaults(fn=cmd_status)
    sp = sub.add_parser("selftest")''', '''    sp = sub.add_parser("guide")
    sp.add_argument("action", choices=["find", "fetch", "status"])
    target(sp)
    sp.add_argument("--app", default="", help="application key (default: from the window)")
    sp.add_argument("--exe", default="", help="path of the application's executable (to search its install folder)")
    sp.add_argument("--url", action="append", help="a documentation page YOU name (fetched politely, same site and path only); repeatable")
    sp.add_argument("--web", action="store_true", help="allow the web search tier for this run (default: off unless HOJAIGA_GUIDE_WEB=1)")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--budget", type=float, default=120.0)
    sp.set_defaults(fn=cmd_guide)
    sp = sub.add_parser("skills")
    sp.add_argument("action", choices=["list", "show", "forget"])
    sp.add_argument("id", nargs="?", default="")
    sp.add_argument("--app", default="")
    sp.set_defaults(fn=cmd_skills)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sp = sub.add_parser("selftest")'''),
    ('''    sp.add_argument("--run", action="store_true", help="actually perform the plan (default: dry run)")''', '''    sp.add_argument("--run", action="store_true", help="actually perform the plan (default: dry run)")
    sp.add_argument("--no-learn", action="store_true", help="do not turn a fully verified run into a skill")'''),
    ('''    python hojaiga_professor.py setup-audio [--download]                  install + verify the local voice stack (faster-whisper, piper-tts, sounddevice)''', '''    python hojaiga_professor.py guide  find|fetch|status [--hwnd N|--title T|--app K] [--url U ...] [--web]   the application's USER GUIDE: install folder, pages you name, web only if enabled
    python hojaiga_professor.py skills list|show|forget [id] [--app K]               sequences verified on screen, replayed without a lookup
    python hojaiga_professor.py setup-audio [--download]                  install + verify the local voice stack (faster-whisper, piper-tts, sounddevice)'''),
])
print("cli patched")
