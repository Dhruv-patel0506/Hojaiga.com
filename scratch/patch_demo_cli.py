import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


B = "D:/new_automation/All codes/core_organs/professor/"

patch(B + "session.py", [(
    "    def explain_here(self, hwnd: int = 0) -> Dict[str, Any]:",
    '''    def demonstrate(self, skill: Any, hwnd: int = 0, speak: bool = True) -> Dict[str, Any]:
        """'Watch me do it': the overlay pointer glides through the skill's targets as ONE continuous Fitts's-law route (arriving at each control, naming it, showing its hotkey). It only
        DRAWS - nothing is clicked and the user's real mouse and keyboard are never touched or blocked. Controls that are not visible now are listed, not guessed."""
        from . import pointing
        sm, img, info = self.look(hwnd)
        cat, _arch = self.frame(sm, hwnd)
        boxes, labels, hotkeys, missing = [], [], [], []
        for st in skill.steps:
            if st.kind != "verb":
                continue
            hit = sm.find(st.label, limit=1)
            if hit:
                boxes.append(hit[0].bbox)
                labels.append(st.label)
                hotkeys.append((cat.shortcut_for(st.label) if cat is not None else "") or "")
            else:
                missing.append(st.label)
        if not boxes:
            return {"ok": False, "error": "none of the skill's controls is visible right now", "missing": missing}
        start = cursor_pos()
        pts, ws = pointing.route_for(boxes, start, "click")
        traj = pointing.stitch(pts, ws)
        t0 = time.time()
        total = self.overlay.glide(pts[1:], ws[1:])
        sp = self.speaker if speak else SilentSpeaker()
        sp.speak(f"{skill.goals[0]}. Watch the pointer.")
        for i, arr in enumerate(traj.arrival[1:]):
            time.sleep(max(0.0, arr - (time.time() - t0)))
            self.overlay.point(boxes[i], labels[i], i + 1, "click", True, labels[i], False, False, hotkeys[i])
            sp.speak(f"{labels[i]}." + (f" Shortcut: {hotkeys[i]}." if hotkeys[i] else ""))
        sp.wait(30)
        time.sleep(0.6)
        self.overlay.clear()
        return {"ok": True, "steps": labels, "missing": missing, "route_seconds": round(traj.duration, 2), "planned": round(total, 2), "hotkeys": hotkeys}

    def explain_here(self, hwnd: int = 0) -> Dict[str, Any]:''')])

PROF = "D:/new_automation/All codes/core_organs/hojaiga_professor.py"
patch(PROF, [
    ('''    if a.action == "forget":
        print("forgotten" if lib.forget(a.id) else "no such skill")
        return 0''', '''    if a.action == "forget":
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
        return 0'''),
    ('''    rep = GF.discover(ident, web=True if a.web else None, user_urls=a.url or [], force=a.force, budget_s=a.budget)''', '''    if a.action == "card":
        from core_organs.professor import harvest as HV
        from core_organs.professor.knowledge import guide_card as GC
        cat = HV.harvest_tree(ident_hwnd, ident.app_key) if (ident_hwnd := (_target_hwnd(a) if (a.hwnd or a.title) else 0)) else None
        card = GC.build_card(ident.app_key, MR.index(), cat)
        print(f"guide card for {ident.app_key}: {card['documents']} document(s), {card['chunks']} chunk(s), {len(card['action_sequences'])} procedure(s), {len(card['shortcuts'])} shortcut(s), "
              f"{len(card['ui_taxonomy']['terms'])} interface terms" + (f", {card['applies_to_installed_version']:.0%} of the guide applies to the installed version" if "applies_to_installed_version" in card else ""))
        print("saved:", GC.card_path(ident.app_key))
        return 0
    rep = GF.discover(ident, web=True if a.web else None, user_urls=a.url or [], force=a.force, budget_s=a.budget)'''),
    ('''        else:
            print("web search: off (pass --web or set HOJAIGA_GUIDE_WEB=1 to allow it)")
        return 0''', '''        else:
            print("web search: off (pass --web or set HOJAIGA_GUIDE_WEB=1 to allow it). It would run these queries:")
            for q in GF.dork_queries(ident):
                print(f"   [{q['kind']:5s}] {q['query']}")
        return 0'''),
    ('''def cmd_status(a) -> int:''', '''def cmd_history(a) -> int:
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


def cmd_status(a) -> int:'''),
    ('''    sp = sub.add_parser("skills")
    sp.add_argument("action", choices=["list", "show", "forget"])
    sp.add_argument("id", nargs="?", default="")
    sp.add_argument("--app", default="")
    sp.set_defaults(fn=cmd_skills)''', '''    sp = sub.add_parser("skills")
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
    sp.set_defaults(fn=cmd_explore)'''),
    ('choices=["find", "fetch", "status"]', 'choices=["find", "fetch", "status", "card"]'),
    ('''    python hojaiga_professor.py skills list|show|forget [id] [--app K]               sequences verified on screen, replayed without a lookup''', '''    python hojaiga_professor.py guide  card [--hwnd N|--app K]                       the guide as one JSON card: UI taxonomy, shortcuts, action sequences, layers
    python hojaiga_professor.py skills list|show|forget|demo [id] [--app K]          sequences verified on screen, replayed without a lookup; `demo` = the overlay pointer glides through them
    python hojaiga_professor.py history stats|recent|recoveries|orders|forget [--app K]   the state-transition log (what each action did, how the app was put back)
    python hojaiga_professor.py explore [--hwnd N|--title T] --allow-input --authorize [--idle S]   idle-time permutation learning (safe verbs only; stops when you return)'''),
])
print("demo + cli patched")
