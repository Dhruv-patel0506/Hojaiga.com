"""
hojaiga_professor.py -- THE entry point of the Professor layer: see any application's screen, find every control, teach, speak and point.

    python hojaiga_professor.py scan    [--hwnd N | --title T | --image F.png] [--mode quick|standard|deep] [--budget S] [--out DIR] [--json]
    python hojaiga_professor.py ask     "<question>" [--hwnd N | --title T | --image F.png] [--mute] [--no-overlay] [--auto] [--no-point]
    python hojaiga_professor.py here    [--mute]               what is the control under my mouse?
    python hojaiga_professor.py listen  [--mute]               push-to-talk: hold Ctrl+Alt and speak; Escape cancels
    python hojaiga_professor.py server  status|start|stop|tune the local vision model server (Qwen3-VL via llama.cpp, hidden, 127.0.0.1)
    python hojaiga_professor.py calibrate                      measure how the loaded model writes coordinates (once per model)
    python hojaiga_professor.py know    <app>                  what is stored about an application's controls
    python hojaiga_professor.py repo    ingest <path>... [--project P] | link "<label>" [--project P] | summary [--project P]
    python hojaiga_professor.py manual  ingest <app> <path-or-url> | search <app> "<q>" | layers <app> | apps    user manual as cited, layer-mapped knowledge (agentic RAG)
    python hojaiga_professor.py divisions find | adopt [path] | show      locate / adopt the "sub-divisions of hojaiga system" document as the layer frame
    python hojaiga_professor.py catalog [--hwnd N | --title T] [--save] [--json]     Verb Registry + Shortcut Map from the app's own menus / tree (passive, no input)
    python hojaiga_professor.py archetype [--hwnd N | --title T | --image F.png]       what KIND of software this is, where properties / structure live
    python hojaiga_professor.py probe   [--hwnd N | --title T] [--allow-input --authorize]   learn how it behaves (safe verbs only; dry run unless both flags)
    python hojaiga_professor.py exec    "<goal>" [--hwnd N | --title T] [--run --allow-input --authorize]   plan with the app's own commands; hotkeys over pixels
    python hojaiga_professor.py guide  find|fetch|status [--hwnd N|--title T|--app K] [--url U ...] [--web]   the application's USER GUIDE: install folder, pages you name, web only if enabled
    python hojaiga_professor.py guide  card [--hwnd N|--app K]                       the guide as one JSON card: UI taxonomy, shortcuts, action sequences, layers
    python hojaiga_professor.py skills list|show|forget|demo [id] [--app K]          sequences verified on screen, replayed without a lookup; `demo` = the overlay pointer glides through them
    python hojaiga_professor.py history stats|recent|recoveries|orders|forget [--app K]   the state-transition log (what each action did, how the app was put back)
    python hojaiga_professor.py explore [--hwnd N|--title T] --allow-input --authorize [--idle S]   idle-time permutation learning (safe verbs only; stops when you return)
    python hojaiga_professor.py setup-audio [--download]                  install + verify the local voice stack (faster-whisper, piper-tts, sounddevice)
    python hojaiga_professor.py preview --scan S.json --image F.png --ids 3,7 --out O.png    draw the overlay onto a picture (nothing shown on screen)
    python hojaiga_professor.py status                         every component, up or skipped, honestly
    python hojaiga_professor.py selftest [--live]              the Professor test suite (offline; --live adds the vision model)

Nothing here clicks, types or presses keys in the application you are learning - except `probe` and `exec`, which are dry runs unless you pass --allow-input AND
--authorize (headless window messages / UI Automation only, safe verbs only, focus handed back to you). The overlay is click-through and never takes focus.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

for _p in (r"D:\new_automation", r"D:\new_automation\All codes"):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_image(path: str):
    from PIL import Image
    return Image.open(path).convert("RGB")


def cmd_scan(a) -> int:
    from core_organs.professor import config as CFG
    from core_organs.professor import sweeper
    from core_organs.professor.capture import pick_target_window
    CFG.ensure_dirs()
    image = _load_image(a.image) if a.image else None
    hwnd = a.hwnd or 0
    if not image and not hwnd:
        w = pick_target_window(a.title or "")
        hwnd = w.hwnd if w else 0
        if not hwnd:
            print("no window found (use --hwnd, --title or --image)")
            return 2
    opt = sweeper.ScanOptions.for_mode(a.mode)
    if a.budget:
        opt.budget_s = a.budget
    sm, fr = sweeper.scan(hwnd=hwnd, image=image, options=opt, progress=lambda s, i: print(f"  .. {s} {i}", file=sys.stderr))
    paths = sweeper.save_scan(sm, fr.image if fr else None, a.name or "") if fr else {}
    if a.out and paths:
        import shutil
        os.makedirs(a.out, exist_ok=True)
        for k, v in paths.items():
            shutil.copy(v, os.path.join(a.out, os.path.basename(v)))
    if a.json:
        print(sm.to_json(indent=1))
    else:
        s = sm.summary()
        print(f"{sm.window_title or '(picture)'}  [{sm.app_key}]  {sm.size[0]}x{sm.size[1]}  mode={sm.mode}  {sm.timings.get('total')}s")
        print(f"controls: {s['elements']} ({s['named']} named)   by source: {s['by_source']}")
        print("coverage: ink explained {:.1%}   exhausted={}   unexplained shapes={}".format(sm.coverage.get("coverage", 0), sm.coverage.get("exhausted"), sm.coverage.get("uncovered_n")))
        print("tiers used:   ", ", ".join(sm.tiers_used))
        print("tiers skipped:", ", ".join(sm.tiers_skipped) or "none")
        for r in sm.regions:
            print(f"  {r.kind:10s} {r.label[:40]:40s} {len(r.element_ids):4d} controls")
        print(sm.inventory_text(limit=60))
        if paths:
            print("saved:", paths)
    return 0


def cmd_ask(a) -> int:
    from core_organs.professor.session import ProfessorSession
    s = ProfessorSession(mute=a.mute, overlay="recording" if a.no_overlay else "auto", interactive=not a.auto, upgrade=not a.no_upgrade)
    try:
        image = _load_image(a.image) if a.image else None
        out = s.ask(a.question, hwnd=a.hwnd or 0, image=image, title_hint=a.title or "", point=not a.no_point, speak=not a.mute)
        les = out.get("lesson") or {}
        print(f"\nspoken: {out.get('spoken', '')}")
        for st in les.get("steps", []):
            print(f"  {st['n']}. [{st['action']}] #{st.get('element_id')} {st.get('label') or st.get('find')}  ({st.get('grounded_by')})  - {st.get('say')}")
        print(json.dumps({k: v for k, v in out.items() if k not in ("lesson", "spoken")}, indent=1, default=str)[:1800])
    finally:
        s.close()
    return 0


def cmd_here(a) -> int:
    from core_organs.professor.session import ProfessorSession
    s = ProfessorSession(mute=a.mute)
    try:
        print(json.dumps(s.explain_here(), indent=1, default=str)[:2000])
    finally:
        s.close()
    return 0


def cmd_listen(a) -> int:
    from core_organs.professor.session import ProfessorSession
    s = ProfessorSession(mute=a.mute)
    print(json.dumps(s.components(), indent=1, default=str))
    s.serve()
    return 0


def cmd_server(a) -> int:
    from core_organs.professor import vision_server as VS
    if a.action == "status":
        print(json.dumps(VS.status(), indent=1, default=str))
    elif a.action == "start":
        print(json.dumps(VS.ensure(wait_s=300), indent=1, default=str))
    elif a.action == "stop":
        print(json.dumps(VS.stop(), indent=1))
    elif a.action == "tune":
        print(json.dumps(VS.tune(), indent=1))
    return 0


def cmd_calibrate(a) -> int:
    from core_organs.professor.vlm import client
    print(json.dumps(client().calibrate(force=True), indent=1))
    return 0


def cmd_know(a) -> int:
    from core_organs.professor.knowledge import app_knowledge
    ak = app_knowledge.for_identity(a.app)
    print(json.dumps({"ui_map": ak.ui_key, "knowledge_base": ak.kb_key, "known": ak.known, "entries": len(ak.entries), "interactions": len(ak.kb_index),
                      "overview": ak.overview()}, indent=1, default=str)[:3500])
    return 0


def cmd_repo(a) -> int:
    from core_organs.professor.knowledge.repo_graph import RepoGraph
    rg = RepoGraph()
    try:
        if a.action == "ingest":
            for p in a.args:
                print(json.dumps(rg.ingest(p, project=a.project or ""), indent=1))
        elif a.action == "link":
            print(json.dumps(rg.link_label(a.args[0], a.project or ""), indent=1, default=str)[:4000])
        else:
            print(json.dumps({"stats": rg.stats(), "divisions": rg.divisions_of(a.project or ""), "central": rg.central_files(a.project or "", 8)}, indent=1))
    finally:
        rg.close()
    return 0


def cmd_manual(a) -> int:
    from core_organs.professor.knowledge import manual_rag as MR
    from core_organs.professor.brain import brain
    ix = MR.ManualIndex()
    try:
        if a.action == "ingest":
            src = a.args[1]
            print(json.dumps(ix.ingest_url(a.args[0], src) if src.startswith(("http://", "https://")) else ix.ingest_path(a.args[0], src), indent=1))
        elif a.action == "search":
            res = ix.retrieve(a.args[1], a.args[0], 4, brain())
            print(json.dumps({"trail": res["trail"], "weak": res["weak"], "passages": [p.to_dict() for p in res["passages"]]}, indent=1)[:4000])
        elif a.action == "layers":
            print(json.dumps(ix.layer_map(a.args[0] if a.args else ""), indent=1))
        else:
            print(json.dumps(ix.apps()))
    finally:
        ix.close()
    return 0


def cmd_divisions(a) -> int:
    from core_organs.professor.knowledge import divisions as D
    if a.action == "find":
        print(D.find_subdivisions_file() or "not found (searched project, architecture folders, Downloads, Documents, Desktop, OneDrive)")
    elif a.action == "adopt":
        print(json.dumps(D.adopt_document(a.args[0] if a.args else ""), indent=1))
    else:
        print(json.dumps({"in_use": D.source_in_use(), "divisions": [d["name"] for d in D.load()]}, indent=1))
    return 0


def cmd_setup_audio(a) -> int:
    from core_organs.professor import setup_audio as SA
    print(json.dumps(SA.install(download=True) if a.download else SA.status(), indent=1, default=str))
    return 0


def cmd_preview(a) -> int:
    from core_organs.professor import overlay_render as R
    from core_organs.professor.schema import ScreenModel
    sm = ScreenModel.from_json(open(a.scan, encoding="utf-8").read())
    img = _load_image(a.image)
    cmds = []
    for n, i in enumerate([int(x) for x in a.ids.split(",") if x.strip()], 1):
        e = sm.element(i)
        if e is None:
            continue
        cmds.append({"type": "highlight", "box": e.bbox.to_list(), "pulse": 0.4})
        cmds.append({"type": "bubble", "text": e.label or f"control {i}", "step": n, "box": e.bbox.to_list()})
    if cmds:
        last = [c for c in cmds if c["type"] == "highlight"][-1]["box"]
        cmds.append({"type": "cursor", "x": (last[0] + last[2]) / 2, "y": (last[1] + last[3]) / 2})
    R.compose_preview(img, cmds, tuple(sm.origin)).save(a.out)
    print("wrote", a.out)
    return 0


def _target_hwnd(a) -> int:
    from core_organs.professor.capture import pick_target_window
    hwnd = a.hwnd or 0
    if not hwnd:
        w = pick_target_window(a.title or "")
        hwnd = w.hwnd if w else 0
    return hwnd


def cmd_catalog(a) -> int:
    """Passive: the application's own menus, accelerators, tooltips and control states -> Verb Registry + Shortcut Map. Reads, never clicks."""
    from core_organs.professor import harvest as HV, safety
    from core_organs.professor.capture import window_info
    hwnd = _target_hwnd(a)
    if not hwnd:
        print("no window found (use --hwnd or --title)")
        return 2
    from core_organs.professor.knowledge import guide_finder as GF
    info = window_info(hwnd)
    title = getattr(info, "title", "") or ""
    proc = getattr(info, "process", "") or ""
    key = a.name or GF.identity_of(hwnd).app_key
    cat = HV.harvest_tree(hwnd, key, title, proc)
    path = cat.save() if a.save else ""
    if a.json:
        print(json.dumps(cat.to_dict(), indent=1, ensure_ascii=False))
        return 0
    print(json.dumps(cat.summary(), indent=1, default=str))
    for v in cat.verbs[:a.limit]:
        print(f"  [{v.safety:9s}] {v.text_path[:60]:60s} {v.shortcut:16s} {('cmd#%d' % v.command_id) if v.command_id else ''}")
    if cat.conflicts():
        print("shortcut conflicts:", cat.conflicts())
    if path:
        print("saved:", path)
    return 0


