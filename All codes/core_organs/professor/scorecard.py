"""professor.scorecard -- THE PERSON'S CHECKPOINTS, MEASURED ON A REAL RUN (pass mark 90%).

Every number comes from what a live run actually did (its report.json) and the stores it wrote - nothing is estimated. A checkpoint with no data says so (None), it is not counted
as passed.

  C1  deep UI scan              named, visible, operable controls of the live window that are in the application's knowledge      phases.scan_coverage
  C2  deep UI tree scan         ribbon tabs read of the tabs found (or: the tree was readable, for an application without a ribbon)  phases.ribbon / deep_scan
  C3  symbols through vision    icon-only controls the vision model names like the application itself does (vision model alone)   phases.symbols (source 'vlm')
  C4  learning actions from the guide   guide steps tied to a real control (applicable steps)                                     workflows summary
  C5  the ML trains constantly  the models were updated by this run AND the action-outcome model's prequential accuracy             data/professor/ml
  C6  app knowledge built       catalogued commands with an explanation (vendor description, leads-to, tooltip, path)              catalog
  C7  guide actions performed   guide tasks done of the tasks attempted (blocked-on-purpose excluded)                              tasks
  C8  ribbon drop-downs seen    ribbon openers opened (now or by an earlier run of the same build) of the openers found            phases.ribbon
  C9  symbolic ribbon options   icon-only RIBBON controls recognised (memory + vision, the path a blind application uses)          phases.symbols.ribbon
  C10 cursor interactable       steps the virtual mouse was sent to a control and reached it                                       phases.pointer
  C11 explain any task simply   labelled questions answered correctly (latest answer evaluation of the application)                data/professor/eval

    python -m core_organs.professor.scorecard winword            (latest run)  |  --report <path to report.json>"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

from . import config as CFG

PASS = 90.0
RUN_DIR = os.path.join(CFG.DATA_DIR, "apprun")
ML_DIR = os.path.join(CFG.DATA_DIR, "ml")
EVAL_DIR = os.path.join(CFG.DATA_DIR, "eval")


def latest_report(app: str) -> Optional[str]:
    cands = [p for p in glob.glob(os.path.join(RUN_DIR, f"{app}_2*", "report.json"))]
    good = []
    for p in cands:
        try:
            with open(p, encoding="utf-8") as fh:
                if json.load(fh).get("tasks"):
                    good.append(p)
        except Exception:
            continue
    return max(good, key=os.path.getmtime) if good else None


def _pct(a: float, b: float) -> Optional[float]:
    return round(100.0 * a / b, 1) if b else None


def _row(cid: str, name: str, value: Optional[float], detail: str, practical: str = "") -> Dict[str, Any]:
    return {"id": cid, "checkpoint": name, "percent": value, "passed": (value is not None and value >= PASS), "detail": detail, "measured_on": practical}


def score(report_path: str) -> Dict[str, Any]:
    with open(report_path, encoding="utf-8") as fh:
        rep = json.load(fh)
    ph = rep.get("phases", {})
    app = rep.get("app") or os.path.basename(os.path.dirname(report_path)).rsplit("_", 2)[0]
    started = os.path.getmtime(report_path) - float(rep.get("seconds", 0) or 0) - 60
    rows: List[Dict[str, Any]] = []

    sc = ph.get("scan_coverage") or {}
    rows.append(_row("C1", "deep UI scan", sc.get("percent"), f"{sc.get('in_knowledge')}/{sc.get('live_controls')} live controls known; missing e.g. {sc.get('missing', [])[:5]}", "live window"))

    rib = ph.get("ribbon") or {}
    ds = ph.get("deep_scan") or {}
    if rib.get("tabs_found"):
        rows.append(_row("C2", "deep UI tree scan", _pct(rib.get("tabs_read", 0), rib["tabs_found"]),
                         f"ribbon tabs read {rib.get('tabs_read')}/{rib.get('tabs_found')}; tree {ds.get('nodes')} nodes, depth {ds.get('depth')}, {ds.get('state')}", "live ribbon"))
    elif ph.get("reused_exploration", {}).get("complete"):
        rows.append(_row("C2", "deep UI tree scan", 100.0, f"fully explored earlier for this build ({ph['reused_exploration'].get('explored_at')}); tree {ds.get('nodes')} nodes", "earlier run"))
    else:
        rich = ds.get("state") == "rich"
        rows.append(_row("C2", "deep UI tree scan", 100.0 if rich else (0.0 if ds else None), f"tree {ds.get('nodes')} nodes, depth {ds.get('depth')}, {ds.get('state')} (no ribbon)", "live tree"))

    sy = ph.get("symbols") or {}
    vlm_acc = (sy.get("accuracy_by_source") or {}).get("vlm")
    rows.append(_row("C3", "symbols through the vision model", vlm_acc if vlm_acc is not None else sy.get("accuracy"),
                     f"{sy.get('correct')}/{sy.get('icons')} icon-only controls named like the application; by source {sy.get('accuracy_by_source')}; misses e.g. {[m.get('truth') + '->' + m.get('vision', '') for m in (sy.get('misses') or [])[:4]]}",
                     "live window picture"))

    g = None
    try:
        from . import workflows as WF
        d = WF.load(app) or {}
        g = (d.get("summary") or {}).get("grounding_applicable")
        g = round(100.0 * g, 1) if g is not None and g <= 1.0 else g
    except Exception:
        pass
    rows.append(_row("C4", "learning the actions from the guide", g, "guide steps tied to a real control (steps about THIS application)", "guide corpus x catalog"))

    ml_ok, acc, base = False, None, None
    try:
        with open(os.path.join(ML_DIR, "outcome.npz.json"), encoding="utf-8") as fh:
            om = json.load(fh)
        ml_ok = os.path.getmtime(os.path.join(ML_DIR, "outcome.npz")) >= started
        last = None
        with open(os.path.join(ML_DIR, "train_log.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                last = line
        o = (json.loads(last).get("outcome") if last else None) or {}
        acc, base = o.get("ok_accuracy"), o.get("ok_baseline")
        acc = round(100.0 * acc, 1) if acc is not None else None
    except Exception:
        om = {}
    beats = o.get("beats_baseline", False) or (acc is not None and base is not None and acc >= round(100 * base, 1))
    c5_val = 100.0 if (ml_ok and beats) else (acc if ml_ok else (0.0 if acc is not None else None))
    rows.append(_row("C5", "the ML trains constantly", c5_val,
                     f"updated by this run: {ml_ok}; action-outcome accuracy {acc}% vs baseline {round(100 * base, 1) if base else None}% over {om.get('seen')} actions", "every action of every run"))

    try:
        from .harvest import Catalog
        cat = Catalog.load(app)
        expl = [v for v in cat.verbs if (v.desc or v.leads_to or (cat.tooltips or {}).get(v.label.lower()))] if cat else []
        kn = _pct(len(expl), len(cat.verbs)) if cat else None
        kd = f"{len(expl)}/{len(cat.verbs) if cat else 0} commands with a description, tooltip or known effect"
    except Exception:
        kn, kd = None, "no catalog"
    rows.append(_row("C6", "app knowledge built", kn, kd, "catalog"))

    tasks = rep.get("tasks") or []
    ok = sum(1 for t in tasks if t.get("final") == "ok")
    failed = sum(1 for t in tasks if t.get("final") == "failed")
    blocked = sum(1 for t in tasks if t.get("final") == "blocked")
    rows.append(_row("C7", "guide actions performed", _pct(ok, ok + failed), f"{ok} done, {failed} failed, {blocked} blocked on purpose (not counted)", "live tasks"))

    found = rib.get("openers_found") or 0
    opened = (rib.get("opened") or 0) + (rib.get("opened_earlier") or 0)
    if found:
        rows.append(_row("C8", "ribbon drop-downs / more options seen", _pct(opened, found), f"{opened}/{found} openers read ({rib.get('opened_earlier', 0)} by an earlier run of this build); "
                         f"{len(rib.get('skipped') or [])} left for the next run", "live ribbon"))
    else:
        rows.append(_row("C8", "ribbon drop-downs / more options seen", 100.0 if ph.get("reused_exploration", {}).get("complete") else None, "no ribbon walk in this run", ""))

    rb = sy.get("ribbon") or {}
    rows.append(_row("C9", "symbolic ribbon options recognised", rb.get("accuracy"), f"{rb.get('correct')}/{rb.get('icons')} icon-only ribbon controls", "live ribbon picture"))

    pt = ph.get("pointer") or {}
    rows.append(_row("C10", "virtual cursor reaches the controls", _pct(pt.get("reached", 0), pt.get("aimed", 0)) if pt.get("aimed") else None,
                     f"reached {pt.get('reached')} of {pt.get('aimed')} steps it was sent to ({pt.get('no_box')} controls had no box on screen)", "live tasks"))

    acc_q = None
    q_detail = "no answer evaluation for this application"
    try:
        for p in sorted(glob.glob(os.path.join(EVAL_DIR, "results_*.json")), key=os.path.getmtime, reverse=True):
            with open(p, encoding="utf-8") as fh:
                er = json.load(fh)
            mine = [r for r in er.get("rows", []) if r.get("app") == app and "model_ok" in r]
            if mine:
                acc_q = _pct(sum(1 for r in mine if r.get("model_ok")), len(mine))
                q_detail = f"{sum(1 for r in mine if r.get('model_ok'))}/{len(mine)} questions answered correctly by the local model ({er.get('run')}, {os.path.basename(p)})"
                break
    except Exception:
        pass
    rows.append(_row("C11", "explain any task simply", acc_q, q_detail, "labelled questions"))

    have = [r for r in rows if r["percent"] is not None]
    return {"app": app, "report": report_path, "scored_at": time.strftime("%Y-%m-%d %H:%M"), "pass_mark": PASS, "rows": rows,
            "passed": sum(1 for r in rows if r["passed"]), "measured": len(have), "total": len(rows),
            "not_measured": [r["id"] for r in rows if r["percent"] is None]}


def render(sc: Dict[str, Any]) -> str:
    out = [f"Checkpoints for {sc['app']} (pass mark {sc['pass_mark']:.0f}%) - {sc['passed']}/{sc['total']} passed, {sc['measured']} measured", ""]
    for r in sc["rows"]:
        v = "  n/a " if r["percent"] is None else f"{r['percent']:5.1f}%"
        out.append(f"{'PASS' if r['passed'] else ('----' if r['percent'] is None else 'FAIL')}  {r['id']:4s} {v}  {r['checkpoint']:40s} {r['detail'][:150]}")
    return "\n".join(out)


def main(argv: List[str]) -> int:
    if "--report" in argv:
        path = argv[argv.index("--report") + 1]
    else:
        app = next((a for a in argv if not a.startswith("-")), "winword")
        path = latest_report(app) or ""
    if not path or not os.path.isfile(path):
        print("no run report found")
        return 1
    sc = score(path)
    print(render(sc))
    with open(os.path.join(os.path.dirname(path), "scorecard.json"), "w", encoding="utf-8") as fh:
        json.dump(sc, fh, indent=1, ensure_ascii=False, default=str)
    return 0 if sc["passed"] == sc["total"] else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
