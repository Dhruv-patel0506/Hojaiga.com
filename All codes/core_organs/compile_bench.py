"""
compile_bench.py -- how well is a task TURNED INTO checkpoints (offline: no desktop, no LLM)?

For each natural-language task with a hand-labelled expectation it measures, with real timings:
  * app detection   the apps found (organ_36 compiler vs the dynamic catalog detector task_intake.detect_apps) vs the labelled apps
  * domain          web / desktop / mixed / system / unknown
  * goal plan       loop_first.plan_app_goals: per-app goals, strength (strong = machine-checkable postcondition), gate decisions
                    (a labelled irreversible step must be queued by the D3 risk gate, a normal one must pass)
  * intake verdict  IMPOSSIBLE / NEEDS_INPUT / ok, vs the label

    python compile_bench.py
"""

import json
import re
import sys
import time

sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]

# (task, expected_apps, expected_domain, expected_verdict, expected_goal_substrings_per_app, irreversible_goal_expected)
CASES = [
    ("open notepad and type hello world", ["notepad"], "desktop", "ok", {"notepad": ["hello world"]}, False),
    ("open notepad, type hello and save it as C:\\temp\\a.txt", ["notepad"], "desktop", "ok", {"notepad": ["hello", "a.txt"]}, False),
    ("open calculator and compute 6 * 7", ["calculator"], "desktop", "ok", {"calculator": ["Six", "Seven"]}, False),
    ("open paint and save the image as C:\\temp\\x.png", ["paint"], "desktop", "ok", {"paint": ["x.png"]}, False),
    ("open notepad and type done, then open calculator and compute 12 + 30", ["notepad", "calculator"], "desktop", "ok",
     {"notepad": ["done"], "calculator": ["One", "Two"]}, False),
    ("open excel, click Blank workbook, type 42", ["excel"], "desktop", "ok", {"excel": ["Blank workbook", "42"]}, False),
    ("open notepad then type hello and delete the old file", ["notepad"], "desktop", "ok", {"notepad": ["hello", "delete"]}, True),
    ("in notepad write a haiku about autumn then save it as C:\\temp\\h.txt", ["notepad"], "desktop", "ok", {"notepad": ["haiku", "h.txt"]}, False),
    ("open visual studio code and type print hello", ["visual studio code"], "desktop", "ok", {"visual studio code": ["print hello"]}, False),
    ("open settings and click Bluetooth & devices", ["settings"], "desktop", "ok", {"settings": ["Bluetooth"]}, False),
    ("go to https://example.org and read the heading", [], "web", "ok", {}, False),
    ("open excel and also search google for weather in Atlanta", ["excel"], "mixed", "ok", {}, False),
    ("1. open calculator and compute 6*7\n2. open notepad and type done", ["calculator", "notepad"], "desktop", "ok", {}, False),
    ("rename the file report.txt to final.txt", [], "system", "ok", {}, False),
    ("clean this up", [], "unknown", "NEEDS_INPUT", {}, False),
    ("use hand gestures to control the app", [], "unknown", "IMPOSSIBLE", {}, False),
    ("solve the captcha on the login page", [], "unknown", "IMPOSSIBLE", {}, False),
    ("my password is hunter2 open notepad and type hi", ["notepad"], "desktop", "ok", {}, False),
    ("open obs studio", ["obs studio"], "desktop", "ok", {}, False),
    ("send the report to my boss", [], "unknown", "NEEDS_INPUT", {}, False),
]


def main():
    from core_organs import task_intake as ti
    from core_organs import loop_first as lf
    from core_organs import organ_48_app_behavior_model as bm
    t0 = time.time()
    catalog = ti.installed_app_names()
    t_cat = time.time() - t0
    rows = []
    for cmd, exp_apps, exp_dom, exp_verdict, exp_goals, exp_irrev in CASES:
        row = {"task": cmd.replace("\n", " | ")[:70]}
        t = time.perf_counter()
        it = ti.analyse(cmd, catalog)
        row["intake_ms"] = round((time.perf_counter() - t) * 1000, 1)
        verdict = "IMPOSSIBLE" if it.impossible else ("NEEDS_INPUT" if it.question else "ok")
        row["verdict_ok"] = verdict == exp_verdict
        row["domain"] = it.domain
        row["domain_ok"] = it.domain == exp_dom or (exp_dom == "unknown" and it.domain in ("unknown",)) or (it.domain == "mixed" and exp_dom == "mixed")
        found = [a for a, _p in ti.detect_apps(it.clean_text, catalog) if not lf.is_browser_app(a)]
        row["apps_found"] = found
        row["apps_ok"] = sorted(found) == sorted(exp_apps) if exp_dom in ("desktop", "mixed") else True
        # goal plan
        t = time.perf_counter()
        plans = lf.plan_app_goals(it.tickets[0] if it.tickets else cmd, [(a, p) for a, p in ti.detect_apps(it.tickets[0] if it.tickets else cmd, catalog) if not lf.is_browser_app(a)])
        row["plan_ms"] = round((time.perf_counter() - t) * 1000, 2)
        goals_ok = True
        for p in plans:
            want = exp_goals.get(p.app, [])
            blob = " | ".join(p.goals).lower()
            for w in want:
                if w.lower() not in blob:
                    goals_ok = False
        for app in exp_goals:
            if app not in [p.app for p in plans]:
                goals_ok = False
        row["goals_ok"] = goals_ok if exp_goals else True
        row["goals"] = {p.app: [g[:40] for g in p.goals] for p in plans}
        row["strong"] = sum(1 for p in plans for s in p.strength if s == "strong")
        row["goal_count"] = sum(len(p.goals) for p in plans)
        risks = [bm.classify_risk(g) for p in plans for g in p.goals]
        row["irreversible_queued"] = any(r == "E2" for r in risks)
        row["gate_ok"] = row["irreversible_queued"] == exp_irrev
        rows.append(row)
    n = len(rows)
    score = lambda k: round(100.0 * sum(1 for r in rows if r[k]) / n, 1)
    summary = {"cases": n, "catalog_load_s": round(t_cat, 3), "installed_apps": len(catalog),
               "verdict_accuracy_pct": score("verdict_ok"), "domain_accuracy_pct": score("domain_ok"),
               "app_detection_accuracy_pct": score("apps_ok"), "goal_plan_accuracy_pct": score("goals_ok"),
               "risk_gate_accuracy_pct": score("gate_ok"),
               "mean_intake_ms": round(sum(r["intake_ms"] for r in rows) / n, 1),
               "mean_plan_ms": round(sum(r["plan_ms"] for r in rows) / n, 2)}
    print(json.dumps(summary, indent=1))
    for r in rows:
        flags = "".join("." if r[k] else k[0].upper() for k in ("verdict_ok", "domain_ok", "apps_ok", "goals_ok", "gate_ok"))
        print(f"[{flags}] {r['task']:<72} apps={r['apps_found']} goals={r['goals']}")
    with open(r"D:\new_automation\data\compile_bench_results.json", "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "rows": rows}, fh, indent=1, default=str)


if __name__ == "__main__":
    main()