def cmd_archetype(a) -> int:
    """What KIND of software is this (from a scan + the catalog): where properties live, where structure lives, the usual workflow."""
    from core_organs.professor import archetype as AR, harvest as HV, sweeper
    from core_organs.professor.brain import brain
    hwnd = _target_hwnd(a)
    image = _load_image(a.image) if a.image else None
    if not hwnd and image is None:
        print("no window found (use --hwnd, --title or --image)")
        return 2
    opt = sweeper.ScanOptions.for_mode("quick")
    sm, fr = sweeper.scan(hwnd=hwnd, image=image, options=opt)
    cat = HV.harvest_model(sm, hwnd) if hwnd else None
    arch = AR.classify(sm, cat, brain())
    print(json.dumps({k: arch[k] for k in ("id", "name", "confidence", "by", "evidence", "ranked", "layout", "blueprint")}, indent=1, default=str))
    print(AR.teaching_line(arch))
    return 0


def _effector(a, hwnd):
    from core_organs.professor.effectors import Effector
    return Effector(hwnd, allow_input=bool(a.allow_input), owned=False, authorized=bool(a.authorize))


def cmd_probe(a) -> int:
    """Hypothesis-driven probing. DRY RUN unless --allow-input AND --authorize (you saying: this window may be driven headlessly). Only 'safe' verbs are ever tried."""
    from core_organs.professor import harvest as HV, probe as P
    hwnd = _target_hwnd(a)
    if not hwnd:
        print("no window found (use --hwnd or --title)")
        return 2
    from core_organs.professor.knowledge import guide_finder as GF
    key = a.name or GF.identity_of(hwnd).app_key
    fx = _effector(a, hwnd)
    cat = HV.harvest_tree(hwnd, key)
    eng = P.ProbeEngine(hwnd, fx, cat, key, budget_s=a.budget, max_probes=a.max)
    rep = eng.run()
    print(f"{'DRY RUN - ' if rep.dry_run else ''}{len(rep.rules)} hypotheses, {rep.seconds}s  {('stopped: ' + rep.stopped) if rep.stopped else ''}")
    for r in rep.rules:
        print(f"  {r.verb[:28]:28s} {r.effect:14s} confirmed={r.confirmed!s:5s} restored={r.restored}  {r.note[:70]}")
    for name, why in rep.skipped[:12]:
        print(f"  skipped {name[:26]:26s} {why}")
    if rep.model:
        print(json.dumps(rep.model, default=str))
    return 0


