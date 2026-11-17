"""
hojaiga_atlas.py -- THE entry point of the Atlas layer: learn how ANY application works, and use that knowledge.

    python hojaiga_atlas.py learn   <app> [--tier instant|fast|deep|full] [--budget S] [--hwnd N] [--no-web] [--json]
    python hojaiga_atlas.py know    <app>                    developer-level report (Markdown) from everything stored
    python hojaiga_atlas.py ask     <app> "<question>"       answer from evidenced knowledge only
    python hojaiga_atlas.py plan    <app> "<task>" [--execute --hwnd N [--allow-destructive]]
    python hojaiga_atlas.py howto   <app> "<goal>"           step-by-step routes through the scanned UI ("insert a picture")
    python hojaiga_atlas.py explain <app> "<control>"        one control: where it is, what it opens, shortcut, state
    python hojaiga_atlas.py describe <app> "<control>"       what a control does (structure measured; one-line meaning from the local model)
    python hojaiga_atlas.py workflow <app> "<task>"          a multi-step task as a sequence of routes (+ programmatic alternatives)
    python hojaiga_atlas.py overview <app>                   the application section by section
    python hojaiga_atlas.py manual  <app>                    write the full generated user manual (Markdown)
    python hojaiga_atlas.py gestures <app>                   the gesture atlas (measured + published)
    python hojaiga_atlas.py web     <name>                   public knowledge only (no install needed)
    python hojaiga_atlas.py loop    <app> [<app> ...] [--cycles N] [--tier T] [--budget S]     overnight: each app in a watchdog subprocess
    python hojaiga_atlas.py selftest [--live]                the Atlas test suite (offline; --live adds the fixture-application tests)

As a library:
    from core_organs.hojaiga_atlas import learn, know, ask, plan, execute, Atlas
"""

from __future__ import annotations

import json
import os
import sys

