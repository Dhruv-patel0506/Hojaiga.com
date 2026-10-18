"""
field_test -- a GENERIC harness for the product section: it knows no task. Jobs arrive as input and are handed to `AppTeachingAutomationSection.handle` exactly as a person's request would be.

    python -m core_organs.field_test --task "build a wooden dining table in Blender" --task "build a desk lamp in Blender"
    python -m core_organs.field_test --jobs data/field_jobs/blender_same_vs_different.json

A jobs file is a list of {"task": "...", "label": "a", "app": "" , "mode": "auto", "file": "" | "@saved:<label>", "recall": true, "expect_words": ["..."], "expect_file_ext": ".docx"}.
  file "@saved:a"   = continue in the document job 'a' saved (the SAME-FILE case: earlier content must survive).
  no file           = a fresh document (the DIFFERENT-FILE case).
Nothing in this program decides what to do; every number in the report is measured by the section during the run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.join("D:" + os.sep, "new_automation", "All codes"))

from core_organs import app_teaching_automation as ATA  # noqa: E402


def run_jobs(jobs: List[Dict[str, Any]], out_dir: str = "", log: Any = print) -> Dict[str, Any]:
    out_dir = out_dir or os.path.join(ATA.RUNS, "field_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    section = ATA.AppTeachingAutomationSection(log=log)
    saved: Dict[str, str] = {}
    results: List[Dict[str, Any]] = []
    for i, job in enumerate(jobs):
        label = job.get("label") or f"job{i + 1}"
        file = job.get("file", "")
        if file.startswith("@saved:"):
            file = saved.get(file[7:], "")
        log(f"\n=== {label}: {job['task']}  (file={'same: ' + os.path.basename(file) if file else 'new'}) ===")
        t0 = time.time()
        rep = section.handle(job["task"], app=job.get("app", ""), mode=job.get("mode", "auto"), file=file, learn=job.get("learn", "auto"), recall=job.get("recall", True),
                             live=job.get("live", False), vlm=job.get("vlm", True))
        rep["label"], rep["wall_s"] = label, round(time.time() - t0, 1)
        sv = (rep.get("saved") or {})
        if sv.get("ok"):
            saved[label] = sv["path"]
        rep["expect"] = check_expectations(rep, job)
        results.append(rep)
        json.dump(rep, open(os.path.join(out_dir, label + ".json"), "w", encoding="utf-8"), indent=1, default=str)
        log(f"=== {label}: {'ERROR ' + rep['error'] if rep.get('error') else 'ok'} in {rep['wall_s']}s; {summary_line(rep)}")
    report = {"out_dir": out_dir, "jobs": results, "summary": summarize(results)}
    json.dump(report, open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8"), indent=1, default=str)
    open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8").write(markdown(report))
    return report


def check_expectations(rep: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    """What the job said must hold, checked on the artefacts the run left (words in the saved document, a file of that kind in the sandbox, words in the spoken answer)."""
    out: Dict[str, Any] = {}
    words = [w.lower() for w in job.get("expect_words", [])]
    if words:
        hay = ((rep.get("say") or "") + " " + (rep.get("final_text") or "")).lower()
        sv = (rep.get("saved") or {}).get("path", "")
        if sv and os.path.isfile(sv):
            hay += " " + ATA.docx_text(sv).lower()
        out["words"] = {w: (w in hay) for w in words}
    ext = job.get("expect_file_ext")
    if ext:
        sb = rep.get("sandbox_files") or []
        out["file_ext"] = {ext: any(f.lower().endswith(ext) for f in sb) or str((rep.get("saved") or {}).get("path", "")).lower().endswith(ext)}
    return out


def summary_line(rep: Dict[str, Any]) -> str:
    q = rep.get("quality")
    if q:
        return f"score {q['score']} parts {q['parts_built']}/{q['parts_wanted']} connected={q['connected']} rollbacks={q['rollbacks']} untouched={q['earlier_objects_untouched']}"
    v = rep.get("verification")
    if v:
        return f"{v['done']}/{v['total']} goals, caught {v['caught']}, rollbacks {v['rollbacks']}"
    if rep.get("say"):
        return "taught: " + rep["say"].splitlines()[0][:80]
    return rep.get("mode", "")


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_state: Dict[str, List[float]] = {}
    for r in results:
        for st in r.get("flow", []):
            by_state.setdefault(st["state"], []).append(st["seconds"])
    return {"jobs": len(results), "errors": sum(1 for r in results if r.get("error")), "by_state_seconds": {k: {"n": len(v), "mean": round(sum(v) / len(v), 2), "max": round(max(v), 2)} for k, v in by_state.items()},
            "learned_on_the_fly": sum(1 for r in results if r.get("learned")), "rollbacks": sum((r.get("quality") or {}).get("rollbacks", 0) + (r.get("verification") or {}).get("rollbacks", 0) for r in results)}


def markdown(report: Dict[str, Any]) -> str:
    L = ["# Field test", "", "| job | mode | app | route | seconds | result |", "|---|---|---|---|---|---|"]
    for r in report["jobs"]:
        L.append(f"| {r['label']} | {r.get('mode', '')} | {r.get('app', '')} | {r.get('route', '')} | {r.get('wall_s', '')} | {r.get('error') or summary_line(r)} |")
    L += ["", "Latency per state (seconds): " + json.dumps(report["summary"]["by_state_seconds"])]
    return "\n".join(L)


def main(argv: Any = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", action="append", default=[])
    ap.add_argument("--jobs", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    jobs: List[Dict[str, Any]] = [{"task": t} for t in a.task]
    if a.jobs:
        jobs += json.load(open(a.jobs, encoding="utf-8"))
    if not jobs:
        print(__doc__)
        return 2
    rep = run_jobs(jobs, a.out)
    print(json.dumps(rep["summary"], indent=1))
    return 0 if not rep["summary"]["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