def cmd_exec(a) -> int:
    """Plan a goal into the application's own commands and (only with --run, --allow-input and --authorize) perform it by hotkey > menu command > control > posted click."""
    from core_organs.professor import executor as X, harvest as HV, skills as SK
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
    print(rep.line())
    for r in rep.results:
        print(f"  step {r.index + 1}: {r.status:10s} {r.route:30s} {r.summary[:90]}")
    return 0 if rep.ok or rep.dry_run else 1


def cmd_guide(a) -> int:
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
            print("web search: off (pass --web or set HOJAIGA_GUIDE_WEB=1 to allow it). It would run these queries:")
            for q in GF.dork_queries(ident):
                print(f"   [{q['kind']:5s}] {q['query']}")
        return 0
    if a.action == "card":
        from core_organs.professor import harvest as HV
        from core_organs.professor.knowledge import guide_card as GC
        cat = HV.harvest_tree(ident_hwnd, ident.app_key) if (ident_hwnd := (_target_hwnd(a) if (a.hwnd or a.title) else 0)) else None
        card = GC.build_card(ident.app_key, MR.index(), cat)
        print(f"guide card for {ident.app_key}: {card['documents']} document(s), {card['chunks']} chunk(s), {len(card['action_sequences'])} procedure(s), {len(card['shortcuts'])} shortcut(s), "
              f"{len(card['ui_taxonomy']['terms'])} interface terms" + (f", {card['applies_to_installed_version']:.0%} of the guide applies to the installed version" if "applies_to_installed_version" in card else ""))
        print("saved:", GC.card_path(ident.app_key))
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
    if a.action == "demo":
        from core_organs.professor.session import ProfessorSession
        s = lib.get(a.id)
        if s is None:
            print("no such skill")
            return 1
        ps = ProfessorSession(mute=a.mute, upgrade=False, find_guide=False)
        try:
            print(json.dumps(ps.demonstrate(s, _target_hwnd(a), speak=not a.mute), indent=1, default=str))
        finally:
            ps.close()
        return 0
    if a.action == "show":
        s = lib.get(a.id)
        print(json.dumps(__import__("dataclasses").asdict(s), indent=1, default=str) if s else "no such skill")
        return 0
    print(json.dumps(lib.stats(a.app or ""), default=str))
    for s in lib.all(a.app or "", include_stale=True):
        print(f"  {s.id}  [{s.status:6s}] {s.app_key:18s} ok={s.verified} fail={s.failed} safety={s.safety:9s} {s.brief()[:90]}   goals={s.goals[:2]}")
    return 0


