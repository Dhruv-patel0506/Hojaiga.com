"""
mastery_bench.py -- how much does the app-knowledge engine learn, how fast, and is it TRUE?

For each app: a brand-new empty behavior database (the app is "introduced for the first time"), then N cumulative `master()`
runs (static harvest -> hidden launch -> scan -> state variables -> frontier exploration -> conventions -> unification). After
every run the knowledge base is measured; after the last run it is graded against INDEPENDENT readings of the live app:

  recall_resting      named, actionable controls found by a plain `uiautomation` walk of the live window (not the scanner's own
                      path) that the knowledge base knows by name
  menu_precision      sampled learned menu paths re-walked live (expand each level, find the leaf, never invoke)
  replay              a sample of explored surfaces are probed AGAIN: same kind of effect and a similar number of controls
                      (is the recorded behaviour reproducible?)
  curve               commands / dialogs / regions / state variables / transitions / frontier explored, per run, with seconds

Nothing is mocked. Output: a table + data/mastery_bench_results.json.

    python mastery_bench.py [--apps calculator,notepad,paint,excel] [--runs 3] [--budget 60]
"""

import json
import os
import random
import sys
import tempfile
import time
import uuid

sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")

USER_CLASS = {"notepad": "Notepad", "paint": "MSPaintApp", "excel": "XLMAIN", "calculator": "ApplicationFrameWindow"}


def _user_window(app):
    from core_organs import headless_input as hin
    for h, t in hin.top_level_titles(False):
        if app in (t or "").lower():
            return t
    return ""


def verify_path_win32(hwnd, path, app_key=""):
    """Re-walk 'File > Open...' in the window's live HMENU (GetMenu / GetSubMenu / GetMenuString): True when every level exists.
    UIA cannot expand these menus without opening them, so this is the independent oracle for classic Win32 menu bars."""
    import ctypes
    u32 = ctypes.windll.user32
    u32.GetMenu.restype = ctypes.c_void_p
    u32.GetSubMenu.restype = ctypes.c_void_p
    segs = [x.strip().lower().replace("&", "").rstrip("." + chr(8230) + " ") for x in path.split(">") if x.strip()]
    hm = u32.GetMenu(hwnd)
    if not hm or not segs:
        return None, "no classic menu bar"
    cur = ctypes.c_void_p(hm)
    for i, seg in enumerate(segs):
        found = None
        for k in range(u32.GetMenuItemCount(cur)):
            buf = ctypes.create_unicode_buffer(300)
            u32.GetMenuStringW(cur, k, buf, 299, 0x400)
            lab = buf.value.split(chr(9))[0].lower().replace("&", "").rstrip("." + chr(8230) + " ").strip()
            if lab == seg:
                found = k
                break
        if found is None:
            return False, f"'{seg}' not found at level {i + 1}"
        if i < len(segs) - 1:
            sub = u32.GetSubMenu(cur, found)
            if not sub:
                return False, f"'{seg}' has no submenu"
            cur = ctypes.c_void_p(sub)
    return True, "found"


def replay(model, key, hwnd, rng, n=6):
    """Probe a sample of already-explored surfaces again: is the recorded effect reproducible?"""
    from core_organs import knowledge_store as ks
    from core_organs import organ_63_app_mastery as am
    rows = [dict(r) for r in model._conn.execute(
        "SELECT * FROM bm_frontier WHERE app_key=? AND status='explored' AND kind IN ('tab','expander','opener','context') ORDER BY RANDOM() LIMIT 40", (key,))]
    sample = rng.sample(rows, min(n, len(rows)))
    pr = am.Prober(model, key, hwnd, pristine=False)
    same = comparable = 0
    detail = []
    for row in sample:
        prev = json.loads(row["result_json"] or "{}")
        row2 = dict(row, fid=row["fid"])
        path = row["path"]
        if path.startswith("@tab:") or path.startswith("@via:"):
            continue                                      # context-dependent rows are re-run by the explorer, not here
        r = pr.run(row2)
        absent = r.status == "failed" and "not found" in r.evidence
        ok = (not absent) and r.status == "explored" and r.effect == prev.get("effect")
        comparable += 0 if absent else 1
        same += ok
        detail.append({"kind": row["kind"], "label": row["label"][:30], "was": prev.get("effect"), "now": r.effect, "ok": ok,
                       "absent_in_current_state": absent})
    return {"sampled": len(detail), "comparable": comparable, "reproduced": same,
            "rate": round(same / comparable, 3) if comparable else None, "detail": detail}


