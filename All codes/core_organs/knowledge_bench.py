"""
knowledge_bench.py -- how ACCURATE and how FAST is first-contact app knowledge?

For each app it starts from an EMPTY behavior model (the app is "introduced for the first time"), runs the real scanner
(universal_scan.scan_desktop: launch hidden, accessibility wake, E0 menu crawl, layout map, E1 probes), then grades what was
learned against an INDEPENDENT reading of the live app (a plain UIA walk with the `uiautomation` library - not the scanner's own
code path):

  recall_resting     of the named, actionable controls visible at rest, how many does the knowledge base know by name
  path_precision     of sampled learned menu paths ("File > Save as"), how many can be re-walked live (expand each level, find the leaf)
  position_accuracy  of sampled learned control positions, how many are within 3% of the window of where the control really is
  commands / regions what it learned and how many regions (menubar, ribbon, toolbar, ...) it understood
  timings            launch, ready, E0 menus, layout, E1 probes, total; a WARM re-scan; and a real task, first run vs repeat

Nothing here is a mock: every number comes from the run. Output: a table + data/knowledge_bench_results.json.

    python knowledge_bench.py [--apps calculator,notepad,paint,excel] [--no-task]
"""

import json
import os
import random
import sys
import tempfile
import time
import uuid

sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]

ACTIONABLE = ("ButtonControl", "MenuItemControl", "TabItemControl", "ListItemControl", "CheckBoxControl", "RadioButtonControl",
              "ComboBoxControl", "EditControl", "HyperlinkControl", "SplitButtonControl")
USER_CLASS = {"notepad": "Notepad", "paint": "MSPaintApp", "excel": "XLMAIN"}


def _lower(s):
    return (s or "").strip().lower()


def ground_truth(hwnd):
    """Independent read: {(type, name)} of named actionable visible controls of the window and its popups, plus live rects."""
    import uiautomation as auto
    from core_organs import headless_input as hin
    gt = {}
    for w in [hwnd] + hin.popup_windows(hwnd)[:6]:
        try:
            root = auto.ControlFromHandle(w)
            for c, _d in auto.WalkControl(root, maxDepth=18):
                # (IsOffscreen is NOT filtered: a parked window is off every monitor by design, its controls are real)
                if c.ControlTypeName in ACTIONABLE and (c.Name or "").strip():
                    r = c.BoundingRectangle
                    gt.setdefault(_lower(c.Name), (c.ControlTypeName, (r.left, r.top, r.right, r.bottom)))
        except Exception:
            continue
    return gt


def verify_path(hwnd, path, app_key=""):
    """Re-walk 'A > B > C' live: expand each level (never invoke), find the leaf by name. True/False + note."""
    import uiautomation as auto
    from core_organs import headless_input as hin
    segs = [s.strip() for s in path.split(">") if s.strip()]
    if len(segs) > 1 and _lower(segs[0]) in (_lower(app_key), _lower(app_key).replace("_", " ")):
        segs = segs[1:]            # '<app> > Settings': the app name is the virtual ROOT of a toolbar/pane control, not a UI element
    if not segs:
        return False, "empty"
    opened = []

    def find(name):
        for w in [hwnd] + hin.popup_windows(hwnd)[:6]:
            try:
                for c, _d in auto.WalkControl(auto.ControlFromHandle(w), maxDepth=18):
                    if _lower(c.Name) == _lower(name) and c.ControlTypeName in ACTIONABLE + ("TreeItemControl", "PaneControl", "GroupControl"):
                        return c
            except Exception:
                continue
        return None
    ok, note = True, "found"
    try:
        for i, seg in enumerate(segs):
            c = find(seg)
            if c is None:
                ok, note = False, f"'{seg}' not found at level {i + 1}"
                break
            if i < len(segs) - 1:
                try:
                    c.GetExpandCollapsePattern().Expand()
                    opened.append(c)
                    time.sleep(0.35)
                except Exception:
                    try:
                        c.GetSelectionItemPattern().Select()          # a tab / list level is selected, never invoked
                        time.sleep(0.35)
                    except Exception:
                        ok, note = False, f"'{seg}' could not be opened (no expand/select pattern)"
                        break
    finally:
        for c in reversed(opened):
            try:
                c.GetExpandCollapsePattern().Collapse()
            except Exception:
                pass
    return ok, note