def cmd_history(a) -> int:
    """The state-transition log: what every action did, which route worked, how the application was put back, which action pairs are order-sensitive."""
    from core_organs.professor import history as HS
    h = HS.library()
    if a.action == "stats":
        print(json.dumps(h.stats(a.app or ""), default=str))
    elif a.action == "recent":
        for r in h.recent(a.app, 20):
            print(f"  {time.strftime('%H:%M:%S', time.localtime(r['ts']))} {r['source']:8s} {r['primitive']:10s} {r['target'][:28]:28s} {r['effect']:14s} ok={r['ok']} unwound={r['unwound']}  {str(r['s1_note'])[:50]}")
    elif a.action == "recoveries":
        print(json.dumps(h.recoveries(a.app), indent=1))
    elif a.action == "orders":
        print(json.dumps(h.order_effects(a.app), indent=1, default=str))
    elif a.action == "forget":
        print("removed", h.forget(a.app), "row(s)")
    return 0


def cmd_explore(a) -> int:
    """IDLE-TIME permutation learning: do pairs of safe actions in both orders, verify the application is put back each time, learn which orders matter. Needs --allow-input --authorize AND a machine
    that has been idle for --idle seconds; stops the moment you return."""
    from core_organs.professor import explore as EX, harvest as HV, history as HS
    from core_organs.professor.knowledge import guide_finder as GF
    hwnd = _target_hwnd(a)
    if not hwnd:
        print("no window found (use --hwnd or --title)")
        return 2
    key = a.name or GF.identity_of(hwnd).app_key
    fx = _effector(a, hwnd)
    cat = HV.harvest_tree(hwnd, key)
    rep = EX.Explorer(hwnd, fx, cat, key, HS.library(), owned=False, idle_required_s=a.idle, max_actions=a.actions, budget_s=a.budget).run()
    print(json.dumps(rep.summary(), indent=1, default=str))
    for p in rep.pairs:
        print(f"  {p.a} / {p.b}: {p.verdict}  {('; '.join(p.diff))[:90]}")
    return 0


