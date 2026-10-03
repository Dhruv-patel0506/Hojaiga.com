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

Usage:
  python run_app_ladder.py                       # easy,medium,hard,web
  python run_app_ladder.py --tiers easy,medium
  python run_app_ladder.py --apps calculator,discord --no-vision
"""

import argparse
import os
import re
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import headless_input as hin
from core_organs import app_scan, popup_policy as pp, qwen_vl_scanner as qv
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


def run_desktop(app, do_vision, g):
    row = {"app": app}
    pre = g.find_window(app) is not None
    t0 = time.perf_counter()
    if not pre:
        try:
            resolve_and_launch(app)
        except Exception as exc:  # noqa: BLE001
            row["error"] = f"launch: {exc}"
            return row
    hwnd = wait_window(g, app)
    row["launch_s"] = round(time.perf_counter() - t0, 1)
    row["launched_by_us"] = not pre
    if not hwnd:
        row["error"] = "no window appeared (tray-only / sign-in gated / not installed)"
        return row
    try:
        pp.clear_blockers(hwnd, mode="preflight")
    except Exception:
        pass
    time.sleep(1.0 if not pre else 0.0)
    scan = app_scan.scan_desktop(hwnd)
    row["scan"] = scan.stats
    if scan.elements:
        row["brain"] = brain_probe(scan, hwnd)
    if do_vision and qv.available():
        row["vision"] = vision_probe(scan, hwnd, g)
    if not pre:
        hin._u32.PostMessageW(hwnd, 0x0010, 0, 0)
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