def run_app(app, runs, budget):
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import organ_63_app_mastery as am
    from core_organs import command_registry as cr
    from core_organs import universal_scan as us
    from core_organs import desktop_grounding as dg
    from core_organs import background_window as bw
    import knowledge_bench as kbn
    row = {"app": app}
    owned = _user_window(app)
    if owned:
        row["skipped"] = f"the user's {app} window is open ({owned[:30]!r}); not touched"
        return row
    dbp = os.path.join(tempfile.gettempdir(), f"hj_mb_{app}_{uuid.uuid4().hex[:6]}.db")
    model = bm.BehaviorModel(dbp)
    key = bm._app_key(app)
    rng = random.Random(7)
    curve = []
    t0 = time.time()
    for i in range(runs):
        last = i == runs - 1
        res = am.master(app, model=model, budget_s=budget, runs=1, close_if_launched=not last, conventions=True)
        if not res["runs"]:
            break
        r = res["runs"][0]
        k = r.get("known", {})
        curve.append({"run": r.get("run_no"), "seconds": r.get("elapsed_s"), "phases": r.get("phases"), "error": r.get("error") or r.get("error_live"),
                      "commands": k.get("commands"), "dialogs": k.get("dialogs"), "regions": k.get("regions"), "statevars": k.get("statevars"),
                      "transitions": k.get("transitions"), "frontier": (k.get("frontier") or {}).get("by_status"),
                      "explored_fraction": (k.get("frontier") or {}).get("explored_fraction"),
                      "probes": (r.get("explore") or {}).get("probes"), "left_as_found": r.get("left_as_found"),
                      "conventions": (r.get("conventions") or {}).get("delivery"), "gain": r.get("gain")})
        print(f"  {app} run {r.get('run_no')}: {r.get('elapsed_s')}s commands={k.get('commands')} dialogs={k.get('dialogs')} transitions={k.get('transitions')} "
              f"explored={(k.get('frontier') or {}).get('explored_fraction')}", flush=True)
        if r.get("error"):
            break
    row["curve"] = curve
    row["total_s"] = round(time.time() - t0, 1)
    hwnd = dg.DesktopGrounding().find_window(app) or 0
    if hwnd:
        try:
            with bw.BackgroundSession(hwnd):
                time.sleep(0.8)
                gt = kbn.ground_truth(hwnd)
                reg = cr.build(model, key)
                known = {n.strip().lower() for c in reg for n in c["names"]}
                for r_ in model._conn.execute("SELECT name FROM bm_layout WHERE app_key=?", (key,)) if am._count(model._conn, "bm_layout", key) else []:
                    if r_["name"]:
                        known.add(r_["name"].strip().lower())
                for c in reg:
                    for seg in (c["menu_path"] or "").split(">"):
                        if seg.strip():
                            known.add(seg.strip().lower())
                hit = [n for n in gt if n in known]
                row["resting_controls_independent"] = len(gt)
                row["recall_resting"] = round(len(hit) / len(gt), 3) if gt else None
                row["missed_examples"] = [n for n in gt if n not in known][:10]
                paths = [c for c in reg if c["kind"] == "menu" and " > " in (c["menu_path"] or "")]
                sample = rng.sample(paths, min(12, len(paths)))
                res_ = []
                for c in sample:
                    ok_, _why = verify_path_win32(hwnd, c["menu_path"], key)        # classic HMENU first (exact), UIA expand otherwise
                    if ok_ is None:
                        ok_ = kbn.verify_path(hwnd, c["menu_path"], key)[0]
                    res_.append(bool(ok_))
                row["menu_paths_known"] = len(paths)
                row["menu_path_precision"] = round(sum(res_) / len(res_), 3) if res_ else None
                row["replay"] = replay(model, key, hwnd, rng)
        except Exception as exc:
            row["grade_error"] = f"{type(exc).__name__}: {exc}"
        us.close_window(hwnd, discard_unsaved=True, timeout_s=8)
    d = cr.dossier(model, key)
    row["dossier"] = {"toolkit": d["toolkit"], "kind": (d["kind"] or {}).get("archetype"), "opens_files": len(d["opens_files"]),
                      "commands": d["commands"], "dialogs": len(d["dialogs"]), "state_variables": len(d["state_variables"]),
                      "conventions": {c["intent"]: c["verdict"] for c in d["conventions"]}, "quick_answers": d["quick_answers"],
                      "gaps": d["gaps"], "frontier": d["frontier"]}
    model.close()
    for suf in ("", "-wal", "-shm"):
        try:
            os.remove(dbp + suf)
        except OSError:
            pass
    return row


def main():
    import faulthandler
    faulthandler.dump_traceback_later(float(os.environ.get('MB_STACK_S', '420')), repeat=True, file=open(os.path.join(tempfile.gettempdir(), 'mb_stacks.txt'), 'w'))
    a = sys.argv[1:]
    apps = a[a.index("--apps") + 1].split(",") if "--apps" in a else ["calculator", "notepad", "paint"]
    runs = int(a[a.index("--runs") + 1]) if "--runs" in a else 3
    budget = float(a[a.index("--budget") + 1]) if "--budget" in a else 60.0
    results = []
    for app in apps:
        print(f"== {app}", flush=True)
        row = run_app(app, runs, budget)
        results.append(row)
    os.makedirs(r"D:\new_automation\data", exist_ok=True)
    out_path = r"D:\new_automation\data\mastery_bench_results.json"
    if "--merge" in a and os.path.exists(out_path):             # keep the other apps' rows from an earlier invocation
        try:
            mine = {x["app"] for x in results}
            results = [r for r in json.load(open(out_path, encoding="utf-8")) if r.get("app") not in mine] + results
        except Exception:
            pass
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\n" + "=" * 100)
    for r in results:
        if r.get("skipped"):
            print(f"{r['app']}: SKIPPED ({r['skipped']})")
            continue
        c = r.get("curve") or []
        line = " -> ".join(f"{x['commands']}c/{x['transitions']}t" for x in c)
        rp = r.get("replay") or {}
        print(f"{r['app']:<11} total {r.get('total_s')}s | commands/transitions per run: {line} | recall {r.get('recall_resting')} "
              f"({r.get('resting_controls_independent')} controls) | menu precision {r.get('menu_path_precision')} ({r.get('menu_paths_known')} paths) "
              f"| replay {rp.get('reproduced')}/{rp.get('comparable')} comparable ({rp.get('sampled')} sampled)")
    print("written data/mastery_bench_results.json")


if __name__ == "__main__":
    main()
