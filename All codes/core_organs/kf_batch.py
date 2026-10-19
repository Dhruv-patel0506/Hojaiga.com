"""
kf_batch -- ONE timed batch: every case twice, COLD (no stored plan, no scanned-app registry) then WARM (what the first pass left behind), with seconds, model calls and the verified status per case.

    python -m core_organs.kf_batch [--only id id ...] [--no-flows]

Cold = data/proc_cache.json and data/app_registry.json are set aside first (merged back at the end: nothing the run did not touch is lost). Warm = the very next run of the same task.
A case counts as PASS only when its own independent check passed (read-back / object model / DOM / 3-view picture score >= 4/5); the latency budget is reported next to it (warm <= 20 s with 0 planner calls, cold <= 90 s),
never folded into the status. Output: data/mvp_proof_gallery/KNOWLEDGE_FIRST_REPORT.md + results/kf_*.json + before_after_<case>_<cold|warm>.png.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.join("D:" + os.sep, "new_automation", "All codes"))

from core_organs import gauntlet as G                                           # noqa: E402

DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
ORDER = ["notepad", "notepad_replace", "calculator", "calculator_chain", "word", "powerpoint", "blender_table", "blender_lamp", "blender_chair", "blender_bookshelf", "excalidraw", "wikipedia", "flow_web_to_excel", "selfheal_calculator"]
WARM_S, COLD_S = 20.0, 90.0


def _calls(res: Dict[str, Any]) -> Optional[int]:
    rep = res.get("report") or {}
    if isinstance(rep.get("model_calls"), int):
        return rep["model_calls"]
    v = rep.get("verification") or {}
    if isinstance(v.get("model_calls"), int):
        return v["model_calls"]
    return None


def _tier(res: Dict[str, Any]) -> str:
    rep = res.get("report") or {}
    return str(rep.get("tier") or rep.get("plan_source") or "")


def run_case(c: Dict[str, Any], section: Any) -> Dict[str, Any]:
    t0 = time.time()
    try:
        if c["kind"] == "desktop":
            r = G.run_desktop(c, section, print)
        elif c["kind"] == "web":
            r = G.run_web(c, section, print)
        elif c["kind"] == "scripted":
            r = G.run_scripted(c, section, print)
        elif c["kind"] == "selfheal":
            r = G.run_selfheal_live(c, section, print)
        elif c["kind"] == "flow":
            from core_organs import flows as F
            r = F.flow_web_to_excel(section, print)
        else:
            r = {"ok": False, "verdict": "kind not handled"}
    except Exception as exc:                                                    # a crash is a FAIL with its reason, never a skipped row
        r = {"ok": False, "verdict": f"crash: {type(exc).__name__}: {str(exc)[:160]}"}
    r["wall_s"] = r.get("wall_s") or round(time.time() - t0, 1)
    r["status"] = r.get("status") or ("PASS" if r.get("ok") else "FAIL")
    return r


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--no-flows", action="store_true")
    a = ap.parse_args(argv)
    G.live_guard()
    cases = {c["id"]: c for c in G.CASES}
    cases["flow_web_to_excel"] = {"id": "flow_web_to_excel", "kind": "flow", "task": "read a facts table on a web page and type it into Excel"}
    ids = [i for i in ORDER if i in cases and (not a.only or i in a.only) and not (a.no_flows and cases[i]["kind"] == "flow")]
    from core_organs import app_teaching_automation as ATA
    section = ATA.AppTeachingAutomationSection(log=lambda s: print(s, flush=True))
    os.makedirs(os.path.join(G.GALLERY, "results"), exist_ok=True)
    aside: Dict[str, Any] = {}
    for name in ("proc_cache.json", "app_registry.json"):                        # cold = nothing stored for these apps; put aside, merged back at the end
        p = os.path.join(DATA, name)
        if os.path.isfile(p):
            try:
                aside[name] = json.load(open(p, encoding="utf-8"))
            except Exception:
                aside[name] = None
            shutil.move(p, p + ".kfbatch_aside")
    rows: List[Dict[str, Any]] = []
    t_all = time.time()
    try:
        for phase in ("cold", "warm"):
            for cid in ids:
                c = cases[cid]
                print(f"\n##### [{phase}] {cid}: {c.get('task', '')}", flush=True)
                r = run_case(c, section)
                png = r.get("png") or ""
                if png and os.path.isfile(png):
                    dst = os.path.join(G.GALLERY, f"before_after_{cid}_{phase}.png")
                    shutil.copy(png, dst)
                    r["png"] = dst
                row = {"case": cid, "phase": phase, "status": r["status"], "seconds": r["wall_s"], "model_calls": _calls(r), "tier": _tier(r), "png": r.get("png", ""), "verdict": str(r.get("verdict", ""))[:300]}
                json.dump(row, open(os.path.join(G.GALLERY, "results", f"kf_{cid}_{phase}.json"), "w", encoding="utf-8"), indent=1)
                rows.append(row)
                print(f"##### [{phase}] {cid}: {row['status']} {row['seconds']}s calls={row['model_calls']} tier={row['tier']}", flush=True)
    finally:
        for name, old in aside.items():                                          # what the run learned wins; what it did not touch comes back
            p = os.path.join(DATA, name)
            try:
                new = json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}
            except Exception:
                new = {}
            if isinstance(old, dict) and isinstance(new, dict):
                json.dump({**old, **new}, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            if os.path.isfile(p + ".kfbatch_aside"):
                os.remove(p + ".kfbatch_aside")
    write_report(rows, time.time() - t_all)
    return 0


def write_report(rows: List[Dict[str, Any]], total_s: float) -> str:
    by: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(r["case"], {})[r["phase"]] = r
    lines = ["# Knowledge-first timed batch", "", f"One batch, {time.strftime('%Y-%m-%d %H:%M')}, total {total_s / 60:.0f} min. Cold = no stored plan / no scanned-app registry; warm = the next run of the same task. "
             f"Budget: warm <= {WARM_S:.0f} s with 0 planner calls, cold <= {COLD_S:.0f} s. Status is the case's own independent check (read-back, object model, DOM, 3-view picture score >= 4/5); the budget columns are separate and never turn a FAIL into a PASS.", "",
             "| case | cold status | cold s | cold calls | warm status | warm s | warm calls | warm tier | within budget (cold / warm) |", "|---|---|---|---|---|---|---|---|---|"]
    for cid, d in by.items():
        c, w = d.get("cold", {}), d.get("warm", {})

        def ok_b(x: Dict[str, Any], lim: float, zero: bool) -> str:
            if not x:
                return "-"
            good = x["seconds"] <= lim and (not zero or x.get("model_calls") in (0, None))
            return "yes" if good else "no"
        lines.append(f"| {cid} | {c.get('status', '-')} | {c.get('seconds', '-')} | {c.get('model_calls', '?')} | {w.get('status', '-')} | {w.get('seconds', '-')} | {w.get('model_calls', '?')} | {w.get('tier', '')} | {ok_b(c, COLD_S, False)} / {ok_b(w, WARM_S, True)} |")
    lines += ["", "## Proof pictures", ""]
    for r in rows:
        if r.get("png"):
            lines.append(f"- {r['case']} ({r['phase']}): `{os.path.basename(r['png'])}` - {r['status']}: {r['verdict'][:160]}")
    n = sum(1 for r in rows if r["phase"] == "warm" and r["status"] == "PASS")
    lines += ["", f"Warm PASS {n}/{sum(1 for r in rows if r['phase'] == 'warm')}; cold PASS {sum(1 for r in rows if r['phase'] == 'cold' and r['status'] == 'PASS')}/{sum(1 for r in rows if r['phase'] == 'cold')}. `?` = the case does not report model calls."]
    out = os.path.join(G.GALLERY, "KNOWLEDGE_FIRST_REPORT.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return out


if __name__ == "__main__":
    sys.exit(main())
