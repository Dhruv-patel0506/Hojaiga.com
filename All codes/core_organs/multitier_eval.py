"""
multitier_eval -- the executor on apps of three difficulty tiers, owned and parked, measured: REPORT FORM 1.

    python -m core_organs.multitier_eval [--apps notepad,calculator,...] [--max-controls 30] [--no-probe]

Per app (an owned instance, never the person's own window; a throw-away profile for browsers):
  * model-alone accuracy        the adapter's click on "Click the <name> <kind>" for every askable control UIA reports (no click is made), v1 prompt
  * name-assisted accuracy      the same answers after the UIA-name correction the Agent applies (exact wording only)
  * crop-assisted accuracy      NOT measured here: it needs an adapter trained on prompt format v2 (zoomed strips + names); what IS measured is how many controls are dense-icon material (<= 28 px) and how
                                many zoom strips the v2 prompt builds for the screen
  * verification catch / rollback   the Agent with a deliberately WRONG target (a different safe control) and the assist off: does goal-aware verification flag it, and is it undone
  * per-step latency            observe + retrieve + ground + act + verify, seconds
Seen / zero-shot: an app is 'seen' when the training set holds any pair of that app_key; each control is 'seen' when its UIA name was in the training split for that app.
Safety: controls are filtered by safety_guard + the recorder's deny list + EXTRA_DENY (record / stream / camera ... in apps that have them); nothing is clicked in the accuracy pass; the probe clicks only
safe, uniquely named controls of an owned throw-away instance; no sign-in, no account, no files of the person.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

TIERS: List[Dict[str, Any]] = [
    {"tier": "easy", "app": "Notepad", "launch": "notepad", "key": "notepad"},
    {"tier": "easy", "app": "Calculator", "launch": "calculator", "key": "calculator"},
    {"tier": "easy", "app": "Clock", "launch": "clock", "key": "clock"},
    {"tier": "easy", "app": "Sticky Notes", "launch": "Sticky Notes", "key": "sticky_notes"},
    {"tier": "medium", "app": "MS Paint (ribbon)", "launch": "paint", "key": "ms_paint", "prepare": ["Show toolbar"]},
    {"tier": "medium", "app": "Word (throw-away doc)", "launch": "Word", "key": "word"},
    {"tier": "medium", "app": "PowerPoint (throw-away deck)", "launch": "PowerPoint", "key": "powerpoint"},
    {"tier": "medium", "app": "Edge (throw-away profile)", "launch": "Microsoft Edge", "key": "edge", "url": "about:blank"},
    {"tier": "medium", "app": "VS Code", "launch": "Visual Studio Code", "key": "vscode"},
    {"tier": "hard", "app": "YouTube Web (no sign-in)", "launch": "Microsoft Edge", "key": "youtube_web", "url": "https://www.youtube.com/", "load_s": 9, "sabotage": False},
    {"tier": "hard", "app": "OBS Studio (no record/stream)", "launch": "OBS Studio", "key": "obs_studio", "sabotage": False},
]
EXTRA_DENY = re.compile(r"record|stream|virtual|camera|broadcast|capture|microphone|mic\b|audio|sign|log ?in|subscribe|like|dislike|share|download|save|clip|buy|join|upgrade|delete|remove|"
                        r"uninstall|exit|quit|close|shutdown|restart|power", re.I)
PROBE_TYPES = ("ButtonControl", "TabItemControl", "RadioButtonControl", "CheckBoxControl", "SplitButtonControl", "MenuItemControl")


def dataset_apps(root: str) -> Dict[str, int]:
    """{app_key: pairs} of everything in the training set (any route)."""
    out: Dict[str, int] = {}
    p = os.path.join(root, "training", "ui_training_dataset.jsonl")
    if os.path.isfile(p):
        for line in open(p, encoding="utf-8"):
            try:
                k = json.loads(line).get("meta", {}).get("app_key")
            except Exception:
                continue
            if k:
                out[k] = out.get(k, 0) + 1
    return out


def _safe_probe_controls(controls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from core_organs import live_eval as LE
    names = [c["name"] for c in controls]
    out, seen = [], set()
    for c in controls:
        if c["type"] not in PROBE_TYPES or c["name"] in seen or names.count(c["name"]) != 1:
            continue
        if not LE._askable(c) or EXTRA_DENY.search(c["name"]) or c["box"][2] < 14 or c["box"][3] < 14 or len(c["name"]) > 40:
            continue
        seen.add(c["name"])
        out.append(c)
    return out


def _spread(items: List[Any], n: int) -> List[Any]:
    if len(items) <= n:
        return list(items)
    step = len(items) / float(n)
    return [items[int(i * step)] for i in range(n)]


def probe(s: Any, key: str, ground: Any, rag: Any, n_honest: int = 3, n_sab: int = 2, sabotage: bool = True) -> Dict[str, Any]:
    """The Agent loop on this app: n_honest steps with the real model, n_sab steps with a wrong target forced (assist off)."""
    from core_organs import agent_executor as AE
    from core_organs.harvest import local_recorder as LR
    out: Dict[str, Any] = {"honest": [], "sabotage": []}
    gt_map: Dict[str, int] = {}

    def observe() -> Dict[str, Any]:
        o = s.observe()
        gt_map.clear()
        for c in o["controls"]:
            el = LR.element_at(o["som"], c["box"])
            if el is not None:
                gt_map[c["name"]] = el["id"]
        return o
    def observe_lite() -> Dict[str, Any]:
        o = s.observe_lite()
        gt_map.clear()
        for c in o["controls"]:
            el = LR.element_at(o["som"], c["box"])
            if el is not None:
                gt_map[c["name"]] = el["id"]
        return o
    first = observe()
    cands = _safe_probe_controls(first["controls"])
    honest = _spread(cands, n_honest)
    rest = [c for c in cands if c not in honest]
    # PRODUCTION path: UIA first (no model, no OCR) when the tree answers; the model on the full scan otherwise
    ag = AE.Agent(key, observe_lite, ground, s.act, rag=rag, settle_s=0.5, recover=s.recover, assist=True, uia_first=True, observe_full=observe)
    for c in honest:
        goal = LR.goal_for(c["name"], c["type"])
        try:
            rec = ag.step(goal)
            want = gt_map.get(c["name"])
            got = rec.attempts[-1]["target_id"] if rec.attempts else (rec.action or {}).get("target_id")
            out["honest"].append({"goal": goal, "status": rec.status, "reason": rec.reason, "right_control": (got == want) if want is not None else None, "route": rec.source, "assisted": rec.assisted,
                                  "rolled_back": rec.rolled_back, "seconds": round(rec.ms / 1000.0, 2), "timings": rec.timings})
        except Exception as exc:
            out["honest"].append({"goal": goal, "status": "exception", "why": f"{type(exc).__name__}: {str(exc)[:80]}"})
        s.app.chord("esc")
        time.sleep(0.6)
    if sabotage and len(rest) >= 2:
        for i, c in enumerate(_spread(rest, n_sab)):
            other = next((x for x in rest if x["name"] != c["name"] and x["name"] not in c["name"]), None)
            if other is None:
                continue
            goal = LR.goal_for(c["name"], c["type"])
            sab_id: Dict[str, Any] = {}

            def wrong(image: Any, som: Dict[str, Any], app_key: str, g: str, _o=other, _id=sab_id):
                el = LR.element_at(som, _o["box"])
                if el is None:
                    return None, ""
                _id["id"] = el["id"]
                return {"step": 1, "action": "click", "target_id": el["id"], "hotkey": None, "text": None, "verify_expectation": "the screen changes"}, "forced wrong target"
            ag2 = AE.Agent(key, observe, wrong, s.act, rag=None, settle_s=1.0, recover=s.recover, assist=False, max_attempts=1)
            try:
                rec = ag2.step(goal)
                flagged = rec.status != "done"
                out["sabotage"].append({"goal": goal, "wrong_control": other["name"], "status": rec.status, "reason": rec.reason, "flagged": flagged, "rolled_back": rec.rolled_back, "seconds": round(rec.ms / 1000.0, 2)})
            except Exception as exc:
                out["sabotage"].append({"goal": goal, "status": "exception", "why": f"{type(exc).__name__}: {str(exc)[:80]}"})
            s.app.chord("esc")
            time.sleep(0.6)
    return out


def run_app(spec: Dict[str, Any], ground: Any, seen_apps: Dict[str, int], seen_controls: Dict[str, set], rag: Any, max_controls: int, do_probe: bool) -> Dict[str, Any]:
    from core_organs import agent_executor as AE, live_eval as LE
    from core_organs.harvest import local_recorder as LR_, prompt_v2 as P2, video_pipeline as VP
    LR_.OwnedApp.READY_S = 25.0
    LR_.OwnedApp.VISIBLE_FALLBACK = True                            # the person asked for this second approach: open the app normally, then park it
    row: Dict[str, Any] = {"tier": spec["tier"], "app": spec["app"], "key": spec["key"], "seen_in_training": spec["key"] in seen_apps, "training_pairs": seen_apps.get(spec["key"], 0)}
    t0 = time.time()
    try:
        s_cm = None
        for attempt in range(3):                                     # a cold start of a packaged / Electron app can miss the first window: one fresh start, a longer wait
            s_cm = AE.LiveSession(spec["launch"])
            try:
                s_cm.__enter__()
                break
            except Exception as exc:
                row.setdefault("start_attempts", []).append(f"{type(exc).__name__}: {str(exc)[:80]}")
                with __import__("contextlib").suppress(Exception):
                    s_cm.__exit__(None, None, None)
                s_cm = None
                time.sleep(4.0)
        if s_cm is None:
            raise RuntimeError(row["start_attempts"][-1])
        s = s_cm
        try:
            for nm in spec.get("prepare", []):                       # data, per app: a control that reveals the rest of the interface (a collapsed toolbar)
                from core_organs import canvas_live as CL
                CL.LivePainter(s).press(nm, "reveal", wait=1.5)
            if spec.get("url"):
                port = (getattr(s.app, "info", {}) or {}).get("cdp_port")
                if port:
                    from core_organs.professor.adapters.cdp import CdpBrowser
                    b = CdpBrowser(port)
                    b.wait(15.0)
                    pg = b.page()
                    if pg is not None:
                        pg.navigate(spec["url"])
                        time.sleep(float(spec.get("load_s", 3)))
                else:
                    row["note"] = "no DevTools port: the page was not navigated"
            res = LE.click_accuracy(s.app, spec["key"], ground, seen_controls.get(spec["key"], set()), VP.som_of_frame, max_controls=max_controls, state="initial")
            row["accuracy"] = res.get("summary", {})
            row["asked"] = len(res.get("rows", []))
            row["rows"] = res.get("rows", [])
            img, origin = s.app.grab(popups=True)
            if img is not None:
                som = VP.som_of_frame(img)
                row["elements"] = len(som["elements"])
                strips = P2.dense_strips(som["elements"], img.size)
                row["dense_strips_v2"] = len(strips)
                row["dense_small_elements"] = sum(1 for e in som["elements"] if e["box"][2] <= 28 and e["box"][3] <= 28)
            if do_probe:
                row["probe"] = probe(s, spec["key"], ground, rag, sabotage=spec.get("sabotage", True))
        finally:
            s_cm.__exit__(None, None, None)
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    row["seconds"] = round(time.time() - t0, 1)
    return row


def form1(rows: List[Dict[str, Any]]) -> str:
    """REPORT FORM 1 as a markdown table + the honest footnotes."""
    def pct(v: Any) -> str:
        return "n/a" if v is None else f"{100 * v:.0f}%"
    lines = ["| Tier | App | Seen / zero-shot | Asked | Model alone | Name-assisted | Dense icons (<=28px) alone / assisted | Crop-assisted | Verification catch | Rollback | s / step |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("error"):
            lines.append(f"| {r['tier']} | {r['app']} | {'seen' if r['seen_in_training'] else 'zero-shot'} | - | could not run: {r['error'][:60]} | | | | | | |")
            continue
        a = r.get("accuracy", {}).get("all", {})
        d = r.get("accuracy", {}).get("dense_icons", {})
        pr = r.get("probe", {})
        hon, sab = pr.get("honest", []), pr.get("sabotage", [])
        caught = [x for x in sab if x.get("flagged")]
        wrong_effect = [x for x in sab if x.get("status") == "wrong_effect"]
        lat = [x["seconds"] for x in hon if "seconds" in x]
        lines.append("| {t} | {app} | {seen} | {n} | {m} | {an} | {dn}: {dm} / {da} | not measurable (needs v2 retrain) | {cat} | {rb} | {lat} |".format(
            t=r["tier"], app=r["app"], seen="seen" if r["seen_in_training"] else "zero-shot", n=r.get("asked", 0), m=pct(a.get("exact")), an=pct(a.get("assisted_exact")), dn=d.get("n", 0), dm=pct(d.get("exact")),
            da=pct(d.get("assisted_exact")), cat=(f"{len(caught)}/{len(sab)}" if sab else "not run"), rb=(f"{sum(1 for x in wrong_effect if x.get('rolled_back'))}/{len(wrong_effect)}" if wrong_effect else ("n/a" if sab else "not run")),
            lat=(f"{sum(lat) / len(lat):.1f}" if lat else "n/a")))
    zs = sum(1 for r in rows if not r["seen_in_training"])
    lines.append("")
    lines.append(f"Zero-shot share: {zs}/{len(rows)} apps ({100 * zs / max(len(rows), 1):.0f}%), target >= 30%.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apps", default="")
    ap.add_argument("--max-controls", type=int, default=12)
    ap.add_argument("--no-probe", action="store_true")
    ap.add_argument("--out", default=r"D:\new_automation\data\multitier")
    a = ap.parse_args(argv)
    from core_organs import agent_executor as AE, live_eval as LE, rag as RAG
    from core_organs.harvest.paths import harvest_dir
    root = harvest_dir()[0]
    run_dir = os.path.dirname(sorted(glob.glob(os.path.join(root, "training", "runs", "run_*", "adapter")), key=os.path.getmtime)[-1])
    seen_apps, seen_controls = dataset_apps(root), LE.trained_control_names(run_dir)
    want = {x.strip().lower() for x in a.apps.split(",") if x.strip()}
    specs = [t for t in TIERS if not want or t["key"] in want or t["launch"].lower() in want]
    ground = AE.AdapterGrounder(os.path.join(run_dir, "adapter"))
    rag = RAG.get_rag()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(a.out, stamp)
    os.makedirs(out_dir, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    for sp in specs:
        r = run_app(sp, ground, seen_apps, seen_controls, rag, a.max_controls, not a.no_probe)
        rows.append(r)
        json.dump({"run_dir": run_dir, "rows": rows}, open(os.path.join(out_dir, "multitier.json"), "w", encoding="utf-8"), indent=1, default=str)
        print("APP", json.dumps({k: v for k, v in r.items() if k not in ("rows",)}, default=str)[:1500], flush=True)
    ground.unload()
    md = form1(rows)
    open(os.path.join(out_dir, "report_form1.md"), "w", encoding="utf-8").write(md)
    print(md, flush=True)
    print("DONE", out_dir, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