for _p in (r"D:\new_automation", r"D:\new_automation\All codes"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core_organs.atlas import common as C                       # noqa: E402
from core_organs.atlas import teach, manual, uimap, scanner, architect, planner, qa, evolve, webknow, devscan, keymaps, distill, gestures, blind, motion, coverage, llm   # noqa: E402,F401
from core_organs.atlas.scanner import Atlas                      # noqa: E402

_ATLAS = None


def atlas() -> Atlas:
    global _ATLAS
    if _ATLAS is None:
        _ATLAS = Atlas()
    return _ATLAS


def learn(target, **kw):
    return atlas().learn(target, **kw)


def know(target, *, write: bool = True):
    a = atlas()
    key = C.app_key_of(str(target))
    am = architect.build(key, a.store, a.model)
    if write:
        am["_paths"] = architect.write_report(key, am, a.store)
    return am


def ask(target, question, **kw):
    """Answer from what the scanner learned. A 'how do I ...' question is first answered from the scanned UI map (step-by-step routes); everything else, and
    anything the map cannot place, from the evidenced facts."""
    a = atlas()
    key = C.app_key_of(str(target))
    r = qa.ask(key, question, a.store, a.model, **kw)
    try:
        if teach.load_map(key):
            t = teach.howto(key, question, use_model=False)
            if t.get("ok") and t["best"]["score"] >= 4.0:
                r["ui_routes"] = t["routes"]
                r["answer"] = t["answer"]
                r["method"] = "ui-map"
    except Exception:
        pass
    return r


def plan(target, task, **kw):
    a = atlas()
    return planner.plan(C.app_key_of(str(target)), task, a.store, a.model, **kw)


def execute(pl, hwnd, **kw):
    return planner.execute(pl, hwnd, **kw)


def _opt(argv, flag, default=None, cast=str):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return cast(argv[i + 1])
    return default


def _out(obj, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, default=str))
    else:
        print(json.dumps(obj, indent=1, default=str, ensure_ascii=False)[:20000])


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    rest = [a for a in argv[1:]]
    as_json = "--json" in rest
    pos = [a for i, a in enumerate(rest) if not a.startswith("--") and (i == 0 or not rest[i - 1].startswith("--") or rest[i - 1] in ("--json", "--no-web", "--execute", "--live", "--allow-destructive"))]
    if cmd in ("learn", "learn1"):
        app = pos[0] if pos else ""
        if not app:
            print("usage: learn <app> [--tier ...]")
            return 2
        res = learn(app, tier=_opt(argv, "--tier", "fast"), budget_s=_opt(argv, "--budget", None, float), hwnd=_opt(argv, "--hwnd", 0, int), web=False if "--no-web" in argv else None)
        if as_json:
            slim = {k: v for k, v in res.items() if k not in ("phases", "claims_by_kind")}
            slim["gestures"] = res.get("gestures")
            _out(slim, True)
        else:
            _out({k: v for k, v in res.items() if k != "claims_by_kind"}, False)
            print("\nreport:", (res.get("report") or {}).get("markdown"))
        return 0
    if cmd == "know":
        am = know(pos[0])
        print(architect.render_markdown(am))
        return 0
    if cmd == "ask":
        r = ask(pos[0], " ".join(pos[1:]))
        print(r["answer"])
        for f in r["facts"][:6]:
            print(f"  [{f['n']}] ({f['trust']}) {f['text'][:200]}")
        return 0
    if cmd == "plan":
        pl = plan(pos[0], " ".join(pos[1:]), use_model=True)
        if "--execute" in argv:
            hw = _opt(argv, "--hwnd", 0, int)
            pl["execution"] = execute(pl, hw, dry_run=False, allow_destructive="--allow-destructive" in argv) if hw else {"error": "--hwnd required to execute"}
        _out(pl, as_json)
        return 0
    if cmd == "howto":
        r = teach.howto(C.app_key_of(pos[0]), " ".join(pos[1:]), use_model="--no-model" not in argv)
        if as_json:
            _out(r, True)
        else:
            print(r["answer"])
        return 0
    if cmd == "explain":
        _out(teach.explain(C.app_key_of(pos[0]), " ".join(pos[1:])), as_json)
        return 0
    if cmd == "describe":
        _out(teach.describe(C.app_key_of(pos[0]), " ".join(pos[1:]), use_model="--no-model" not in argv), as_json)
        return 0
    if cmd == "workflow":
        r = teach.workflow(C.app_key_of(pos[0]), " ".join(pos[1:]), use_model="--no-model" not in argv)
        print(r["answer"]) if not as_json else _out(r, True)
        return 0
    if cmd == "overview":
        _out(teach.overview(C.app_key_of(pos[0])), as_json)
        return 0
    if cmd == "manual":
        print(manual.write(C.app_key_of(pos[0]), pos[0]))
        return 0
    if cmd == "gestures":
        key = C.app_key_of(pos[0])
        for g in atlas().store.gestures(key):
            print(f"{g['region_kind']:8s} {g['gesture']:20s} -> {g['effect_class']:26s} eff={g['effective']} rev={g['reversible']} x{g['n_obs']}")
        for c in atlas().store.claims(key, "gesture.shipped")[:40]:
            print("published:", c["statement"])
        return 0
    if cmd == "web":
        w = webknow.knowledge_for(" ".join(pos))
        _out({k: (v if k not in ("github",) else {kk: vv for kk, vv in v.items() if kk != "files"}) for k, v in w.items()}, as_json)
        return 0
    if cmd == "loop":
        res = evolve.learn_loop(pos, cycles=_opt(argv, "--cycles", 1, int), tier=_opt(argv, "--tier", "deep"), budget_s=_opt(argv, "--budget", 120, float))
        print(f"{len(res)} visit(s) done")
        return 0
    if cmd == "selftest":
        from core_organs import si_tests_atlas
        return si_tests_atlas.main(live="--live" in argv)
    print(f"unknown command: {cmd}\n")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
