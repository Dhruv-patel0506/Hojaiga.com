"""
overnight -- learn many applications in one unattended run: scan each owned app deeply, fill the RAG while scanning, record training pairs in prompt format v2, mark every control that opens a child window as a
deep section, and write a progress file a person (or another agent) can read in the morning.

    python -m core_organs.overnight scan   [--limit 55] [--per-app-min 12] [--only "Blender 5.2,OBS Studio"]
    python -m core_organs.overnight one    "<app name>" [--per-app-min 12]        (one app, one process; what `scan` runs for each app)
    python -m core_organs.overnight report                                         (a table of what was learned so far)

Each app runs in its OWN process with a hard wall-clock limit (a hung app cannot stop the night); the process owns the app through owned_guard, so when it ends -- finished, killed or timed out -- the app
goes with it. Quality is not traded for speed: the scan is the same deep scan (every safe control, every menu, every child window, 2-3 layouts when time allows); the per-app limit only bounds the worst case.
Safety: catalogue.EXCLUDE removes accounts / personal data / the machine; the recorder's control filters skip anything that saves, deletes, sends, signs in or leaves the app; child windows are closed with Cancel /
Close / Escape, never OK / Create; no sign-in, no account, no network action.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List

OUT = r"D:\new_automation\data\overnight"


def _state_path() -> str:
    os.makedirs(OUT, exist_ok=True)
    return os.path.join(OUT, "state.json")


def load_state() -> Dict[str, Any]:
    try:
        return json.load(open(_state_path(), encoding="utf-8"))
    except Exception:
        return {"apps": {}}


def save_state(st: Dict[str, Any]) -> None:
    json.dump(st, open(_state_path(), "w", encoding="utf-8"), indent=1, default=str)


def one(name: str, per_app_min: float) -> Dict[str, Any]:
    """Scan one application in this process; print a single RESULT line."""
    from core_organs.harvest import catalogue as CAT, local_recorder as LR
    LR.OwnedApp.READY_S = 25.0
    LR.OwnedApp.VISIBLE_FALLBACK = False                             # a visible start is only used when the person has allowed it
    if os.environ.get("HOJAIGA_VISIBLE_SCAN") == "1":
        LR.OwnedApp.VISIBLE_FALLBACK = True
    import faulthandler
    faulthandler.dump_traceback_later(int(per_app_min * 60 + 360), exit=True, file=sys.stderr)      # a scan that overruns its budget by 2.5 min reports where it stands and ends (what it learned is already saved)
    key = CAT.slug(name)
    spec = LR.APPS.get(key) or {"launch": name, "chords": [], "type": None}
    t0 = time.time()
    res: Dict[str, Any] = {"name": name, "key": key}
    try:
        progress = os.path.join(OUT, "progress", f"{key}.json")        # controls done / controls that ended the app: the next pass (or night) skips them
        rep, crashes = {}, []
        for attempt in range(5):                                        # an app that dies on a control is restarted and the scan continues from where it was
            left = per_app_min * 60.0 - (time.time() - t0)
            if left < 45 and attempt:
                break
            try:
                rep = LR.record_app(key, max_actions=90, budget_s=max(left, 60.0), spec_override=spec, rag_sink=True, progress_path=progress)
                break
            except LR.AppCrashed as ce:
                crashes.append(ce.control)
                rep = ce.rep
                with __import__("contextlib").suppress(Exception):
                    from core_organs import rag as _R
                    _R.get_rag().proc.ingest_procedure(key, f"Do not operate '{ce.control}' through UI Automation: it ends the application", [
                        {"text": f"Avoid '{ce.control}': operating it with a UI Automation pattern made {name} exit (crash). Use the keyboard or leave it alone.", "route_hint": "avoid"}], "local_recorder:crash", trust="verified")
                time.sleep(4)
        res["crashed_on"] = crashes
        rep.pop("errors", None)
        res.update({k: rep.get(k) for k in ("actions", "pairs", "pairs_v2", "no_change", "not_delivered", "no_grounding", "skipped_unsafe", "duplicates", "popups_closed", "menus_found", "mode", "child_windows_registered", "timing_s")})
        cw = rep.get("child_windows", [])
        res["child_windows"] = [{"opener": e["opener"], "child": e["child_title"], "kind": e["child_kind"], "controls": e["n_controls"], "closed_by": e["closed_by"]} for e in cw]
        res["controls_seen"] = rep.get("actions", 0) + rep.get("skipped_unsafe", 0)
        res["tier_measured"] = CAT.measured_tier(res["controls_seen"], len([e for e in cw if e["child_kind"] != "menu"]), len(rep.get("menus_found") or []))
        res["ok"] = bool(rep.get("pairs", 0) or rep.get("actions", 0))
    except Exception as exc:
        import traceback
        res["ok"] = False
        res["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        res["trace"] = traceback.format_exc()[-900:]
        print(traceback.format_exc()[-1500:], file=sys.stderr, flush=True)
    res["seconds"] = round(time.time() - t0, 1)
    print("RESULT " + json.dumps(res, default=str), flush=True)
    return res


def scan(limit: int, per_app_min: float, only: List[str]) -> None:
    from core_organs.harvest import catalogue as CAT
    from core_organs import owned_guard as OG
    apps = CAT.select(limit=limit)
    CAT.save(apps)
    if only:
        want = {o.strip().lower() for o in only}
        apps = [a for a in apps if a["name"].lower() in want] or [{"name": o, "key": CAT.slug(o), "category": CAT.classify(o)["category"], "tier_hint": CAT.classify(o)["tier_hint"]} for o in only]
    st = load_state()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = open(os.path.join(OUT, f"scan_{stamp}.log"), "a", encoding="utf-8")
    print(f"[overnight] {len(apps)} apps, {per_app_min} min each at most", flush=True)
    for i, a in enumerate(apps):
        if st["apps"].get(a["name"], {}).get("ok"):
            print(f"[overnight] {i + 1}/{len(apps)} {a['name']}: done before, skipped", flush=True)
            continue
        OG.reap_orphans()
        t0 = time.time()
        cmd = [sys.executable, "-u", "-W", "ignore", "-m", "core_organs.overnight", "one", a["name"], "--per-app-min", str(per_app_min)]
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=per_app_min * 60 + 420, env=env, cwd=r"D:\new_automation\All codes")
            out = p.stdout
            log.write(f"=== {a['name']}\n{out[-3000:]}\n{p.stderr[-1500:]}\n")
            line = next((l for l in out.splitlines() if l.startswith("RESULT ")), "")
            res = json.loads(line[7:]) if line else {"name": a["name"], "ok": False, "error": "no result line (the process ended without one)"}
        except subprocess.TimeoutExpired:
            res = {"name": a["name"], "ok": False, "error": f"hard time limit ({per_app_min * 60 + 420:.0f}s): the process and its app were ended"}
        res.update({"category": a.get("category"), "tier_hint": a.get("tier_hint")})
        st["apps"][a["name"]] = res
        save_state(st)
        log.flush()
        print(f"[overnight] {i + 1}/{len(apps)} {a['name']}: ok={res.get('ok')} pairs={res.get('pairs')} v2={res.get('pairs_v2')} tier={res.get('tier_measured')} child_windows={len(res.get('child_windows') or [])} "
              f"{res.get('seconds')}s {res.get('error', '')[:100]}", flush=True)
        time.sleep(3)
    report()


def report() -> None:
    st = load_state()
    rows = sorted(st["apps"].values(), key=lambda r: (r.get("tier_measured") if r.get("tier_measured") is not None else 9, r.get("name", "")))
    print("| app | category | tier (hint -> measured) | pairs (v1/v2) | child windows | s | note |\n|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r.get('name')} | {r.get('category')} | {r.get('tier_hint')} -> {r.get('tier_measured')} | {r.get('pairs')}/{r.get('pairs_v2')} | {len(r.get('child_windows') or [])} | {r.get('seconds')} | {'' if r.get('ok') else (r.get('error') or '')[:70]} |")
    ok = [r for r in rows if r.get("ok")]
    print(f"\n{len(ok)}/{len(rows)} apps scanned; {sum((r.get('pairs') or 0) for r in ok)} pairs; {sum(len(r.get('child_windows') or []) for r in ok)} child-window openers found")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "one", "report"])
    ap.add_argument("name", nargs="?", default="")
    ap.add_argument("--limit", type=int, default=55)
    ap.add_argument("--per-app-min", type=float, default=12.0)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    if a.cmd == "one":
        one(a.name, a.per_app_min)
    elif a.cmd == "scan":
        scan(a.limit, a.per_app_min, [x for x in a.only.split(",") if x.strip()])
    else:
        report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
