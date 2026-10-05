"""
run_app_ladder.py -- real-organ test run across a difficulty ladder of apps.

Every app goes through the organs for real:
  organ_40  single-instance launch            app_scan   headless UIA scan (adaptive, time-budgeted)
  Brain     ConstrainedJudge -> local LLM     Vision     Qwen2.5-VL-7B (llama.cpp :8081) [+ OmniParser if warm]
  organ_29  popup policy preflight            web tier   CDP scan + new-origin registry (gmail, linkedin, ...)

Brain test is self-grading and dynamic: from the app's own scan it picks N named controls, asks the
judge to "click the '<name>' control" (decisive shortcut OFF), and checks it chose that control.
Vision test grades Qwen-VL boxes against the same UIA ground truth (centre-in-box + label overlap).
Nothing is clicked. Apps we launched are closed again (WM_CLOSE); apps already open are left alone.

Desktop apps are started MINIMIZED and unfocused (universal_scan.launch_hidden), read while parked off-screen
(background_window), and - this is the part that used to say "no window appeared" - waited for with the loop's
progress-aware readiness (a splash -> login -> main-frame chain such as Steam's is followed instead of abandoned after a
flat 25 s). Each row reports the per-tier ms of the grounding ladder (uia / win32 / uia@offscreen / ocr / vision) and an
element count that is non-empty for a UIA-sparse app too, because the off-screen capture rung reads its pixels. Only
instances THIS run started are closed (a tray-resident app such as WhatsApp or Steam is shut down by its own process
family, never by name); an instance the user already had open is read passively and left alone.

Usage:
  python run_app_ladder.py                       # easy,medium,hard,web
  python run_app_ladder.py --tiers easy,medium
  python run_app_ladder.py --apps calculator,discord --no-vision
  python run_app_ladder.py --apps excel,whatsapp,steam --no-vision
"""

import argparse
import os
import re
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import headless_input as hin
from core_organs import app_scan, popup_policy as pp, qwen_vl_scanner as qv
from core_organs import background_window as bw, universal_scan as us
from core_organs.desktop_grounding import (ConstrainedJudge, DesktopGrounding, GroundedElement,
                                           JUDGE_MODEL, get_loop)
from core_organs.organ_40_app_launcher import resolve_and_launch

TIERS = {
    "easy": ["calculator", "notepad"],
    "medium": ["word", "excel", "whatsapp"],
    "hard": ["discord", "obs studio", "steam"],
}
WEB = ["https://mail.google.com/", "https://www.linkedin.com/login"]


def toks(s):
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 1}


def wait_window(g, app, timeout=25.0):
    end = time.time() + timeout
    while time.time() < end:
        h = g.find_window(app)
        if h:
            return h
        time.sleep(0.5)
    return None


