import ast
import io

P = "D:/new_automation/All codes/core_organs/hojaiga_professor.py"
s = io.open(P, "r", encoding="utf-8").read()

# the command
cmd = '''def cmd_workflow(a) -> int:
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


'''
anchor = "def cmd_apprun(a) -> int:"
assert anchor in s and "def cmd_workflow" not in s
s = s.replace(anchor, cmd + anchor, 1)
reg = '''    sp = sub.add_parser("workflow")
    sp.add_argument("action", choices=["build", "list", "show", "find", "run"])
    sp.add_argument("app", nargs="?", default="", help="application key (for show: the workflow id)")
    sp.add_argument("id", nargs="?", default="", help="workflow id (run) / the request in words (find)")
    sp.add_argument("--all", action="store_true", help="build: every application that has a guide")
    sp.add_argument("--no-cursor", action="store_true", help="run: park the window (no visible virtual cursor)")
    sp.add_argument("--no-vision", action="store_true")
    sp.set_defaults(fn=cmd_workflow)
'''
anchor2 = '    sub.add_parser("status").set_defaults(fn=cmd_status)'
assert anchor2 in s
s = s.replace(anchor2, reg + anchor2, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