def grade(model, key, hwnd, rng):
    from core_organs import background_window as bw
    out = {}
    with bw.BackgroundSession(hwnd):
        time.sleep(0.8)
        gt = ground_truth(hwnd)
        lay = [dict(r) for r in model._conn.execute("SELECT name, role, rx0, ry0, rx1, ry1, region_kind FROM bm_layout WHERE app_key=?", (key,))]
        cmds = model.commands(key, limit=5000)
        known = {_lower(r["name"]) for r in lay if r["name"]} | {_lower(c["name"]) for c in cmds if c.get("name")}
        for c in cmds:
            for seg in (c.get("menu_path") or "").split(">"):
                if seg.strip():
                    known.add(_lower(seg))
        hit = [n for n in gt if n in known]
        out["resting_controls_independent"] = len(gt)
        out["recall_resting"] = round(len(hit) / len(gt), 3) if gt else None
        out["missed_examples"] = [n for n in gt if n not in known][:8]
        # path precision
        # two kinds of 'path': a real MENU path found by the E0 crawl ('File > Save as': a UI hierarchy that can be re-walked) and a
        # LAYOUT path ('Grid > O8', 'list > Gold': region kind > control - a location label, not a hierarchy)
        paths = [c for c in cmds if " > " in (c.get("menu_path") or "")]
        menu_paths = [c for c in paths if (c.get("origin") or "").startswith("e0:")]
        layout_paths = [c for c in paths if not (c.get("origin") or "").startswith("e0:")]
        for label, pool in (("menu", menu_paths), ("layout", layout_paths)):
            sample = rng.sample(pool, min(12, len(pool)))
            res = []
            for c in sample:
                ok, note = verify_path(hwnd, c["menu_path"], key)
                res.append({"path": c["menu_path"][:60], "ok": ok, "note": note})
                time.sleep(0.2)
            out[f"{label}_paths_known"] = len(pool)
            out[f"{label}_paths_sampled"] = len(res)
            out[f"{label}_path_precision"] = round(sum(1 for r in res if r["ok"]) / len(res), 3) if res else None
            out[f"{label}_path_failures"] = [r for r in res if not r["ok"]][:3]
        # position accuracy: stored relative centre vs the control's real relative centre
        import ctypes.wintypes as wt
        rc = wt.RECT()
        ctypes_user32 = __import__("ctypes").windll.user32
        ctypes_user32.GetWindowRect(hwnd, __import__("ctypes").byref(rc))
        W, H = max(rc.right - rc.left, 1), max(rc.bottom - rc.top, 1)
        pos = [r for r in lay if r["name"] and _lower(r["name"]) in gt and (r["rx1"] - r["rx0"]) > 0
               and gt[_lower(r["name"])][1][2] > gt[_lower(r["name"])][1][0]]
        samp = rng.sample(pos, min(40, len(pos)))
        good = 0
        errs = []
        for r in samp:
            _t, (l, t, rr, b) = gt[_lower(r["name"])]
            cx, cy = ((l + rr) / 2 - rc.left) / W, ((t + b) / 2 - rc.top) / H
            sx, sy = (r["rx0"] + r["rx1"]) / 2, (r["ry0"] + r["ry1"]) / 2
            e = max(abs(cx - sx), abs(cy - sy))
            errs.append(e)
            good += e <= 0.03
        out["positions_sampled"] = len(samp)
        out["position_accuracy"] = round(good / len(samp), 3) if samp else None
        out["position_median_error"] = round(sorted(errs)[len(errs) // 2], 4) if errs else None
        out["layout_controls"] = len(lay)
        out["regions"] = sorted({r["region_kind"] for r in lay if r["region_kind"]})
        out["commands"] = len(cmds)
        out["commands_by_risk"] = {k: sum(1 for c in cmds if c.get("risk") == k) for k in ("E1", "E2", "EU")}
    return out


def task_for(app, tmp):
    """(command, truth_fn): a real task per app with an independent check."""
    if app == "notepad":
        p = os.path.join(tmp, "kb_notepad_%s.txt" % uuid.uuid4().hex[:5])
        return (f"open notepad, type knowledge bench and save it as {p}",
                lambda: os.path.exists(p) and "knowledge bench" in open(p, errors="replace").read().lower())
    if app == "paint":
        p = os.path.join(tmp, "kb_paint_%s.png" % uuid.uuid4().hex[:5])
        return (f"open paint and save the image as {p}",
                lambda: os.path.exists(p) and open(p, "rb").read(8) == b"\x89PNG\r\n\x1a\n")
    if app == "calculator":
        return ("open calculator and compute 6 * 7", None)
    return (None, None)


def main():
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import universal_scan as us
    from core_organs import headless_input as hin
    from core_organs import desktop_grounding as dg
    a = sys.argv[1:]
    apps = (a[a.index("--apps") + 1].split(",") if "--apps" in a else ["calculator", "notepad", "paint", "excel"])
    do_task = "--no-task" not in a
    rng = random.Random(7)
    tmp = tempfile.gettempdir()
    results = []
    for app in apps:
        row = {"app": app}
        cls = USER_CLASS.get(app)
        if cls:
            owned = [t for h, t in hin.top_level_titles(False) if hin._class_name(h) == cls]
            if owned:
                row["skipped"] = f"the user's {app} window is open ({owned[0][:30]!r}); not touched"
                results.append(row)
                print(f"{app}: SKIPPED ({row['skipped']})", flush=True)
                continue
        db = os.path.join(tmp, "hj_kb_%s.db" % uuid.uuid4().hex[:6])
        model = bm.BehaviorModel(db)
        key = bm._app_key(app)
        t0 = time.time()
        rep = us.scan_desktop(app, model, fresh=True, force=True, deepen=True, e1_actions=3, close_if_launched=False)
        row["scan_total_s"] = round(time.time() - t0, 1)
        row["phases_s"] = rep.get("phases")
        row["window_mode"] = rep.get("window_mode")
        row["e1"] = {k: (rep.get("e1") or {}).get(k) for k in ("probes", "effects_observed", "unwound_all")}
        row["scan_error"] = rep.get("error")
        hwnd = dg.DesktopGrounding().find_window(app) or 0
        if hwnd:
            try:
                row.update(grade(model, key, hwnd, rng))
            except Exception as exc:
                row["grade_error"] = f"{type(exc).__name__}: {exc}"
            # warm re-scan: the knowledge exists, how fast is the second contact
            t1 = time.time()
            rep2 = us.scan_desktop(app, model, fresh=False, force=False, deepen=True, e1_actions=3, close_if_launched=False)
            row["warm_rescan_s"] = round(time.time() - t1, 1)
            row["warm"] = rep2.get("warm")
            us.close_window(hwnd, discard_unsaved=True, timeout_s=8)
        row["ended"] = "closed"
        # ---- a real task, first run vs repeat (the knowledge/recipe benefit)
        if do_task:
            from core_organs import task_lifecycle as tl
            cmd, truth = task_for(app, tmp)
            if cmd:
                times, ok = [], []
                from core_organs import si_tests_fixes as sf_close
                before_task = sf_close._top_hwnds()
                for rep_i in range(2):
                    cmd_i, truth_i = task_for(app, tmp)
                    t2 = time.time()
                    r = tl.run_lifecycle(cmd_i)
                    times.append(round(time.time() - t2, 1))
                    verified = None
                    if truth_i:
                        time.sleep(0.5)
                        verified = bool(truth_i())
                    elif app == "calculator":
                        from core_organs import loop_first as lf
                        from core_organs import si_tests_fixes as sf
                        h = lf.handle_for("calculator")
                        verified = bool(h and "42" in " ".join(sf._names_in(h)))
                    ok.append({"status": r["status"], "verified_independently": verified, "via": [t.get("via") for t in r["tickets"]]})
                    sf_close._close_new_windows(before_task)         # only windows that did not exist before THIS task
                row["task"] = {"command": cmd[:70], "seconds_first_run": times[0], "seconds_repeat": times[1], "runs": ok}
        results.append(row)
        print(json.dumps({k: v for k, v in row.items() if k not in ("missed_examples", "path_failures")}, default=str)[:900], flush=True)
        try:
            os.remove(db)
        except OSError:
            pass
    os.makedirs(r"D:\new_automation\data", exist_ok=True)
    with open(r"D:\new_automation\data\knowledge_bench_results.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1, default=str)
    print("\nwritten data/knowledge_bench_results.json")


if __name__ == "__main__":
    main()