def cmd_teach_run(a) -> int:
    """ONE COMMAND: ask -> find the workflow -> run it on a visible owned window -> narrate each step -> report the verified result (professor.teach_run)."""
    from core_organs.professor import teach_run as TR
    out = TR.teach(a.question, app=a.app, mute=a.mute, cursor=not a.no_cursor, vision=not a.no_vision, dry=a.dry)
    print(json.dumps({k: v for k, v in out.items() if k not in ("narration", "verify_log")}, indent=1, ensure_ascii=False, default=str))
    return 0 if out.get("final") in ("ok", None) and not out.get("error") else 1


def cmd_grounding(a) -> int:
    """How much of each application's guide is tied to a real control: raw and over the steps that are about THIS application (other editions / the OS / boiler-plate set aside, with reasons)."""
    from core_organs.professor import workflows as WF
    for app in (a.apps or ["notepad", "mspaint", "winword", "powerpnt"]):
        d = WF.build(app, write=not a.no_write)
        s_ = d["summary"]
        print(f"{app:14s} grounded {s_['grounded_steps']:4d} / applicable {s_['applicable_steps']:4d} = {s_['grounding_applicable']:.1%}   (raw {s_['grounding_raw']:.1%} of {s_['steps']}; "
              f"set aside {s_['outside_steps']})   by how: {s_['by_how']}")
    return 0


def cmd_knowledge(a) -> int:
    """FULL APP KNOWLEDGE: one record per application (controls, effects, routes, workflows, coverage score) in data/professor/apps/ (professor.app_record)."""
    from core_organs.professor import app_record as AR_
    if a.all or not a.apps:
        print(open(AR_.build_all(a.apps or None), encoding="utf-8").read())
        return 0
    for k in a.apps:
        r = AR_.build(k)
        print(json.dumps({"app": k, "identity": r["identity"], "coverage": r["coverage"], "workflows": r["workflows"], "routes": len(r["routes"])}, indent=1, ensure_ascii=False, default=str))
    return 0