def brain_probe(scan, hwnd, n=3):
    """Ask the judge to pick named controls; ground truth = the control we named."""
    named = {}
    for e in scan.elements:
        nm = (e["name"] or "").strip()
        if 3 <= len(nm) <= 30 and nm.lower() not in named and e["bbox"][2] > e["bbox"][0]:
            named[nm.lower()] = e
    picks = list(named.values())[:: max(1, len(named) // n)][:n]
    judge = ConstrainedJudge()
    els = [GroundedElement(id=str(i), name=e["name"] or e["role"], role=e["role"], bbox=e["bbox"],
                           tier="uia", confidence=0.9, hwnd=hwnd) for i, e in enumerate(scan.elements)]
    ok = valid = 0
    lat = []
    for tgt in picks:
        goal = f"click the '{tgt['name']}' control"
        t0 = time.perf_counter()
        d = judge.decide(goal, els, app_hint="", use_decisive=False)
        lat.append((time.perf_counter() - t0) * 1000)
        if d and not d.get("invalid"):
            valid += 1
            chosen = els[d["element_index"]]
            if chosen.name.lower() == tgt["name"].lower():
                ok += 1
    k = max(1, len(picks))
    return {"n": len(picks), "valid": valid / k, "correct": ok / k, "ms": int(sum(lat) / max(1, len(lat)))}


def vision_probe(scan, hwnd, g, n=2, backend="llamacpp"):
    """Targeted grounding: ask the VLM to LOCATE n named controls (a full-screen parse is minutes
    at ~2 tok/s on this GPU). Hit = box overlaps the real UIA box (IoU>0.3 or centre inside)."""
    img, why = hin.capture_window(hwnd)
    if img is None:
        return {"error": why}
    off = g._window_origin(hwnd)
    named = {}
    for e in scan.elements:
        nm = (e["name"] or "").strip()
        if 3 <= len(nm) <= 24 and nm.lower() not in named and e["bbox"][2] - e["bbox"][0] > 8 and e["hwnd"] == hwnd:
            named[nm.lower()] = e
    targets = list(named.values())[:: max(1, len(named) // n)][:n]
    hits, ms, err = 0, [], ""
    for t in targets:
        rb = (t["bbox"][0] - off[0], t["bbox"][1] - off[1], t["bbox"][2] - off[0], t["bbox"][3] - off[1])
        box, meta = qv.locate(img, t["name"], backend=backend, timeout_s=100)
        ms.append(meta["ms"])
        err = err or meta["error"]
        if box:
            cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
            ix = max(0, min(box[2], rb[2]) - max(box[0], rb[0])) * max(0, min(box[3], rb[3]) - max(box[1], rb[1]))
            un = (box[2] - box[0]) * (box[3] - box[1]) + (rb[2] - rb[0]) * (rb[3] - rb[1]) - ix
            if (un and ix / un > 0.3) or (rb[0] <= cx <= rb[2] and rb[1] <= cy <= rb[3]):
                hits += 1
    return {"n": len(targets), "hits": hits, "ms": int(sum(ms) / max(1, len(ms))), "error": err}


def _family_pids(main_pid):
    """PIDs of the process family a window belongs to: the owning process and everything descended from it."""
    try:
        import psutil
        root = psutil.Process(main_pid)
        return {main_pid} | {c.pid for c in root.children(recursive=True)}
    except Exception:
        return {main_pid}


def _stop_instance(hwnd, pre_pids):
    """Close an instance THIS run started and VERIFY it is gone. Polite first (WM_CLOSE, discard-unsaved prompt), then - for
    a tray-resident app that hides instead of closing - its own process family (processes that did not exist before the
    launch and descend from, or share the install folder of, the window's process). Never by image name."""
    pid = hin.window_pid(hwnd) if hwnd else 0
    closed = us.close_window(hwnd, timeout_s=4.0, discard_unsaved=True) if hwnd else True
    if closed and not pid:
        return "closed"
    try:
        import psutil
        main = psutil.Process(pid)
        install = os.path.dirname(main.exe()).lower()
        fam = {p for p in psutil.process_iter(["pid", "exe"])
               if p.pid not in pre_pids and (p.info.get("exe") or "").lower().startswith(install)}
        fam |= {psutil.Process(x) for x in _family_pids(pid) if x not in pre_pids and psutil.pid_exists(x)}
        killed = 0
        for p in fam:
            try:
                p.terminate()
                killed += 1
            except Exception:
                pass
        gone, alive = psutil.wait_procs(list(fam), timeout=5)
        for p in alive:
            try:
                p.kill()
            except Exception:
                pass
        # A tray-resident packaged app may be RESTARTED by its own supervisor right after we stop it (measured: WhatsApp.Root
        # came back ~20 s later). Look again for a bounded moment and stop whatever our run caused to exist.
        respawned = 0
        for _ in range(2):
            time.sleep(2.5)
            late = [p for p in psutil.process_iter(["pid", "exe"])
                    if p.pid not in pre_pids and (p.info.get("exe") or "").lower().startswith(install)]
            for p in late:
                try:
                    p.terminate()
                    respawned += 1
                except Exception:
                    pass
            if late:
                psutil.wait_procs(late, timeout=4)
            else:
                break
        return (f"window {'closed' if closed else 'hid-to-tray'}; stopped {killed} process(es) of its own family"
                + (f" + {respawned} respawned by the app's supervisor" if respawned else ""))
    except Exception as exc:  # noqa: BLE001
        return f"window {'closed' if closed else 'still open'} ({type(exc).__name__})"


def run_desktop(app, do_vision, g):
    row = {"app": app}
    try:
        import psutil
        pre_pids = {p.pid for p in psutil.process_iter()}
    except Exception:
        pre_pids = set()
    pre_hwnd = g.find_window(app)
    pre = pre_hwnd is not None
    t0 = time.perf_counter()
    hwnd, launch_note = pre_hwnd, ""
    if not pre:
        info = us.launch_hidden(app, timeout_s=90.0)
        launch_note = "; ".join(info.get("notes", []))[:120]
        hwnd = info.get("hwnd") or None
        row["launched_hidden"] = bool(hwnd)
    loop = get_loop()
    loop._launched_apps.add(app.lower()) if not pre else None
    # progress-aware readiness (follows a splash chain) + keeps a minimized window parked for the whole measurement
    loop._run_depth += 1
    try:
        hwnd2, elements, rep = loop._wait_for_ready(app)
        hwnd = hwnd2 or hwnd
        row["launch_s"] = round(time.perf_counter() - t0, 1)
        row["launched_by_us"] = not pre
        row["launch_note"] = launch_note
        row["ready_wait_s"] = rep.get("ready_wait_s")
        if rep.get("ready_deadline_extended_s"):
            row["ready_deadline_extended_s"] = rep["ready_deadline_extended_s"]
        if not hwnd:
            row["error"] = "no window appeared (tray-only / sign-in gated / not installed)"
            return row
        try:
            pp.clear_blockers(hwnd, mode="preflight")
        except Exception:
            pass
        # the ladder, with per-tier ms: UIA first; a UIA-sparse app escalates through the off-screen capture (OCR)
        g_rep_tiers = {}
        tg = time.perf_counter()
        h1, els1, rep1 = g.ground(app, max_tier=2)
        g_rep_tiers.update(rep1.get("tier_ms", {}))
        ladder_els = els1
        sparse = len([e for e in els1 if e.role != "pane"]) < 8
        if sparse:
            h2, els2, rep2 = g.ground(app, target_text="zz_absent_widget_zz", max_tier=4 if do_vision else 3)
            g_rep_tiers.update(rep2.get("tier_ms", {}))
            ladder_els = els2 or els1
            row["escalated"] = {"offscreen": rep2.get("offscreen"), "tiers_ran": rep2.get("tiers_ran"),
                                "tiers_skipped": rep2.get("tiers_skipped")}
        row["ladder"] = {"elements": len(ladder_els), "uia_elements": len(els1), "tier_ms": g_rep_tiers,
                         "by_tier": {t: sum(1 for e in ladder_els if e.tier == t) for t in {e.tier for e in ladder_els}},
                         "ladder_s": round(time.perf_counter() - tg, 1)}
        scan = app_scan.scan_desktop(hwnd)
        row["scan"] = scan.stats
        if scan.elements:
            row["brain"] = brain_probe(scan, hwnd)
        if do_vision and qv.available() and scan.elements:
            row["vision"] = vision_probe(scan, hwnd, g)
    finally:
        loop._run_depth -= 1
        if loop._run_depth == 0:
            loop._release_held()
        if not pre and hwnd:
            row["stopped"] = _stop_instance(hwnd, pre_pids)
    return row


def run_web():
    from core_organs.organ_40_app_launcher import AppLauncher, AppCatalog
    rows = []
    if not app_scan.cdp_tabs():
        AppLauncher(AppCatalog()).launch("chrome")
        end = time.time() + 20
        while time.time() < end and not app_scan.cdp_tabs():
            time.sleep(1)
    if not app_scan.cdp_tabs():
        return [{"app": "web", "error": "Chrome CDP (9222) not reachable"}]
    watcher = app_scan.WebAppWatcher()
    for url in WEB:
        try:
            urllib_req = __import__("urllib.request").request.Request(
                f"http://127.0.0.1:9222/json/new?{url}", method="PUT")
            __import__("urllib.request").request.urlopen(urllib_req, timeout=5).read()
        except Exception as exc:  # noqa: BLE001
            rows.append({"app": url, "error": f"open tab: {exc}"})
            continue
    time.sleep(6)
    t0 = time.perf_counter()
    results = watcher.poll_once()
    for r in results:
        rows.append({"app": r.target[:48], "scan": r.stats})
    rows.append({"app": "(registry)", "registry": [(o, d, e) for o, _t, _s, _n, e, _dep, d, _v in watcher.reg.all()][:8],
                 "detected_new": watcher.detected, "poll_s": round(time.perf_counter() - t0, 1)})
    return rows


def fmt(row):
    if row.get("registry") is not None:
        return f"  registry: {row['registry']} new={row.get('detected_new')} poll={row.get('poll_s')}s"
    if row.get("error"):
        return f"  {row['app']:<28} ERROR {row['error']}"
    s = row.get("scan", {})
    line = (f"  {row['app'][:28]:<28} {s.get('difficulty','?'):<6} score={s.get('difficulty_score')} "
            f"nodes={s.get('nodes')} act={s.get('actionable')} depth={s.get('max_depth')} "
            f"scan={s.get('ms')}ms vision_needed={s.get('needs_vision')} trunc={s.get('truncated')}")
    lad = row.get("ladder")
    if lad:
        line += (f"\n      ladder: {lad['elements']} elements (uia {lad['uia_elements']}; by tier {lad['by_tier']}) "
                 f"per-tier ms {lad['tier_ms']} in {lad['ladder_s']}s; ready after {row.get('ready_wait_s')}s"
                 + (f" (deadline extended {row['ready_deadline_extended_s']}s: window chain followed)" if row.get('ready_deadline_extended_s') else ""))
        esc = row.get("escalated")
        if esc and esc.get("offscreen"):
            o = esc["offscreen"]
            line += (f"\n      off-screen capture: used={o.get('used')} resolved_by={o.get('resolved_by')} round_trip={o.get('round_trip_ms')}ms "
                     f"ended_minimized={o.get('ended_minimized')} via {o.get('tiers_via')} skipped={esc.get('tiers_skipped')}")
    if row.get("stopped"):
        line += f"\n      cleanup: {row['stopped']}"
    b, v = row.get("brain"), row.get("vision")
    if b:
        line += f"\n      brain[{JUDGE_MODEL}]: valid={b['valid']*100:.0f}% correct={b['correct']*100:.0f}% {b['ms']}ms/decision (n={b['n']})"
    if v:
        line += ("\n      vision[Qwen2.5-VL-7B locate]: " + (v["error"] if v.get("error") and not v.get("n")
                 else f"hit {v['hits']}/{v['n']} {v['ms']}ms/locate {v.get('error', '')}"))
    return line


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", default="easy,medium,hard,web")
    ap.add_argument("--apps", default="")
    ap.add_argument("--no-vision", action="store_true")
    a = ap.parse_args()
    g = DesktopGrounding()
    get_loop()  # arms background OmniParser warmup + organ wiring
    out = [f"App ladder run {time.strftime('%Y-%m-%d %H:%M:%S')}  judge={JUDGE_MODEL}  "
           f"qwen-vl={'up' if qv.available() else 'DOWN'}", ""]
    t_all = time.perf_counter()
    if a.apps:
        order = [("custom", [x.strip() for x in a.apps.split(",") if x.strip()])]
    else:
        order = [(t, TIERS[t]) for t in a.tiers.split(",") if t in TIERS]
    for tier, apps in order:
        out.append(f"== tier: {tier}")
        for app in apps:
            row = run_desktop(app, not a.no_vision, g)
            out.append(fmt(row))
            print(fmt(row), flush=True)
    if "web" in a.tiers and not a.apps:
        out.append("== tier: web")
        for row in run_web():
            out.append(fmt(row))
            print(fmt(row), flush=True)
    out.append(f"\ntotal {time.perf_counter() - t_all:.0f}s; physical-input guard violations={len(hin.VIOLATIONS)}")
    text = "\n".join(out)
    print("\n" + text)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_ladder_results.txt"), "a",
              encoding="utf-8") as f:
        f.write(text + "\n\n")


if __name__ == "__main__":
    main()