def cmd_eval_answers(a) -> int:
    """A labelled question set with known answers, and the measured accuracy of the rules answerer and the local model (professor.answer_eval)."""
    from core_organs.professor import answer_eval as AE
    r = AE.run(a.apps or ["notepad", "mspaint", "winword", "powerpnt"], use_model=not a.no_model, rebuild=a.rebuild, n_per_kind=a.n)
    print(json.dumps(r["summary"], indent=1))
    print("files:", r.get("files"))
    return 0


def cmd_workflow(a) -> int:
    """THE GUIDES AS WORKFLOWS: `workflow build <app>|--all` analyse every guide procedure against the application's controls and write data/professor/workflows/<app>.json + .md;
    `workflow list [app]`, `workflow show <id>`, `workflow find <app> "<request>"`, `workflow run <app> <id>` (an owned instance, window left visible, virtual cursor shown)."""
    from core_organs.professor import workflows as WF
    if a.action == "build":
        from core_organs.professor.knowledge import manual_rag as MR
        ix = MR.ManualIndex()
        try:
            apps = ix.apps() if a.all else ([a.app] if a.app else [])
            if not apps:
                print("name an application, or --all")
                return 2
            for k in apps:
                d = WF.build(k, ix=ix)
                s_ = d["summary"]
                print(f"{k:22s} {d['documents']:4d} docs -> {s_['workflows']:3d} workflows, {s_['grounded_steps']}/{s_['steps']} steps grounded  {s_['by_status']}")
        finally:
            ix.close()
        print("library:", WF.WF_DIR)
        return 0
    if a.action == "list":
        doc = WF.load(a.app) if a.app else None
        if doc is None:
            print(open(os.path.join(WF.WF_DIR, "INDEX.md"), encoding="utf-8").read() if os.path.exists(os.path.join(WF.WF_DIR, "INDEX.md")) else "no library yet: workflow build --all")
            return 0
        for w in doc["workflows"]:
            print(f"  {w['id']:60s} {w['status']:18s} {w['step_count']:2d} steps  last: {w['last_run']['result']}  {w['goal'][:60]}")
        return 0
    if a.action == "show":
        w = WF.get(a.app)
        print(json.dumps(w, indent=1, ensure_ascii=False) if w else "no such workflow")
        return 0 if w else 1
    if a.action == "find":
        for w in WF.fetch(a.app, a.id or "", 8):
            print(f"  {w['id']:60s} {w['status']:18s} {w['goal'][:70]}")
        return 0
    if a.action == "run":
        out = WF.run(a.app, a.id, cursor=not a.no_cursor, vision=not a.no_vision)
        print(json.dumps({k: out.get(k) for k in ("final", "goal", "error")}, default=str), "|", (out.get("attempts") or [{}])[-1].get("why", ""))
        return 0
    return 2


def cmd_apprun(a) -> int:
    """RUN AN APPLICATION'S GUIDE against the real application (an owned instance, never yours): deep scan with annotated pictures, every guide procedure performed and judged, a ledger, one HTML report.
    `apprun notepad` | `apprun --tier 1` | `apprun --list`."""
    from core_organs.professor import apprun as AR
    if a.list:
        for t, ks in sorted(AR.TIERS.items()):
            print(f"tier {t}: " + ", ".join(f"{k} ({AR.SPECS[k].scenario or AR.SPECS[k].name})" for k in ks))
        return 0
    keys = AR.TIERS.get(a.tier, []) if a.tier else ([a.app] if a.app else [])
    if not keys:
        print("name an application (see --list) or --tier N")
        return 2
    for k in keys:
        if a.tasks:
            AR.SPECS[k].max_tasks = a.tasks
        AR.run_app(k, max_attempts=a.attempts, vision=not a.no_vision, phases=tuple(x.strip() for x in a.phases.split(",") if x.strip()))
    return 0


def cmd_status(a) -> int:
    from core_organs.professor import vision_server as VS, config as CFG
    from core_organs.professor.session import ProfessorSession
    from core_organs.professor.icon_memory import memory
    s = ProfessorSession(mute=True, overlay="recording", upgrade=False)
    out = {"components": s.components(), "vision_server": VS.status(), "icon_memory": memory().stats(), "profile": getattr(CFG.active_profile(), "name", None)}
    try:
        from core_organs.professor.knowledge.explain import repo_graph
        rg = repo_graph()
        out["repo_graph"] = rg.stats() if rg else "none ingested"
    except Exception as exc:
        out["repo_graph"] = f"{type(exc).__name__}"
    print(json.dumps(out, indent=1, default=str))
    s.close()
    return 0


def cmd_selftest(a) -> int:
    from core_organs import si_tests_professor as T
    return T.main(live=a.live)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="hojaiga_professor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def target(sp):
        sp.add_argument("--hwnd", type=int, default=0)
        sp.add_argument("--title", default="")
        sp.add_argument("--image", default="")

    sp = sub.add_parser("scan")
    target(sp)
    sp.add_argument("--mode", default="standard", choices=["quick", "standard", "deep"])
    sp.add_argument("--budget", type=float, default=0)
    sp.add_argument("--out", default="")
    sp.add_argument("--name", default="")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_scan)
    sp = sub.add_parser("ask")
    sp.add_argument("question")
    target(sp)
    sp.add_argument("--mute", action="store_true")
    sp.add_argument("--no-overlay", action="store_true")
    sp.add_argument("--auto", action="store_true", help="do not wait for the learner between steps")
    sp.add_argument("--no-point", action="store_true")
    sp.add_argument("--no-upgrade", action="store_true")
    sp.set_defaults(fn=cmd_ask)
    sp = sub.add_parser("here")
    sp.add_argument("--mute", action="store_true")
    sp.set_defaults(fn=cmd_here)
    sp = sub.add_parser("listen")
    sp.add_argument("--mute", action="store_true")
    sp.set_defaults(fn=cmd_listen)
    sp = sub.add_parser("server")
    sp.add_argument("action", choices=["status", "start", "stop", "tune"])
    sp.set_defaults(fn=cmd_server)
    sub.add_parser("calibrate").set_defaults(fn=cmd_calibrate)
    sp = sub.add_parser("know")
    sp.add_argument("app")
    sp.set_defaults(fn=cmd_know)
    sp = sub.add_parser("repo")
    sp.add_argument("action", choices=["ingest", "link", "summary"])
    sp.add_argument("args", nargs="*")
    sp.add_argument("--project", default="")
    sp.set_defaults(fn=cmd_repo)
    sp = sub.add_parser("manual")
    sp.add_argument("action", choices=["ingest", "search", "layers", "apps"])
    sp.add_argument("args", nargs="*")
    sp.set_defaults(fn=cmd_manual)
    sp = sub.add_parser("divisions")
    sp.add_argument("action", choices=["find", "adopt", "show"])
    sp.add_argument("args", nargs="*")
    sp.set_defaults(fn=cmd_divisions)
    sp = sub.add_parser("setup-audio")
    sp.add_argument("--download", action="store_true")
    sp.set_defaults(fn=cmd_setup_audio)
    sp = sub.add_parser("preview")
    sp.add_argument("--scan", required=True)
    sp.add_argument("--image", required=True)
    sp.add_argument("--ids", required=True)
    sp.add_argument("--out", required=True)
    sp.set_defaults(fn=cmd_preview)
    sp = sub.add_parser("catalog")
    target(sp)
    sp.add_argument("--name", default="")
    sp.add_argument("--save", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--limit", type=int, default=60)
    sp.set_defaults(fn=cmd_catalog)
    sp = sub.add_parser("archetype")
    target(sp)
    sp.set_defaults(fn=cmd_archetype)

    def gate(sp):
        sp.add_argument("--allow-input", action="store_true", help="let the Professor send headless input (messages / UI Automation) - closed by default")
        sp.add_argument("--authorize", action="store_true", help="you confirm this window may be driven (needed for any window the Professor did not launch)")
        sp.add_argument("--name", default="")

    sp = sub.add_parser("probe")
    target(sp)
    gate(sp)
    sp.add_argument("--budget", type=float, default=90.0)
    sp.add_argument("--max", type=int, default=15)
    sp.set_defaults(fn=cmd_probe)
    sp = sub.add_parser("exec")
    sp.add_argument("goal")
    target(sp)
    gate(sp)
    sp.add_argument("--run", action="store_true", help="actually perform the plan (default: dry run)")
    sp.add_argument("--no-learn", action="store_true", help="do not turn a fully verified run into a skill")
    sp.set_defaults(fn=cmd_exec)
    sp = sub.add_parser("guide")
    sp.add_argument("action", choices=["find", "fetch", "status", "card"])
    target(sp)
    sp.add_argument("--app", default="", help="application key (default: from the window)")
    sp.add_argument("--exe", default="", help="path of the application's executable (to search its install folder)")
    sp.add_argument("--url", action="append", help="a documentation page YOU name (fetched politely, same site and path only); repeatable")
    sp.add_argument("--web", action="store_true", help="allow the web search tier for this run (default: off unless HOJAIGA_GUIDE_WEB=1)")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--budget", type=float, default=120.0)
    sp.set_defaults(fn=cmd_guide)
    sp = sub.add_parser("skills")
    sp.add_argument("action", choices=["list", "show", "forget", "demo"])
    sp.add_argument("id", nargs="?", default="")
    sp.add_argument("--app", default="")
    sp.add_argument("--hwnd", type=int, default=0)
    sp.add_argument("--title", default="")
    sp.add_argument("--mute", action="store_true")
    sp.set_defaults(fn=cmd_skills)
    sp = sub.add_parser("history")
    sp.add_argument("action", choices=["stats", "recent", "recoveries", "orders", "forget"])
    sp.add_argument("--app", default="")
    sp.set_defaults(fn=cmd_history)
    sp = sub.add_parser("explore")
    target(sp)
    gate(sp)
    sp.add_argument("--idle", type=float, default=300.0, help="seconds without keyboard / mouse before exploring (default 300)")
    sp.add_argument("--actions", type=int, default=4)
    sp.add_argument("--budget", type=float, default=180.0)
    sp.set_defaults(fn=cmd_explore)
    sp = sub.add_parser("apprun")
    sp.add_argument("app", nargs="?", default="")
    sp.add_argument("--tier", type=int, default=0)
    sp.add_argument("--list", action="store_true")
    sp.add_argument("--attempts", type=int, default=3)
    sp.add_argument("--tasks", type=int, default=0)
    sp.add_argument("--no-vision", action="store_true")
    sp.add_argument("--phases", default="guide", help="comma list: guide, probe, explore")
    sp.set_defaults(fn=cmd_apprun)
    sp = sub.add_parser("workflow")
    sp.add_argument("action", choices=["build", "list", "show", "find", "run"])
    sp.add_argument("app", nargs="?", default="", help="application key (for show: the workflow id)")
    sp.add_argument("id", nargs="?", default="", help="workflow id (run) / the request in words (find)")
    sp.add_argument("--all", action="store_true", help="build: every application that has a guide")
    sp.add_argument("--no-cursor", action="store_true", help="run: park the window (no visible virtual cursor)")
    sp.add_argument("--no-vision", action="store_true")
    sp.set_defaults(fn=cmd_workflow)
    sp = sub.add_parser("teach-run", help="ask -> find workflow -> run on a visible window -> narrate each step -> verified result")
    sp.add_argument("question")
    sp.add_argument("--app", default="")
    sp.add_argument("--mute", action="store_true")
    sp.add_argument("--no-cursor", action="store_true", help="park the window instead of leaving it visible")
    sp.add_argument("--no-vision", action="store_true")
    sp.add_argument("--dry", action="store_true", help="plan and narrate only; the application is not started")
    sp.set_defaults(fn=cmd_teach_run)
    sp = sub.add_parser("grounding", help="guide-step grounding per application (raw and applicable)")
    sp.add_argument("apps", nargs="*")
    sp.add_argument("--no-write", action="store_true")
    sp.set_defaults(fn=cmd_grounding)
    sp = sub.add_parser("knowledge", help="one knowledge record per application, with a coverage score")
    sp.add_argument("apps", nargs="*")
    sp.add_argument("--all", action="store_true")
    sp.set_defaults(fn=cmd_knowledge)
    sp = sub.add_parser("eval-answers", help="labelled questions with known answers -> measured accuracy")
    sp.add_argument("apps", nargs="*")
    sp.add_argument("--no-model", action="store_true")
    sp.add_argument("--rebuild", action="store_true")
    sp.add_argument("--n", type=int, default=8)
    sp.set_defaults(fn=cmd_eval_answers)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sp = sub.add_parser("selftest")
    sp.add_argument("--live", action="store_true")
    sp.set_defaults(fn=cmd_selftest)
    a = p.parse_args(argv)
    return int(a.fn(a) or 0)


if __name__ == "__main__":
    sys.exit(main())
